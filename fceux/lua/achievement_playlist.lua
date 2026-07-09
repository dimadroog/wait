-- Achievement playlist replay (один клип за запуск FCEUX).
-- Python play_inference_fm2.py перезапускает FCEUX для каждого клипа.
-- Конфиг: WAIT_PLAYLIST_CONFIG + WAIT_PLAYLIST_CLIP_IDX (1-based)
-- Fallback: WAIT_ACHIEVEMENT_OVERLAY + WAIT_BLOCK_LABEL

local overlay_cache = nil
local overlay_until_frame = 0
local last_overlay_raw = ""
local block_label = ""
local block_label_until = 0
local block_label_frames = 120

local function read_file(path)
  local f = io.open(path, "r")
  if not f then
    return nil
  end
  local text = f:read("*a")
  f:close()
  return text
end

local function parse_overlay_json(text)
  local show_until = tonumber(text:match('"show_until_frame"%s*:%s*(%d+)')) or 180
  local max_cp = tonumber(text:match('"max_cp"%s*:%s*([%d%.%-]+)')) or 0
  local reward = tonumber(text:match('"reward"%s*:%s*([%d%.%-]+)')) or 0
  local steps = tonumber(text:match('"steps"%s*:%s*(%d+)')) or 0
  local achievements = {}
  for ach_block in text:gmatch('{[^}]*"slug"[^}]*}') do
    local idx = tonumber(ach_block:match('"idx"%s*:%s*(%d+)')) or 0
    local title = ach_block:match('"title"%s*:%s*"([^"]*)"') or ""
    local label = ach_block:match('"label"%s*:%s*"([^"]*)"') or ""
    local slug = ach_block:match('"slug"%s*:%s*"([^"]*)"') or ""
    local tier = ach_block:match('"tier"%s*:%s*"([^"]*)"') or "gold"
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

local function clip_from_playlist()
  local cfg_path = os.getenv("WAIT_PLAYLIST_CONFIG")
  local idx_str = os.getenv("WAIT_PLAYLIST_CLIP_IDX")
  if not cfg_path or cfg_path == "" or not idx_str or idx_str == "" then
    return nil
  end
  local want = tonumber(idx_str)
  if not want then
    return nil
  end
  local text = read_file(cfg_path)
  if not text then
    return nil
  end
  for clip_block in text:gmatch('{[^}]*"fm2"[^}]*}') do
    local clip_idx = tonumber(clip_block:match('"idx"%s*:%s*(%d+)'))
    if clip_idx == want then
      local overlay_name = clip_block:match('"overlay"%s*:%s*"([^"]*)"') or ""
      local label = clip_block:match('"block_label"%s*:%s*"([^"]*)"') or ""
      local cfg_dir = cfg_path:match("^(.*)[/\\][^/\\]+$") or "."
      local overlay_path = overlay_name
      if overlay_path ~= "" and not overlay_path:match("^[/\\]") and not overlay_path:match("^%a:[/\\]") then
        overlay_path = cfg_dir .. "/" .. overlay_name
      end
      return {overlay = overlay_path, block_label = label}
    end
  end
  return nil
end

local function resolve_overlay_path()
  local clip = clip_from_playlist()
  if clip and clip.overlay and clip.overlay ~= "" then
    if clip.block_label and clip.block_label ~= "" then
      block_label = clip.block_label
    end
    return clip.overlay
  end
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

local function load_overlay()
  local path = resolve_overlay_path()
  if path == "" then
    return
  end
  local text = read_file(path)
  if not text then
    overlay_cache = nil
    last_overlay_raw = ""
    return
  end
  if text ~= last_overlay_raw then
    last_overlay_raw = text
    overlay_cache = parse_overlay_json(text)
    overlay_until_frame = emu.framecount() + (overlay_cache.show_until_frame or 180)
  end
end

local function draw_overlay()
  if block_label ~= "" and emu.framecount() <= block_label_until then
    gui.text(8, 2, "[" .. block_label .. "]", "cyan")
  end
  if not overlay_cache or emu.framecount() > overlay_until_frame then
    return
  end
  local y = 16
  if block_label ~= "" and emu.framecount() <= block_label_until then
    y = 28
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
load_overlay()

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
