-- M-proto-1 шаги 4–5: RAM-probe при -playmovie на заданном movie frame.
-- WAIT_FCEUX_LUA_CONFIG: { done_flag, probe_flag, probe_at_mf, room, x, lives }

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
  local done_flag = text:match('"done_flag"%s*:%s*"([^"]+)"')
  local probe_flag = text:match('"probe_flag"%s*:%s*"([^"]+)"')
  local probe_at = tonumber(text:match('"probe_at_mf"%s*:%s*(%d+)')) or 8
  local room_addr = tonumber(text:match('"room"%s*:%s*(%d+)'))
  local x_addr = tonumber(text:match('"x"%s*:%s*(%d+)'))
  local lives_addr = tonumber(text:match('"lives"%s*:%s*(%d+)'))
  if not done_flag or not probe_flag then
    error("Invalid config.json")
  end
  return done_flag, probe_flag, probe_at, room_addr, x_addr, lives_addr
end

local DONE_FLAG, PROBE_FLAG, PROBE_AT_MF, ROOM_ADDR, X_ADDR, LIVES_ADDR = read_config()
local finished = false
local probed = false
local MAX_EMU_FRAMES = math.max(600, PROBE_AT_MF + 200)

local function ram_snapshot()
  local room = ROOM_ADDR and memory.readbyte(ROOM_ADDR) or -1
  local x_pos = X_ADDR and memory.readbyte(X_ADDR) or -1
  local lives = LIVES_ADDR and memory.readbyte(LIVES_ADDR) or -1
  -- lives 1..9 = controllable play; room=0+x=129 alone is title/attract (ISSUE G0)
  local gameplay_like = (lives >= 1 and lives <= 9)
  return room, x_pos, lives, gameplay_like
end

local function finish(payload)
  if finished then
    return
  end
  finished = true
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

emu.registerafter(function()
  if finished then
    return
  end
  local emu_frame = emu.framecount()
  local movie_active = movie and movie.active and movie.active() or false
  local mf = 0
  if movie_active and movie.framecount then
    mf = movie.framecount()
  end

  if movie_active and mf >= PROBE_AT_MF and not probed then
    probed = true
    local room, x_pos, lives, gameplay_like = ram_snapshot()
    finish(string.format(
      '{"ok":true,"mf":%d,"emu_frame":%d,"room":%d,"x":%d,"lives":%d,"gameplay_like_ram":%s,"movie_active":true}',
      mf, emu_frame, room, x_pos, lives, gameplay_like and "true" or "false"
    ))
    return
  end

  if movie and movie.mode and movie.mode() == "finished" then
    local room, x_pos, lives, gameplay_like = ram_snapshot()
    finish(string.format(
      '{"ok":false,"error":"movie_finished","mf":%d,"emu_frame":%d,"room":%d,"x":%d,"lives":%d,"gameplay_like_ram":%s,"movie_active":%s}',
      mf, emu_frame, room, x_pos, lives, gameplay_like and "true" or "false", movie_active and "true" or "false"
    ))
    return
  end

  if emu_frame >= MAX_EMU_FRAMES then
    local room, x_pos, lives, gameplay_like = ram_snapshot()
    finish(string.format(
      '{"ok":false,"error":"emu_frame_cap","mf":%d,"emu_frame":%d,"room":%d,"x":%d,"lives":%d,"gameplay_like_ram":%s,"movie_active":%s}',
      mf, emu_frame, room, x_pos, lives, gameplay_like and "true" or "false", movie_active and "true" or "false"
    ))
  end
end)
