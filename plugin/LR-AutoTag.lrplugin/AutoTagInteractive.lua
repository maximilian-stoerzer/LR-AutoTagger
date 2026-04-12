local LrApplication = import "LrApplication"
local LrDialogs = import "LrDialogs"
local LrFunctionContext = import "LrFunctionContext"
local LrTasks = import "LrTasks"
local LrProgressScope = import "LrProgressScope"
local LrPrefs = import "LrPrefs"
local LrPathUtils = import "LrPathUtils"
local LrFileUtils = import "LrFileUtils"
local LrExportSession = import "LrExportSession"
local LrLogger = import "LrLogger"

local apiClient = require "AutoTagApiClient"

local logger = LrLogger("LR-AutoTag")
logger:enable("print")
local log = logger:quickf("info")
local logWarn = logger:quickf("warn")
local logErr = logger:quickf("error")
local logDebug = logger:quickf("debug")

-- ──────────────────────────────────────────────
-- Helper: export a single photo as JPEG preview
-- ──────────────────────────────────────────────

local function exportPreview(photo, tempDir)
    local prefs = LrPrefs.prefsForPlugin()
    local maxSide = prefs.previewSize or 1024
    logDebug("[interactive/export] maxSide=%d, tempDir=%s", maxSide, tostring(tempDir))

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
            log("[interactive/export] Preview exportiert: %s", tostring(path))
            return path
        else
            logErr("[interactive/export] Render fehlgeschlagen: %s", tostring(path))
        end
    end

    logErr("[interactive/export] Kein Rendition-Ergebnis")
    return nil
end

-- ──────────────────────────────────────────────
-- Helper: write keywords to a photo
-- ──────────────────────────────────────────────

local function writeKeywords(catalog, photo, keywords)
    if not keywords or #keywords == 0 then
        logWarn("[interactive/keywords] Keine Keywords zum Schreiben")
        return
    end

    log("[interactive/keywords] Schreibe %d Keywords: %s", #keywords, table.concat(keywords, ", "))
    catalog:withWriteAccessDo("LR-AutoTag Keywords", function()
        for _, kw in ipairs(keywords) do
            local keyword = catalog:createKeyword(kw, {}, true, nil, true)
            if keyword then
                photo:addKeyword(keyword)
                logDebug("[interactive/keywords] Keyword hinzugefuegt: %s", kw)
            else
                logWarn("[interactive/keywords] createKeyword lieferte nil fuer: %s", kw)
            end
        end
    end)
end

-- ──────────────────────────────────────────────
-- Main entry point
-- ──────────────────────────────────────────────

LrTasks.startAsyncTask(function()
    LrFunctionContext.callWithContext("AutoTagInteractive", function(context)
        log("[interactive] ====== Interaktiver Modus gestartet ======")
        local catalog = LrApplication.activeCatalog()
        local photos = catalog:getTargetPhotos()
        log("[interactive] Ausgewaehlte Bilder: %d", photos and #photos or 0)

        if not photos or #photos == 0 then
            logWarn("[interactive] Keine Bilder ausgewaehlt, Abbruch")
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
            if progress:isCanceled() then
                logWarn("[interactive] Abbruch durch Benutzer bei Bild %d/%d", i, #photos)
                break
            end

            progress:setPortionComplete(i - 1, #photos)
            progress:setCaption("Bild " .. i .. " von " .. #photos)

            log("[interactive] ---- Bild %d/%d ----", i, #photos)

            -- Export preview
            local previewPath = exportPreview(photo, tempDir)
            if not previewPath then
                failed = failed + 1
                errors[#errors + 1] = "Bild " .. i .. ": Export fehlgeschlagen"
                logErr("[interactive] Bild %d: Export fehlgeschlagen", i)
            else
                -- Read GPS
                local gps = photo:getRawMetadata("gps")
                local gpsLat = gps and gps.latitude or nil
                local gpsLon = gps and gps.longitude or nil
                logDebug("[interactive] Bild %d: GPS lat=%s, lon=%s", i, tostring(gpsLat), tostring(gpsLon))

                -- Image ID (catalog UUID)
                local imageId = photo:getRawMetadata("uuid")
                log("[interactive] Bild %d: uuid=%s, preview=%s", i, tostring(imageId), tostring(previewPath))

                -- Call API
                local result, err = apiClient.analyzeImage(previewPath, imageId, gpsLat, gpsLon)

                -- Clean up temp file
                if LrFileUtils.exists(previewPath) then
                    LrFileUtils.delete(previewPath)
                    logDebug("[interactive] Temp-Datei geloescht: %s", previewPath)
                end

                if err then
                    failed = failed + 1
                    errors[#errors + 1] = "Bild " .. i .. ": " .. err
                    logErr("[interactive] Bild %d: API-Fehler: %s", i, err)
                elseif result and result.keywords then
                    log("[interactive] Bild %d: %d Keywords erhalten", i, #result.keywords)
                    writeKeywords(catalog, photo, result.keywords)
                    processed = processed + 1
                else
                    logWarn("[interactive] Bild %d: Kein keywords-Feld in der Antwort", i)
                end
            end
        end

        progress:done()

        -- Summary
        log("[interactive] ====== Fertig: %d verarbeitet, %d fehlgeschlagen ======", processed, failed)
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
