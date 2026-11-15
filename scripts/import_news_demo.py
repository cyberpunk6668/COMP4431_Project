"""Archive reviewed primary sources in SQLite and export into FinPilot's JSON KB.

This imports a fixed reviewed snapshot, not an unattended current-news crawler.
HTML and provenance are stored separately from user conversations. No model call.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def visible_text(html: str) -> str:
    parser = VisibleText()
    parser.feed(html)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def validate_source(document: dict, text: str) -> None:
    missing = [anchor for anchor in document["review_checks"] if anchor.casefold() not in text.casefold()]
    if missing:
        raise ValueError(f"Source changed or incomplete for {document['id']}: {missing}")


def import_sources(*, manifest_path: Path, knowledge_path: Path, db_path: Path,
                   archive_path: Path, report_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    knowledge = json.loads(knowledge_path.read_text(encoding="utf-8"))
    prepared = []
    # Validate every download before mutating either database or retrieval corpus.
    with httpx.Client(timeout=30, follow_redirects=False, headers={
        "User-Agent": "Mozilla/5.0 (compatible; FinPilot/1.0; academic evidence archive)"
    }) as client:
        for doc in manifest["documents"]:
            response = client.get(doc["url"])
            response.raise_for_status()
            if "html" not in response.headers.get("content-type", "").lower():
                raise ValueError(f"Expected primary-source HTML: {doc['id']}")
            text = visible_text(response.text)
            validate_source(doc, text)
            stamp = datetime.now(timezone.utc).isoformat()
            digest = hashlib.sha256(response.content).hexdigest()
            exported = {k: v for k, v in doc.items() if k != "review_checks"}
            exported.update(fetched_at=stamp, raw_sha256=digest)
            exported["text"] = doc["text_zh"] + "\n" + doc["text_en"]
            prepared.append((exported, response.content, text))

    db_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.mkdir(parents=True, exist_ok=True)
    rows = []
    with sqlite3.connect(db_path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS news_source_snapshots (
            id TEXT NOT NULL, raw_sha256 TEXT NOT NULL, url TEXT NOT NULL,
            publisher TEXT NOT NULL, published_at TEXT NOT NULL, event_date TEXT NOT NULL,
            reviewed_at TEXT NOT NULL, fetched_at TEXT NOT NULL, raw_html BLOB NOT NULL,
            extracted_text TEXT NOT NULL, reviewed_document TEXT NOT NULL,
            PRIMARY KEY (id, raw_sha256))""")
        for document, raw, text in prepared:
            # Identical bytes keep their first capture time; a rerun is only a
            # new availability check. Reviewed summaries may change separately.
            existing = db.execute("SELECT fetched_at FROM news_source_snapshots WHERE id=? AND raw_sha256=?",
                                  (document["id"], document["raw_sha256"])).fetchone()
            if existing:
                document["fetched_at"] = existing[0]
            db.execute("""INSERT INTO news_source_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(id,raw_sha256) DO UPDATE SET
                       reviewed_at=excluded.reviewed_at, reviewed_document=excluded.reviewed_document""",
                       (document["id"], document["raw_sha256"], document["url"], document["publisher"],
                        document["published_at"], document["event_date"], document["updated_at"],
                        document["fetched_at"], raw, text, json.dumps(document, ensure_ascii=False)))
            name = document["id"] + "-" + document["raw_sha256"][:12]
            (archive_path / (name + ".html")).write_bytes(raw)
            (archive_path / (name + ".txt")).write_text(text, encoding="utf-8")
            rows.append({k: document[k] for k in ("id", "url", "published_at", "event_date", "updated_at", "fetched_at", "raw_sha256")})

    # Preserve all other knowledge documents and their order; importing twice adds no duplicates.
    incoming = {d["id"]: d for d, _, _ in prepared}
    existing_ids = {d["id"] for d in knowledge["documents"]}
    knowledge["documents"] = [incoming.get(d["id"], d) for d in knowledge["documents"]]
    knowledge["documents"].extend(d for key, d in incoming.items() if key not in existing_ids)
    knowledge["company_news_reviewed_at"] = manifest["reviewed_at"]
    knowledge_path.write_text(json.dumps(knowledge, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {"status": "imported", "checked_at": datetime.now(timezone.utc).isoformat(),
              "sqlite": str(db_path), "knowledge": str(knowledge_path), "archive": str(archive_path),
              "document_count": len(knowledge["documents"]), "sources": rows,
            "limits": "Anchor checks detect incomplete pages, not semantic truth. Summaries are reviewed against primary sources; rerunning is not a fresh review or proof of the latest CEO. Restart running servers to reload JSON knowledge."}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/news_demo_sources.json")
    parser.add_argument("--knowledge", type=Path, default=ROOT / "data/knowledge.json")
    parser.add_argument("--db", type=Path, default=ROOT / "data/news_evidence.sqlite3")
    parser.add_argument("--archive", type=Path, default=ROOT / "data/news_sources")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/news_demo_import.json")
    args = parser.parse_args()
    try:
        result = import_sources(manifest_path=args.manifest, knowledge_path=args.knowledge,
                                db_path=args.db, archive_path=args.archive, report_path=args.output)
    except (httpx.HTTPError, ValueError) as error:
        print(f"Import failed; review source availability/content before retrying: {type(error).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
