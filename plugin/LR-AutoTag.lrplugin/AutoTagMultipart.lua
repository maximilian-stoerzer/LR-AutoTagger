local LrFileUtils = import "LrFileUtils"
local LrMath = import "LrMath"
local LrLogger = import "LrLogger"

local logger = LrLogger("LR-AutoTag")
logger:enable("print")
local log = logger:quickf("info")
local logDebug = logger:quickf("debug")
local logErr = logger:quickf("error")

local AutoTagMultipart = {}

local function generateBoundary()
    local chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    local parts = {}
    for i = 1, 32 do
        local idx = math.random(1, #chars)
        parts[#parts + 1] = chars:sub(idx, idx)
    end
    return "----LRAutoTag" .. table.concat(parts)
end

--- Build a multipart/form-data body for HTTP upload.
-- @param fields table  Key-value pairs for form fields (values may be nil, which skips the field)
-- @param files  table  Array of {name, filename, path} for file parts
-- @return body string, contentType string
function AutoTagMultipart.build(fields, files)
    local boundary = generateBoundary()
    logDebug("[multipart] boundary=%s, fields=%d, files=%d", boundary, fields and #fields or 0, files and #files or 0)
    local parts = {}

    -- Form fields
    if fields then
        for key, value in pairs(fields) do
            if value ~= nil then
                parts[#parts + 1] = "--" .. boundary .. "\r\n"
                    .. "Content-Disposition: form-data; name=\"" .. key .. "\"\r\n"
                    .. "\r\n"
                    .. tostring(value) .. "\r\n"
            end
        end
    end

    -- File parts
    if files then
        for _, file in ipairs(files) do
            log("[multipart] Lese Datei: %s (%s)", file.path, file.filename)
            local fileData = LrFileUtils.readFile(file.path)
            parts[#parts + 1] = "--" .. boundary .. "\r\n"
                .. "Content-Disposition: form-data; name=\"" .. file.name .. "\"; filename=\"" .. file.filename .. "\"\r\n"
                .. "Content-Type: image/jpeg\r\n"
                .. "\r\n"
                .. fileData .. "\r\n"
        end
    end

    -- Closing boundary
    parts[#parts + 1] = "--" .. boundary .. "--\r\n"

    local body = table.concat(parts)
    local contentType = "multipart/form-data; boundary=" .. boundary
    logDebug("[multipart] Body erstellt: %d bytes, contentType=%s", #body, contentType)

    return body, contentType
end

return AutoTagMultipart
