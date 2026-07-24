-- Плейлист inference FM2: один процесс FCEUX, клипы подряд через movie.play.
-- Конфиг WAIT_FCEUX_LUA_CONFIG (относительный путь, cwd=staging):
--   { done_flag, queue_path, block_label_frames? }
-- queue_path = jsonl: {"fm2":"...","overlay":"...","block_label":"...","hold":180}

local boot = io.open("playlist_boot.txt", "w")
if boot then
  boot:write("lua_loaded\n")
  boot:write("cfg_env=" .. tostring(os.getenv("WAIT_FCEUX_LUA_CONFIG")) .. "\n")
  boot:close()
end

local function read_file(path)
  local f = io.open(path, "r")
  if not f then
    return nil
  end
  local text = f:read("*a")
  f:close()
  return text
end

local function log_msg(msg)
  local f = io.open("playlist_runtime.log", "a")
  if f then
    local fc = 0
    if emu and emu.framecount then
      fc = emu.framecount()
    end
    f:write(tostring(fc) .. " " .. tostring(msg) .. "\n")
    f:close()
  end
end

local function read_config()
  local cfg_path = os.getenv("WAIT_FCEUX_LUA_CONFIG")
  if not cfg_path then
    error("WAIT_FCEUX_LUA_CONFIG not set")
  end
  local text = read_file(cfg_path)
  if not text then
    error("Cannot open config: " .. cfg_path)
  end
  local done_flag = text:match('"done_flag"%s*:%s*"([^"]+)"')
  local queue_path = text:match('"queue_path"%s*:%s*"([^"]+)"')
  local label_frames = tonumber(text:match('"block_label_frames"%s*:%s*(%d+)')) or 120
  if not done_flag or not queue_path then
    error("Invalid playlist config (need done_flag, queue_path)")
  end
  return done_flag, queue_path, label_frames
end

local function parse_queue(path)
  local text = read_file(path)
  if not text then
    error("Cannot open queue: " .. path)
  end
  local clips = {}
  for line in text:gmatch("[^\r\n]+") do
    if line:match("%S") then
      local fm2 = line:match('"fm2"%s*:%s*"([^"]+)"')
      local overlay = line:match('"overlay"%s*:%s*"([^"]*)"') or ""
      local block_label = line:match('"block_label"%s*:%s*"([^"]*)"') or ""
      local hold = tonumber(line:match('"hold"%s*:%s*(%d+)')) or 180
      if not fm2 then
        error("Bad queue line (need fm2): " .. line)
      end
      clips[#clips + 1] = {
        fm2 = fm2,
        overlay = overlay,
        block_label = block_label,
        hold = hold,
      }
    end
  end
  if #clips == 0 then
    error("Empty playlist queue: " .. path)
  end
  return clips
end

local DONE_FLAG, QUEUE_PATH, BLOCK_LABEL_FRAMES = read_config()
local CLIPS = parse_queue(QUEUE_PATH)

local clip_idx = 0
local current = nil
local overlay_cache = nil
local overlay_until_frame = 0
local last_overlay_raw = ""
local block_label = ""
local block_label_until = 0
local movie_ever_active = false
local hold_until = nil
local finished_all = false

local function movie_is_active()
  return movie and movie.active and movie.active()
end

local function movie_is_finished()
  if movie and movie.mode then
    local mode = movie.mode()
    if mode == "finished" then
      return true
    end
  end
  if movie_ever_active and not movie_is_active() then
    return true
  end
  if movie_is_active() and movie.length and movie.framecount then
    local mlen = movie.length()
    local mf = movie.framecount()
    if mlen and mlen > 0 and mf >= mlen then
      return true
    end
  end
  return false
end

local function parse_overlay_json(text)
  local show_until = tonumber(text:match('"show_until_frame"%s*:%s*(%d+)')) or 180
  local max_cp = tonumber(text:match('"max_cp"%s*:%s*([%d%.%-]+)')) or 0
  local model_version = text:match('"model_version"%s*:%s*"([^"]*)"') or ""
  local tag = text:match('"tag"%s*:%s*"([^"]*)"') or ""
  local death_room = text:match('"death"%s*:%s*{[^}]*"room"%s*:%s*"([^"]*)"')
  local death_x = tonumber(text:match('"death"%s*:%s*{[^}]*"x"%s*:%s*(%d+)'))
  if tag == "" then
    local first = text:match('{[^}]*"slug"[^}]*}')
    if first then
      tag = first:match('"label"%s*:%s*"([^"]*)"')
        or first:match('"title"%s*:%s*"([^"]*)"')
        or first:match('"slug"%s*:%s*"([^"]*)"')
        or ""
    end
  end
  return {
    model_version = model_version,
    tag = tag,
    stats = {max_cp = max_cp},
    death_room = death_room,
    death_x = death_x,
    show_until_frame = show_until,
  }
end

local function refresh_overlay_cache()
  if not current or not current.overlay or current.overlay == "" then
    overlay_cache = nil
    last_overlay_raw = ""
    return
  end
  local text = read_file(current.overlay)
  if not text then
    overlay_cache = nil
    last_overlay_raw = ""
    return
  end
  if text ~= last_overlay_raw then
    last_overlay_raw = text
    overlay_cache = parse_overlay_json(text)
    local hold = current.hold or (overlay_cache.show_until_frame or 180)
    overlay_until_frame = emu.framecount() + hold
  end
end

local function draw_playback_hud()
  -- Только индекс клипа — без карты комнаты / TITLE (это Board)
  local n = clip_idx
  local total = #CLIPS
  gui.text(8, 220, string.format("[%d/%d]", n, total), "white")
end

local function draw_overlay()
  refresh_overlay_cache()
  if not overlay_cache or emu.framecount() > overlay_until_frame then
    return
  end
  local y = 4
  if block_label ~= "" and emu.framecount() <= block_label_until then
    gui.text(8, y, block_label, "cyan")
    y = y + 12
  end
  local gen = overlay_cache.model_version or ""
  local cp = (overlay_cache.stats and overlay_cache.stats.max_cp) or 0
  local line = ""
  if gen ~= "" then
    line = gen .. "  CP:" .. tostring(cp)
  else
    line = "CP:" .. tostring(cp)
  end
  if overlay_cache.tag and overlay_cache.tag ~= "" then
    line = line .. "  " .. overlay_cache.tag
  end
  gui.text(8, y, line, "white")
  y = y + 12
  if overlay_cache.death_room then
    local death = "X " .. tostring(overlay_cache.death_room)
    if overlay_cache.death_x then
      death = death .. " x=" .. tostring(overlay_cache.death_x)
    end
    gui.text(8, y, death, "orange")
  end
end

local function write_done()
  local f = io.open(DONE_FLAG, "w")
  if f then
    f:write("ok\n")
    f:close()
  end
end

local function finish_all()
  if finished_all then
    return
  end
  finished_all = true
  write_done()
  if os and os.exit then
    os.exit(0)
  end
end

local function start_clip(i)
  if i < 1 or i > #CLIPS then
    finish_all()
    return
  end
  clip_idx = i
  current = CLIPS[i]
  overlay_cache = nil
  last_overlay_raw = ""
  movie_ever_active = false
  hold_until = nil
  block_label = current.block_label or ""
  if block_label ~= "" then
    block_label_until = emu.framecount() + BLOCK_LABEL_FRAMES
  else
    block_label_until = 0
  end
  if movie and movie.active and movie.active() then
    pcall(function() movie.stop() end)
  end
  pcall(function()
    if movie.close then
      movie.close()
    end
  end)
  local ok, res = pcall(function()
    return movie.play(current.fm2, true)
  end)
  log_msg("start_clip " .. tostring(i) .. " fm2=" .. tostring(current.fm2) .. " ok=" .. tostring(ok) .. " res=" .. tostring(res))
  if not ok or res == false then
    log_msg("movie.play failed")
    finish_all()
    return
  end
  local hold = current.hold or 180
  overlay_until_frame = emu.framecount() + hold
end

local function advance_or_finish()
  if hold_until == nil then
    local hold = (current and current.hold) or 180
    if overlay_cache and overlay_cache.show_until_frame then
      hold = math.max(hold, overlay_cache.show_until_frame)
    end
    hold_until = emu.framecount() + hold
    return
  end
  if emu.framecount() < hold_until then
    return
  end
  if clip_idx >= #CLIPS then
    log_msg("finish_all after clip " .. tostring(clip_idx))
    finish_all()
    return
  end
  log_msg("advance to clip " .. tostring(clip_idx + 1))
  start_clip(clip_idx + 1)
end

if FCEU and FCEU.setrenderplanes then
  FCEU.setrenderplanes(true, true)
end

local bootstrapped = false

emu.registerafter(function()
  if finished_all then
    return
  end
  if not bootstrapped then
    bootstrapped = true
    start_clip(1)
    return
  end
  draw_playback_hud()
  draw_overlay()
  if movie_is_active() then
    movie_ever_active = true
  end
  if hold_until ~= nil then
    advance_or_finish()
    return
  end
  if movie_is_finished() then
    advance_or_finish()
  end
end)
