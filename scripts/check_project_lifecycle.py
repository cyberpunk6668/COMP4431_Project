"""Real Windows process-tree checks for the project lifecycle supervisor.

Uses a private HTTP fixture, a headless fake pet and its child process. It never
opens the real pet, reads .env/user chats, invokes models, or connects to IBKR.
Ctrl+C is delivered only to a hidden console created and owned by this check.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = r'''
import argparse,ctypes,json,os,signal,subprocess,sys,time
from ctypes import wintypes
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
p=argparse.ArgumentParser();p.add_argument('role');p.add_argument('--runtime',type=Path,required=True);p.add_argument('--port',type=int,default=0);p.add_argument('--kind',default='normal');a=p.parse_args()
a.runtime.mkdir(parents=True,exist_ok=True)
def identity():
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    kernel.GetProcessTimes.restype=wintypes.BOOL
    stamps=[wintypes.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(kernel.GetCurrentProcess(),*map(ctypes.byref,stamps)):raise ctypes.WinError(ctypes.get_last_error())
    return (stamps[0].dwHighDateTime<<32)|stamps[0].dwLowDateTime
def write(name,value):
    value.update(pid=os.getpid(),identity=identity())
    path=a.runtime/name;temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value),encoding='utf-8');os.replace(temporary,path)
if a.role=='grandchild':
    write('grandchild.json',{'pid':os.getpid()})
    while True:time.sleep(.1)
elif a.role=='backend':
    write('fixture-backend.json',{'pid':os.getpid(),'port':a.port})
    if a.kind=='exit':raise SystemExit(23)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            payload={'application':'FinPilot','project_run_token':os.getenv('FINPILOT_PROJECT_RUN_TOKEN')}
            if a.kind=='wrong-token':payload['project_run_token']='not-this-run'
            write('fixture-health.json',{'served_at_ns':time.time_ns(),'run_token':payload['project_run_token']})
            body=json.dumps(payload).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler)
    try:server.serve_forever(.1)
    except KeyboardInterrupt:pass
    finally:server.server_close()
elif a.role=='show-client':
    state=json.loads((a.runtime/'lifecycle.json').read_text(encoding='utf-8'))
    previous=a.runtime/'fixture-shown.json'
    count=json.loads(previous.read_text(encoding='utf-8'))['count'] if previous.exists() else 0
    write('fixture-shown.json',{'count':count+1,'pet_pid':state['pet_pid']})
else:
    write('fixture-pet.json',{'pid':os.getpid(),'started_at_ns':time.time_ns(),'backend_health_seen':(a.runtime/'fixture-health.json').exists()})
    if a.kind=='pet-exit':raise SystemExit(29)
    child=subprocess.Popen([sys._base_executable,__file__,'grandchild','--runtime',str(a.runtime)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        if a.kind=='pet-delayed-ack':time.sleep(.8)
        if a.kind!='pet-no-ack':
            state=json.loads((a.runtime/'lifecycle.json').read_text(encoding='utf-8'))
            acknowledgement={'schema':'finpilot.pet-ready.v1','run_token':state['run_token'],'owner_pid':state['owner_pid'],'owner_started_at':state['owner_started_at'],'pet_pid':os.getpid(),'base_url':state['base_url']}
            if a.kind=='pet-wrong-ack':acknowledgement['run_token']='0'*32
            write('pet-ready-'+state['run_token']+'.json',acknowledgement)
        while not (a.runtime/'pet-quit.request').exists():time.sleep(.1)
    except KeyboardInterrupt:pass
    finally:
        child.terminate()
        try:child.wait(3)
        except subprocess.TimeoutExpired:child.kill();child.wait(3)
'''

RUNNER = r'''
import json,sys
from pathlib import Path
source,project,runtime,fixture,port,kind=map(str,sys.argv[1:])
sys.path.insert(0,str(Path(source)/'scripts'))
import project_lifecycle as lifecycle
project=Path(project);runtime=Path(runtime)
config=lifecycle.Config(project_root=project,python=Path(sys.executable),runtime_dir=runtime,electron=Path(sys.executable),desktop_dir=project/'desktop',profile_dir=runtime/'profile',port=int(port),no_browser=True,offline=True,no_desktop=kind=='no-desktop')
backend=lambda selected:[sys.executable,fixture,'backend','--runtime',str(runtime),'--port',str(selected),'--kind',kind]
pet=lambda base,state:[sys._base_executable,fixture,'show-client' if state.get('pet_ready') else 'pet','--runtime',str(runtime),'--kind',kind]
if kind=='browser-request':
    real_run=lifecycle.run
    def fixture_run(actual_config,**options):
        if 'open_browser' not in options:raise AssertionError('CLI must forward browser requests to its parent')
        return real_run(actual_config,backend_command=backend,pet_command=pet,startup_timeout=6,pet_startup_timeout=2,**options)
    lifecycle.run=fixture_run
    raise SystemExit(lifecycle.main(['--project-root',str(project),'--python',sys.executable,'--runtime-dir',str(runtime),'--electron',sys._base_executable,'--desktop-dir',str(project/'desktop'),'--port',str(port),'--offline','--browser-request']))
raise SystemExit(lifecycle.run(config,backend_command=backend,pet_command=pet,startup_timeout=6,pet_startup_timeout=2,open_browser=lambda url:None))
'''

CTRL_C = r'''
import ctypes,sys,time
from ctypes import wintypes
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.AttachConsole.argtypes=[wintypes.DWORD];k.AttachConsole.restype=wintypes.BOOL
k.SetConsoleCtrlHandler.argtypes=[ctypes.c_void_p,wintypes.BOOL];k.SetConsoleCtrlHandler.restype=wintypes.BOOL
k.GenerateConsoleCtrlEvent.argtypes=[wintypes.DWORD,wintypes.DWORD];k.GenerateConsoleCtrlEvent.restype=wintypes.BOOL
k.FreeConsole.argtypes=[];k.FreeConsole.restype=wintypes.BOOL
k.FreeConsole()
if not k.AttachConsole(int(sys.argv[1])):raise ctypes.WinError(ctypes.get_last_error())
try:
    if not k.SetConsoleCtrlHandler(None,True):raise ctypes.WinError(ctypes.get_last_error())
    if not k.GenerateConsoleCtrlEvent(0,0):raise ctypes.WinError(ctypes.get_last_error())
    time.sleep(.25)
finally:k.FreeConsole()
'''


def read_json(path):
    try:
        value = path.read_text(encoding="utf-8-sig")
        return json.loads(value)
    except (OSError, ValueError):
        return None


def wait_for(check, timeout=12, message="condition timed out"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(.05)
    raise AssertionError(message)


def process_identity(pid):
    if not pid:
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        if ctypes.get_last_error() in {6, 87}:
            return None
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        status = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(status)):
            raise ctypes.WinError(ctypes.get_last_error())
        if status.value != 259:
            return None
        created, ended, system, user = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *map(ctypes.byref, (created, ended, system, user))):
            raise ctypes.WinError(ctypes.get_last_error())
        return (created.dwHighDateTime << 32) | created.dwLowDateTime
    finally:
        kernel.CloseHandle(handle)


def force_exact(pid, identity):
    if identity is None or process_identity(pid) != identity:
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1001, False, int(pid))
    if not handle:
        return
    try:
        if process_identity(pid) == identity and not kernel.TerminateProcess(handle, 47):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)


def available_port():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return server.getsockname()[1]


class OwnedFixture:
    def __init__(self, base, name, source, runner, fixture, *, project=None, port=None, kind="normal"):
        self.source = source
        self.directory = base / name
        self.directory.mkdir()
        self.project = project or self.directory / "project"
        self.runtime = self.directory / "runtime"
        self.project.mkdir(exist_ok=True)
        (self.project / "app").mkdir(exist_ok=True)
        (self.project / "app/main.py").write_text("# Private lifecycle fixture\n")
        (self.project / "data").mkdir(exist_ok=True)
        (self.project / "desktop").mkdir(exist_ok=True)
        self.runtime.mkdir()
        self.port = port or available_port()
        self.env = dict(os.environ, DEEPSEEK_API_KEY="", IBKR_ENABLED="false", FINPILOT_OFFLINE="true", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        self.output = (self.directory / "owner.log").open("w", encoding="utf-8")
        self.command = [sys.executable, str(runner), str(source), str(self.project), str(self.runtime), str(fixture), str(self.port), kind]
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        self.process = subprocess.Popen(self.command, cwd=self.directory, env=self.env, stdout=self.output, stderr=subprocess.STDOUT,
                                        creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup)
        self.identities = {}
        owner_identity = process_identity(self.process.pid)
        if owner_identity is not None:
            self.identities[self.process.pid] = owner_identity

    def state(self):
        return read_json(self.runtime / "lifecycle.json") or {}

    def ready(self, *, desktop=True):
        def check():
            if self.process.poll() is not None:
                raise AssertionError(f"Owner exited early ({self.process.returncode}); inspect {self.directory / 'owner.log'}")
            value = self.state()
            names = ("fixture-backend.json", "fixture-pet.json", "grandchild.json") if desktop else ("fixture-backend.json",)
            fixtures = [read_json(self.runtime / name) for name in names]
            if value.get("status") != "ready" or not all(fixtures):
                return None
            if not all(process_identity(item['pid']) == item['identity'] for item in fixtures):
                return None
            if desktop and (not value.get("pet_ready") or fixtures[1]['pid'] != value.get('pet_pid')):
                return None
            return value
        state = wait_for(check, message=f"Fixture did not become ready: {self.directory}")
        self.capture()
        return state

    def capture(self):
        state = self.state()
        candidates = [(state.get("owner_pid"), state.get("owner_started_at")),
                      (state.get("backend_pid"), state.get("backend_started_at"))]
        for name in ("fixture-backend.json", "fixture-pet.json", "grandchild.json"):
            value = read_json(self.runtime / name)
            if value:
                candidates.append((value["pid"], value.get("identity")))
        for pid, expected in candidates:
            if pid and expected is not None:
                identity = process_identity(pid)
                if identity is not None and identity == int(expected):
                    self.identities[int(pid)] = identity
        return dict(self.identities)

    def cli(self, flag="--stop", project=None):
        return subprocess.run([sys.executable, str(self.source / "scripts/project_lifecycle.py"), "--project-root", str(project or self.project),
                               "--runtime-dir", str(self.runtime), flag], cwd=self.directory, env=self.env,
                              capture_output=True, text=True, encoding="utf-8", timeout=22)

    def all_gone(self):
        return all(process_identity(pid) != identity for pid, identity in self.identities.items())

    def stopped(self):
        self.process.wait(timeout=15)
        wait_for(self.all_gone, timeout=10, message=f"Owned descendant survived: {self.directory}")

    def cleanup(self):
        self.capture()
        if self.process.poll() is None:
            try:
                self.cli()
                self.process.wait(5)
            except (OSError, subprocess.TimeoutExpired):
                state = self.state()
                owner = state.get("owner_pid")
                if owner:
                    force_exact(owner, self.identities.get(int(owner)))
        for pid, identity in self.identities.items():
            force_exact(pid, identity)
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(5)
        self.output.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This check validates Windows Job Objects and console control events")
    source = args.target_root.resolve()
    if not (source / "scripts/project_lifecycle.py").is_file():
        parser.error("Project supervisor source is missing")
    private = Path(tempfile.mkdtemp(prefix="finpilot-lifecycle-check-"))
    fixture, runner = private / "fixture.py", private / "runner.py"
    fixture.write_text(FIXTURE, encoding="utf-8")
    runner.write_text(RUNNER, encoding="utf-8")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or source / "reports" / f"project_lifecycle_{stamp}.json"
    report = {"status": "failed", "checked_at_utc": stamp, "scope": "Real Windows supervisor, private console, HTTP backend and headless fake pet/child; no native pet UI or model/broker", "diagnostics": str(private), "cases": [], "real_model_requests": 0, "broker_requests": 0}
    owners = []

    def spawn(name, **kwargs):
        owner = OwnedFixture(private, name, source, runner, fixture, **kwargs)
        owners.append(owner)
        return owner

    def passed(name, **details):
        report["cases"].append({"name": name, "status": "passed", **details})
        print(json.dumps({"case": name, "status": "passed"}), flush=True)

    try:
        first = spawn("normal-stop")
        original = first.ready()
        assert read_json(first.runtime / 'fixture-pet.json')['backend_health_seen'], 'Pet was created before backend health succeeded'
        duplicate_log = (first.directory / "duplicate.log").open("w", encoding="utf-8")
        try:
            duplicate = subprocess.run(first.command, cwd=first.directory, env=first.env, stdout=duplicate_log, stderr=subprocess.STDOUT, timeout=12)
            assert duplicate.returncode == 0, "A repeat launch did not reuse the running project"
        finally:
            duplicate_log.close()
        assert first.state()["run_token"] == original["run_token"]
        assert first.state()["owner_pid"] == original["owner_pid"]
        assert first.state()["pet_pid"] == original["pet_pid"]
        assert first.state().get("companion_request_seq", 0) > original.get("companion_request_seq", 0)
        shown = read_json(first.runtime / "fixture-shown.json")
        assert shown and shown['count'] == 1 and shown['pet_pid'] == original['pet_pid']
        assert first.cli().returncode == 0
        first.stopped()
        passed("startup_order_duplicate_reuse_cli_stop_and_descendant_cleanup", controlled_processes=len(first.identities))

        pending = spawn('duplicate-during-pet-start', kind='pet-delayed-ack')
        initial = wait_for(lambda: pending.state() if pending.state().get('pet_pid') and not pending.state().get('pet_ready') else None)
        repeated = subprocess.run(pending.command, cwd=pending.directory, env=pending.env, capture_output=True, text=True, encoding='utf-8', timeout=12)
        assert repeated.returncode == 0, repeated.stderr
        pending_state = pending.ready()
        assert all(pending_state[key] == initial[key] for key in ('owner_pid', 'backend_pid', 'pet_pid', 'run_token'))
        assert pending.cli().returncode == 0
        pending.stopped()
        passed('duplicate_during_pending_pet_ack_reuses_original_session')

        crashed = spawn("backend-crash")
        crashed.ready()
        backend = read_json(crashed.runtime / "fixture-backend.json")["pid"]
        force_exact(backend, crashed.identities[backend])
        crashed.stopped()
        passed("backend_exit_closes_pet_and_its_child")

        killed = spawn("owner-force-killed")
        state = killed.ready()
        force_exact(state["owner_pid"], killed.identities[state["owner_pid"]])
        killed.stopped()
        passed("kill_on_job_close_cleans_entire_tree_after_owner_termination")

        interrupted = spawn("console-ctrl-c")
        state = interrupted.ready()
        sender = subprocess.run([sys.executable, "-I", "-c", CTRL_C, str(state["owner_pid"])], env=interrupted.env,
                                capture_output=True, text=True, encoding="utf-8", timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
        assert sender.returncode == 0, sender.stderr
        interrupted.stopped()
        passed("ctrl_c_on_owned_hidden_console_cleans_project")

        manual = spawn("pet-manual-exit")
        state = manual.ready()
        pet_pids = [state["pet_pid"], read_json(manual.runtime / "fixture-pet.json")["pid"], read_json(manual.runtime / "grandchild.json")["pid"]]
        (manual.runtime / "pet-quit.request").write_text("quit", encoding="utf-8")
        wait_for(lambda: all(process_identity(pid) != manual.identities.get(pid) for pid in pet_pids), message="Manually exited pet retained its child")
        before = manual.state().get("heartbeat_seq")
        wait_for(lambda: manual.state().get("heartbeat_seq") != before, timeout=4)
        assert manual.process.poll() is None and process_identity(state["backend_pid"]) == manual.identities[state["backend_pid"]]
        wait_for(lambda: manual.state().get("pet_ready") is False, timeout=4)
        passed("manual_pet_quit_keeps_backend_until_project_stop")
        (manual.runtime / "pet-quit.request").unlink()
        repeat = subprocess.run(manual.command, cwd=manual.directory, env=manual.env, capture_output=True, text=True, encoding='utf-8', timeout=12)
        assert repeat.returncode == 0, repeat.stderr
        reopened = manual.ready()
        assert reopened['run_token'] == state['run_token'] and reopened['owner_pid'] == state['owner_pid']
        assert reopened['backend_pid'] == state['backend_pid'] and reopened['backend_started_at'] == state['backend_started_at']
        assert reopened['pet_pid'] != state['pet_pid'] or reopened['pet_started_at'] != state['pet_started_at']
        assert manual.cli().returncode == 0
        manual.stopped()
        passed("repeat_launch_reopens_quit_pet_without_restarting_backend")

        headless = spawn('headless-upgrade', kind='no-desktop')
        headless_state = headless.ready(desktop=False)
        default_command = [*headless.command[:-1], 'normal']
        upgrade = subprocess.run(default_command, cwd=headless.directory, env=headless.env, capture_output=True, text=True, encoding='utf-8', timeout=12)
        assert upgrade.returncode != 0, 'Headless-to-desktop launch reported a false success'
        assert 'stop' in (upgrade.stdout + upgrade.stderr).lower(), 'The rejection did not explain stopping and restarting'
        assert headless.process.poll() is None and headless.state()['run_token'] == headless_state['run_token']
        assert process_identity(headless_state['backend_pid']) == headless.identities[headless_state['backend_pid']]
        assert not (headless.runtime / 'fixture-pet.json').exists()
        assert headless.cli().returncode == 0
        headless.stopped()
        passed('headless_to_desktop_requires_stop_and_preserves_backend')

        browser = spawn('browser-parent-request', kind='browser-request')
        browser_state = browser.ready()
        marker = f"FINPILOT_BROWSER_URL={browser_state['base_url']}/"
        wait_for(lambda: marker in (browser.directory / 'owner.log').read_text(encoding='utf-8'))
        # Stand in for the parent's browser only after receiving the production
        # CLI marker. This process is created by the checker, outside the job.
        sentinel = subprocess.Popen([sys._base_executable, '-I', '-c', 'import time;time.sleep(90)'], creationflags=subprocess.CREATE_NO_WINDOW)
        sentinel_identity = process_identity(sentinel.pid)
        assert sentinel_identity is not None
        try:
            force_exact(browser_state['owner_pid'], browser.identities[browser_state['owner_pid']])
            browser.stopped()
            assert sentinel.poll() is None and process_identity(sentinel.pid) == sentinel_identity
            passed('browser_request_is_forwarded_to_parent_and_external_process_survives_stop')
        finally:
            force_exact(sentinel.pid, sentinel_identity)
            sentinel.wait(5)

        class ExistingHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200); self.end_headers(); self.wfile.write(b'{"application":"FinPilot","project_run_token":"another-project"}')
            def log_message(self, *args):
                pass
        existing = ThreadingHTTPServer(("127.0.0.1", 0), ExistingHandler)
        thread = threading.Thread(target=existing.serve_forever, daemon=True)
        thread.start()
        try:
            occupied = spawn("occupied-port", port=existing.server_port)
            assert occupied.process.wait(12) != 0
            assert not (occupied.runtime / "fixture-backend.json").exists()
            assert not (occupied.runtime / "fixture-pet.json").exists()
            assert thread.is_alive()
            with socket.create_connection(("127.0.0.1", existing.server_port), timeout=2):
                pass
            passed("occupied_unowned_service_is_not_adopted_or_stopped")
        finally:
            existing.shutdown(); existing.server_close(); thread.join(3)

        left, right = spawn("project-a"), spawn("project-b")
        left.ready(); right_state = right.ready()
        wrong = left.cli(project=right.project)
        assert left.process.poll() is None and right.process.poll() is None
        assert left.cli().returncode == 0
        left.stopped()
        assert right.process.poll() is None and process_identity(right_state["backend_pid"]) == right.identities[right_state["backend_pid"]]
        assert right.cli().returncode == 0
        right.stopped()
        passed("different_project_and_wrong_root_stop_are_isolated", wrong_root_exit_code=wrong.returncode)

        failure = spawn("startup-failure", kind="exit")
        failure.process.wait(12)
        assert failure.process.returncode != 0
        failure.capture()
        wait_for(failure.all_gone)
        assert not (failure.runtime / "fixture-pet.json").exists()
        passed("backend_startup_failure_leaves_no_pet_or_owned_child")

        wrong_token = spawn("wrong-backend-token", kind="wrong-token")
        wait_for(lambda: read_json(wrong_token.runtime / "fixture-backend.json"))
        wrong_token.capture()
        assert wrong_token.process.wait(15) != 0
        wrong_token.stopped()
        assert not (wrong_token.runtime / "fixture-pet.json").exists()
        passed("wrong_backend_run_token_is_not_accepted_as_ready")

        for kind, label in (("pet-exit", "pet_startup_exit_is_failure"),
                            ("pet-no-ack", "pet_without_ready_ack_is_failure"),
                            ("pet-wrong-ack", "pet_wrong_token_ack_is_failure")):
            rejected = spawn(kind, kind=kind)
            wait_for(lambda: read_json(rejected.runtime / "fixture-pet.json"))
            if kind != "pet-exit":
                wait_for(lambda: read_json(rejected.runtime / "grandchild.json"))
            rejected.capture()
            assert rejected.process.wait(15) != 0, f"{kind} reported success"
            rejected.stopped()
            assert rejected.state().get("status") == "stopped"
            passed(label)

        report["status"] = "passed"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        cleanup_errors = []
        for owner in owners:
            try:
                owner.cleanup()
            except Exception as error:
                cleanup_errors.append({"directory": str(owner.directory), "error": str(error)})
        report["cleanup_errors"] = cleanup_errors
        if cleanup_errors:
            report["status"] = "failed"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": report["status"], "cases": len(report["cases"]), "report": str(output)}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
