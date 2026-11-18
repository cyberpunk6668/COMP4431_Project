"""Source packaging must retain launchers/instructions and fail on omissions."""
import hashlib

import pytest

from scripts import package_submission as package


@pytest.fixture
def source_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(package, "ROOT", tmp_path)
    monkeypatch.setattr(package, "V16_REQUIRED_FILES", [])
    monkeypatch.setattr(package, "V17_REQUIRED_FILES", [])
    monkeypatch.setattr(package, "DIRECTORIES", ["app", "data"])
    monkeypatch.setattr(package, "DESKTOP_FILES", [])
    for name in package.FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test source")
    portable = tmp_path / package.PORTABLE
    portable.parent.mkdir(parents=True, exist_ok=True)
    payload = b"reviewed portable fixture"
    portable.write_bytes(payload)
    monkeypatch.setattr(package, "PORTABLE_BYTES", len(payload))
    monkeypatch.setattr(package, "PORTABLE_SHA256", hashlib.sha256(payload).hexdigest())
    return tmp_path


def test_collect_includes_launchers_and_renamed_course_instructions(source_tree):
    selected = {path.relative_to(source_tree).as_posix() for path in package.collect_paths()}
    assert {"start-finpilot.bat", "start.ps1", "start-desktop.ps1",
            "start-options-demo.ps1", "start-options-demo.cmd",
            "COMP4431_GroupProject2027-1.pdf"} <= selected
    assert "COMP4431_GroupProject2027-1 (1).pdf" not in selected


@pytest.mark.parametrize("missing", ["start-finpilot.bat", "COMP4431_GroupProject2027-1.pdf"])
def test_missing_required_root_file_stops_packaging(source_tree, missing):
    (source_tree / missing).unlink()
    with pytest.raises(FileNotFoundError, match="Required project deliverable missing"):
        package.collect_paths()


def test_collection_still_excludes_private_runtime_files(source_tree):
    app = source_tree / "app"
    app.mkdir()
    for name in ("main.py", ".env", "sessions.sqlite3", "private.key"):
        (app / name).write_bytes(b"test fixture")
    (source_tree / ".env").write_bytes(b"test fixture")
    selected = {path.relative_to(source_tree).as_posix() for path in package.collect_paths()}
    assert "app/main.py" in selected
    assert ".env.example" in selected
    assert not {".env", "app/.env", "app/sessions.sqlite3", "app/private.key"} & selected


def test_raw_downloads_excluded_while_reviewed_corpus_is_kept(source_tree):
    raw = source_tree / "data/news_sources"
    raw.mkdir(parents=True)
    (raw / "third-party.html").write_bytes(b"sk-" + b"x" * 32)
    (source_tree / "data/knowledge.json").write_bytes(b'{"documents": []}')
    selected = {path.relative_to(source_tree).as_posix() for path in package.collect_paths()}
    assert "data/knowledge.json" in selected
    assert "data/news_sources/third-party.html" not in selected
