local LrView = import "LrView"
local LrPrefs = import "LrPrefs"
local LrDialogs = import "LrDialogs"
local LrTasks = import "LrTasks"
local LrFunctionContext = import "LrFunctionContext"
local LrBinding = import "LrBinding"
local LrColor = import "LrColor"
local LrLogger = import "LrLogger"

local logger = LrLogger("LR-AutoTag")
logger:enable("print")
local log = logger:quickf("info")
local logErr = logger:quickf("error")

local apiClient = require "AutoTagApiClient"

local InfoProvider = {}

function InfoProvider.sectionsForTopOfDialog(f, properties)
    local prefs = LrPrefs.prefsForPlugin()

    -- Defaults
    if not prefs.backendUrl then prefs.backendUrl = "" end
    if not prefs.apiKey then prefs.apiKey = "" end
    if not prefs.connectionTimeout then prefs.connectionTimeout = 30 end
    if not prefs.previewSize then prefs.previewSize = 1024 end
    if not prefs.ollamaModel then prefs.ollamaModel = "" end
    if not prefs.sunCalcLocation then prefs.sunCalcLocation = "" end
    -- Cache for model list; fetched on demand. Empty string = "use backend default".
    if not prefs.ollamaModelList then prefs.ollamaModelList = "" end

    local bind = LrView.bind

    return {
        {
            title = "LR-AutoTag — Verbindung",
            synopsis = prefs.backendUrl ~= "" and prefs.backendUrl or "Nicht konfiguriert",

            f:row {
                spacing = f:control_spacing(),
                f:static_text {
                    title = "Backend-URL:",
                    alignment = "right",
                    width = LrView.share "label_width",
                },
                f:edit_field {
                    value = bind { key = "backendUrl", object = prefs },
                    width_in_chars = 40,
                    tooltip = "Vollständige URL inkl. Port, z.B. http://192.168.1.20:8000",
                },
            },

            f:row {
                spacing = f:control_spacing(),
                f:static_text {
                    title = "API-Key:",
                    alignment = "right",
                    width = LrView.share "label_width",
                },
                f:password_field {
                    value = bind { key = "apiKey", object = prefs },
                    width_in_chars = 40,
                    tooltip = "API-Key vom Administrator",
                },
            },

            f:row {
                spacing = f:control_spacing(),
                f:push_button {
                    title = "Verbindung testen",
                    action = function()
                        LrTasks.startAsyncTask(function()
                            log("[settings] Verbindungstest gestartet")
                            local data, err = apiClient.checkHealth()
                            if err then
                                logErr("[settings] Verbindungstest fehlgeschlagen: %s", err)
                                LrDialogs.message(
                                    "Verbindungstest fehlgeschlagen",
                                    err,
                                    "critical"
                                )
                            elseif data then
                                local dbStatus = data.database or "unbekannt"
                                local ollamaStatus = data.ollama or "unbekannt"
                                if data.status == "ok" then
                                    log("[settings] Verbindungstest OK: db=%s, ollama=%s", dbStatus, ollamaStatus)
                                    LrDialogs.message(
                                        "Verbindung erfolgreich",
                                        "Backend erreichbar — alle Dienste OK\n"
                                            .. "Datenbank: " .. dbStatus .. "\n"
                                            .. "Ollama: " .. ollamaStatus,
                                        "info"
                                    )
                                else
                                    LrDialogs.message(
                                        "Backend erreichbar, aber eingeschränkt",
                                        "Status: " .. tostring(data.status) .. "\n"
                                            .. "Datenbank: " .. dbStatus .. "\n"
                                            .. "Ollama: " .. ollamaStatus,
                                        "warning"
                                    )
                                end
                            end
                        end)
                    end,
                },
            },
        },

        {
            title = "LR-AutoTag — Einstellungen",

            f:row {
                spacing = f:control_spacing(),
                f:static_text {
                    title = "Timeout (Sek.):",
                    alignment = "right",
                    width = LrView.share "label_width",
                },
                f:slider {
                    value = bind { key = "connectionTimeout", object = prefs },
                    min = 10,
                    max = 900,
                    integral = true,
                    width = 200,
                },
                f:static_text {
                    title = bind { key = "connectionTimeout", object = prefs },
                    width_in_chars = 4,
                },
            },

            f:row {
                spacing = f:control_spacing(),
                f:static_text {
                    title = "Vorschaugröße (px):",
                    alignment = "right",
                    width = LrView.share "label_width",
                },
                f:slider {
                    value = bind { key = "previewSize", object = prefs },
                    min = 256,
                    max = 2048,
                    integral = true,
                    width = 200,
                },
                f:static_text {
                    title = bind { key = "previewSize", object = prefs },
                    width_in_chars = 5,
                },
            },

            f:row {
                spacing = f:control_spacing(),
                f:static_text {
                    title = "",
                    width = LrView.share "label_width",
                },
                f:static_text {
                    title = "Maximale lange Seite der JPG-Vorschau für den Upload.",
                    text_color = LrColor(0.5, 0.5, 0.5),
                },
            },
        },

        {
            title = "LR-AutoTag — Analyse-Optionen",
            synopsis = (prefs.ollamaModel ~= "" and prefs.ollamaModel or "Modell: Backend-Default")
                .. "  ·  "
                .. "Fallback: " .. (prefs.sunCalcLocation ~= "" and prefs.sunCalcLocation or "Backend-Default"),

            f:row {
                spacing = f:control_spacing(),
                f:static_text {
                    title = "Ollama-Modell:",
                    alignment = "right",
                    width = LrView.share "label_width",
                },
                f:combo_box {
                    value = bind { key = "ollamaModel", object = prefs },
                    items = {}, -- filled on demand via "Modelle laden"
                    width_in_chars = 30,
                    tooltip = "Leer lassen, um das im Backend konfigurierte Standard-Modell zu verwenden. "
                        .. "Sonst muss es ein auf dem Ollama-Server verfügbares Vision-Modell sein "
                        .. "(z.B. llava:13b, llava:7b).",
                },
                f:push_button {
                    title = "Modelle laden",
                    action = function()
                        LrTasks.startAsyncTask(function()
                            log("[settings] Modelle laden")
                            local data, err = apiClient.listModels()
                            if err then
                                logErr("[settings] Modelle laden fehlgeschlagen: %s", err)
                                LrDialogs.message("Fehler", "Modelle konnten nicht abgerufen werden:\n" .. err, "critical")
                                return
                            end
                            local list = (data and data.models) or {}
                            if #list == 0 then
                                LrDialogs.message("Keine Modelle", "Der Ollama-Server hat keine Modelle gemeldet.", "warning")
                                return
                            end
                            prefs.ollamaModelList = table.concat(list, ",")
                            LrDialogs.message(
                                "Modelle geladen",
                                "Verfügbare Modelle (" .. #list .. "):\n\n" .. table.concat(list, "\n")
                                    .. "\n\nBitte gewünschtes Modell in das Feld eintragen (leer = Backend-Default).",
                                "info"
                            )
                        end)
                    end,
                },
            },

            f:row {
                spacing = f:control_spacing(),
                f:static_text {
                    title = "Tageslicht-Fallback:",
                    alignment = "right",
                    width = LrView.share "label_width",
                },
                f:popup_menu {
                    value = bind { key = "sunCalcLocation", object = prefs },
                    items = {
                        { title = "Backend-Default verwenden", value = "" },
                        { title = "BAYERN (Regensburg) — Standard", value = "BAYERN" },
                        { title = "MUNICH (München)", value = "MUNICH" },
                        { title = "NONE (kein Fallback ohne GPS)", value = "NONE" },
                    },
                    width_in_chars = 30,
                    tooltip = "Wenn ein Foto keine GPS-Daten hat, wird für die Sonnenstand-Berechnung "
                        .. "(Goldene/Blaue Stunde etc.) diese Fallback-Position benutzt. "
                        .. "NONE liefert dann gar kein Tageslicht-Keyword.",
                },
            },

            f:row {
                spacing = f:control_spacing(),
                f:static_text {
                    title = "",
                    width = LrView.share "label_width",
                },
                f:static_text {
                    title = "Diese Optionen überschreiben die Backend-Defaults nur für Anfragen dieses Plugins.",
                    text_color = LrColor(0.5, 0.5, 0.5),
                },
            },
        },
    }
end

return InfoProvider
