"""Release integrity checks over the actual built, attributed sprite assets."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'web/companion'


def test_pinned_sources_budget_and_output_integrity():
    report=json.loads((BASE/'provenance.json').read_text(encoding='utf-8'))
    assert report['commit']=='7661c8b304c5400701f91da01b1a643a207331de'
    assert report['runtime_image_bytes']<=12*1024*1024
    for filename,item in report['outputs'].items():
        content=(BASE/'assets'/filename).read_bytes()
        assert len(content)==item['bytes']
        assert hashlib.sha256(content).hexdigest()==item['sha256']
    assert sum(item['bytes'] for item in report['outputs'].values())==report['runtime_image_bytes']


def test_all_authored_frames_have_bounds_and_duration():
    manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    for name,clip in manifest['clips'].items():
        assert clip['frames'],name
        for frame in clip['frames']:
            assert frame['duration_ms']>0
            atlas=manifest['atlases'][frame['atlas']]
            bounds=atlas['frames'][str(frame['source_index'])]
            assert bounds['x']>=0 and bounds['y']>=0
            assert bounds['x']+bounds['w']<=atlas['width']
            assert bounds['y']+bounds['h']<=atlas['height']
    assert len(manifest['clips']['wave']['frames'])>=8
    assert len(manifest['clips']['walk-right']['frames'])==16
    assert manifest['clips']['walk-left']['flip'] is True


def test_real_upstream_hq_and_story_cells_are_not_misread_as_manifest_512():
    manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['atlases']['idle-front']['source_cell']==1024
    assert manifest['atlases']['story-token']['source_cell']==384
    assert manifest['clips']['thinking']['frames'][0]['duration_ms']==110


def test_complete_separate_license_and_attribution_retained():
    license_dir=BASE/'licenses'
    for filename in ['ATTRIBUTION.md','YUNYUESAMA-LICENSE.txt','UPSTREAM-ASSET_LICENSE.md','CC-BY-NC-SA-4.0.txt']:
        assert (license_dir/filename).is_file()
    attribution=(license_dir/'ATTRIBUTION.md').read_text(encoding='utf-8')
    for author in ['YunYueSama','上善无形','ZipZipPipe']:
        assert author in attribution
    assert '非商业' in attribution and '7661c8b304c5400701f91da01b1a643a207331de' in attribution
    assert 'Creative Commons' in (license_dir/'CC-BY-NC-SA-4.0.txt').read_text(encoding='utf-8')
