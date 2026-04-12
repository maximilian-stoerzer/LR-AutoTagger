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
    logDebug("[batch/export] maxSide=%d, tempDir=%s", maxSide, tostring(tempDir))

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
    }

    local session = LrExportSession {
        photosToExport = { photo },
        exportSettings = exportSettings,
    }

    for _, rendition in session:renditions() do
        local success, path = rendition:waitForRender()
        if success then
            log("[batch/export] Preview exportiert: %s", tostring(path))
            return path
        else
            logErr("[batch/export] Render fehlgeschlagen: %s", tostring(path))
        end
    end

    logErr("[batch/export] Kein Rendition-Ergebnis")
    return nil
end

-- ──────────────────────────────────────────────
-- Helper: write keywords to a photo
-- ──────────────────────────────────────────────

local function writeKeywords(catalog, photo, keywords)
    if not keywords or #keywords == 0 then
        logWarn("[batch/keywords] Keine Keywords zum Schreiben")
        return
    end

    log("[batch/keywords] Schreibe %d Keywords: %s", #keywords, table.concat(keywords, ", "))
    catalog:withWriteAccessDo("LR-AutoTag Keywords", function()
        for _, kw in ipairs(keywords) do
            local keyword = catalog:createKeyword(kw, {}, true, nil, true)
            if keyword then
                photo:addKeyword(keyword)
                logDebug("[batch/keywords] Keyword hinzugefuegt: %s", kw)
            else
                logWarn("[batch/keywords] createKeyword lieferte nil fuer: %s", kw)
            end
        end
    end)
end

-- ──────────────────────────────────────────────
-- Helper: find photo by UUID in catalog
-- ──────────────────────────────────────────────

local function buildPhotoIndex(photos)
    local index = {}
    for _, photo in ipairs(photos) do
        local uuid = photo:getRawMetadata("uuid")
        if uuid then
            index[uuid] = photo
        end
    end
    return index
end

-- ──────────────────────────────────────────────
-- Helper: format estimated time remaining
-- ──────────────────────────────────────────────

local function formatDuration(seconds)
    if not seconds or seconds <= 0 then return "wird berechnet..." end
    local h = math.floor(seconds / 3600)
    local m = math.floor((seconds % 3600) / 60)
    if h > 0 then
        return string.format("%d Std. %d Min.", h, m)
    else
        return string.format("%d Min.", m)
    end
end

-- ──────────────────────────────────────────────
-- Main entry point
-- ──────────────────────────────────────────────

LrTasks.startAsyncTask(function()
    LrFunctionContext.callWithContext("AutoTagBatch", function(context)
        log("[batch] ====== Batch-Modus gestartet ======")
        local catalog = LrApplication.activeCatalog()
        local allPhotos = catalog:getAllPhotos()
        log("[batch] Bilder im Katalog: %d", allPhotos and #allPhotos or 0)

        if not allPhotos or #allPhotos == 0 then
            logWarn("[batch] Katalog leer, Abbruch")
            LrDialogs.message(
                "Keine Bilder im Katalog",
                "Der Katalog enthält keine Bilder.",
                "info"
            )
            return
        end

        -- Confirm batch start
        local answer = LrDialogs.confirm(
            "Bibliothek verschlagworten",
            #allPhotos .. " Bilder im Katalog gefunden.\n"
                .. "Bereits verschlagwortete Bilder werden automatisch übersprungen.\n\n"
                .. "Batch-Verschlagwortung starten?",
            "Starten",
            "Abbrechen"
        )
        if answer == "cancel" then
            log("[batch] Benutzer hat Batch abgebrochen")
            return
        end

        local progress = LrProgressScope {
            title = "LR-AutoTag: Batch-Verschlagwortung",
            functionContext = context,
        }
        progress:setCaption("Katalog wird vorbereitet...")

        -- Build image list with GPS data
        local images = {}
        local photoIndex = buildPhotoIndex(allPhotos)

        for _, photo in ipairs(allPhotos) do
            local uuid = photo:getRawMetadata("uuid")
            local gps = photo:getRawMetadata("gps")
            local entry = { image_id = uuid }
            if gps then
                entry.gps_lat = gps.latitude
                entry.gps_lon = gps.longitude
            end
            images[#images + 1] = entry
        end
        log("[batch] Image-Liste erstellt: %d Eintraege", #images)

        -- Start batch on backend
        progress:setCaption("Batch wird gestartet...")
        local batchResult, err = apiClient.batchStart(images)
        if err then
            progress:done()
            logErr("[batch] Batch-Start fehlgeschlagen: %s", err)
            LrDialogs.message("Batch-Start fehlgeschlagen", err, "critical")
            return
        end

        local totalImages = batchResult.total_images or #images
        local skipped = batchResult.skipped or 0
        log("[batch] Backend meldet: total=%d, skipped=%d", totalImages, skipped)

        -- Polling loop
        local tempDir = LrPathUtils.getStandardFilePath("temp")
        local processed = 0
        local failed = 0
        local startTime = os.time()

        progress:setCaption(
            "0 von " .. totalImages .. " Bildern"
            .. (skipped > 0 and (" (" .. skipped .. " übersprungen)") or "")
        )

        local running = true
        while running do
            -- Check for cancellation
            if progress:isCanceled() then
                logWarn("[batch] Abbruch durch Benutzer")
                apiClient.batchCancel()
                break
            end

            -- Get next image
            local nextResult, nextErr = apiClient.batchNext()
            if nextErr then
                failed = failed + 1
                logErr("[batch] batchNext Fehler: %s (pause 2s)", nextErr)
                LrTasks.sleep(2)
            elseif not nextResult or not nextResult.image_id then
                log("[batch] Keine weiteren Bilder vom Backend")
                running = false
            else
                local imageId = nextResult.image_id
                local photo = photoIndex[imageId]
                log("[batch] ---- Verarbeite imageId=%s ----", tostring(imageId))

                if not photo then
                    failed = failed + 1
                    logErr("[batch] Foto mit UUID %s nicht im Katalog gefunden", tostring(imageId))
                else
                    -- Export preview
                    local previewPath = exportPreview(photo, tempDir)
                    if not previewPath then
                        failed = failed + 1
                        logErr("[batch] Export fehlgeschlagen fuer %s", tostring(imageId))
                    else
                        -- Read GPS for upload
                        local gps = photo:getRawMetadata("gps")
                        local gpsLat = gps and gps.latitude or nil
                        local gpsLon = gps and gps.longitude or nil
                        logDebug("[batch] GPS lat=%s, lon=%s", tostring(gpsLat), tostring(gpsLon))

                        -- Upload and analyze
                        local result, uploadErr = apiClient.batchImage(previewPath, imageId, gpsLat, gpsLon)

                        -- Clean up temp file
                        if LrFileUtils.exists(previewPath) then
                            LrFileUtils.delete(previewPath)
                        end

                        if uploadErr then
                            failed = failed + 1
                            logErr("[batch] Upload/Analyse fehlgeschlagen fuer %s: %s", tostring(imageId), uploadErr)
                        else
                            -- Write keywords
                            if result and result.keywords then
                                log("[batch] %s: %d Keywords erhalten", tostring(imageId), #result.keywords)
                                writeKeywords(catalog, photo, result.keywords)
                            else
                                logWarn("[batch] %s: Kein keywords-Feld in Antwort", tostring(imageId))
                            end

                            processed = processed + 1
                        end
                    end
                end

                -- Update progress
                local done = processed + failed + skipped
                progress:setPortionComplete(done, totalImages)

                local elapsed = os.time() - startTime
                local rate = elapsed > 0 and (processed / elapsed) or 0
                local remaining = rate > 0 and ((totalImages - done) / rate) or 0

                progress:setCaption(
                    done .. " von " .. totalImages .. " Bildern"
                    .. " — Restdauer: " .. formatDuration(remaining)
                )
            end
        end

        progress:done()

        -- Summary dialog
        log("[batch] ====== Batch fertig: %d verarbeitet, %d uebersprungen, %d fehlgeschlagen ======", processed, skipped, failed)
        local msg = processed .. " Bilder verschlagwortet."
        if skipped > 0 then
            msg = msg .. "\n" .. skipped .. " übersprungen (hatten bereits Keywords)."
        end
        if failed > 0 then
            msg = msg .. "\n" .. failed .. " fehlgeschlagen."
        end

        local severity = "info"
        if failed > 0 and processed == 0 then
            severity = "critical"
        elseif failed > 0 then
            severity = "warning"
        end

        LrDialogs.message("LR-AutoTag — Batch abgeschlossen", msg, severity)
    end)
end)
