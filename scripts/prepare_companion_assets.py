"""Rebuild the pinned, attributed FinPilot whale-maid atlases (build-time only).

Uses Python 3.11+, Pillow==11.3.0 and Node.js. No account, model or broker API.
Only immutable raw GitHub URLs are fetched; every source Git blob is verified.
The audited upstream motion sampler is evaluated in an isolated no-I/O Node VM
to export its final clip tables, never loaded as an application or installer.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import subprocess
import urllib.request
from PIL import Image, __version__ as PILLOW_VERSION

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "7661c8b304c5400701f91da01b1a643a207331de"
REPO = "YunYueSama/codex-deepseek-pet"
RAW = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/"
CACHE = ROOT / "tmp" / "companion-assets-v15" / COMMIT
DEST = ROOT / "web" / "companion"
SOURCES = json.loads(r'''{
    "ASSET_LICENSE.md": {
        "sha": "ef7cd63ee2672a0da5126cef06057ce0233c5843",
        "size": 2524
    },
    "LICENSE": {
        "sha": "57a0bb973d4a0a6ecc25716de05f9598dae11bf9",
        "size": 2469
    },
    "assets/whale/actions.png": {
        "sha": "811c8496744ad137e305b3fe595a5f4792a35af6",
        "size": 3898755
    },
    "assets/whale/dense-idle.png": {
        "sha": "74487a6f23a7c98a2bf3c18383f7d018b0a981d9",
        "size": 7960979
    },
    "assets/whale/dense-wave.png": {
        "sha": "f9fc5cf57b041e6b30d2ee6abd10a34602b09554",
        "size": 8204942
    },
    "assets/whale/expressions.png": {
        "sha": "018d1ad59c9775978b77cb29522ed50f4d46acc7",
        "size": 3905134
    },
    "assets/whale/idle-front.png": {
        "sha": "e19f88b5826aba89ea2aa0d086d31d40c9def912",
        "size": 1516887
    },
    "assets/whale/inbetween-jump.png": {
        "sha": "57a799bdb58d7347f1ae5a0ef2162d9bc570fc5e",
        "size": 11809882
    },
    "assets/whale/inbetween-sleep.png": {
        "sha": "f7b68276899a3510c030f48de2800f69cf8aba9b",
        "size": 10862152
    },
    "assets/whale/inbetween-walk.png": {
        "sha": "c84213762f8cba68b4d502dd13771983831763e9",
        "size": 3686066
    },
    "assets/whale/manifest.json": {
        "sha": "3f257c0d39ba7dc0366f187f6f5ea1b052dd7c20",
        "size": 322
    },
    "assets/whale/motion-turn.png": {
        "sha": "ae0a096e5c1df658bb9626d9c3901e1803c425ac",
        "size": 1755160
    },
    "assets/whale/portrait.png": {
        "sha": "4afdeae2b6f5212c6c17006ff22847bfa5d4d57e",
        "size": 769600
    },
    "assets/whale/story-token.png": {
        "sha": "50edf1bab5aa1de428f6e39bb12c8b8d39fc10f3",
        "size": 4700739
    },
    "src/renderer/motion.js": {
        "sha": "2f04719943e4a4a1a36c7d3132b90ba2d12a0085",
        "size": 12312
    }
}''')
CLIPS = {
    "idle": "idle", "shift": "shift", "wave": "wave", "pat": "happy",
    "walk-right": "right", "walk-left": "left", "drag": "drag",
    "fall": "fall", "land": "land", "sleep": "sleep", "wake": "wake",
    "thinking": "think", "listening": "review", "speaking": "wave", "error": "sad",
}
CC_LICENSE_URL = "https://raw.githubusercontent.com/tegnike/deepseek-chan-vrm/3aceb037df7a8b8126efea89d3a75664d1af868d/LICENSE"
CC_LICENSE_BLOB = "7cdbe0b482f604a06a0988dad8877ae8d9257f7d"


def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def fetch(path):
    target = CACHE / path
    assert target.resolve().is_relative_to(CACHE.resolve())
    if target.exists() and blob_sha(target.read_bytes()) == SOURCES[path]["sha"]:
        return target
    request = urllib.request.Request(RAW + path, headers={"User-Agent": "FinPilot-course-asset-builder"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    assert len(data) == SOURCES[path]["size"], path
    assert blob_sha(data) == SOURCES[path]["sha"], path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def make_clips():
    script = """
const fs=require('node:fs'),vm=require('node:vm');
const ctx={module:{exports:{}}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),ctx,{timeout:1000});
process.stdout.write(JSON.stringify(ctx.module.exports.clips));
"""
    result = subprocess.run(["node", "-e", script, str(CACHE / "src/renderer/motion.js")],
                            capture_output=True, text=True, check=True, timeout=5)
    raw = json.loads(result.stdout)
    selected = {}
    for name, original in CLIPS.items():
        source = raw[original]
        frames = []
        for index, ms in zip(source["frames"], source["times"], strict=True):
            atlas = source["atlas"]
            if atlas == "legacy":
                atlas, index = ("expressions", index - 16) if index >= 16 else ("actions", index)
            frames.append({"atlas": atlas, "source_index": index, "duration_ms": ms})
        selected[name] = {"frames": frames, "loop": source["loop"], "hold": source["hold"],
                          "flip": name == "walk-left", "upstream_clip": original}
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Use only already verified source cache")
    args = parser.parse_args()
    if args.offline:
        for name in SOURCES:
            path = CACHE / name
            assert path.exists() and blob_sha(path.read_bytes()) == SOURCES[name]["sha"], name
    else:
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(fetch, SOURCES))
    clips = make_clips()
    needed = {"idle-front": {0, 1}}
    for clip in clips.values():
        for frame in clip["frames"]:
            needed.setdefault(frame["atlas"], set()).add(frame["source_index"])
    (DEST / "assets").mkdir(parents=True, exist_ok=True)
    (DEST / "licenses").mkdir(parents=True, exist_ok=True)
    outputs, atlas_meta = {}, {}
    for atlas, indexes in sorted(needed.items()):
        path = CACHE / f"assets/whale/{atlas}.png"
        with Image.open(path) as original:
            original = original.convert("RGBA")
            columns = 2 if atlas == "idle-front" else 4
            # Upstream renderer samples width/columns: the HQ idle is 1024px,
            # normal atlases 512px, and story-token 384px despite manifest.cell.
            # Preserve normalized transparent padding, never crop the body.
            cell = original.width // columns
            if original.width % columns or original.height % cell:
                raise ValueError(f"Unexpected upstream atlas shape: {atlas} {original.size}")
            target_cell = 512 if atlas == "idle-front" else 256
            ordered = sorted(indexes)
            target_columns = min(4, len(ordered))
            atlas_image = Image.new("RGBA", (target_columns * target_cell,
                                    math.ceil(len(ordered)/target_columns) * target_cell))
            mapping = {}
            for output_index, index in enumerate(ordered):
                if index < 0 or (index//columns + 1)*cell > original.height:
                    raise ValueError(f"Invalid frame {atlas}:{index}")
                cropped = original.crop((index%columns*cell, index//columns*cell,
                                         (index%columns+1)*cell, (index//columns+1)*cell))
                if target_cell != cell:
                    cropped = cropped.resize((target_cell, target_cell), Image.Resampling.LANCZOS)
                x, y = output_index%target_columns*target_cell, output_index//target_columns*target_cell
                atlas_image.paste(cropped, (x,y))
                mapping[str(index)] = {"x":x, "y":y, "w":target_cell, "h":target_cell}
            out = DEST / "assets" / f"{atlas}.webp"
            atlas_image.save(out, "WEBP", quality=88, method=6, exact=True)
            atlas_meta[atlas] = {"url": f"assets/{atlas}.webp", "frames":mapping,
                                 "width":atlas_image.width, "height":atlas_image.height,
                                 "source_cell":cell, "source_columns":columns,
                                 "upstream_path":f"assets/whale/{atlas}.png"}
            outputs[out.name] = {"bytes":out.stat().st_size, "sha256":hashlib.sha256(out.read_bytes()).hexdigest()}
    # Static fallback: existing portrait, scaled within a 512px box with alpha.
    with Image.open(CACHE / "assets/whale/portrait.png") as portrait:
        portrait = portrait.convert("RGBA")
        portrait.thumbnail((512,512), Image.Resampling.LANCZOS)
        portrait.save(DEST / "assets/portrait.webp", "WEBP", quality=92, method=6, exact=True)
    fallback = DEST / "assets/portrait.webp"
    outputs[fallback.name] = {"bytes":fallback.stat().st_size, "sha256":hashlib.sha256(fallback.read_bytes()).hexdigest()}
    runtime_bytes = sum(item["bytes"] for item in outputs.values())
    assert runtime_bytes <= 12 * 1024 * 1024, runtime_bytes
    manifest = {"version":1, "character":"deepseek-whale-maid", "asset_revision":COMMIT,
                "source_repository":f"https://github.com/{REPO}", "fallback":"assets/portrait.webp",
                "atlases":atlas_meta, "clips":clips, "runtime_image_bytes":runtime_bytes,
                "state_notes":{"speaking":"Existing gesture; not phoneme lip sync.",
                               "error":"Operation state, never a market-risk assessment."}}
    (DEST / "manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for name, output_name in (("LICENSE","YUNYUESAMA-LICENSE.txt"),("ASSET_LICENSE.md","UPSTREAM-ASSET_LICENSE.md")):
        (DEST / "licenses" / output_name).write_bytes((CACHE / name).read_bytes())
    # Full standard legal text, fetched from a pinned mirror because the
    # Creative Commons legalcode endpoint rejects this build host with 403.
    # This fetch copies only the license text, never any VRM/model asset.
    cc_path = DEST / "licenses/CC-BY-NC-SA-4.0.txt"
    if not cc_path.exists() or blob_sha(cc_path.read_bytes()) != CC_LICENSE_BLOB:
        if args.offline:
            raise ValueError("CC license cache missing; run once without --offline")
        with urllib.request.urlopen(CC_LICENSE_URL, timeout=20) as response:
            cc_bytes = response.read()
        assert blob_sha(cc_bytes) == CC_LICENSE_BLOB
        cc_path.write_bytes(cc_bytes)
    provenance = {"source_repository":f"https://github.com/{REPO}", "commit":COMMIT,
        "build_tools":{"pillow":PILLOW_VERSION,"node":"audited motion-table export only"},
        "modifications":["Selected source frames only; original art and identity retained.",
                         "4-column frame repacking, 256px animation cells and 512px idle/fallback, WebP quality88/92.",
                         "No generated new artwork, no 3D, no recoloring or watermark."],
        "sources":{name:{**meta,"sha256":hashlib.sha256((CACHE/name).read_bytes()).hexdigest()} for name,meta in SOURCES.items()},
        "outputs":outputs, "runtime_image_bytes":runtime_bytes,
        "clip_origin":"src/renderer/motion.js final clips, including selected in-between frames and original duration_ms",
        "standard_license_text":{"url":CC_LICENSE_URL,"git_blob_sha":CC_LICENSE_BLOB,
                                 "sha256":hashlib.sha256(cc_path.read_bytes()).hexdigest()},
        "scope":"Noncommercial course/personal demo; source licenses and underlying character conditions retained."}
    (DEST / "provenance.json").write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"runtime_image_bytes":runtime_bytes,"atlases":len(atlas_meta),
                      "clips":len(clips),"destination":"web/companion","pillow":PILLOW_VERSION}))


if __name__ == "__main__":
    main()

