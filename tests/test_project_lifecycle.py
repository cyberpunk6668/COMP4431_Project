"""Ownership and stop contracts for the project/desktop supervisor (no GUI)."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest

from scripts import project_lifecycle as lifecycle


@pytest.fixture
def config(tmp_path):
    project = tmp_path / "project with spaces"
    project.mkdir()
    return lifecycle.Config(project_root=project, python=Path(sys.executable),
                            runtime_dir=tmp_path / "private runtime", no_browser=True,
                            no_desktop=True)


def current_state(config, **updates):
    value = {"schema": lifecycle.SCHEMA, "project_root": str(config.project_root),
             "owner_pid": os.getpid(), "owner_started_at": lifecycle.process_identity(os.getpid()),
             "run_token": "a" * 32, "status": "ready", "base_url": "http://127.0.0.1:8123",
             "heartbeat_at": time.time(), "heartbeat_seq": 4, "pet_ready": True}
    value.update(updates)
    return value


def test_pid_identity_excludes_missing_and_exited_processes():
    identity = lifecycle.process_identity(os.getpid())
    assert identity and lifecycle.is_process_identity(os.getpid(), identity)
    assert not lifecycle.is_process_identity(os.getpid(), identity + "0")
    assert lifecycle.process_identity(-1) is None
    assert lifecycle.process_identity(True) is None
    child = subprocess.Popen([sys.executable, "-I", "-c", "pass"])
    child.wait(timeout=10)
    # In Windows the Popen handle can keep the process object around after
    # exit. Its creation time must no longer count as a live owner.
    assert lifecycle.process_identity(child.pid) is None


def test_foreign_project_or_reused_pid_state_cannot_be_stopped(config):
    state = current_state(config, project_root=str(config.project_root.parent / "other"))
    lifecycle.atomic_json(config.state_file, state)
    assert lifecycle.read_owned_state(config) is None
    assert lifecycle.request_stop(config, timeout=0)
    assert not list(config.runtime_dir.glob("stop-*.request"))
    lifecycle.atomic_json(config.state_file, current_state(config, owner_started_at="wrong-process"))
    assert lifecycle.read_owned_state(config) is None


@pytest.mark.parametrize("token", ["../escape", "a" * 31, "G" * 32, 123])
def test_untrusted_stop_token_never_becomes_a_filesystem_target(config, token):
    lifecycle.atomic_json(config.state_file, current_state(config, run_token=token))
    assert lifecycle.read_owned_state(config) is None
    assert lifecycle.request_stop(config, timeout=0)
    assert not list(config.runtime_dir.glob("*.request"))


def test_stale_heartbeat_is_not_a_running_project(config):
    state = current_state(config, heartbeat_at=time.time() - 30)
    lifecycle.atomic_json(config.state_file, state)
    assert lifecycle.read_owned_state(config) is not None
    assert lifecycle.read_active_state(config) is None
    lifecycle.atomic_json(config.state_file, current_state(config))
    assert lifecycle.read_active_state(config)["heartbeat_seq"] == 4


def test_stop_request_is_run_scoped_and_timeout_never_kills_pid(config):
    state = current_state(config)
    lifecycle.atomic_json(config.state_file, state)
    assert not lifecycle.request_stop(config, timeout=0)
    request = config.runtime_dir / ("stop-" + state["run_token"] + ".request")
    assert request.read_text(encoding="ascii") == state["run_token"]
    assert lifecycle.is_process_identity(os.getpid(), state["owner_started_at"])


def test_duplicate_project_lease_does_not_start_children(config, monkeypatch):
    lease = lifecycle.SessionLock(config.runtime_dir / "project-session.lock")
    assert lease.acquire()
    lifecycle.atomic_json(config.state_file, current_state(config))
    started = []
    monkeypatch.setattr(lifecycle.subprocess, "Popen", lambda *a, **k: started.append(a))
    try:
        assert lifecycle.run(config) == 0
        assert started == []
    finally:
        lease.close()


@pytest.mark.parametrize("status", ["starting", "ready"])
def test_headless_session_cannot_silently_accept_a_desktop_launcher(config, monkeypatch, capsys, status):
    lease = lifecycle.SessionLock(config.runtime_dir / "project-session.lock")
    assert lease.acquire()
    lifecycle.atomic_json(config.state_file, current_state(config, no_desktop=True, status=status))
    desktop_config = lifecycle.Config(**{**config.__dict__, "no_desktop": False})
    started = []
    monkeypatch.setattr(lifecycle.subprocess, "Popen", lambda *a, **k: started.append(a))
    try:
        assert lifecycle.run(desktop_config, pet_command=lambda *args: []) == 1
        assert "-Stop" in capsys.readouterr().err
        assert started == []
        assert not list(config.runtime_dir.glob("companion-*.request"))
    finally:
        lease.close()


@pytest.mark.parametrize("content, accepted", [("a" * 32, True), ("b" * 32, False), ("a" * 129, False), ("exe arbitrary", False)])
def test_companion_request_contains_only_the_current_nonce(config, content, accepted):
    config.runtime_dir.mkdir()
    request = config.runtime_dir / ("companion-" + "a" * 32 + ".request")
    request.write_text(content, encoding="ascii")
    assert lifecycle.consume_companion_request(request, "a" * 32) is accepted
    assert not request.exists()


@pytest.mark.parametrize("successful", [True, False])
def test_reopen_request_waits_for_owner_result_without_launching_any_process(config, monkeypatch, successful):
    config.runtime_dir.mkdir()
    state = current_state(config, companion_request_seq=2)
    acknowledgement = {**state, "companion_request_seq": 3, "pet_ready": successful,
                       "companion_request_error": None if successful else "startup failed"}
    monkeypatch.setattr(lifecycle, "read_active_state", lambda value: acknowledgement)
    monkeypatch.setattr(lifecycle.subprocess, "Popen", lambda *a, **k: pytest.fail("The requesting launcher must not own a second pet"))
    assert lifecycle.request_companion(config, state, timeout=0.1) is successful
    request = config.runtime_dir / f"companion-{state['run_token']}.request"
    assert request.read_text(encoding="ascii") == state["run_token"]


def test_explicit_occupied_port_refuses_without_touching_other_service():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(OSError, match="occupied"):
            lifecycle.choose_port(port)
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass


def test_desktop_arguments_are_data_and_bound_to_the_current_owner(config):
    config = lifecycle.Config(**{**config.__dict__, "electron": Path("C:/runtime with spaces/electron.exe"),
                                 "desktop_dir": Path("C:/host with spaces"),
                                 "profile_dir": Path("C:/private profile"), "no_desktop": False})
    state = current_state(config)
    command = lifecycle.pet_command_for(config, state["base_url"], state)
    assert command[0] == str(config.electron)
    assert command[1] == str(config.desktop_dir)
    assert f"--run-token={state['run_token']}" in command
    assert f"--owner-start-time={state['owner_started_at']}" in command
    assert f"--lifecycle-file={config.state_file}" in command
    assert "--pet-data-dir=C:\\private profile" in command if os.name == "nt" else True


def test_backend_command_has_bounded_shutdown_and_no_credentials(config):
    command = lifecycle.backend_command_for(config, 8123)
    assert command[:5] == [str(config.python), "-m", "uvicorn", "app.main:app", "--host"]
    assert command[-2:] == ["--timeout-graceful-shutdown", "5"]
    assert not any("key" in part.lower() or "token" in part.lower() for part in command)


@pytest.mark.parametrize("requested", [-1, 1, 1023, 65536])
def test_invalid_requested_port_is_rejected(requested):
    with pytest.raises(ValueError):
        lifecycle.choose_port(requested)


def test_atomic_state_is_complete_and_does_not_leave_a_partial_file(config):
    for status in ("starting", "ready", "stopping", "stopped"):
        value = current_state(config, status=status)
        lifecycle.atomic_json(config.state_file, value)
        assert json.loads(config.state_file.read_text(encoding="utf-8")) == value
    assert not list(config.runtime_dir.glob("*.tmp"))


def ready_ack(config, state, **updates):
    value = {"schema": "finpilot.pet-ready.v1", "run_token": state["run_token"],
             "owner_pid": state["owner_pid"], "owner_started_at": state["owner_started_at"],
             "base_url": state["base_url"], "pet_pid": os.getpid()}
    value.update(updates)
    lifecycle.atomic_json(config.runtime_dir / f"pet-ready-{state['run_token']}.json", value)


class OwnedFixtureJob:
    def contains(self, pid):
        return pid == os.getpid()


def test_pet_ack_requires_loaded_window_owned_by_current_run(config):
    state = current_state(config)
    assert lifecycle.read_pet_ready(config, state, os.getpid(), OwnedFixtureJob()) is None
    ready_ack(config, state)
    result = lifecycle.read_pet_ready(config, state, os.getpid(), OwnedFixtureJob())
    assert result == {"pet_pid": os.getpid(), "pet_started_at": lifecycle.process_identity(os.getpid()), "pet_ready": True}


@pytest.mark.parametrize("field", ["schema", "run_token", "owner_pid", "owner_started_at", "base_url", "pet_pid"])
def test_pet_ack_rejects_wrong_run_identity_or_invalid_process(config, field):
    state = current_state(config)
    ready_ack(config, state, **{field: "wrong"})
    assert lifecycle.read_pet_ready(config, state, os.getpid(), OwnedFixtureJob()) is None


def test_pet_ack_cannot_adopt_an_unowned_existing_companion(config):
    state = current_state(config)
    ready_ack(config, state)
    class ForeignJob:
        def contains(self, pid):
            return False
    assert lifecycle.read_pet_ready(config, state, os.getpid(), ForeignJob()) is None
    assert lifecycle.read_pet_ready(config, state, os.getpid() + 1, OwnedFixtureJob()) is None


def test_parent_browser_request_cli_preserves_config_and_exit_code(config, monkeypatch, capsys):
    def fake_run(received, *, open_browser):
        assert received.project_root == config.project_root
        assert not received.no_browser
        assert not hasattr(received, "browser_request")
        open_browser("http://127.0.0.1:8123/")
        return 19
    monkeypatch.setattr(lifecycle, "run", fake_run)
    assert lifecycle.main(["--project-root", str(config.project_root), "--runtime-dir", str(config.runtime_dir),
                           "--browser-request"]) == 19
    assert capsys.readouterr().out == "FINPILOT_BROWSER_URL=http://127.0.0.1:8123/\n"


def test_default_cli_and_no_browser_keep_existing_browser_policy(config, monkeypatch):
    received = []
    monkeypatch.setattr(lifecycle, "run", lambda value: received.append(value) or 0)
    arguments = ["--project-root", str(config.project_root), "--runtime-dir", str(config.runtime_dir)]
    assert not lifecycle.parse_args(arguments).browser_request
    assert lifecycle.main(arguments) == 0
    assert not received[-1].no_browser
    assert lifecycle.main(arguments + ["--no-browser"]) == 0
    assert received[-1].no_browser


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell native process pipeline")
def test_powershell_parent_keeps_blocking_stderr_and_exact_exit_code(tmp_path):
    powershell = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    if not powershell.is_file():
        pytest.skip("Windows PowerShell 5 is unavailable")
    fixture = tmp_path / "native fixture.py"
    fixture.write_text('''import sys, time
print("normal-start", flush=True)
print("native-stderr", file=sys.stderr, flush=True)
for value in ("https://example.invalid/", "http://127.0.0.1:1000/", "http://127.0.0.1:65536/", "http://127.0.0.1:8123/ trailing", "http://127.0.0.1:8123/"):
    print("FINPILOT_BROWSER_URL=" + value, flush=True)
time.sleep(0.7)
print("normal-end", flush=True)
sys.exit(23)
''', encoding="utf-8")
    wrapper = tmp_path / "pipeline fixture.ps1"
    wrapper.write_text('''param([string]$Runner,[string]$Python,[string]$Fixture,[string]$Opened,[string]$Result)
$ErrorActionPreference='Stop'
. $Runner
$script:openedPath=$Opened
function Start-Process {
    [CmdletBinding()]
    param([string]$FilePath)
    Add-Content -LiteralPath $script:openedPath -Value $FilePath -Encoding UTF8
}
$watch=[Diagnostics.Stopwatch]::StartNew()
$code=Invoke-FinPilotProject -Python $Python -Arguments @('-I',$Fixture)
$watch.Stop()
@{code=$code;elapsed=$watch.Elapsed.TotalSeconds;preference=[string]$ErrorActionPreference} | ConvertTo-Json -Compress | Set-Content -LiteralPath $Result -Encoding UTF8
''', encoding="utf-8-sig")
    opened, result = tmp_path / "opened.txt", tmp_path / "result.json"
    runner = Path(lifecycle.__file__).with_name("run-project.ps1")
    completed = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(wrapper),
                                "-Runner", str(runner), "-Python", sys.executable, "-Fixture", str(fixture),
                                "-Opened", str(opened), "-Result", str(result)],
                               capture_output=True, text=True, timeout=20)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    outcome = json.loads(result.read_text(encoding="utf-8-sig"))
    assert outcome["code"] == 23
    assert outcome["elapsed"] >= 0.7
    assert outcome["preference"] == "Stop"
    assert opened.read_text(encoding="utf-8-sig").splitlines() == ["http://127.0.0.1:8123/"]
    assert "normal-start" in completed.stdout and "normal-end" in completed.stdout
    assert "native-stderr" in completed.stdout + completed.stderr
