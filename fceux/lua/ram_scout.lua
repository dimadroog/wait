-- RAM scout: лог RAM при проигрывании FM2 (сборка эталона)
-- Конфиг: tmp/ram_scout/config.json (output_jsonl, done_flag)

local RAM_START = 0x0000
local RAM_SIZE = 0x0800
local BUFFER_SIZE = 64

local function read_config()
  local cfg_path = os.getenv("WAIT_RAM_SCOUT_CONFIG")
  if not cfg_path then
    error("WAIT_RAM_SCOUT_CONFIG not set")
  end
  local f = io.open(cfg_path, "r")
  if not f then
    error("Cannot open config: " .. cfg_path)
  end
  local text = f:read("*a")
  f:close()
  local out_jsonl = text:match('"output_jsonl"%s*:%s*"([^"]+)"')
  local done_flag = text:match('"done_flag"%s*:%s*"([^"]+)"')
  if not out_jsonl or not done_flag then
    error("Invalid config.json")
  end
  return out_jsonl, done_flag
end

local OUT_PATH, DONE_FLAG = read_config()
local out = io.open(OUT_PATH, "w")
if not out then
  error("Cannot open output: " .. OUT_PATH)
end

local finished = false
local write_buffer = {}

local function joy_str()
  local j = joypad.read(1)
  if not j then
    return ""
  end
  local keys = {"right", "left", "up", "down", "A", "B", "start", "select"}
  local parts = {}
  for _, k in ipairs(keys) do
    if j[k] then
      parts[#parts + 1] = k
    end
  end
  return table.concat(parts, "+")
end

local function ram_hex()
  local raw = memory.readbyterange(RAM_START, RAM_SIZE)
  local hex = {}
  for i = 1, #raw do
    hex[i] = string.format("%02X", string.byte(raw, i))
  end
  return table.concat(hex)
end

local function flush_out()
  if #write_buffer > 0 then
    out:write(table.concat(write_buffer))
    write_buffer = {}
  end
end

local function finish()
  if finished then
    return
  end
  finished = true
  flush_out()
  out:close()
  local df = io.open(DONE_FLAG, "w")
  if df then
    df:write("ok\n")
    df:close()
  end
  if os and os.exit then
    os.exit(0)
  end
end

emu.registerafter(function()
  if finished then
    return
  end
  if not movie.active() then
    finish()
    return
  end

  local frame = movie.framecount()
  local mode = movie.mode()
  write_buffer[#write_buffer + 1] = string.format(
    '{"frame":%d,"mode":"%s","input":"%s","ram_hex":"%s"}\n',
    frame,
    mode or "",
    joy_str(),
    ram_hex()
  )
  if #write_buffer >= BUFFER_SIZE then
    flush_out()
  end

  local mlen = movie.length()
  if mode == "finished" or (mlen and frame >= mlen) then
    finish()
  end
end)

if movie.active() then
  FCEU.speedmode("nothrottle")
  FCEU.setrenderplanes(false, false)
  movie.playbeginning()
else
  gui.popup("RAM scout: FM2 not loaded. Check -playmovie and ROM path.", "ok")
  finish()
end
