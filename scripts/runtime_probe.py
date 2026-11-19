"""Small bootstrap probes, invoked as a file to avoid Windows shell quoting."""
from __future__ import annotations

import argparse
import json
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("core", "optional-config"))
    parser.add_argument("env_file", nargs="?")
    args = parser.parse_args()
    if args.command == "optional-config":
        from dotenv import dotenv_values
        values = dotenv_values(args.env_file)
        names = ("IBKR_ENABLED", "FINPILOT_ML_PYTHON", "FINPILOT_HF_HOME", "FINPILOT_ADAPTER")
        print(json.dumps({key: os.environ.get(key, values.get(key) or "") for key in names}))
        return 0
    try:
        import fastapi, uvicorn, httpx, dotenv  # noqa: F401
        from zoneinfo import ZoneInfo
        ZoneInfo("America/New_York")
    except (ImportError, RuntimeError, ValueError, KeyError) as error:
        print(json.dumps({"status": "not_ready", "reason": type(error).__name__}))
        return 1
    print(json.dumps({"status": "ready"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
