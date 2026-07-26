-- Slim Lua HUD: gen, CP, короткий тег / смерть (STREAMING §7 / TASK_HYBRID_BROADCAST).
-- Запуск: scripts/play_inference_fm2.py
-- Конфиг: WAIT_ACHIEVEMENT_OVERLAY, опц. WAIT_BLOCK_LABEL

local overlay_cache = nil
local overlay_until_frame = 0
local last_overlay_raw = ""
local block_label = ""
local block_label_until = 0
local block_label_frames = 90

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

init_block_label()

if FCEU and FCEU.setrenderplanes then
  FCEU.setrenderplanes(true, true)
end

emu.registerafter(function()
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
