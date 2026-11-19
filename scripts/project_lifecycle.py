"""Own the backend and desktop companion for one visible project session.

The launcher prepares dependencies, then blocks in this stdlib supervisor.
Windows Job Object membership is inherited by all descendants; its handle is
owned only by this process. Closing the terminal or forcibly ending this owner
therefore cannot leave its backend, model worker or Electron processes orphaned.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Callable
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener
import webbrowser


SCHEMA = "finpilot.project-lifecycle.v1"
HEARTBEAT_INTERVAL = 0.75
HEARTBEAT_MAX_AGE = 8.0
_JOB_HANDLES: list[int] = []


@dataclass(frozen=True)
class Config:
    project_root: Path
    python: Path
    runtime_dir: Path
    electron: Path | None = None
    desktop_dir: Path | None = None
    profile_dir: Path | None = None
    electron_app: Path | None = None
    port: int = 0
    no_browser: bool = False
    offline: bool = False
    no_desktop: bool = False

    @property
    def state_file(self) -> Path:
        return self.runtime_dir / "lifecycle.json"


def same_path(left, right) -> bool:
    try:
        return Path(left).resolve() == Path(right).resolve()
    except (OSError, ValueError, TypeError):
        return False


def process_identity(pid: int) -> str | None:
    """Return an OS creation identity, never merely the existence of a PID."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4))
        kernel.GetProcessTimes.restype = wintypes.BOOL
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            exit_code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)) or exit_code.value != 259:
                return None
            created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
            if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel_time), ctypes.byref(user_time)):
                return None
            # FILETIME is stable across all observers and contains no secrets.
            return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    try:
        # Linux test runners can use the same ownership contract.
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def is_process_identity(pid: int, identity: str) -> bool:
    return bool(identity) and process_identity(pid) == str(identity)


class OwnedProcessJob:
    """Strict Windows child-tree lifetime; do not close while owner is alive."""
    def install(self):
        if os.name != "nt":
            return self
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)

        class BasicLimits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                        ("flags", wintypes.DWORD), ("min_working", ctypes.c_size_t),
                        ("max_working", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                        ("scheduling", wintypes.DWORD)]

        class IOCounts(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io", IOCounts), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

        kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.SetHandleInformation.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD)
        kernel.SetHandleInformation.restype = wintypes.BOOL
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "Could not create the project lifetime Job Object")
        try:
            limits = ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise OSError(ctypes.get_last_error(), "Could not configure child-tree cleanup")
            if not kernel.SetHandleInformation(handle, 1, 0):
                raise OSError(ctypes.get_last_error(), "Could not isolate the Job Object handle")
            if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
                raise OSError(ctypes.get_last_error(), "Cannot safely own the project process tree in this Windows session")
        except BaseException:
            kernel.CloseHandle(handle)
            raise
        # No child inherits this handle. The OS closes it when THIS Python
        # process exits, including console-close/TerminateProcess. Closing it
        # manually would terminate this owner before normal cleanup completed.
        _JOB_HANDLES.append(handle)
        self.handle = handle
        return self

    def contains(self, pid: int) -> bool:
        if os.name != "nt":
            return True
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.IsProcessInJob.argtypes = (wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL))
        kernel.IsProcessInJob.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            member = wintypes.BOOL()
            return bool(kernel.IsProcessInJob(handle, self.handle, ctypes.byref(member)) and member.value)
        finally:
            kernel.CloseHandle(handle)


class SessionLock:
    def __init__(self, path: Path):
        self.path, self.stream = path, None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("a+b")
        try:
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            stream.close()
            return False
        self.stream = stream
        return True

    def close(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None


def atomic_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + str(os.getpid()) + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    # Desktop may briefly hold the old file open during a status read.
    for attempt in range(10):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.02)


def read_owned_state(config: Config) -> dict | None:
    try:
        if config.state_file.stat().st_size > 65536:
            return None
        value = json.loads(config.state_file.read_text(encoding="utf-8-sig"))
        if (not isinstance(value, dict) or value.get("schema") != SCHEMA
                or not same_path(value.get("project_root"), config.project_root)
                or not re.fullmatch(r"[0-9a-f]{32}", value.get("run_token", ""))
                or not is_process_identity(value.get("owner_pid"), value.get("owner_started_at"))):
            return None
        return value
    except (OSError, ValueError, TypeError):
        return None


def read_active_state(config: Config) -> dict | None:
    state = read_owned_state(config)
    if state is None or state.get("status") not in {"starting", "ready"}:
        return None
    try:
        if not 0 <= time.time() - float(state["heartbeat_at"]) <= HEARTBEAT_MAX_AGE:
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return state


def request_stop(config: Config, timeout: float = 15) -> bool:
    state = read_owned_state(config)
    if state is None or state.get("status") == "stopped":
        print("No managed project session is running.", flush=True)
        return True
    request = config.runtime_dir / f"stop-{state['run_token']}.request"
    request.write_text(state["run_token"], encoding="ascii")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_process_identity(state["owner_pid"], state["owner_started_at"]):
            print("Project backend and companion stopped.", flush=True)
            return True
        time.sleep(0.1)
    print("The project is still shutting down. Its ownership record was retained.", file=sys.stderr, flush=True)
    return False


def consume_companion_request(path: Path, run_token: str) -> bool:
    """A request contains only this run's nonce, never a program or arguments."""
    try:
        if path.stat().st_size > 128:
            return False
        return path.read_text(encoding="ascii") == run_token
    except (OSError, UnicodeError):
        return False
    finally:
        path.unlink(missing_ok=True)


def request_companion(config: Config, state: dict, *, timeout: float = 28) -> bool:
    previous = state.get("companion_request_seq", 0)
    request = config.runtime_dir / f"companion-{state['run_token']}.request"
    temporary = request.with_name(request.name + f".{os.getpid()}.tmp")
    try:
        temporary.write_text(state["run_token"], encoding="ascii")
        # The owner must never consume an empty file between open and write.
        for attempt in range(10):
            try:
                temporary.replace(request)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.02)
    finally:
        temporary.unlink(missing_ok=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = read_active_state(config)
        if current is None or current.get("run_token") != state["run_token"]:
            break
        if current.get("companion_request_seq", 0) > previous:
            if current.get("pet_ready") and not current.get("companion_request_error"):
                return True
            print("The companion could not reopen. Inspect the original launch window and runtime log; the backend is still running.", file=sys.stderr, flush=True)
            return False
        time.sleep(0.1)
    print("The existing project did not acknowledge the companion request. Keep its original launch window open.", file=sys.stderr, flush=True)
    return False


def choose_port(requested: int) -> int:
    if requested and not 1024 <= requested <= 65535:
        raise ValueError("Choose a port between 1024 and 65535")
    for port in (range(8000, 8011) if requested == 0 else (requested,)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise OSError("The requested port(s) are occupied. No unrelated service was stopped.")


def backend_command_for(config: Config, port: int) -> list[str]:
    return [str(config.python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
            "--port", str(port), "--timeout-graceful-shutdown", "5"]


def pet_command_for(config: Config, base_url: str, state: dict) -> list[str]:
    args = [str(config.electron)]
    app = config.electron_app
    if app is None and config.electron and config.electron.name.lower() == "electron.exe":
        app = config.desktop_dir
    if app is not None:
        args.append(str(app))
    args.extend([f"--base-url={base_url}", f"--pet-data-dir={config.profile_dir or config.runtime_dir / 'pet-profile'}",
                 f"--owner-pid={state['owner_pid']}", f"--owner-start-time={state['owner_started_at']}",
                 f"--lifecycle-file={config.state_file}", f"--run-token={state['run_token']}"])
    return args


def healthy_backend(base_url: str, run_token: str) -> bool:
    try:
        # Never send loopback health through a configured external proxy.
        with build_opener(ProxyHandler({})).open(Request(base_url + "/api/health"), timeout=0.6) as response:
            body = response.read(65536)
            value = json.loads(body)
            return (response.status == 200 and isinstance(value, dict)
                    and value.get("application") == "FinPilot"
                    and value.get("project_run_token") == run_token)
    except (OSError, URLError, ValueError, TypeError):
        return False


def read_pet_ready(config: Config, state: dict, launched_pid: int, job, *, allow_descendant=False) -> dict | None:
    """Accept a loaded-window ACK only from this run and its owned process tree."""
    path = config.runtime_dir / f"pet-ready-{state['run_token']}.json"
    try:
        if path.stat().st_size > 16384:
            return None
        ack = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(ack, dict) or any(ack.get(key) != expected for key, expected in (
            ("schema", "finpilot.pet-ready.v1"), ("run_token", state["run_token"]),
            ("owner_pid", state["owner_pid"]), ("owner_started_at", state["owner_started_at"]),
            ("base_url", state["base_url"]),
        )):
            return None
        pid = ack.get("pet_pid")
        identity = process_identity(pid)
        if identity is None or (not allow_descendant and pid != launched_pid) or not job.contains(pid):
            return None
        return {"pet_pid": pid, "pet_started_at": identity, "pet_ready": True}
    except (OSError, ValueError, TypeError):
        return None


def stop_child(process: subprocess.Popen | None, *, graceful_timeout: float = 4):
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.send_signal(signal.SIGTERM)
        process.wait(timeout=graceful_timeout)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def run(config: Config, *, backend_command: Callable[[int], list[str]] | None = None,
        pet_command: Callable[[str, dict], list[str]] | None = None,
        startup_timeout: float = 20, pet_startup_timeout: float = 25, job_factory=OwnedProcessJob,
        open_browser=webbrowser.open) -> int:
    config = Config(**{**config.__dict__, "project_root": config.project_root.resolve(), "runtime_dir": config.runtime_dir.resolve()})
    if not config.project_root.is_dir() or not config.python.is_file():
        raise ValueError("Project directory or prepared Python interpreter is missing")
    if not config.no_desktop and pet_command is None and (config.electron is None or not config.electron.is_file()):
        raise ValueError("Desktop runtime is missing; prepare it before starting the project")
    config.runtime_dir.mkdir(parents=True, exist_ok=True)
    lease = SessionLock(config.runtime_dir / "project-session.lock")
    if not lease.acquire():
        prior = read_active_state(config)
        if prior and prior.get("no_desktop") and not config.no_desktop:
            print("This project was started with --no-desktop. Run -Stop, then start it again to enable the companion.", file=sys.stderr, flush=True)
            return 1
        if prior and prior.get("status") == "ready":
            if not config.no_desktop:
                if not request_companion(config, prior, timeout=pet_startup_timeout + 5):
                    return 1
            print(f"FinPilot is already running: {prior.get('base_url')}. Reusing its existing project session.", flush=True)
            if not config.no_browser and prior.get("status") == "ready":
                open_browser(prior["base_url"] + "/")
        else:
            print("This project's startup or shutdown is already in progress. No duplicate session was created.", flush=True)
        return 0
    backend = pet = None
    state = None
    stop_requested = threading.Event()
    old_handlers = {}
    log_streams = []
    secondary_pets = []
    exit_code = 0
    try:
        # No child is created until hard-close cleanup is guaranteed.
        job = job_factory().install()
        identity = process_identity(os.getpid())
        if identity is None:
            raise RuntimeError("Could not establish the launcher process identity")
        port = choose_port(config.port)
        base_url = f"http://127.0.0.1:{port}"
        token = secrets.token_hex(16)
        stop_file = config.runtime_dir / f"stop-{token}.request"
        state = {"schema": SCHEMA, "project_root": str(config.project_root),
                 "owner_pid": os.getpid(), "owner_started_at": identity, "run_token": token,
                 "status": "starting", "base_url": base_url, "port": port,
                 "backend_pid": None, "backend_started_at": None, "pet_pid": None, "pet_ready": False,
                 "companion_request_seq": 0, "companion_request_error": None,
                 "heartbeat_seq": 0, "heartbeat_at": time.time(), "no_desktop": config.no_desktop}
        atomic_json(config.state_file, state)
        for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            signum = getattr(signal, name, None)
            if signum is not None:
                old_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, lambda *_: stop_requested.set())
        environment = dict(os.environ)
        environment.update(FINPILOT_PROJECT_RUN_TOKEN=token, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        if config.offline:
            environment["FINPILOT_OFFLINE"] = "true"
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        for label in ("backend", "companion"):
            log_streams.append((config.runtime_dir / f"{label}-{token}.log").open("ab", buffering=0))
        backend = subprocess.Popen((backend_command or (lambda p: backend_command_for(config, p)))(port),
                                   cwd=config.project_root, env=environment, stdout=log_streams[0], stderr=subprocess.STDOUT,
                                   creationflags=flags)
        state.update(backend_pid=backend.pid, backend_started_at=process_identity(backend.pid))
        atomic_json(config.state_file, state)
        deadline = time.monotonic() + startup_timeout
        next_heartbeat = 0.0
        ready = False
        while not stop_requested.is_set() and not stop_file.exists():
            if backend.poll() is not None:
                raise RuntimeError("Backend exited before becoming ready; inspect its runtime log")
            if time.monotonic() >= next_heartbeat:
                state["heartbeat_seq"] += 1
                state["heartbeat_at"] = time.time()
                atomic_json(config.state_file, state)
                next_heartbeat = time.monotonic() + HEARTBEAT_INTERVAL
            if healthy_backend(base_url, token) and backend.poll() is None:
                ready = True
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Backend startup timed out; inspect its runtime log")
            stop_requested.wait(0.1)
        if not ready:
            return 0
        state["status"] = "ready"
        state["heartbeat_seq"] += 1
        state["heartbeat_at"] = time.time()
        atomic_json(config.state_file, state)
        pet_env = {key: value for key, value in environment.items() if key != "ELECTRON_RUN_AS_NODE"}

        def launch_companion():
            nonlocal pet, next_heartbeat
            # The token is stable for this backend session, so remove the old
            # loaded-window ACK before explicitly reopening its companion.
            stop_child(pet, graceful_timeout=0.5)
            (config.runtime_dir / f"pet-ready-{token}.json").unlink(missing_ok=True)
            state.update(pet_ready=False, pet_pid=None, pet_started_at=None)
            pet = subprocess.Popen((pet_command or (lambda url, s: pet_command_for(config, url, s)))(base_url, state),
                                   cwd=config.desktop_dir or config.project_root, env=pet_env,
                                   stdout=log_streams[1], stderr=subprocess.STDOUT, creationflags=flags)
            state["pet_pid"] = pet.pid
            atomic_json(config.state_file, state)
            # Electron Popen success is not window readiness. Require the host
            # ACK emitted after did-finish-load; missing modules/failed loads
            # must tear down this session instead of displaying false success.
            pet_deadline = time.monotonic() + pet_startup_timeout
            portable_wrapper = pet_command is None and config.electron_app is None and config.electron is not None and config.electron.name.lower() != "electron.exe"
            acknowledged = False
            while not stop_requested.is_set() and not stop_file.exists():
                acknowledgement = read_pet_ready(config, state, pet.pid, job, allow_descendant=portable_wrapper)
                if acknowledgement:
                    state.update(acknowledgement)
                    atomic_json(config.state_file, state)
                    acknowledged = True
                    break
                pet_exit = pet.poll()
                if pet_exit is not None and (pet_exit != 0 or not portable_wrapper):
                    raise RuntimeError("Companion exited before its window was ready; inspect its runtime log")
                if backend.poll() is not None:
                    raise RuntimeError("Backend exited while the companion was starting")
                if time.monotonic() >= pet_deadline:
                    raise RuntimeError("Companion window readiness timed out; inspect its runtime log")
                if time.monotonic() >= next_heartbeat:
                    state["heartbeat_seq"] += 1
                    state["heartbeat_at"] = time.time()
                    atomic_json(config.state_file, state)
                    next_heartbeat = time.monotonic() + HEARTBEAT_INTERVAL
                stop_requested.wait(0.1)
            if not acknowledged:
                return False
            return True

        if not config.no_desktop and not launch_companion():
            return 0
        print(f"FinPilot: {base_url}", flush=True)
        print("The companion follows this project session. Close this terminal or press Ctrl+C to stop both.", flush=True)
        if not config.no_browser:
            open_browser(base_url + "/")
        while not stop_requested.wait(0.2) and not stop_file.exists():
            if backend.poll() is not None:
                exit_code = int(backend.returncode or 0)
                print("Backend exited; closing this session's companion.", flush=True)
                break
            if state.get("pet_ready") and not is_process_identity(state.get("pet_pid"), state.get("pet_started_at")):
                state.update(pet_ready=False, pet_pid=None, pet_started_at=None)
                atomic_json(config.state_file, state)
            companion_request = config.runtime_dir / f"companion-{token}.request"
            if companion_request.exists() and consume_companion_request(companion_request, token) and not config.no_desktop:
                state["companion_request_error"] = None
                reopening = not state.get("pet_ready")
                client = None
                try:
                    if state.get("pet_ready"):
                        # Electron's project-scoped single-instance handler
                        # shows the existing window, then this client exits.
                        client = subprocess.Popen(
                            (pet_command or (lambda url, s: pet_command_for(config, url, s)))(base_url, state),
                            cwd=config.desktop_dir or config.project_root, env=pet_env,
                            stdout=log_streams[1], stderr=subprocess.STDOUT, creationflags=flags)
                        secondary_pets.append(client)
                        if client.wait(timeout=3) != 0:
                            raise RuntimeError("The companion show request failed")
                    elif not launch_companion():
                        break
                except Exception as error:
                    stop_child(client, graceful_timeout=0.5)
                    if reopening:
                        stop_child(pet, graceful_timeout=0.5)
                        state.update(pet_ready=False, pet_pid=None, pet_started_at=None)
                    state["companion_request_error"] = "Companion request failed; inspect its runtime log"
                    print(f"Companion could not reopen: {error}. The backend remains running.", file=sys.stderr, flush=True)
                finally:
                    state["companion_request_seq"] += 1
                    atomic_json(config.state_file, state)
            secondary_pets[:] = [client for client in secondary_pets if client.poll() is None]
            if time.monotonic() >= next_heartbeat:
                state["heartbeat_seq"] += 1
                state["heartbeat_at"] = time.time()
                atomic_json(config.state_file, state)
                next_heartbeat = time.monotonic() + HEARTBEAT_INTERVAL
        return exit_code
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        print(f"FinPilot could not start: {error}", file=sys.stderr, flush=True)
        return 1
    finally:
        if state is not None:
            state.update(status="stopping", heartbeat_at=time.time())
            try:
                atomic_json(config.state_file, state)
            except OSError:
                pass
        # A linked pet normally quits itself on status=stopping, preserving its
        # preferences first. A crashed/unresponsive child is bounded below.
        if pet is not None and pet.poll() is None:
            try:
                pet.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                stop_child(pet, graceful_timeout=0.5)
        elif state is not None and state.get("pet_ready"):
            # A portable SFX launcher may already have exited, leaving the
            # actual Electron member. Give its ownership guard time to save.
            pet_deadline = time.monotonic() + 1.5
            while time.monotonic() < pet_deadline and is_process_identity(state["pet_pid"], state.get("pet_started_at")):
                time.sleep(0.05)
        stop_child(backend, graceful_timeout=5)
        for client in secondary_pets:
            stop_child(client, graceful_timeout=0.5)
        if state is not None:
            state.update(status="stopped", heartbeat_at=time.time())
            try:
                atomic_json(config.state_file, state)
                (config.runtime_dir / f"stop-{state['run_token']}.request").unlink(missing_ok=True)
                (config.runtime_dir / f"companion-{state['run_token']}.request").unlink(missing_ok=True)
            except OSError:
                pass
        for stream in log_streams:
            stream.close()
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
        lease.close()
        # On return from this standalone Python process the last job handle is
        # closed by Windows, also reaping model/renderer/GPU grandchildren.


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--electron", type=Path)
    parser.add_argument("--desktop-dir", type=Path)
    parser.add_argument("--profile-dir", type=Path)
    parser.add_argument("--electron-app", type=Path)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--browser-request", action="store_true", help="Ask the parent launcher to open the browser outside this process job")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--no-desktop", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--status", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    config = Config(**{key: value for key, value in vars(args).items() if key not in {"stop", "status", "browser_request"}})
    if args.stop:
        return 0 if request_stop(config) else 1
    if args.status:
        state = read_owned_state(config)
        print(json.dumps({"running": state is not None and state.get("status") != "stopped", "state": state}, ensure_ascii=False))
        return 0
    if args.browser_request:
        # The PowerShell parent launches the browser outside this process's
        # kill-on-close job. Both fresh and reused sessions use this callback.
        return run(config, open_browser=lambda url: print(f"FINPILOT_BROWSER_URL={url}", flush=True))
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
