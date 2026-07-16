-- Visual + RAM probe для emulation replay inference_inputs.jsonl (BACKLOG 3.4 / N4).
-- Синхронный цикл frameadvance (как bridge.lua), не registerafter screenshot.
-- WAIT_FCEUX_LUA_CONFIG: jsonl_path, episode, frame_skip, probe_at_frame,
--   probe_flag, screenshot_path, done_flag, room, x, lives

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
  local probe_at = tonumber(text:match('"probe_at_frame"%s*:%s*(%d+)')) or 8
  local probe_flag = text:match('"probe_flag"%s*:%s*"([^"]+)"')
  local screenshot_path = text:match('"screenshot_path"%s*:%s*"([^"]+)"')
  local done_flag = text:match('"done_flag"%s*:%s*"([^"]+)"')
  local room_addr = tonumber(text:match('"room"%s*:%s*(%d+)'))
  local x_addr = tonumber(text:match('"x"%s*:%s*(%d+)'))
  local lives_addr = tonumber(text:match('"lives"%s*:%s*(%d+)'))
  if not jsonl_path or not episode or not probe_flag or not screenshot_path or not done_flag then
    error("Invalid visual probe config.json")
  end
  return jsonl_path, episode, frame_skip, probe_at, probe_flag, screenshot_path, done_flag,
    room_addr, x_addr, lives_addr
end

local JSONL_PATH, EPISODE, FRAME_SKIP, PROBE_AT, PROBE_FLAG, SCREENSHOT_PATH, DONE_FLAG,
  ROOM_ADDR, X_ADDR, LIVES_ADDR = read_config()

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

local function ram_snapshot()
  local room = ROOM_ADDR and memory.readbyte(ROOM_ADDR) or -1
  local x_pos = X_ADDR and memory.readbyte(X_ADDR) or -1
  local lives = LIVES_ADDR and memory.readbyte(LIVES_ADDR) or -1
  local gameplay_like = (lives >= 1 and lives <= 9)
  return room, x_pos, lives, gameplay_like
end

local function finish(payload)
  if payload then
    local pf = io.open(PROBE_FLAG, "w")
    if pf then
      pf:write(payload)
      pf:close()
    end
  end
  local df = io.open(DONE_FLAG, "w")
  if df then
    df:write("ok\n")
    df:close()
  end
  if os and os.exit then
    os.exit(0)
  end
end

local function capture_screenshot(gd_path)
  local shot = gui.gdscreenshot()
  local sf = io.open(gd_path, "wb")
  if not sf then
    error("cannot open " .. gd_path)
  end
  sf:write(shot)
  sf:close()
  return shot and #shot or -1
end

local replay_steps = load_episode_steps(JSONL_PATH, EPISODE, FRAME_SKIP)
local playback_frame = 0
local MAX_FRAMES = math.max(600, PROBE_AT + 150)

FCEU.speedmode("nothrottle")
FCEU.setrenderplanes(true, true)

local gd_path = SCREENSHOT_PATH
if not gd_path:match("%.gd$") then
  gd_path = SCREENSHOT_PATH .. ".gd"
end

local steps_needed = math.max(#replay_steps, PROBE_AT)
for step_idx = 1, steps_needed do
  joypad.set(1, parse_input(replay_steps[step_idx] or ""))
  emu.frameadvance()
  playback_frame = playback_frame + 1

  if playback_frame >= PROBE_AT then
    local room, x_pos, lives, gameplay_like = ram_snapshot()
    local shot_ok = false
    local shot_err = ""
    local shot_size = -1
    if gui and gui.gdscreenshot then
      local ok, err = pcall(function()
        shot_size = capture_screenshot(gd_path)
      end)
      shot_ok = ok
      if not ok then
        shot_err = tostring(err)
      end
    else
      shot_err = "gui.gdscreenshot unavailable"
    end
    finish(string.format(
      '{"ok":true,"playback_frame":%d,"emu_frame":%d,"room":%d,"x":%d,"lives":%d,"gameplay_like_ram":%s,"screenshot_path":"%s","screenshot_gd_path":"%s","screenshot_ok":%s,"screenshot_size":%d,"screenshot_error":"%s"}',
      playback_frame, emu.framecount(), room, x_pos, lives, gameplay_like and "true" or "false",
      SCREENSHOT_PATH:gsub("\\", "\\\\"),
      gd_path:gsub("\\", "\\\\"),
      shot_ok and "true" or "false",
      shot_size or -1,
      shot_err:gsub("\\", "\\\\"):gsub('"', '\\"')
    ))
    return
  end

  if playback_frame >= MAX_FRAMES then
    finish('{"ok":false,"error":"playback_frame_cap"}')
    return
  end
end

finish('{"ok":false,"error":"probe_not_reached"}')
