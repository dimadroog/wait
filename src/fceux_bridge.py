"""Python ↔ FCEUX IPC."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from json import JSONDecodeError
from pathlib import Path

import numpy as np

from fm2_export import default_fm2_template
from project_paths import parse_fm2_rom_basename, repo_root, resolve_fceux_binary, resolve_rom
from ram_map_load import load_ram_addresses

GD_HEADER_BYTES = 11
NES_WIDTH = 256
NES_HEIGHT = 240

DEFAULT_FRAME_SKIP = 4
DEFAULT_TIMEOUT = 30.0
STARTUP_STAGGER_SEC = 5.0
STARTUP_TIMEOUT_BASE = 45.0
STARTUP_TIMEOUT_PER_RANK = 15.0
POLL_INTERVAL = 0.002
IPC_RETRIES = 100
LOAD_LOCK_TIMEOUT_SEC = 90.0
LOAD_LOCK_HOLD_MAX_SEC = 30.0
LOAD_LOCK_STALE_SEC = 120.0


class FceuxBridgeError(RuntimeError):
    pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        synchronize = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _try_release_stale_load_lock(lock_path: Path) -> None:
    if not lock_path.exists():
        return
    if lock_path.is_dir():
        try:
            lock_path.rmdir()
        except OSError:
            shutil.rmtree(lock_path, ignore_errors=True)
        return
    if not lock_path.is_file():
        return
    try:
        raw = lock_path.read_text(encoding="utf-8").strip()
        parts = raw.split(",", 1)
        pid = int(parts[0]) if parts and parts[0] else -1
        ts = float(parts[1]) if len(parts) > 1 else lock_path.stat().st_mtime
        age = time.time() - ts
        if age > LOAD_LOCK_HOLD_MAX_SEC or age > LOAD_LOCK_STALE_SEC or not _pid_alive(pid):
            lock_path.unlink(missing_ok=True)
    except (OSError, ValueError):
        try:
            if time.time() - lock_path.stat().st_mtime > LOAD_LOCK_STALE_SEC:
                lock_path.unlink(missing_ok=True)
        except OSError:
            pass


@contextmanager
def bridge_load_lock():
    """Сериализует gdscreenshot на hot reset между параллельными FCEUX (один IPC LOAD_OBS)."""
    lock_path = repo_root() / "tmp" / "bridge" / ".load_lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + LOAD_LOCK_TIMEOUT_SEC
    fd: int | None = None
    while time.time() < deadline:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()},{time.time()}".encode())
            break
        except (FileExistsError, PermissionError):
            _try_release_stale_load_lock(lock_path)
            time.sleep(POLL_INTERVAL)
    else:
        raise FceuxBridgeError(f"load lock timeout ({LOAD_LOCK_TIMEOUT_SEC:.0f}s)")
    try:
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        _safe_unlink(lock_path)


def _safe_unlink(path: Path) -> None:
    """Best-effort удаление IPC-файла; на Windows unlink может быть занят — не fatal."""
    if not path.exists():
        return
    for _ in range(IPC_RETRIES * 10):
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except (PermissionError, OSError):
            time.sleep(POLL_INTERVAL)
    # seq-mismatch защищает от stale response; краш train из-за unlink не нужен


def _read_file_retry(path: Path, *, binary: bool = True, retries: int = IPC_RETRIES) -> bytes | str:
    """Чтение IPC-файла с retry на Windows file locking."""
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            if binary:
                return path.read_bytes()
            return path.read_text(encoding="utf-8")
        except (PermissionError, OSError, JSONDecodeError) as e:
            last_err = e
            time.sleep(POLL_INTERVAL)
    if last_err:
        raise last_err
    raise OSError(f"IPC read failed: {path}")


def _write_ipc_atomic(path: Path, content: bytes, *, retries: int = IPC_RETRIES) -> None:
    """Запись через .tmp + replace; retry при PermissionError на Windows."""
    tmp = path.with_name(path.name + ".tmp")
    _safe_unlink(tmp)
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            tmp.write_bytes(content)
            try:
                tmp.replace(path)
            except (PermissionError, OSError):
                _safe_unlink(path)
                tmp.replace(path)
            return
        except (PermissionError, OSError) as e:
            last_err = e
            _safe_unlink(tmp)
            time.sleep(POLL_INTERVAL)
    if last_err:
        raise last_err
    raise OSError(f"IPC write failed: {path}")


def decode_raw_obs(path: Path, width: int = 84, height: int = 84) -> np.ndarray:
    """Raw grayscale width×height из obs_*.raw."""
    raw = path.read_bytes()
    if len(raw) != width * height:
        raise FceuxBridgeError(f"Bad raw obs size: {len(raw)} != {width}x{height}")
    return np.frombuffer(raw, dtype=np.uint8).reshape(height, width)


def decode_gd_screenshot(path: Path, width: int = 84, height: int = 84) -> np.ndarray:
    """GD-скриншот FCEUX (gui.gdscreenshot) → grayscale width×height."""
    import cv2

    gd_bytes = path.read_bytes()
    expected = GD_HEADER_BYTES + NES_WIDTH * NES_HEIGHT * 4
    if len(gd_bytes) != expected:
        raise FceuxBridgeError(f"Bad GD obs size {len(gd_bytes)}, expected {expected}")
    rgba = np.frombuffer(gd_bytes[GD_HEADER_BYTES:], dtype=np.uint8).reshape(NES_HEIGHT, NES_WIDTH, 4)
    gray = (0.299 * rgba[:, :, 0] + 0.587 * rgba[:, :, 1] + 0.114 * rgba[:, :, 2]).astype(np.uint8)
    return cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)


class FceuxBridge:
    """Управляет долгоживущим FCEUX + bridge.lua через файлы в tmp/bridge/."""

    def __init__(
        self,
        mission: Path,
        game_id: str,
        *,
        frame_skip: int = DEFAULT_FRAME_SKIP,
        session_id: str = "default",
        show_window: bool = False,
        fm2_template: Path | None = None,
        no_focus: bool | None = None,
        obs_format: str | None = None,
    ) -> None:
        self.mission = mission.resolve()
        self.game_id = game_id
        self.frame_skip = frame_skip
        self.session_id = session_id
        self.show_window = show_window
        self.fm2_template = fm2_template
        if no_focus is None:
            from fceux_launch import fceux_no_focus_enabled

            no_focus = fceux_no_focus_enabled() and not show_window
        self.no_focus = no_focus
        self.obs_format = self._resolve_obs_format(obs_format)
        self.session_root = repo_root() / "tmp" / "bridge" / session_id
        self.staging = self.session_root / "staging"
        self.ipc_dir = self.session_root / "ipc"
        self._seq = 0
        self._proc: subprocess.Popen | None = None
        self._rom_base: str | None = None
        self._ram_addrs = load_ram_addresses(self.mission)
        self._cached_states: set[str] = set()

    def _resolve_obs_format(self, obs_format: str | None) -> str:
        if obs_format:
            return obs_format.strip().lower()
        from fceux_launch import fceux_obs_format

        return fceux_obs_format(show_window=self.show_window)

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _resolve_state_path(self, rel_path: str | Path) -> tuple[Path, str]:
        src = Path(rel_path)
        if not src.is_absolute():
            src = self.mission / src
        if not src.is_file():
            raise FileNotFoundError(f"Save state not found: {src}")
        return src, src.name

    def _stage_state_file(self, src: Path) -> str:
        self.staging.mkdir(parents=True, exist_ok=True)
        dest = self.staging / src.name
        if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
            shutil.copy2(src, dest)
        return src.name

    def _session_rank(self) -> int | None:
        sid = self.session_id
        for prefix in ("train_", "record_demos_"):
            if sid.startswith(prefix):
                try:
                    return int(sid.rsplit("_", 1)[-1])
                except ValueError:
                    return None
        return None

    def _startup_stagger(self) -> None:
        """Windows: разнести старт нескольких FCEUX (SubprocVecEnv / parallel record)."""
        rank = self._session_rank()
        if rank is not None and sys.platform == "win32":
            time.sleep(rank * STARTUP_STAGGER_SEC)

    def _startup_timeout(self, timeout: float) -> float:
        rank = self._session_rank()
        if rank is None:
            return timeout
        return max(timeout, STARTUP_TIMEOUT_BASE + rank * STARTUP_TIMEOUT_PER_RANK)

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _resolve_fm2_template(self) -> Path:
        if self.fm2_template and self.fm2_template.is_file():
            return self.fm2_template
        portable = default_fm2_template(self.game_id)
        if portable.is_file():
            return portable
        ref = next(self.mission.glob("reference/*.fm2"), None)
        if ref and ref.is_file():
            return ref
        raise FileNotFoundError(
            f"No FM2 template for ROM staging (game={self.game_id}). "
            "Set fm2_template or add fceux/portable/movies/*.fm2"
        )

    def _stage_rom(self, rom: Path) -> Path:
        self.staging.mkdir(parents=True, exist_ok=True)
        self._rom_base = parse_fm2_rom_basename(self._resolve_fm2_template())
        staged_rom = self.staging / self._rom_base
        for name in (self._rom_base, self._rom_base + ".nes", rom.name):
            shutil.copy2(rom, self.staging / name)
        return staged_rom

    def _write_config(self) -> Path:
        self.ipc_dir.mkdir(parents=True, exist_ok=True)
        lua_config_path = self.session_root / "config.json"
        ram_hex = {k: f"0x{v:04X}" for k, v in self._ram_addrs.items()}
        lua_config_path.write_text(
            json.dumps(
                {
                    "ipc_dir": self.ipc_dir.resolve().as_posix(),
                    "frame_skip": self.frame_skip,
                    "ram_addrs": ram_hex,
                    "no_focus": self.no_focus,
                    "obs_format": self.obs_format,
                }
            ),
            encoding="utf-8",
        )
        return lua_config_path

    def _clear_ipc(self) -> None:
        self.ipc_dir.mkdir(parents=True, exist_ok=True)
        for name in ("request.json", "response.json", "ready.flag"):
            _safe_unlink(self.ipc_dir / name)
        for obs in list(self.ipc_dir.glob("obs_*.raw")) + list(self.ipc_dir.glob("obs_*.gd")):
            _safe_unlink(obs)

    def _wait_ready(self, timeout: float) -> None:
        ready = self.ipc_dir / "ready.flag"
        deadline = time.time() + timeout
        while time.time() < deadline:
            if ready.is_file():
                return
            if self._proc and self._proc.poll() is not None:
                raise FceuxBridgeError(f"FCEUX exited before ready (code {self._proc.returncode})")
            time.sleep(POLL_INTERVAL)
        raise FceuxBridgeError(f"Bridge ready timeout ({timeout}s)")

    def start(self, *, load_state: str | Path | None = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        """Запуск FCEUX. load_state — путь относительно mission/ (напр. states/cp1.fc0)."""
        if self._proc and self._proc.poll() is None:
            self.close()

        self._startup_stagger()

        if self.session_root.exists():
            shutil.rmtree(self.session_root, ignore_errors=True)
        self.staging.mkdir(parents=True, exist_ok=True)

        rom = resolve_rom(self.game_id)
        staged_rom = self._stage_rom(rom)
        config = self._write_config()
        self._clear_ipc()

        fceux = resolve_fceux_binary()
        lua = repo_root() / "fceux" / "lua" / "bridge.lua"
        env = os.environ.copy()
        env["WAIT_FCEUX_BRIDGE_CONFIG"] = str(config.resolve())

        cmd = [
            str(fceux),
            "-noicon",
            "1",
            "-lua",
            str(lua.resolve()),
        ]
        from fceux_launch import fceux_no_focus_cmdline, fceux_sound_off, win32_popen_kwargs

        if self.no_focus:
            cmd.extend(fceux_no_focus_cmdline())

        staged_state: Path | None = None
        if load_state is not None:
            src = Path(load_state)
            if not src.is_absolute():
                src = self.mission / src
            if not src.is_file():
                raise FileNotFoundError(f"Save state not found: {src}")
            staged_state = self.staging / src.name
            shutil.copy2(src, staged_state)
            cmd.extend(["-loadstate", src.name])

        cmd.append(str(staged_rom))

        startup_timeout = self._startup_timeout(timeout)
        popen_kwargs = win32_popen_kwargs(show_window=self.show_window, no_focus=self.no_focus)

        with fceux_sound_off(fceux.parent):
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(self.staging),
                env=env,
                **popen_kwargs,
            )
            self._wait_ready(startup_timeout)
        self.request("PING", timeout=startup_timeout)
        if load_state is not None:
            _, key = self._resolve_state_path(load_state)
            self.cache_state(key)
            self._cached_states.add(key)

    def _force_close_proc(self) -> None:
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        self._cached_states.clear()

    def close(self) -> None:
        if self._proc is None:
            return
        if self._proc.poll() is None:
            try:
                self.request("QUIT", timeout=5.0)
            except FceuxBridgeError:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
        elif self._proc.poll() is not None and self._proc.returncode not in (0, None):
            pass
        self._proc = None
        self._cached_states.clear()

    def __enter__(self) -> FceuxBridge:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def request(self, cmd: str, arg: str = "", *, timeout: float = DEFAULT_TIMEOUT) -> dict:
        if self._proc is None or self._proc.poll() is not None:
            raise FceuxBridgeError("FCEUX bridge is not running")
        seq = self._next_seq()
        req_path = self.ipc_dir / "request.json"
        resp_path = self.ipc_dir / "response.json"
        payload = json.dumps({"seq": seq, "cmd": cmd, "arg": arg}).encode("utf-8")

        _safe_unlink(resp_path)

        deadline = time.time() + timeout
        request_sent = False
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise FceuxBridgeError(f"FCEUX exited during {cmd} (code {self._proc.returncode})")

            if not request_sent:
                try:
                    _write_ipc_atomic(req_path, payload, retries=5)
                    request_sent = True
                except (PermissionError, OSError):
                    time.sleep(POLL_INTERVAL)
                    continue

            if not resp_path.is_file():
                time.sleep(POLL_INTERVAL)
                continue

            try:
                text = _read_file_retry(resp_path, binary=False)
                response = json.loads(text)
            except (JSONDecodeError, ValueError, PermissionError, OSError):
                time.sleep(POLL_INTERVAL)
                continue

            if response.get("seq") != seq:
                stale = response.get("seq")
                if isinstance(stale, int) and stale < seq:
                    _safe_unlink(resp_path)
                time.sleep(POLL_INTERVAL)
                continue

            if not response.get("ok", False):
                raise FceuxBridgeError(response.get("error", f"{cmd} failed"))
            _safe_unlink(resp_path)
            return response

        raise FceuxBridgeError(f"IPC timeout for {cmd} ({timeout}s)")

    def ping(self) -> dict:
        return self.request("PING")

    def step(self, action: str = "") -> dict:
        return self.request("STEP", action, timeout=max(DEFAULT_TIMEOUT, 15.0))

    def decode_obs_from_response(self, bridge_response: dict) -> np.ndarray:
        """Obs из STEP (obs_file) или отдельный GET_OBS."""
        w, h = int(bridge_response.get("w", 84)), int(bridge_response.get("h", 84))
        if not bridge_response.get("obs_file"):
            raise FceuxBridgeError("Response missing obs_file")
        path = Path(str(bridge_response["obs_file"]))
        if bridge_response.get("format") == "gd":
            last_err: Exception | None = None
            for _ in range(IPC_RETRIES):
                try:
                    if path.is_file() and path.stat().st_size > 0:
                        obs = decode_gd_screenshot(path, w, h)
                        _safe_unlink(path)
                        return obs
                except (FceuxBridgeError, PermissionError, OSError) as e:
                    last_err = e
                time.sleep(POLL_INTERVAL)
            if last_err:
                raise last_err
            raise FceuxBridgeError(f"Obs file not ready: {path}")
        if bridge_response.get("format") == "raw":
            last_err = None
            for _ in range(IPC_RETRIES):
                try:
                    if path.is_file() and path.stat().st_size >= w * h:
                        obs = decode_raw_obs(path, w, h)
                        _safe_unlink(path)
                        return obs
                except (FceuxBridgeError, PermissionError, OSError) as e:
                    last_err = e
                time.sleep(POLL_INTERVAL)
            if last_err:
                raise last_err
            raise FceuxBridgeError(f"Obs file not ready: {path}")
        last_err = None
        for _ in range(IPC_RETRIES):
            try:
                if path.is_file() and path.stat().st_size >= w * h:
                    raw = path.read_bytes()
                    if len(raw) != w * h:
                        raise FceuxBridgeError(f"Bad obs size: {len(raw)} != {w}x{h}")
                    _safe_unlink(path)
                    return np.frombuffer(raw, dtype=np.uint8).reshape(h, w)
            except (FceuxBridgeError, PermissionError, OSError) as e:
                last_err = e
            time.sleep(POLL_INTERVAL)
        if last_err:
            raise last_err
        raise FceuxBridgeError(f"Obs file not ready: {path}")

    def get_ram(self) -> dict:
        return self.request("GET_RAM")

    def get_obs(self) -> np.ndarray:
        bridge_response = self.request("GET_OBS", timeout=max(DEFAULT_TIMEOUT, 15.0))
        return self.decode_obs_from_response(bridge_response)

    def turbo(self, on: bool = True) -> dict:
        return self.request("TURBO", "on" if on else "off")

    def cache_state(self, key: str) -> None:
        """Сохранить текущее состояние эмулятора в Lua-кэш (после cold start)."""
        self.request("CACHE", key)

    def load_obs(self, key: str, *, timeout: float = DEFAULT_TIMEOUT) -> dict:
        """Hot reset: LOAD из кэша + obs за один IPC round-trip."""
        return self.request("LOAD_OBS", key, timeout=max(timeout, 15.0))

    def reset_to_state(self, rel_path: str | Path, *, timeout: float = DEFAULT_TIMEOUT) -> dict:
        """Hot LOAD из кэша или cold start; возвращает RAM + obs_file."""
        src, key = self._resolve_state_path(rel_path)
        self._stage_state_file(src)

        if self.is_running() and key in self._cached_states:
            try:
                with bridge_load_lock():
                    return self.load_obs(key, timeout=timeout)
            except FceuxBridgeError:
                self._force_close_proc()

        if self.is_running():
            self.close()

        self.start(load_state=rel_path, timeout=timeout)
        with bridge_load_lock():
            return self.load_obs(key, timeout=timeout)

    def save_state(self) -> dict:
        """Сохраняет в слот FCEUX (fceux/portable/fcs/)."""
        return self.request("SAVE")

    def load_state(self, rel_path: str | Path, *, timeout: float = DEFAULT_TIMEOUT) -> dict:
        """Alias: hot reset через savestate.load (см. reset_to_state)."""
        return self.reset_to_state(rel_path, timeout=timeout)
