"""Run all offline Python regressions without loading user secrets or user DB.

Tests retain their controlled-provider configurations. A child-process network
guard blocks external/DNS/broker connections; only asyncio's internal loopback
ephemeral sockets are allowed. Each report, JUnit and log is retained separately.
"""
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

CHILD = r'''
import json, pathlib, socket, sys
root, junit, guard_report = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(root))
import dotenv
dotenv.load_dotenv = lambda *args, **kwargs: False
blocked = []
original_connect, original_connect_ex, original_getaddrinfo = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo
def permitted(address):
    if not isinstance(address, tuple) or len(address) < 2:
        return False
    return address[0] in {'127.0.0.1', '::1', 'localhost'} and isinstance(address[1], int) and address[1] >= 32768
def connect(sock, address):
    if not permitted(address):
        blocked.append({'operation':'socket.connect','address':str(address)[:180]})
        raise AssertionError('Network blocked during isolated offline regression')
    return original_connect(sock, address)
def connect_ex(sock, address):
    if not permitted(address):
        blocked.append({'operation':'socket.connect_ex','address':str(address)[:180]})
        raise AssertionError('Network blocked during isolated offline regression')
    return original_connect_ex(sock, address)
def getaddrinfo(host, *args, **kwargs):
    if host not in {None, '127.0.0.1', '::1', 'localhost'}:
        blocked.append({'operation':'socket.getaddrinfo','host':str(host)[:120]})
        raise AssertionError('External DNS blocked during isolated offline regression')
    return original_getaddrinfo(host, *args, **kwargs)
socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = connect, connect_ex, getaddrinfo
import pytest
code = 1
try:
    code = int(pytest.main(['-q','tests','--junitxml='+str(junit)]))
finally:
    guard_report.write_text(json.dumps({'dotenv_loading_disabled':True,'blocked_attempts':blocked,'external_model_requests':0,'broker_requests':0}),encoding='utf-8')
sys.exit(code)
'''


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    scratch = ROOT / "tmp/python-regression-v17" / stamp
    scratch.mkdir(parents=True, exist_ok=False)
    assert scratch.resolve().is_relative_to((ROOT / "tmp").resolve())
    helper = scratch / "runner.py"
    helper.write_text(CHILD, encoding="utf-8")
    junit = ROOT / "reports" / ("tests_v17-" + stamp + ".xml")
    log = scratch / "pytest.log"
    guard_path = scratch / "network_guard.json"
    target = ROOT / "reports/python_regression_v17.json"
    if target.exists():
        target = target.with_stem(target.stem + "-" + stamp)
    env = {**os.environ, "DEEPSEEK_API_KEY": "", "FINPILOT_OFFLINE": "false", "IBKR_ENABLED": "false",
           "FINPILOT_DB": str(scratch / "default.sqlite3"), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
           "FINPILOT_OPTIONS_MODEL_DIAGNOSTICS": "0", "PYTHONIOENCODING": "utf-8"}
    started = time.perf_counter()
    timed_out = False
    with log.open("w", encoding="utf-8") as output:
        try:
            result = subprocess.run([sys.executable, str(helper), str(ROOT), str(junit), str(guard_path)], cwd=ROOT,
                                    env=env, stdout=output, stderr=subprocess.STDOUT, timeout=240)
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            timed_out, exit_code = True, 124
            output.write("\nIsolated regression deadline exceeded; failure artifacts retained.\n")
    counts = {}
    if junit.exists():
        try:
            xml = ET.parse(junit).getroot()
            counts = {key: sum(int(x.attrib.get(key, 0)) for x in xml.iter("testsuite"))
                      for key in ("tests", "failures", "errors", "skipped")}
        except ET.ParseError:
            counts = {"parse_error": True}
    try:
        guard = json.loads(guard_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        guard = {"error":"No complete child guard report"}
    passed = exit_code == 0 and counts.get("tests", 0) > 0 and counts.get("failures") == counts.get("errors") == 0 and guard.get("blocked_attempts") == []
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "passed" if passed else "failed",
              "scope": "Complete pytest tests/ suite using the workspace .venv, controlled providers/transports; not real broker or cloud-model acceptance.",
              "command": [".venv/Scripts/python.exe", "-m", "pytest", "-q", "tests", "--junitxml=<versioned report>"],
              "runner": "Child calls pytest.main with a process-local dotenv/network guard before importing application code.",
              "counts": counts, "exit_code": exit_code, "timed_out": timed_out,
              "junit": junit.relative_to(ROOT).as_posix(), "log": log.relative_to(ROOT).as_posix(),
              "default_database": (scratch / "default.sqlite3").relative_to(ROOT).as_posix(),
              "source_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for folder in (ROOT / "app", ROOT / "tests") for p in sorted(folder.rglob("*.py"))},
              "user_dotenv_or_chat_database_read": False, "network_guard": guard,
              "elapsed_seconds": round(time.perf_counter() - started, 3),
              "limits": ["Unit/API tests use mocks for models and broker transports.", "Native Windows and browser workflows are separate reports."]}
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"status":report["status"],"counts":counts,"exit_code":exit_code,"report":target.relative_to(ROOT).as_posix()}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
