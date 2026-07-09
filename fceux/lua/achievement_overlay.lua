-- Achievement overlay при проигрывании inference FM2 (ML_CONCEPT §8).
-- Запуск: scripts/play_inference_fm2.py  или  -lua achievement_overlay.lua -playmovie …
-- Конфиг: WAIT_ACHIEVEMENT_OVERLAY → путь к .overlay.json (или sidecar рядом с .fm2)

local overlay_cache = nil
local overlay_until_frame = 0
local last_overlay_raw = ""

local function overlay_path()
  local from_env = os.getenv("WAIT_ACHIEVEMENT_OVERLAY")
  if from_env and from_env ~= "" then
    return from_env
  end
  if movie and movie.getfilename then
    local mf = movie.getfilename()
    if mf and mf ~= "" then
      return mf:gsub("%.fm2$", ".overlay.json")
    end
  end
  return ""
end

local function parse_overlay_json(text)
  local show_until = tonumber(text:match('"show_until_frame"%s*:%s*(%d+)')) or 180
  local max_cp = tonumber(text:match('"max_cp"%s*:%s*([%d%.%-]+)')) or 0
  local reward = tonumber(text:match('"reward"%s*:%s*([%d%.%-]+)')) or 0
  local steps = tonumber(text:match('"steps"%s*:%s*(%d+)')) or 0
  local achievements = {}
  for block in text:gmatch('{[^}]*"slug"[^}]*}') do
    local idx = tonumber(block:match('"idx"%s*:%s*(%d+)')) or 0
    local title = block:match('"title"%s*:%s*"([^"]*)"') or ""
    local label = block:match('"label"%s*:%s*"([^"]*)"') or ""
    local slug = block:match('"slug"%s*:%s*"([^"]*)"') or ""
    local tier = block:match('"tier"%s*:%s*"([^"]*)"') or "gold"
    local display = label ~= "" and label or (title ~= "" and title or slug)
    if display ~= "" then
      achievements[#achievements + 1] = {idx = idx, title = display, tier = tier, slug = slug}
    end
  end
  table.sort(achievements, function(a, b) return a.idx < b.idx end)
  return {
    achievements = achievements,
    stats = {max_cp = max_cp, reward = reward, steps = steps},
    show_until_frame = show_until,
  }
end

local function debug_log(hypothesis_id, message, data_json)
  -- #region agent log
  local log_path = os.getenv("WAIT_DEBUG_LOG")
  if not log_path or log_path == "" then return end
  local f = io.open(log_path, "a")
  if not f then return end
  f:write('{"sessionId":"04d5f1","hypothesisId":"' .. (hypothesis_id or "?")
    .. '","location":"achievement_overlay.lua","message":"' .. (message or "")
    .. '","data":' .. (data_json or "{}") .. ',"timestamp":' .. ((os.time() or 0) * 1000) .. "}\n")
  f:close()
  -- #endregion
end

local function draw_overlay()
  local path = overlay_path()
  if path == "" then
    return
  end
  local f = io.open(path, "r")
  if not f then
    overlay_cache = nil
    last_overlay_raw = ""
    return
  end
  local text = f:read("*a")
  f:close()
  if text ~= last_overlay_raw then
    last_overlay_raw = text
    overlay_cache = parse_overlay_json(text)
    overlay_until_frame = emu.framecount() + (overlay_cache.show_until_frame or 180)
    -- #region agent log
    debug_log("H-D", "overlay loaded", '{"count":' .. #(overlay_cache.achievements or {}) .. '}')
    -- #endregion
  end
  if not overlay_cache or emu.framecount() > overlay_until_frame then
    return
  end
  local y = 12
  for _, ach in ipairs(overlay_cache.achievements or {}) do
    local prefix = "*"
    if ach.tier == "skull" then
      prefix = "X"
    elseif ach.tier == "silver" then
      prefix = "+"
    end
    gui.text(8, y, prefix .. " " .. ach.title, "yellow")
    y = y + 12
  end
  local st = overlay_cache.stats or {}
  gui.text(8, y + 4, string.format("CP:%d  R:%.0f  steps:%d", st.max_cp or 0, st.reward or 0, st.steps or 0), "white")
end

local movie_done = false

emu.registerafter(function()
  draw_overlay()
  if movie_done then
    return
  end
  local active = movie and movie.active and movie.active()
  local frame = (movie and movie.framecount and movie.framecount()) or 0
  local mlen = (movie and movie.length and movie.length()) or -1
  if not active then
    if overlay_cache and emu.framecount() <= overlay_until_frame then
      return
    end
    movie_done = true
    if os and os.exit then
      os.exit(0)
    end
    return
  end
  if mlen and mlen > 0 and frame >= mlen then
    if overlay_cache and emu.framecount() <= overlay_until_frame then
      return
    end
    movie_done = true
    if os and os.exit then
      os.exit(0)
    end
  end
end)
