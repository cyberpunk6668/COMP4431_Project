"""Optional range downloader for the large OFFICIAL Windows CUDA wheel.

Some proxies stall multi-GB single responses. All bytes are fetched from the
official PyTorch CDN and the full file is checked against its official index
SHA-256 before pip may install it. No external credentials are involved.
"""
import concurrent.futures
import hashlib
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

FILENAME = "torch-2.7.1+cu128-cp311-cp311-win_amd64.whl"
URL = "https://download-r2.pytorch.org/whl/cu128/" + urllib.parse.quote(FILENAME)
SIZE = 3273066072
CHUNK = 16 * 1024 * 1024


def main():
    index = urllib.request.urlopen("https://download.pytorch.org/whl/cu128/torch/", timeout=30).read().decode()
    match = next(re.finditer(r'href="([^"]*torch-2\.7\.1(?:%2B|\+)cu128-cp311-cp311-win_amd64\.whl)#sha256=([a-f0-9]{64})"', index), None)
    if not match:
        raise RuntimeError("Could not find official SHA-256; do not proceed without integrity check")
    expected = match[2]
    cache = Path(os.environ.get("FINPILOT_HF_HOME", str(Path.home()/".cache"/"huggingface"))).parent / "wheels"
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / FILENAME
    progress = cache / (FILENAME + ".parts.json")
    completed = set(json.loads(progress.read_text()) if progress.exists() and target.exists() else [])
    if not target.exists() or target.stat().st_size != SIZE:
        with target.open("wb") as stream:
            stream.truncate(SIZE)
        completed = set()
    lock = threading.Lock()
    start = time.perf_counter()
    count = (SIZE + CHUNK - 1)//CHUNK

    def fetch(part):
        if part in completed:
            return
        first, last = part * CHUNK, min(SIZE-1, (part+1)*CHUNK-1)
        for attempt in range(4):
            try:
                request = urllib.request.Request(URL+f"?finpilot_part={part}&retry={attempt}&resume=2", headers={"Range": f"bytes={first}-{last}"})
                with urllib.request.urlopen(request, timeout=90) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {first}-{last}/{SIZE}":
                        raise RuntimeError("Range response did not match requested bytes")
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
                        raise RuntimeError("Incomplete range response")
                with lock:
                    completed.add(part)
                    progress.write_text(json.dumps(sorted(completed)))
                    if len(completed)%8 == 0 or len(completed)==count:
                        print(json.dumps({"downloaded_parts":len(completed),"parts":count,"elapsed_seconds":round(time.perf_counter()-start,1)}),flush=True)
                return
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(1 + attempt)

    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
        list(executor.map(fetch, range(count)))
    digest = hashlib.file_digest(target.open("rb"), "sha256").hexdigest()
    if digest != expected:
        raise RuntimeError(f"Integrity check failed. Got {digest}, expected {expected}")
    print(json.dumps({"verified_path":str(target),"sha256":digest,"bytes":SIZE},indent=2),flush=True)


if __name__ == "__main__":
    main()
