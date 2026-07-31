-- BC demos: FM2 playmovie → obs samples (112×112 raw grayscale) + samples.jsonl
-- Конфиг: WAIT_DEMOS_BC_CONFIG → JSON (ipc_dir, samples_jsonl, done_flag, frame_skip, obs_w, obs_h, segments[])

local NES_W, NES_H = 256, 240

local function read_config()
  local cfg_path = os.getenv("WAIT_DEMOS_BC_CONFIG")
  if not cfg_path then
    error("WAIT_DEMOS_BC_CONFIG not set")
  end
  local f = io.open(cfg_path, "r")
  if not f then
    error("Cannot open config: " .. cfg_path)
  end
  local text = f:read("*a")
  f:close()

  local ipc_dir = text:match('"ipc_dir"%s*:%s*"([^"]+)"')
  local samples_jsonl = text:match('"samples_jsonl"%s*:%s*"([^"]+)"')
  local done_flag = text:match('"done_flag"%s*:%s*"([^"]+)"')
  local frame_skip = tonumber(text:match('"frame_skip"%s*:%s*(%d+)')) or 4
  local obs_w = tonumber(text:match('"obs_w"%s*:%s*(%d+)')) or 112
  local obs_h = tonumber(text:match('"obs_h"%s*:%s*(%d+)')) or 112
  if not ipc_dir or not samples_jsonl or not done_flag then
    error("Invalid demos_for_bc config.json")
  end

  local segments = {}
  for id, start_s, end_s in text:gmatch(
    '"id"%s*:%s*"([^"]+)".-"frame_start"%s*:%s*(%d+).-"frame_end"%s*:%s*(%d+)'
  ) do
    segments[#segments + 1] = {
      id = id,
      frame_start = tonumber(start_s),
      frame_end = tonumber(end_s),
    }
  end

  return ipc_dir, samples_jsonl, done_flag, frame_skip, segments, obs_w, obs_h
end

local IPC_DIR, SAMPLES_JSONL, DONE_FLAG, FRAME_SKIP, SEGMENTS, OBS_W, OBS_H = read_config()
local samples_out = io.open(SAMPLES_JSONL, "w")
if not samples_out then
  error("Cannot open samples jsonl: " .. SAMPLES_JSONL)
end

local finished = false
local sample_count = 0

local function gd_to_raw_gray(shot, w, h)
  local parts = {}
  local idx = 1
  local sx = NES_W / w
  local sy = NES_H / h
  for y = 0, h - 1 do
    local src_y = math.floor((y + 0.5) * sy)
    local row_base = src_y * NES_W * 4
    for x = 0, w - 1 do
      local src_x = math.floor((x + 0.5) * sx)
      local p = row_base + src_x * 4
      local r = shot:byte(p)
      local g = shot:byte(p + 1)
      local b = shot:byte(p + 2)
      parts[idx] = string.char(math.floor(0.299 * r + 0.587 * g + 0.114 * b))
      idx = idx + 1
    end
  end
  return table.concat(parts)
end

local function capture_gray(frame)
  local path = IPC_DIR .. "/obs_" .. string.format("%06d", frame) .. ".raw"
  local shot = gui.gdscreenshot()
  local f = io.open(path, "wb")
  if not f then
    error("Cannot open obs file: " .. path)
  end
  f:write(gd_to_raw_gray(shot, OBS_W, OBS_H))
  f:close()
  return path
end

local function should_sample(frame)
  for _, seg in ipairs(SEGMENTS) do
    if frame >= seg.frame_start and frame <= seg.frame_end then
      local offset = frame - seg.frame_start
      if offset % FRAME_SKIP == 0 then
        return true
      end
    end
  end
  return false
end

local function finish()
  if finished then
    return
  end
  finished = true
  samples_out:close()
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
  if should_sample(frame) then
    local path = capture_gray(frame)
    sample_count = sample_count + 1
    samples_out:write(string.format('{"frame":%d,"obs":"%s"}\n', frame, path))
  end

  local mlen = movie.length()
  if mode == "finished" or (mlen and frame >= mlen) then
    finish()
  end
end)

if movie.active() then
  FCEU.speedmode("nothrottle")
  FCEU.setrenderplanes(true, true)
  movie.playbeginning()
else
  gui.popup("demos_for_bc: FM2 not loaded. Check -playmovie and ROM path.", "ok")
  finish()
end
