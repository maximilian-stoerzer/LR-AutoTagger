local LrHttp = import "LrHttp"
local LrPrefs = import "LrPrefs"

local multipart = require "AutoTagMultipart"

local ApiClient = {}

-- ──────────────────────────────────────────────
-- Minimal JSON decoder
-- Handles: objects, arrays, strings, numbers, booleans, null
-- ──────────────────────────────────────────────

local JSON = {}

local function skipWhitespace(s, pos)
    return s:match("^%s*()", pos)
end

local function decodeString(s, pos)
    -- pos points at the opening quote
    local i = pos + 1
    local parts = {}
    while i <= #s do
        local c = s:sub(i, i)
        if c == '"' then
            return table.concat(parts), i + 1
        elseif c == '\\' then
            i = i + 1
            local esc = s:sub(i, i)
            if esc == '"' or esc == '\\' or esc == '/' then
                parts[#parts + 1] = esc
            elseif esc == 'n' then
                parts[#parts + 1] = '\n'
            elseif esc == 'r' then
                parts[#parts + 1] = '\r'
            elseif esc == 't' then
                parts[#parts + 1] = '\t'
            elseif esc == 'u' then
                -- Basic unicode escape: just pass through as-is for German chars
                local hex = s:sub(i + 1, i + 4)
                local codepoint = tonumber(hex, 16)
                if codepoint and codepoint < 128 then
                    parts[#parts + 1] = string.char(codepoint)
                else
                    parts[#parts + 1] = "\\u" .. hex
                end
                i = i + 4
            else
                parts[#parts + 1] = esc
            end
        else
            parts[#parts + 1] = c
        end
        i = i + 1
    end
    error("Unterminated string")
end

local decodeValue -- forward declaration

local function decodeArray(s, pos)
    local arr = {}
    pos = pos + 1 -- skip '['
    pos = skipWhitespace(s, pos)
    if s:sub(pos, pos) == ']' then
        return arr, pos + 1
    end
    while true do
        local value
        value, pos = decodeValue(s, pos)
        arr[#arr + 1] = value
        pos = skipWhitespace(s, pos)
        local c = s:sub(pos, pos)
        if c == ']' then
            return arr, pos + 1
        elseif c == ',' then
            pos = skipWhitespace(s, pos + 1)
        else
            error("Expected ',' or ']' in array at position " .. pos)
        end
    end
end

local function decodeObject(s, pos)
    local obj = {}
    pos = pos + 1 -- skip '{'
    pos = skipWhitespace(s, pos)
    if s:sub(pos, pos) == '}' then
        return obj, pos + 1
    end
    while true do
        -- key
        if s:sub(pos, pos) ~= '"' then
            error("Expected string key at position " .. pos)
        end
        local key
        key, pos = decodeString(s, pos)
        pos = skipWhitespace(s, pos)
        if s:sub(pos, pos) ~= ':' then
            error("Expected ':' at position " .. pos)
        end
        pos = skipWhitespace(s, pos + 1)
        -- value
        local value
        value, pos = decodeValue(s, pos)
        obj[key] = value
        pos = skipWhitespace(s, pos)
        local c = s:sub(pos, pos)
        if c == '}' then
            return obj, pos + 1
        elseif c == ',' then
            pos = skipWhitespace(s, pos + 1)
        else
            error("Expected ',' or '}' in object at position " .. pos)
        end
    end
end

function decodeValue(s, pos)
    pos = skipWhitespace(s, pos)
    local c = s:sub(pos, pos)
    if c == '"' then
        return decodeString(s, pos)
    elseif c == '{' then
        return decodeObject(s, pos)
    elseif c == '[' then
        return decodeArray(s, pos)
    elseif c == 't' then
        if s:sub(pos, pos + 3) == "true" then return true, pos + 4 end
    elseif c == 'f' then
        if s:sub(pos, pos + 4) == "false" then return false, pos + 5 end
    elseif c == 'n' then
        if s:sub(pos, pos + 3) == "null" then return nil, pos + 4 end
    else
        -- number
        local numStr = s:match("^-?%d+%.?%d*[eE]?[+-]?%d*", pos)
        if numStr then
            return tonumber(numStr), pos + #numStr
        end
    end
    error("Unexpected character at position " .. pos .. ": " .. c)
end

function JSON.decode(s)
    if not s or s == "" then return nil end
    local value, _ = decodeValue(s, 1)
    return value
end

local function jsonEncode(val)
    if val == nil then
        return "null"
    elseif type(val) == "boolean" then
        return val and "true" or "false"
    elseif type(val) == "number" then
        return tostring(val)
    elseif type(val) == "string" then
        return '"' .. val:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n'):gsub('\r', '\\r') .. '"'
    elseif type(val) == "table" then
        -- Check if array (sequential integer keys starting at 1)
        if #val > 0 or next(val) == nil then
            local parts = {}
            for i = 1, #val do
                parts[i] = jsonEncode(val[i])
            end
            return "[" .. table.concat(parts, ",") .. "]"
        else
            local parts = {}
            for k, v in pairs(val) do
                parts[#parts + 1] = jsonEncode(tostring(k)) .. ":" .. jsonEncode(v)
            end
            return "{" .. table.concat(parts, ",") .. "}"
        end
    end
    return "null"
end

-- ──────────────────────────────────────────────
-- HTTP helpers
-- ──────────────────────────────────────────────

local function getPrefs()
    local prefs = LrPrefs.prefsForPlugin()
    return {
        url = prefs.backendUrl or "",
        apiKey = prefs.apiKey or "",
        timeout = prefs.connectionTimeout or 30,
    }
end

local function apiUrl(path)
    local prefs = getPrefs()
    local base = prefs.url:gsub("/$", "")
    return base .. "/api/v1" .. path
end

local function authHeaders()
    local prefs = getPrefs()
    return {
        { field = "X-API-Key", value = prefs.apiKey },
    }
end

local function jsonHeaders()
    local prefs = getPrefs()
    return {
        { field = "X-API-Key", value = prefs.apiKey },
        { field = "Content-Type", value = "application/json" },
    }
end

local function handleResponse(body, headers)
    if not body then
        return nil, "Keine Antwort vom Backend"
    end

    local status = headers and headers.status
    local data = JSON.decode(body)

    if status and status >= 400 then
        local msg = "HTTP " .. tostring(status)
        if data and data.detail then
            msg = msg .. ": " .. tostring(data.detail)
        end
        return nil, msg
    end

    return data, nil
end

-- ──────────────────────────────────────────────
-- Public API
-- ──────────────────────────────────────────────

function ApiClient.checkHealth()
    local prefs = getPrefs()
    local url = prefs.url:gsub("/$", "") .. "/api/v1/health"
    local body, headers = LrHttp.get(url, {
        { field = "X-API-Key", value = prefs.apiKey },
    })
    return handleResponse(body, headers)
end

function ApiClient.analyzeImage(filePath, imageId, gpsLat, gpsLon)
    local fields = {
        image_id = imageId,
        gps_lat = gpsLat,
        gps_lon = gpsLon,
    }
    local files = {
        { name = "file", filename = "preview.jpg", path = filePath },
    }
    local reqBody, contentType = multipart.build(fields, files)

    local prefs = getPrefs()
    local hdrs = {
        { field = "X-API-Key", value = prefs.apiKey },
        { field = "Content-Type", value = contentType },
    }

    local body, headers = LrHttp.post(apiUrl("/analyze"), reqBody, hdrs, "POST", prefs.timeout)
    return handleResponse(body, headers)
end

function ApiClient.batchStart(images)
    local payload = jsonEncode({ images = images })
    local body, headers = LrHttp.post(apiUrl("/batch/start"), payload, jsonHeaders(), "POST", getPrefs().timeout)
    return handleResponse(body, headers)
end

function ApiClient.batchNext()
    local body, headers = LrHttp.get(apiUrl("/batch/next"), authHeaders())
    return handleResponse(body, headers)
end

function ApiClient.batchImage(filePath, imageId, gpsLat, gpsLon)
    local fields = {
        image_id = imageId,
        gps_lat = gpsLat,
        gps_lon = gpsLon,
    }
    local files = {
        { name = "file", filename = "preview.jpg", path = filePath },
    }
    local reqBody, contentType = multipart.build(fields, files)

    local prefs = getPrefs()
    local hdrs = {
        { field = "X-API-Key", value = prefs.apiKey },
        { field = "Content-Type", value = contentType },
    }

    local body, headers = LrHttp.post(apiUrl("/batch/image"), reqBody, hdrs, "POST", prefs.timeout)
    return handleResponse(body, headers)
end

function ApiClient.batchStatus()
    local body, headers = LrHttp.get(apiUrl("/batch/status"), authHeaders())
    return handleResponse(body, headers)
end

function ApiClient.batchPause()
    local body, headers = LrHttp.post(apiUrl("/batch/pause"), "", jsonHeaders(), "POST", getPrefs().timeout)
    return handleResponse(body, headers)
end

function ApiClient.batchResume()
    local body, headers = LrHttp.post(apiUrl("/batch/resume"), "", jsonHeaders(), "POST", getPrefs().timeout)
    return handleResponse(body, headers)
end

function ApiClient.batchCancel()
    local body, headers = LrHttp.post(apiUrl("/batch/cancel"), "", jsonHeaders(), "POST", getPrefs().timeout)
    return handleResponse(body, headers)
end

return ApiClient
