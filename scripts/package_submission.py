"""Create a reviewed allowlist submission ZIP; never include credentials or local DB."""
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "FinPilot_submission_v14.zip"
DIRECTORIES = ["app", "web", "frontend", "data", "tests", "evaluation", "scripts", "docs", "finetuning", "models/finpilot-lora", "output/pdf", "output/presentations", "reports"]
FILES = ["README.md", ".env.example", ".gitignore", "requirements.txt", "requirements-dev.txt", "requirements-ui-tests.txt", "requirements-ml.txt", "requirements-options.txt", "requirements-lock.txt", "start.ps1", "pytest.ini", "COMP4431_GroupProject2027-1 (1).pdf"]


def package():
    paths = [ROOT / item for item in FILES if (ROOT / item).is_file()]
    for directory in DIRECTORIES:
        for path in (ROOT / directory).rglob("*"):
            if not path.is_file() or any(p in {"__pycache__", "node_modules", "browser", "previews", ".pytest_cache", "checkpoints", "cache"} for p in path.parts):
                continue
            if path.name.startswith(".env") or path.suffix.lower() in {".sqlite3", ".db", ".pyc", ".log", ".tsbuildinfo"} or "sqlite" in path.name:
                continue
            paths.append(path)
    secret_pattern = re.compile(rb"sk-[A-Za-z0-9_-]{20,}")
    for path in paths:
        if path.suffix.lower() in {".py", ".js", ".html", ".css", ".md", ".json", ".txt", ".ps1"} and secret_pattern.search(path.read_bytes()):
            raise RuntimeError(f"Possible credential in submission: {path.relative_to(ROOT)}")
    OUTPUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(paths)):
            archive.write(path, "FinPilot/" + path.relative_to(ROOT).as_posix())
    result = {"file": OUTPUT.name, "files": len(set(paths)), "bytes": OUTPUT.stat().st_size,
              "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(), "secrets_excluded": True, "local_database_excluded": True}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    package()
