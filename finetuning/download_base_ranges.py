"""Proxy fallback: range-fetch the pinned official model, verify LFS SHA-256."""
import concurrent.futures
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finetuning.model_config import BASE_MODEL_ID, BASE_REVISION, configure_cache


def main():
    home = configure_cache()
    metadata_url = f"https://huggingface.co/api/models/{BASE_MODEL_ID}/revision/{BASE_REVISION}?blobs=true"
    metadata = json.load(urllib.request.urlopen(metadata_url, timeout=30))
    info = next(s for s in metadata["siblings"] if s["rfilename"] == "model.safetensors")
    size, expected = info["size"], info["lfs"]["sha256"]
    folder = home / "hub" / "models--Qwen--Qwen3-0.6B" / "snapshots" / BASE_REVISION
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "model.safetensors"
    progress = folder / "model.safetensors.parts.json"
    completed = set(json.loads(progress.read_text()) if progress.exists() and target.exists() else [])
    chunk = 16*1024*1024
    count = (size+chunk-1)//chunk
    if not target.exists() or target.stat().st_size != size:
        with target.open("wb") as stream:
            stream.truncate(size)
        completed = set()
    lock = threading.Lock()
    start = time.perf_counter()
    url = f"https://huggingface.co/{BASE_MODEL_ID}/resolve/{BASE_REVISION}/model.safetensors?download=true"
    def fetch(part):
        if part in completed:
            return
        first, last = part*chunk, min(size-1,(part+1)*chunk-1)
        for attempt in range(4):
            try:
                req = urllib.request.Request(url+f"&finpilot_part={part}", headers={"Range":f"bytes={first}-{last}"})
                with urllib.request.urlopen(req, timeout=90) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {first}-{last}/{size}":
                        raise RuntimeError("Unexpected model range response")
                    with target.open("r+b") as stream:
                        stream.seek(first)
                        received = 0
                        while True:
                            block = response.read(1024*1024)
                            if not block:
                                break
                            stream.write(block)
                            received += len(block)
                    if received != last-first+1:
                        raise RuntimeError("Incomplete model range")
                with lock:
                    completed.add(part)
                    progress.write_text(json.dumps(sorted(completed)))
                    if len(completed)%8 == 0 or len(completed)==count:
                        print(json.dumps({"model_parts":len(completed),"parts":count,"elapsed_seconds":round(time.perf_counter()-start,1)}),flush=True)
                return
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(1+attempt)
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        list(pool.map(fetch, range(count)))
    digest = hashlib.file_digest(target.open("rb"), "sha256").hexdigest()
    if digest != expected:
        raise RuntimeError("Model failed official LFS integrity check")
    print(json.dumps({"verified_path":str(target),"sha256":digest,"bytes":size},indent=2),flush=True)


if __name__ == "__main__":
    main()
