local LrApplication = import "LrApplication"
local LrDialogs = import "LrDialogs"
local LrFunctionContext = import "LrFunctionContext"
local LrTasks = import "LrTasks"
local LrProgressScope = import "LrProgressScope"
local LrPrefs = import "LrPrefs"
local LrPathUtils = import "LrPathUtils"
local LrFileUtils = import "LrFileUtils"
local LrExportSession = import "LrExportSession"

local apiClient = require "AutoTagApiClient"

-- ──────────────────────────────────────────────
-- Helper: export a single photo as JPEG preview
-- ──────────────────────────────────────────────

local function exportPreview(photo, tempDir)
    local prefs = LrPrefs.prefsForPlugin()
    local maxSide = prefs.previewSize or 1024

    local exportSettings = {
        LR_export_destinationType = "specificFolder",
        LR_export_destinationPathPrefix = tempDir,
        LR_export_useSubfolder = false,
        LR_format = "JPEG",
        LR_jpeg_quality = 0.85,
        LR_size_doConstrain = true,
        LR_size_maxHeight = maxSide,
        LR_size_maxWidth = maxSide,
        LR_size_resizeType = "longEdge",
        LR_collisionHandling = "rename",
        LR_reimportExportedPhoto = false,
        LR_includeVideoFiles = false,
        LR_removeLocationMetadata = false,
        LR_metadata_keywordOptions = "lightroomHierarchical",
    }

    local session = LrExportSession {
        photosToExport = { photo },
        exportSettings = exportSettings,
    }

    for _, rendition in session:renditions() do
        local success, path = rendition:waitForRender()
        if success then
            return path
        end
    end

    return nil
end

-- ──────────────────────────────────────────────
-- Helper: write keywords to a photo
-- ──────────────────────────────────────────────

local function writeKeywords(catalog, photo, keywords)
    if not keywords or #keywords == 0 then return end

    catalog:withWriteAccessDo("LR-AutoTag Keywords", function()
        for _, kw in ipairs(keywords) do
            local keyword = catalog:createKeyword(kw, {}, true, nil, true)
            if keyword then
                photo:addKeyword(keyword)
            end
        end
    end)
end

-- ──────────────────────────────────────────────
-- Main entry point
-- ──────────────────────────────────────────────

LrTasks.startAsyncTask(function()
    LrFunctionContext.callWithContext("AutoTagInteractive", function(context)
        local catalog = LrApplication.activeCatalog()
        local photos = catalog:getTargetPhotos()

        if not photos or #photos == 0 then
            LrDialogs.message(
                "Keine Bilder ausgewählt",
                "Bitte wähle mindestens ein Bild in der Bibliothek aus.",
                "info"
            )
            return
        end

        -- Confirm if many photos selected
        if #photos > 50 then
            local answer = LrDialogs.confirm(
                #photos .. " Bilder verschlagworten?",
                "Das kann einige Zeit dauern. Für große Mengen empfiehlt sich der Batch-Modus.",
                "Fortfahren",
                "Abbrechen"
            )
            if answer == "cancel" then return end
        end

        local progress = LrProgressScope {
            title = "LR-AutoTag: Verschlagwortung",
            functionContext = context,
        }

        local tempDir = LrPathUtils.getStandardFilePath("temp")
        local processed = 0
        local failed = 0
        local errors = {}

        for i, photo in ipairs(photos) do
            if progress:isCanceled() then break end

            progress:setPortionComplete(i - 1, #photos)
            progress:setCaption("Bild " .. i .. " von " .. #photos)

            -- Export preview
            local previewPath = exportPreview(photo, tempDir)
            if not previewPath then
                failed = failed + 1
                errors[#errors + 1] = "Bild " .. i .. ": Export fehlgeschlagen"
                goto continue
            end

            -- Read GPS
            local gps = photo:getRawMetadata("gps")
            local gpsLat = gps and gps.latitude or nil
            local gpsLon = gps and gps.longitude or nil

            -- Image ID (catalog UUID)
            local imageId = photo:getRawMetadata("uuid")

            -- Call API
            local result, err = apiClient.analyzeImage(previewPath, imageId, gpsLat, gpsLon)

            -- Clean up temp file
            if LrFileUtils.exists(previewPath) then
                LrFileUtils.delete(previewPath)
            end

            if err then
                failed = failed + 1
                errors[#errors + 1] = "Bild " .. i .. ": " .. err
                goto continue
            end

            -- Write keywords back to catalog
            if result and result.keywords then
                writeKeywords(catalog, photo, result.keywords)
                processed = processed + 1
            end

            ::continue::
        end

        progress:done()

        -- Summary
        local msg = processed .. " Bilder verschlagwortet."
        if failed > 0 then
            msg = msg .. "\n" .. failed .. " fehlgeschlagen."
        end
        if #errors > 0 and #errors <= 10 then
            msg = msg .. "\n\nFehler:\n" .. table.concat(errors, "\n")
        elseif #errors > 10 then
            msg = msg .. "\n\nErste 10 Fehler:\n" .. table.concat(errors, "\n", 1, 10)
        end

        LrDialogs.message("LR-AutoTag — Ergebnis", msg, failed > 0 and "warning" or "info")
    end)
end)
