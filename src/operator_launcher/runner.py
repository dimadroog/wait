"""Subprocess runner: фазы preflight→main, stop дерева процессов, FCEUX cleanup."""
from __future__ import annotations

import os
import queue
import signal
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import IO, TextIO

from project_paths import repo_root


def _kill_process_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            cwd=str(repo_root()),
            capture_output=True,
            check=False,
        )
    else:
        proc.kill()


def _cleanup_fceux_orphans() -> None:
    try:
        from train.env_factory import kill_orphan_fceux_bridge

        kill_orphan_fceux_bridge()
    except Exception:
        pass


class ProcessRunner:
    """Один сеанс: одна или несколько фаз (preflight → main); stdout в callback."""

    def __init__(self, on_line: Callable[[str], None]) -> None:
        self._on_line = on_line
        self._proc: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._phases: list[list[str]] = []
        self._phase_index = 0
        self._session_active = False
        self._last_exit_code: int | None = None
        self._use_process_group = False
        self._tee_file: TextIO | None = None

    @property
    def running(self) -> bool:
        if self._session_active:
            return True
        return self._proc is not None and self._proc.poll() is None

    @property
    def last_exit_code(self) -> int | None:
        return self._last_exit_code

    def start(
        self,
        argv: list[str] | list[list[str]],
        *,
        tee_path: Path | None = None,
    ) -> None:
        if self.running:
            raise RuntimeError("Процесс уже запущен")
        if self._proc is not None:
            self.wait_done()
        self._close_tee()
        if argv and isinstance(argv[0], list):
            self._phases = [list(phase) for phase in argv]  # type: ignore[arg-type]
        else:
            self._phases = [list(argv)]  # type: ignore[arg-type]
        self._phase_index = 0
        self._session_active = True
        self._last_exit_code = None
        if tee_path is not None:
            tee_path.parent.mkdir(parents=True, exist_ok=True)
            self._tee_file = tee_path.open("w", encoding="utf-8", errors="replace", newline="")
        self._start_current_phase()

    def pump(self) -> None:
        while True:
            try:
                line = self._queue.get_nowait()
            except queue.Empty:
                break
            if line is None:
                self._on_reader_finished()
                break
            self._emit_line(line)

    def stop(
        self,
        *,
        graceful: bool = True,
        kill_after_s: float = 12.0,
        cleanup_fceux: bool = True,
    ) -> None:
        self._session_active = False
        proc = self._proc
        if proc is None or proc.poll() is not None:
            if cleanup_fceux:
                _cleanup_fceux_orphans()
            return
        if graceful and self._use_process_group:
            try:
                if sys.platform == "win32":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.send_signal(signal.SIGINT)
            except (ProcessLookupError, OSError):
                pass
            try:
                proc.wait(timeout=kill_after_s)
                if cleanup_fceux:
                    _cleanup_fceux_orphans()
                return
            except subprocess.TimeoutExpired:
                pass
        _kill_process_tree(proc)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        if cleanup_fceux:
            _cleanup_fceux_orphans()

    def wait_done(self) -> int | None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.wait()
        if self._reader is not None:
            self._reader.join(timeout=2)
        self._drain_queue()
        code = self._last_exit_code
        if proc is not None and proc.poll() is not None and code is None:
            code = proc.returncode
            self._last_exit_code = code
        self._proc = None
        self._reader = None
        self._phases = []
        self._phase_index = 0
        self._session_active = False
        self._close_tee()
        return code

    def _start_current_phase(self) -> None:
        if self._phase_index >= len(self._phases):
            self._session_active = False
            return
        argv = self._phases[self._phase_index]
        self._phase_index += 1
        cwd = repo_root()
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        creationflags = 0
        self._use_process_group = False
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            self._use_process_group = True
        self._proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()

    def _on_reader_finished(self) -> None:
        proc = self._proc
        if proc is None:
            self._session_active = False
            return
        code = proc.wait()
        self._last_exit_code = code
        if not self._session_active:
            return
        if code != 0:
            self._session_active = False
            return
        if self._phase_index < len(self._phases):
            self._emit_line(f"\n--- фаза {self._phase_index + 1}/{len(self._phases)} ---\n")
            self._start_current_phase()
        else:
            self._session_active = False

    def _emit_line(self, line: str) -> None:
        tee: IO[str] | None = self._tee_file
        if tee is not None:
            try:
                tee.write(line)
                tee.flush()
            except OSError:
                pass
        self._on_line(line)

    def _close_tee(self) -> None:
        tee = self._tee_file
        self._tee_file = None
        if tee is None:
            return
        try:
            tee.close()
        except OSError:
            pass

    def _read_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            self._queue.put(None)
            return
        try:
            for line in proc.stdout:
                self._queue.put(line)
        finally:
            self._queue.put(None)

    def _drain_queue(self) -> None:
        while True:
            try:
                line = self._queue.get_nowait()
            except queue.Empty:
                break
            if line is None:
                continue
            self._emit_line(line)
