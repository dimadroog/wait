-- Achievement overlay при проигрывании inference FM2 (single clip или playlist).
-- Запуск: scripts/play_inference_fm2.py
-- Конфиг: WAIT_ACHIEVEMENT_OVERLAY, опц. WAIT_BLOCK_LABEL (заголовок блока эфира)

local overlay_cache = nil
local overlay_until_frame = 0
local last_overlay_raw = ""
local block_label = ""
local block_label_until = 0
local block_label_frames = 120

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

local function init_block_label()
  local from_env = os.getenv("WAIT_BLOCK_LABEL")
  if from_env and from_env ~= "" then
    block_label = from_env
  end
  local frames_env = os.getenv("WAIT_BLOCK_LABEL_FRAMES")
  if frames_env and frames_env ~= "" then
    local n = tonumber(frames_env)
    if n and n > 0 then
      block_label_frames = n
    end
  end
  if block_label ~= "" then
    block_label_until = emu.framecount() + block_label_frames
  end
end

local function movie_is_active()
  return movie and movie.active and movie.active()
end

local movie_done = false
local movie_ever_active = false

local function gameplay_start_mf()
  local from_env = os.getenv("WAIT_PLAYBACK_GAMEPLAY_START")
  if from_env and from_env ~= "" then
    local n = tonumber(from_env)
    if n and n > 0 then
      return n
    end
  end
  return 18
end

local function is_title_phase(room, lives, mf)
  local start_mf = gameplay_start_mf()
  if mf > 0 and mf < start_mf then
    return true
  end
  if room == 0xFF or room == 0x13 or room == 0x05 then
    return true
  end
  if lives > 10 then
    return true
  end
  return false
end

local function draw_playback_hud()
  local room_env = os.getenv("WAIT_PLAYBACK_ROOM")
  if not room_env or room_env == "" then
    return
  end
  local room_addr = tonumber(room_env)
  if not room_addr then
    return
  end
  local active = movie_is_active()
  local mf = 0
  if active then
    mf = movie.framecount()
  end
  local room = memory.readbyte(room_addr)
  local lives = 0
  local lives_env = os.getenv("WAIT_PLAYBACK_LIVES")
  if lives_env and lives_env ~= "" then
    local lives_addr = tonumber(lives_env)
    if lives_addr then
      lives = memory.readbyte(lives_addr)
    end
  end
  local phase = "GAMEPLAY"
  if is_title_phase(room, lives, mf) then
    phase = "TITLE"
  end
  local tag = active and ("REPLAY/" .. phase) or "NO-MOVIE"
  local color = "red"
  if active and phase == "GAMEPLAY" then
    color = "limegreen"
  elseif active then
    color = "orange"
  end
  local hud = string.format("%s f=%d r=0x%02X L=%d", tag, mf, room, lives)
  gui.text(8, 220, hud, color)
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
  end
  if block_label ~= "" and emu.framecount() <= block_label_until then
    gui.text(8, 2, "[" .. block_label .. "]", "cyan")
  end
  if not overlay_cache or emu.framecount() > overlay_until_frame then
    return
  end
  local y = 12
  if block_label ~= "" and emu.framecount() <= block_label_until then
    y = 24
  end
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

init_block_label()

emu.registerafter(function()
  draw_playback_hud()
  draw_overlay()
  if movie_done then
    return
  end
  if movie_is_active() then
    movie_ever_active = true
  end
  if not movie_is_active() then
    if movie_ever_active and overlay_cache and emu.framecount() <= overlay_until_frame then
      return
    end
    if movie_ever_active then
      movie_done = true
      if os and os.exit then
        os.exit(0)
      end
    end
    return
  end
  local frame = movie.framecount()
  local mlen = movie.length()
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
