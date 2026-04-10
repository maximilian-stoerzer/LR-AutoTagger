local LrView = import "LrView"
local LrPrefs = import "LrPrefs"
local LrDialogs = import "LrDialogs"
local LrTasks = import "LrTasks"
local LrFunctionContext = import "LrFunctionContext"
local LrBinding = import "LrBinding"

local apiClient = require "AutoTagApiClient"

local InfoProvider = {}

function InfoProvider.sectionsForTopOfDialog(f, properties)
    local prefs = LrPrefs.prefsForPlugin()

    -- Defaults
    if not prefs.backendUrl then prefs.backendUrl = "" end
    if not prefs.apiKey then prefs.apiKey = "" end
    if not prefs.connectionTimeout then prefs.connectionTimeout = 30 end
    if not prefs.previewSize then prefs.previewSize = 1024 end

    -- Observable property for connection test result
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
                            local data, err = apiClient.checkHealth()
                            if err then
                                LrDialogs.message(
                                    "Verbindungstest fehlgeschlagen",
                                    err,
                                    "critical"
                                )
                            elseif data then
                                local dbStatus = data.database or "unbekannt"
                                local ollamaStatus = data.ollama or "unbekannt"
                                if data.status == "ok" then
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
                    max = 300,
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
    }
end

return InfoProvider
