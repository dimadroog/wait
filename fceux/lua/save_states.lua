-- Save states на заданных кадрах FM2 (Phase 0)
-- FCEUX: savestate.create(1..10) → слоты UI 0..9; create(1) = .fc0, create(2) = .fc1, …
-- Конфиг: WAIT_FCEUX_LUA_CONFIG → { states_dir, done_flag, save_frames: [{frame, file, slot}] }

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
  local states_dir = text:match('"states_dir"%s*:%s*"([^"]+)"')
  local done_flag = text:match('"done_flag"%s*:%s*"([^"]+)"')
  if not states_dir or not done_flag then
    error("Invalid config.json")
  end
  local frames = {}
  for frame_s, file, slot_s in text:gmatch(
    '"frame"%s*:%s*(%d+).-"file"%s*:%s*"([^"]+)".-"slot"%s*:%s*(%d+)'
  ) do
    frames[#frames + 1] = {
      frame = tonumber(frame_s),
      file = file,
      slot = tonumber(slot_s),
    }
  end
  return states_dir, done_flag, frames
end

local STATES_DIR, DONE_FLAG, SAVE_PLAN = read_config()
local finished = false
local saved = {}
local state_handles = {}

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

local function save_at(plan)
  local fceux_slot = plan.slot + 1
  local st = state_handles[plan.slot]
  if not st then
    st = savestate.create(fceux_slot)
    state_handles[plan.slot] = st
  end
  savestate.save(st)
  savestate.persist(st)
  saved[plan.frame] = plan.file
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
  for _, plan in ipairs(SAVE_PLAN) do
    if frame >= plan.frame and not saved[plan.frame] then
      local ok, err = pcall(save_at, plan)
      if not ok then
        error("save_states: frame " .. frame .. ": " .. tostring(err))
      end
    end
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
  gui.popup("save_states: FM2 not loaded.", "ok")
  finish()
end
