"""Create a reviewed allowlist submission ZIP; never include credentials or local DB."""
import hashlib
import json
import os
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPLICATION_VERSION = "17.0.0"
NATIVE_HOST_VERSION = "15.0.0"
OUTPUT = ROOT / "dist" / "FinPilot_submission_v17.zip"
DIRECTORIES = ["app", "web", "frontend", "data", "tests", "evaluation", "scripts", "docs", "finetuning", "models/finpilot-lora", "output/pdf", "reports"]
FILES = ["README.md", ".env.example", ".gitignore", "requirements.txt", "requirements-dev.txt", "requirements-ui-tests.txt", "requirements-ml.txt", "requirements-options.txt", "requirements-lock.txt", "start.ps1", "start-desktop.ps1", "pytest.ini", "COMP4431_GroupProject2027-1 (1).pdf"]
# Keep the two project demo decks, without copying unrelated presentation drafts,
# exports and intermediate renders from the shared output directory.
FILES += ["output/presentations/FinPilot_Demo_EN.pptx", "output/presentations/FinPilot_Demo_EN_v2.pptx"]
FILES += ["start-options-demo.ps1", "start-options-demo.cmd"]
DESKTOP_FILES = ["desktop/package.json", "desktop/package-lock.json", "desktop/main.cjs", "desktop/preload.cjs",
                 "desktop/geometry.cjs", "desktop/build.cjs", "desktop/README.md", "desktop/.gitignore", "desktop/tray.png"]
PORTABLE = "desktop/artifacts/FinPilotPet-15.0.0-win-x64-portable.exe"
PORTABLE_BYTES = 109966509
PORTABLE_SHA256 = "64b4f47bc9d7522c9c62c6f3a63903a5fcca952865d84f92dcd5892cb92b80f0"
V16_REQUIRED_FILES = ["app/project_help.py", "app/project_help_chat.py", "data/project_help.json",
                      "web/help.html", "web/help.js", "web/help.css", "docs/project_help_v16.md",
                      "evaluation/project_help_cases_v16.json", "scripts/check_project_help_live_v16.py",
                      "reports/project_help_ui_v16.json", "reports/project_help_live_v16.json",
                      "reports/python_regression_v16.json"]
V17_REQUIRED_FILES = ["app/options_lab.py", "data/options_lab_knowledge.json", "web/learn.html", "web/learn.js", "web/learn.css",
                      "web/experience-v17.css", "docs/options_learning_v17.md", "docs/demo_v17.md",
                      "reports/options_lab_ui_v17.json", "reports/experience_ui_v17.json", "reports/python_regression_v17.json", "reports/options_lab_live_v17.json",
                      "reports/feature_audit_v17.json", "reports/options_lab_semantic_review_v17.json"]
EXCLUDED_DIRS = {"__pycache__", "node_modules", "browser", "previews", ".pytest_cache", "checkpoints", "cache",
                 "win-unpacked", "artifacts", ".git", ".hg", ".svn", ".venv", ".venv-ml", "tmp"}
SECRET_PATTERNS = [re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
                   re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")]


def excluded_file(path):
    name = path.name.lower()
    return (name.startswith(".env") or "sqlite" in name or
            path.suffix.lower() in {".db", ".pyc", ".log", ".tsbuildinfo", ".pem", ".pfx", ".p12", ".key"} or
            name.endswith((".db-wal", ".db-shm")) or name in {".npmrc", ".pypirc", "id_rsa", "id_ed25519"})


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scan_stream(stream, label):
    """Check all payload types, including CJS and the portable binary; no secret values in errors."""
    tail = b""
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        combined = tail + block
        if any(pattern.search(combined) for pattern in SECRET_PATTERNS):
            raise RuntimeError(f"Possible credential/private key in submission: {label}")
        tail = combined[-128:]


def collect_paths():
    """Only known project trees, known desktop source, and one reviewed binary."""
    for item in [*V16_REQUIRED_FILES, *V17_REQUIRED_FILES]:
        if not (ROOT / item).is_file():
            raise FileNotFoundError(f"Required project deliverable missing: {item}")
    paths = [ROOT / item for item in FILES if (ROOT / item).is_file()]
    for item in DESKTOP_FILES:
        path = ROOT / item
        if not path.is_file():
            raise FileNotFoundError(f"Required desktop source missing: {item}")
        paths.append(path)
    for directory in [*DIRECTORIES, "desktop/tests"]:
        base = ROOT / directory
        for current, directories, filenames in os.walk(base, followlinks=False):
            # Prune before descent, avoiding enumeration/copy of installed Node,
            # unpacked Electron, caches, VCS and symlink/junction targets.
            directories[:] = [name for name in directories if name not in EXCLUDED_DIRS
                              and not (Path(current) / name).is_symlink()
                              and (Path(current) / name).resolve().is_relative_to(ROOT.resolve())]
            for name in filenames:
                path = Path(current) / name
                if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()) or excluded_file(path):
                    continue
                paths.append(path)
    portable = ROOT / PORTABLE
    if not portable.is_file() or portable.stat().st_size != PORTABLE_BYTES or file_sha256(portable) != PORTABLE_SHA256:
        raise RuntimeError("The desktop portable does not match the reviewed v15 build. Rebuild/review before updating its allowlist.")
    paths.append(portable)
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise RuntimeError(f"Submission source escapes workspace: {path.name}")
    return sorted(set(paths))


def package():
    paths = collect_paths()
    for path in paths:
        with path.open("rb") as stream:
            scan_stream(stream, path.relative_to(ROOT).as_posix())
    OUTPUT.parent.mkdir(exist_ok=True)
    partial = OUTPUT.with_suffix(".zip.partial")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, "FinPilot/" + path.relative_to(ROOT).as_posix())
    partial.replace(OUTPUT)
    result = {"file": OUTPUT.name, "files": len(set(paths)), "bytes": OUTPUT.stat().st_size,
              "application_version": APPLICATION_VERSION, "native_host_version": NATIVE_HOST_VERSION,
              "sha256": file_sha256(OUTPUT), "secrets_excluded": True, "local_database_excluded": True,
              "desktop_portable": {"version": NATIVE_HOST_VERSION, "path": PORTABLE, "bytes": PORTABLE_BYTES, "sha256": PORTABLE_SHA256},
              "desktop_source_explicit_allowlist": True, "installed_or_unpacked_desktop_dependencies_excluded": True,
              "python_runtime_bundled": False, "requires_existing_finpilot_python_environment": True}
    (OUTPUT.parent / "submission_manifest_v17.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    package()
