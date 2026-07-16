-- Inference playback: emulation replay from inference_inputs.jsonl + achievement overlay.
-- GUI: registerbefore/registerafter (FCEUX рисует окно между кадрами).
-- Config (WAIT_FCEUX_LUA_CONFIG): jsonl_path, episode, frame_skip, done_flag,
--   overlay_path (opt.), turbo (opt.), probe_at_frame/probe_flag/screenshot_path (opt., smoke).

local BUTTONS = {"right", "left", "up", "down", "A", "B", "start", "select"}

local function read_config()
  local cfg_path = os.getenv("WAIT_FCEUX_LUA_CONFIG")
  if not cfg_path then
    error("WAIT_FCEUX_LUA_CONFIG not set")
  end
  local f = io.open(cfg_path, "r")
  if not f then
    error("Cannot open config: " .. cfg_path)
  end
  local text = f:read("*a")
  f:close()
  local jsonl_path = text:match('"jsonl_path"%s*:%s*"([^"]+)"')
  local episode = tonumber(text:match('"episode"%s*:%s*(%d+)'))
  local frame_skip = tonumber(text:match('"frame_skip"%s*:%s*(%d+)')) or 4
  local done_flag = text:match('"done_flag"%s*:%s*"([^"]+)"')
  local overlay_path = text:match('"overlay_path"%s*:%s*"([^"]+)"')
  local turbo = text:match('"turbo"%s*:%s*true') ~= nil
  local probe_at = tonumber(text:match('"probe_at_frame"%s*:%s*(%d+)'))
  local probe_flag = text:match('"probe_flag"%s*:%s*"([^"]+)"')
  local screenshot_path = text:match('"screenshot_path"%s*:%s*"([^"]+)"')
  local probe_only = text:match('"probe_only"%s*:%s*true') ~= nil
  if not jsonl_path or not episode or not done_flag then
    error("Invalid playback config.json")
  end
  return jsonl_path, episode, frame_skip, done_flag, overlay_path, turbo,
    probe_at, probe_flag, screenshot_path, probe_only
end

local JSONL_PATH, EPISODE, FRAME_SKIP, DONE_FLAG, OVERLAY_PATH_CFG, TURBO,
  PROBE_AT, PROBE_FLAG, SCREENSHOT_PATH, PROBE_ONLY = read_config()

local empty_input = {
  right = false, left = false, up = false, down = false,
  A = false, B = false, start = false, select = false,
}

local function parse_input(s)
  local t = {}
  for _, b in ipairs(BUTTONS) do
    t[b] = false
  end
  if s and s ~= "" then
    for part in string.gmatch(s, "[^%+]+") do
      if t[part] ~= nil then
        t[part] = true
      end
    end
  end
  return t
end

local function load_episode_steps(jsonl_path, episode, frame_skip)
  local f = io.open(jsonl_path, "r")
  if not f then
    error("Cannot open jsonl: " .. jsonl_path)
  end
  local steps = {}
  for line in f:lines() do
    if line ~= "" then
      local ep = tonumber(line:match('"episode"%s*:%s*(%d+)'))
      local action = line:match('"action"%s*:%s*"([^"]*)"') or ""
      if ep == episode then
        for _ = 1, frame_skip do
          steps[#steps + 1] = action
        end
      end
    end
  end
  f:close()
  if #steps == 0 then
    error("No steps for episode " .. tostring(episode))
  end
  return steps
end

local replay_steps = load_episode_steps(JSONL_PATH, EPISODE, FRAME_SKIP)
local step_idx = 0
local replay_done = false
local playback_frame = 0
local finished = false
local probed = false

if TURBO then
  FCEU.speedmode("nothrottle")
end

local overlay_cache = nil
local overlay_until_frame = 0
local last_overlay_raw = ""
local block_label = ""
local block_label_until = 0
local block_label_frames = 120

local function overlay_path()
  if OVERLAY_PATH_CFG and OVERLAY_PATH_CFG ~= "" then
    return OVERLAY_PATH_CFG
  end
  local from_env = os.getenv("WAIT_ACHIEVEMENT_OVERLAY")
  if from_env and from_env ~= "" then
    return from_env
  end
  return ""
end

local function parse_overlay_json(text)
  local show_until = tonumber(text:match('"show_until_frame"%s*:%s*(%d+)')) or 180
  local max_cp = tonumber(text:match('"max_cp"%s*:%s*([%d%.%-]+)')) or 0
  local reward = tonumber(text:match('"reward"%s*:%s*([%d%.%-]+)')) or 0
  local steps_n = tonumber(text:match('"steps"%s*:%s*(%d+)')) or 0
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
    stats = {max_cp = max_cp, reward = reward, steps = steps_n},
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
    block_label_until = playback_frame + block_label_frames
  end
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
  local room = memory.readbyte(room_addr)
  local lives = 0
  local lives_env = os.getenv("WAIT_PLAYBACK_LIVES")
  if lives_env and lives_env ~= "" then
    local lives_addr = tonumber(lives_env)
    if lives_addr then
      lives = memory.readbyte(lives_addr)
    end
  end
  local tag = replay_done and "REPLAY/DONE" or "REPLAY/GAMEPLAY"
  local color = replay_done and "orange" or "limegreen"
  local hud = string.format("%s f=%d r=0x%02X L=%d", tag, playback_frame, room, lives)
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
    overlay_until_frame = playback_frame + (overlay_cache.show_until_frame or 180)
  end
  if block_label ~= "" and playback_frame <= block_label_until then
    gui.text(8, 2, "[" .. block_label .. "]", "cyan")
  end
  if not overlay_cache or playback_frame > overlay_until_frame then
    return
  end
  local y = 12
  if block_label ~= "" and playback_frame <= block_label_until then
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

local function capture_probe_screenshot(force)
  if not PROBE_AT or not SCREENSHOT_PATH or not PROBE_FLAG or probed then
    return
  end
  if not force and playback_frame < PROBE_AT then
    return
  end
  probed = true
  local gd_path = SCREENSHOT_PATH
  if not gd_path:match("%.gd$") then
    gd_path = SCREENSHOT_PATH .. ".gd"
  end
  local shot_ok = false
  local shot_err = ""
  local shot_size = -1
  if gui and gui.gdscreenshot then
    local ok, err = pcall(function()
      if FCEU and FCEU.setrenderplanes then
        FCEU.setrenderplanes(true, true)
      end
      local shot = gui.gdscreenshot()
      local sf = io.open(gd_path, "wb")
      if not sf then
        error("cannot open " .. gd_path)
      end
      sf:write(shot)
      sf:close()
    end)
    shot_ok = ok
    if not ok then
      shot_err = tostring(err)
    end
    local sf = io.open(gd_path, "rb")
    if sf then
      shot_size = sf:seek("end")
      sf:close()
    end
  else
    shot_err = "gui.gdscreenshot unavailable"
  end
  local pf = io.open(PROBE_FLAG, "w")
  if pf then
    pf:write(string.format(
      '{"ok":true,"playback_frame":%d,"emu_frame":%d,"screenshot_path":"%s","screenshot_gd_path":"%s","screenshot_ok":%s,"screenshot_size":%d,"screenshot_error":"%s"}',
      playback_frame, emu.framecount(),
      SCREENSHOT_PATH:gsub("\\", "\\\\"),
      gd_path:gsub("\\", "\\\\"),
      shot_ok and "true" or "false",
      shot_size or -1,
      shot_err:gsub("\\", "\\\\"):gsub('"', '\\"')
    ))
    pf:close()
  end
end

local function finish()
  if finished then
    return
  end
  finished = true
  local df = io.open(DONE_FLAG, "w")
  if df then
    df:write("ok\n")
    df:close()
  end
  if os and os.exit then
    os.exit(0)
  end
end

init_block_label()

-- Smoke/probe: снимок сразу после -loadstate, до первого joypad.
if PROBE_ONLY and PROBE_AT and PROBE_AT <= 1 and SCREENSHOT_PATH then
  capture_probe_screenshot(true)
  if probed then
    finish()
    return
  end
end

emu.registerbefore(function()
  if finished then
    return
  end
  if replay_done then
    joypad.set(1, empty_input)
    return
  end
  step_idx = step_idx + 1
  joypad.set(1, parse_input(replay_steps[step_idx] or ""))
  if step_idx >= #replay_steps then
    replay_done = true
  end
end)

emu.registerafter(function()
  if finished then
    return
  end
  playback_frame = playback_frame + 1
  draw_playback_hud()
  draw_overlay()
  capture_probe_screenshot()
  if PROBE_ONLY and probed then
    finish()
    return
  end

  if replay_done then
    local hold_until = overlay_until_frame
    if hold_until <= 0 then
      hold_until = #replay_steps + 60
    end
    if playback_frame >= hold_until then
      finish()
    end
  end
end)
