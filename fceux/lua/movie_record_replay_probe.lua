-- N6: native movie.record → stop → play → RAM-probe.
-- WAIT_FCEUX_LUA_CONFIG: done_flag, result_flag, out_fm2, num_record_frames,
--   probe_at_mf, save_type, variant, require_gameplay_ram, load_slot_before_record,
--   savestate_slot, room, x, lives

local EMPTY_INPUT = {
  right = false,
  left = false,
  up = false,
  down = false,
  A = false,
  B = false,
  start = false,
  select = false,
}

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

  local function req(key)
    local val = text:match('"' .. key .. '"%s*:%s*"([^"]+)"')
    if not val then
      error("Invalid config.json: missing " .. key)
    end
    return val
  end

  local done_flag = req("done_flag")
  local result_flag = req("result_flag")
  local out_fm2 = req("out_fm2")
  local variant = text:match('"variant"%s*:%s*"([^"]+)"') or "N6-B"
  local num_frames = tonumber(text:match('"num_record_frames"%s*:%s*(%d+)')) or 60
  local probe_at = tonumber(text:match('"probe_at_mf"%s*:%s*(%d+)')) or 8
  local save_type = tonumber(text:match('"save_type"%s*:%s*(%d+)')) or 1
  local savestate_slot = tonumber(text:match('"savestate_slot"%s*:%s*(%d+)')) or 0
  local require_gameplay = text:match('"require_gameplay_ram"%s*:%s*(true)')
  local load_slot = text:match('"load_slot_before_record"%s*:%s*(true)')
  local room_addr = tonumber(text:match('"room"%s*:%s*(%d+)'))
  local x_addr = tonumber(text:match('"x"%s*:%s*(%d+)'))
  local lives_addr = tonumber(text:match('"lives"%s*:%s*(%d+)'))
  return done_flag, result_flag, out_fm2, variant, num_frames, probe_at, save_type, savestate_slot,
    require_gameplay == "true", load_slot == "true", room_addr, x_addr, lives_addr
end

local DONE_FLAG, RESULT_FLAG, OUT_FM2, VARIANT, NUM_RECORD_FRAMES, PROBE_AT_MF, SAVE_TYPE, SAVESTATE_SLOT,
  REQUIRE_GAMEPLAY_RAM, LOAD_SLOT_BEFORE_RECORD, ROOM_ADDR, X_ADDR, LIVES_ADDR = read_config()

local phase = "init"
local record_frames = 0
local probed = false
local finished = false
local init_checked = false
local pre_record = nil
local record_step = nil
local stop_step = nil
local MAX_EMU_FRAMES = 1200

local function ram_snapshot()
  local room = ROOM_ADDR and memory.readbyte(ROOM_ADDR) or -1
  local x_pos = X_ADDR and memory.readbyte(X_ADDR) or -1
  local lives = LIVES_ADDR and memory.readbyte(LIVES_ADDR) or -1
  local gameplay_like = (room == 0 and x_pos == 129)
  return room, x_pos, lives, gameplay_like
end

local function file_size(path)
  local f = io.open(path, "rb")
  if not f then
    return -1
  end
  local size = f:seek("end")
  f:close()
  return size or -1
end

local function is_from_savestate()
  if movie and movie.isfromsavestate then
    return movie.isfromsavestate()
  end
  return false
end

local function finish(payload)
  if finished then
    return
  end
  finished = true
  if payload then
    local rf = io.open(RESULT_FLAG, "w")
    if rf then
      rf:write(payload)
      rf:close()
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

local function fail(error_code, extra)
  extra = extra or ""
  finish(string.format('{"ok":false,"error":"%s","variant":"%s"%s}', error_code, VARIANT, extra))
end

emu.registerbefore(function()
  if phase == "recording" then
    joypad.set(1, EMPTY_INPUT)
  end
end)

emu.registerafter(function()
  if finished then
    return
  end

  local emu_frame = emu.framecount()

  if phase == "init" then
    if not init_checked and emu_frame >= 1 then
      init_checked = true
      if LOAD_SLOT_BEFORE_RECORD then
        local fceux_slot = SAVESTATE_SLOT + 1
        local ok_load, err_load = pcall(function()
          local st = savestate.create(fceux_slot)
          savestate.load(st)
        end)
        if not ok_load then
          local err_msg = tostring(err_load):gsub("\\", "\\\\"):gsub('"', '\\"')
          fail("savestate_load", string.format(',"slot":%d,"load_error":"%s"', SAVESTATE_SLOT, err_msg))
          return
        end
      end
      local room, x_pos, lives, gameplay_like = ram_snapshot()
      pre_record = string.format(
        '{"ok":%s,"emu_frame":%d,"room":%d,"x":%d,"lives":%d,"gameplay_like_ram":%s,"movie_active":%s,"load_slot":%s}',
        (not REQUIRE_GAMEPLAY_RAM or gameplay_like) and "true" or "false",
        emu_frame,
        room,
        x_pos,
        lives,
        gameplay_like and "true" or "false",
        (movie and movie.active and movie.active()) and "true" or "false",
        LOAD_SLOT_BEFORE_RECORD and "true" or "false"
      )
      if REQUIRE_GAMEPLAY_RAM and not gameplay_like then
        fail("pre_record_ram", ',"pre_record":' .. pre_record)
        return
      end
      local ok_record = movie.record(OUT_FM2, SAVE_TYPE, "wait-n6")
      local mode = movie.mode and movie.mode() or "unknown"
      local from_save = is_from_savestate()
      record_step = string.format(
        '{"ok":%s,"movie_record_return":%s,"movie_mode":"%s","is_from_savestate":%s,"save_type":%d}',
        (ok_record and mode == "record") and "true" or "false",
        ok_record and "true" or "false",
        mode,
        from_save and "true" or "false",
        SAVE_TYPE
      )
      if not ok_record or mode ~= "record" then
        fail("record_start", ',"pre_record":' .. pre_record .. ',"record":' .. record_step)
        return
      end
      phase = "recording"
    end
    return
  end

  if phase == "recording" then
    record_frames = record_frames + 1
    if record_frames >= NUM_RECORD_FRAMES then
      movie.stop()
      local fm2_size = file_size(OUT_FM2)
      stop_step = string.format(
        '{"ok":%s,"fm2_exists":%s,"fm2_size":%d,"record_frames":%d}',
        (fm2_size > 0) and "true" or "false",
        (fm2_size > 0) and "true" or "false",
        fm2_size,
        record_frames
      )
      if fm2_size <= 0 then
        fail("record_stop", ',"pre_record":' .. pre_record .. ',"record":' .. record_step .. ',"stop":' .. stop_step)
        return
      end
      local ok_play = movie.play(OUT_FM2, true)
      if not ok_play then
        fail("playback_start", ',"pre_record":' .. pre_record .. ',"record":' .. record_step .. ',"stop":' .. stop_step)
        return
      end
      phase = "playing"
    end
    return
  end

  if phase == "playing" then
    local movie_active = movie and movie.active and movie.active() or false
    local mf = 0
    if movie_active and movie.framecount then
      mf = movie.framecount()
    end

    if movie_active and mf >= PROBE_AT_MF and not probed then
      probed = true
      local room, x_pos, lives, gameplay_like = ram_snapshot()
      local playback_probe = string.format(
        '{"ok":%s,"mf":%d,"emu_frame":%d,"room":%d,"x":%d,"lives":%d,"gameplay_like_ram":%s,"movie_active":true}',
        gameplay_like and "true" or "false",
        mf,
        emu_frame,
        room,
        x_pos,
        lives,
        gameplay_like and "true" or "false"
      )
      local pass = REQUIRE_GAMEPLAY_RAM and gameplay_like or true
      finish(string.format(
        '{"ok":%s,"variant":"%s","save_type":%d,"pre_record":%s,"record":%s,"stop":%s,"playback_probe":%s}',
        pass and "true" or "false",
        VARIANT,
        SAVE_TYPE,
        pre_record,
        record_step,
        stop_step,
        playback_probe
      ))
      return
    end

    if movie and movie.mode and movie.mode() == "finished" then
      local room, x_pos, lives, gameplay_like = ram_snapshot()
      fail(
        "movie_finished_early",
        string.format(
          ',"mf":%d,"emu_frame":%d,"room":%d,"x":%d,"gameplay_like_ram":%s',
          mf,
          emu_frame,
          room,
          x_pos,
          gameplay_like and "true" or "false"
        )
      )
      return
    end
  end

  if emu_frame >= MAX_EMU_FRAMES then
    fail("emu_frame_cap", string.format(',"emu_frame":%d,"phase":"%s"', emu_frame, phase))
  end
end)
