-- IPC bridge: Python ↔ FCEUX
-- Конфиг: WAIT_FCEUX_BRIDGE_CONFIG → JSON (ipc_dir, frame_skip, ram_addrs)
-- Протокол: ipc_dir/request.json → ipc_dir/response.json; ready.flag при старте

local OBS_W, OBS_H = 84, 84
local NES_W, NES_H = 256, 240
local BUTTONS = {"right", "left", "up", "down", "A", "B", "start", "select"}

local function read_config()
  local cfg_path = os.getenv("WAIT_FCEUX_BRIDGE_CONFIG")
  if not cfg_path then
    error("WAIT_FCEUX_BRIDGE_CONFIG not set")
  end
  local f = io.open(cfg_path, "r")
  if not f then
    error("Cannot open bridge config: " .. cfg_path)
  end
  local text = f:read("*a")
  f:close()

  local ipc_dir = text:match('"ipc_dir"%s*:%s*"([^"]+)"')
  local frame_skip_s = text:match('"frame_skip"%s*:%s*(%d+)')
  local no_focus_s = text:match('"no_focus"%s*:%s*(true|false)')
  local obs_format = text:match('"obs_format"%s*:%s*"([^"]+)"') or "gd"
  if not ipc_dir then
    error("Invalid bridge config: ipc_dir missing")
  end

  local ram_addrs = {}
  local ram_block = text:match('"ram_addrs"%s*:%s*{([^}]+)}')
  if ram_block then
    for field, addr in ram_block:gmatch('"([%w_]+)"%s*:%s*"(0x[%x]+)"') do
      ram_addrs[field] = tonumber(addr)
    end
  end

  return ipc_dir, tonumber(frame_skip_s) or 4, ram_addrs, no_focus_s == "true", obs_format
end

local IPC_DIR, FRAME_SKIP, RAM_ADDRS, NO_FOCUS, OBS_FORMAT = read_config()
local REQ_PATH = IPC_DIR .. "/request.json"
local RESP_PATH = IPC_DIR .. "/response.json"
local READY_PATH = IPC_DIR .. "/ready.flag"

local save_slot = 9
local save_handle = nil
local state_cache = {}
local empty_input = {right = false, left = false, up = false, down = false, A = false, B = false, start = false, select = false}
local step_input = empty_input
local stepping = false
local step_frames_left = 0
local step_req = nil
local should_quit = false
local obs_pending = nil
local overlay_cache = nil
local overlay_until_frame = 0
local last_overlay_raw = ""

local function overlay_session_dir()
  return (IPC_DIR:match("^(.+)/[^/]+$") or IPC_DIR)
end

local function parse_overlay_json(text)
  local show_until = tonumber(text:match('"show_until_frame"%s*:%s*(%d+)')) or 0
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

local function draw_overlay()
  local path = overlay_session_dir() .. "/overlay.json"
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
    overlay_until_frame = emu.framecount() + (overlay_cache.show_until_frame or 0)
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

-- Hypothesis B: winapi minimize / off-screen (train no-focus)
local focus_hidden = false

local function hide_fceux_window()
  if focus_hidden or not NO_FOCUS then
    return
  end
  local ok = pcall(function()
    require("winapi")
    local w = winapi.find_window("FCEUXWindowClass", nil)
    if not w then
      error("FCEUX window not found")
    end
    if w.minimize then
      w:minimize()
    else
      w:set_position(-32000, -32000)
    end
  end)
  if ok then
    focus_hidden = true
  end
end

emu.registerafter(function()
  hide_fceux_window()
  draw_overlay()
end)

local function write_ready()
  local f = io.open(READY_PATH, "w")
  if f then
    f:write("ok\n")
    f:close()
  end
end

local function write_response(seq, ok, fields)
  local parts = {string.format('{"seq":%d,"ok":%s', seq, ok and "true" or "false")}
  for k, v in pairs(fields) do
    if type(v) == "number" then
      parts[#parts + 1] = string.format(',"%s":%s', k, v)
    elseif type(v) == "boolean" then
      parts[#parts + 1] = string.format(',"%s":%s', k, v and "true" or "false")
    else
      parts[#parts + 1] = string.format(',"%s":"%s"', k, tostring(v):gsub('"', '\\"'))
    end
  end
  parts[#parts + 1] = "}"
  local f = io.open(RESP_PATH, "w")
  if not f then
    error("Cannot write response: " .. RESP_PATH)
  end
  f:write(table.concat(parts))
  f:close()
end

local function read_request()
  local f = io.open(REQ_PATH, "r")
  if not f then
    return nil
  end
  local text = f:read("*a")
  f:close()
  if not text or text == "" then
    return nil
  end
  local seq = tonumber(text:match('"seq"%s*:%s*(%d+)'))
  local cmd = text:match('"cmd"%s*:%s*"([^"]+)"')
  local arg = text:match('"arg"%s*:%s*"([^"]*)"')
  if not seq or not cmd then
    return nil
  end
  return {seq = seq, cmd = cmd, arg = arg or ""}
end

local function clear_request()
  os.remove(REQ_PATH)
end

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

local function read_ram()
  local out = {}
  for field, addr in pairs(RAM_ADDRS) do
    local v = memory.readbyte(addr)
    if field == "room" then
      out[field] = string.format("0x%02X", v)
    else
      out[field] = v
    end
  end
  out.frame = emu.framecount()
  return out
end

local GD_HEADER_BYTES = 11

local function gd_to_raw_gray(shot, w, h)
  local src_w, src_h = NES_W, NES_H
  local parts = {}
  local idx = 1
  for oy = 0, h - 1 do
    local sy = math.floor(oy * src_h / h)
    local row_base = GD_HEADER_BYTES + sy * src_w * 4
    for ox = 0, w - 1 do
      local sx = math.floor(ox * src_w / w)
      local p = row_base + sx * 4 + 1
      local r = shot:byte(p)
      local g = shot:byte(p + 1)
      local b = shot:byte(p + 2)
      parts[idx] = string.char(math.floor(0.299 * r + 0.587 * g + 0.114 * b))
      idx = idx + 1
    end
  end
  return table.concat(parts)
end

local function capture_obs(seq, skip_advance)
  local use_raw = OBS_FORMAT == "raw"
  local ext = use_raw and "raw" or "gd"
  local path = IPC_DIR .. "/obs_" .. seq .. "." .. ext
  FCEU.setrenderplanes(true, true)
  if not skip_advance then
    emu.frameadvance()
  end
  local shot = gui.gdscreenshot()
  FCEU.setrenderplanes(false, false)
  local f = io.open(path, "wb")
  if not f then
    error("Cannot open obs file: " .. path)
  end
  if use_raw then
    f:write(gd_to_raw_gray(shot, OBS_W, OBS_H))
  else
    f:write(shot)
  end
  f:close()
  return path, use_raw and "raw" or "gd"
end

local function reset_stepping()
  stepping = false
  step_frames_left = 0
  step_req = nil
  step_input = empty_input
  obs_pending = nil
end

local function cache_current_state(key)
  if not key or key == "" then
    error("CACHE key missing")
  end
  local st = savestate.create()
  savestate.save(st)
  savestate.persist(st)
  state_cache[key] = st
end

local function load_cached_state(key)
  local st = state_cache[key]
  if not st then
    error("state not cached: " .. tostring(key))
  end
  savestate.load(st)
  reset_stepping()
end

local function response_with_obs(seq, cmd, extra)
  local path, fmt = capture_obs(seq, false)
  local ram = read_ram()
  ram.cmd = cmd
  ram.obs_file = path
  ram.format = fmt
  ram.w = OBS_W
  ram.h = OBS_H
  if extra then
    for k, v in pairs(extra) do
      ram[k] = v
    end
  end
  write_response(seq, true, ram)
end

local function finish_obs(req)
  local path, fmt = capture_obs(req.seq, false)
  if req.cmd == "LOAD_OBS" then
    local ram = read_ram()
    ram.cmd = "LOAD_OBS"
    ram.key = req.arg
    ram.obs_file = path
    ram.format = fmt
    ram.w = OBS_W
    ram.h = OBS_H
    write_response(req.seq, true, ram)
  else
    local fields = {
      cmd = "GET_OBS",
      format = fmt,
      src_w = NES_W,
      src_h = NES_H,
      w = OBS_W,
      h = OBS_H,
      obs_file = path,
    }
    write_response(req.seq, true, fields)
  end
  clear_request()
  obs_pending = nil
end

emu.registerbefore(function()
  joypad.set(1, stepping and step_input or empty_input)
end)

local function finish_step()
  local path, fmt = capture_obs(step_req.seq, true)
  local ram = read_ram()
  ram.cmd = "STEP"
  ram.obs_file = path
  ram.format = fmt
  ram.w = OBS_W
  ram.h = OBS_H
  write_response(step_req.seq, true, ram)
  clear_request()
  stepping = false
  step_req = nil
  step_frames_left = 0
end

local function dispatch_immediate(req)
  if req.cmd == "PING" then
    write_response(req.seq, true, {cmd = "PING"})
  elseif req.cmd == "GET_RAM" then
    local ram = read_ram()
    ram.cmd = "GET_RAM"
    write_response(req.seq, true, ram)
  elseif req.cmd == "GET_OBS" then
    obs_pending = req
  elseif req.cmd == "TURBO" then
    local on = req.arg == "on" or req.arg == "1" or req.arg == "true"
    if on then
      FCEU.speedmode("nothrottle")
      FCEU.setrenderplanes(false, false)
    else
      FCEU.speedmode("normal")
      FCEU.setrenderplanes(true, true)
    end
    write_response(req.seq, true, {cmd = "TURBO", on = on})
  elseif req.cmd == "CACHE" then
    local ok, err = pcall(cache_current_state, req.arg)
    if ok then
      write_response(req.seq, true, {cmd = "CACHE", key = req.arg})
    else
      write_response(req.seq, false, {error = tostring(err)})
    end
  elseif req.cmd == "LOAD" then
    local ok, err = pcall(function()
      load_cached_state(req.arg)
    end)
    if ok then
      local ram = read_ram()
      ram.cmd = "LOAD"
      ram.key = req.arg
      write_response(req.seq, true, ram)
    else
      write_response(req.seq, false, {error = tostring(err)})
    end
  elseif req.cmd == "LOAD_OBS" then
    local ok, err = pcall(function()
      load_cached_state(req.arg)
    end)
    if ok then
      obs_pending = req
    else
      write_response(req.seq, false, {error = tostring(err)})
    end
  elseif req.cmd == "SAVE" then
    local fceux_slot = save_slot + 1
    if not save_handle then
      save_handle = savestate.create(fceux_slot)
    end
    savestate.save(save_handle)
    savestate.persist(save_handle)
    write_response(req.seq, true, {
      cmd = "SAVE",
      slot = save_slot,
      rom = rom.getfilename(),
    })
  elseif req.cmd == "QUIT" then
    write_response(req.seq, true, {cmd = "QUIT"})
    should_quit = true
  else
    write_response(req.seq, false, {error = "unknown cmd: " .. req.cmd})
  end
end

FCEU.speedmode("nothrottle")
FCEU.setrenderplanes(false, false)
write_ready()

while not should_quit do
  if stepping then
    emu.frameadvance()
    step_frames_left = step_frames_left - 1
    if step_frames_left <= 0 then
      finish_step()
    end
  elseif obs_pending then
    finish_obs(obs_pending)
  else
    local req = read_request()
    if req then
      if req.cmd == "STEP" then
        step_req = req
        step_input = parse_input(req.arg)
        step_frames_left = FRAME_SKIP
        stepping = true
      else
        dispatch_immediate(req)
        clear_request()
      end
    end
  end
end

if os and os.exit then
  os.exit(0)
end
