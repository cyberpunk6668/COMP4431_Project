"""Independent learning-demo release; preserve other tasks' general packager.

The runtime needs curated knowledge.json, not unreviewed raw HTML download
caches. Keep those original caches in the workspace, outside this deliverable.
"""
from pathlib import Path
import hashlib
import json
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.package_submission import (APPLICATION_VERSION,NATIVE_HOST_VERSION,
    V16_REQUIRED_FILES,V17_REQUIRED_FILES,PORTABLE,PORTABLE_BYTES,PORTABLE_SHA256,
    SECRET_PATTERNS,scan_stream,file_sha256,collect_paths as shared_paths)

OUTPUT=ROOT/'dist/FinPilot_options_learning_v17.zip'
RAW_CACHES={'data/news_sources'}


def collect_paths():
    return [path for path in shared_paths() if not any(path.is_relative_to(ROOT/tree) for tree in RAW_CACHES)]


def package():
    paths=collect_paths()
    frozen={p.relative_to(ROOT).as_posix():file_sha256(p) for p in paths}
    for path in paths:
        with path.open('rb') as stream:scan_stream(stream,path.relative_to(ROOT).as_posix())
    OUTPUT.parent.mkdir(exist_ok=True)
    partial=OUTPUT.with_suffix('.zip.partial')
    with zipfile.ZipFile(partial,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in paths:archive.write(path,'FinPilot/'+path.relative_to(ROOT).as_posix())
    current=collect_paths()
    assert {p.relative_to(ROOT).as_posix() for p in current}==set(frozen),'Concurrent file-set change; partial retained'
    assert all(file_sha256(p)==frozen[p.relative_to(ROOT).as_posix()] for p in paths),'Concurrent source change; partial retained'
    with zipfile.ZipFile(partial) as archive:
        for name,digest in frozen.items():
            with archive.open('FinPilot/'+name) as stream:
                assert hashlib.file_digest(stream,'sha256').hexdigest()==digest,'Packaged bytes differ from source snapshot'
    partial.replace(OUTPUT)
    source_manifest=OUTPUT.parent/'options_learning_source_manifest_v17.json'
    source_manifest.write_text(json.dumps({'application_version':APPLICATION_VERSION,'source_sha256':frozen},indent=2),encoding='utf-8')
    result={'file':OUTPUT.name,'files':len(paths),'bytes':OUTPUT.stat().st_size,'sha256':file_sha256(OUTPUT),
        'application_version':APPLICATION_VERSION,'native_host_version':NATIVE_HOST_VERSION,
        'stable_source_snapshot_verified':True,'source_manifest':source_manifest.name,
        'secrets_excluded':True,'local_database_excluded':True,'raw_source_caches_excluded':sorted(RAW_CACHES),
        'desktop_portable':{'version':NATIVE_HOST_VERSION,'path':PORTABLE,'bytes':PORTABLE_BYTES,'sha256':PORTABLE_SHA256},
        'python_runtime_bundled':False,'requires_existing_finpilot_python_environment':True}
    (OUTPUT.parent/'options_learning_submission_manifest_v17.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':package()
