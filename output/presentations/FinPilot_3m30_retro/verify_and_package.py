"""Inspect the assembled image-based PPTX, make QA previews, and package delivery.

This script never draws or modifies a final slide image.
"""
from pathlib import Path
import hashlib
import io
import json
import re
import shutil
import zipfile

from PIL import Image
from pptx import Presentation

ROOT = Path(__file__).resolve().parent
PPTX = ROOT / "FinPilot_3m30_retro.pptx"
BUILD = ROOT / "build"
BUILD.mkdir(exist_ok=True)

with zipfile.ZipFile(PPTX) as archive:
    assert archive.testzip() is None, "Corrupt PPTX ZIP entry"

prs = Presentation(PPTX)
assert len(prs.slides) == 6
assert (prs.slide_width, prs.slide_height) == (9144000, 5143500)
speech = (ROOT / "speech.md").read_text(encoding="utf-8")
parts = re.split(r"(?m)^## Slide (\d+):[^\n]*\n", speech)
expected = {int(parts[i]): parts[i + 1].strip() for i in range(1, len(parts), 2)}
assert set(expected) == set(range(1, 7))

checks = []
thumbs = []
for index, slide in enumerate(prs.slides, 1):
    assert len(slide.shapes) == 1, (index, "Expected one full-slide picture")
    pic = slide.shapes[0]
    assert (pic.left, pic.top, pic.width, pic.height) == (0, 0, prs.slide_width, prs.slide_height)
    assert slide.has_notes_slide
    actual = slide.notes_slide.notes_text_frame.text.strip()
    assert actual == expected[index], (index, "Speaker note mismatch")
    image = Image.open(io.BytesIO(pic.image.blob)).convert("RGB")
    assert abs(image.width / image.height - 16 / 9) < 0.005
    image.save(BUILD / f"embedded_slide_{index:02d}.png")
    thumb = image.copy()
    thumb.thumbnail((816, 459), Image.Resampling.LANCZOS)
    thumbs.append(thumb)
    checks.append({"slide": index, "image_pixels": list(image.size),
                   "embedded_image_format": pic.image.ext,
                   "note_words": len(actual.split()), "notes_match": True,
                   "full_slide_picture": True})

montage = Image.new("RGB", (1664, 1425), "#F5F3E8")
for i, thumb in enumerate(thumbs):
    montage.paste(thumb, (8 + (i % 2) * 832, 8 + (i // 2) * 475))
montage.save(ROOT / "preview.png")

audit = (ROOT / "source_audit.draft.md").read_text(encoding="utf-8")
(ROOT / "source_audit.md").write_text(audit.replace("Technical fact check · draft", "Technical fact check"), encoding="utf-8")
license_source = ROOT.parents[2] / "web" / "companion" / "licenses"
license_dest = ROOT / "character_licenses"
shutil.copytree(license_source, license_dest, dirs_exist_ok=True)

jobs = json.loads((ROOT / "slide_jobs.json").read_text(encoding="utf-8"))
assert all(j["status"] in ("accepted", "recorded") for j in jobs["slides"])
word_count = sum(c["note_words"] for c in checks)
assert word_count == 383, word_count
report = {
    "status": "passed", "slide_count": 6, "aspect_ratio": "16:9",
    "slide_size_emu": [prs.slide_width, prs.slide_height],
    "speaker_notes_match_speech_md": True, "english_word_count": word_count,
    "planned_seconds": 210, "planned_seconds_by_speaker": [40, 60, 55, 55],
    "words_by_speaker": [checks[0]["note_words"], checks[1]["note_words"] + checks[2]["note_words"],
                         checks[3]["note_words"], checks[4]["note_words"] + checks[5]["note_words"]],
    "timing_limitation": "Planned from word counts, not an audio rehearsal measurement.",
    "backend": "built-in image tool", "primary_skill": "ningzimu/codex-ppt-skill",
    "primary_skill_commit": "941dcafe2f23ea4ae61de99e9b22fb0ef3d9e06c",
    "visual_review": "All six original images inspected; embedded images 2 and 5 inspected after assembly compression; final montage inspected.",
    "repair": "Slide 6 edited with same built-in image tool to show bidirectional connections.",
    "pptx_sha256": hashlib.sha256(PPTX.read_bytes()).hexdigest(),
    "not_claimed": ["PowerPoint native application opened", "live model/broker retested", "audio timing measured"],
    "slides": checks,
}
(ROOT / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

files = [PPTX, ROOT / "preview.png", ROOT / "speech.md", ROOT / "speaker_guide.md",
         ROOT / "outline.md", ROOT / "source_audit.md", ROOT / "delivery.md", ROOT / "validation.json"]
files += list(ROOT.glob("speaker_[1-4].md"))
files += [ROOT / "deck_spec.json", ROOT / "slide_jobs.json", ROOT / "slide_run_state.json", ROOT / "sample_prompt.txt"]
files += list((ROOT / "prompts").glob("slide_*.json"))
files += [BUILD / "package_integrity.json", BUILD / "layout_geometry.json"]
files += list((ROOT / "origin_image").glob("slide_*.png"))
files += list(license_dest.rglob("*"))
archive_path = ROOT.parent / "FinPilot_3m30_retro_delivery.zip"
with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        if path.is_file():
            archive.write(path, Path(ROOT.name) / path.relative_to(ROOT))
with zipfile.ZipFile(archive_path) as archive:
    assert archive.testzip() is None
print(json.dumps({"pptx": str(PPTX), "notes": 6, "word_count": word_count,
                  "zip": str(archive_path), "slides": checks}, ensure_ascii=False))
