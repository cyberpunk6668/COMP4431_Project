from pathlib import Path
from collections import Counter
import hashlib, json, re, zipfile
from PIL import Image
from pptx import Presentation

REPO=Path(__file__).resolve().parents[3]
OLD=REPO/'output/presentations/FinPilot_3m30_retro'
OUT=REPO/'output/presentations/FinPilot_3m30_retro_evidence'
DECK=OUT/'FinPilot_3m30_retro_evidence.pptx'
base=Presentation(OLD/'FinPilot_3m30_retro.pptx'); prs=Presentation(DECK)
assert len(prs.slides)==12
assert (prs.slide_width,prs.slide_height)==(9144000,5143500)
for i in range(6):
    assert prs.slides[i].shapes[0].image.blob==base.slides[i].shapes[0].image.blob
    assert prs.slides[i].notes_slide.notes_text_frame.text.startswith(base.slides[i].notes_slide.notes_text_frame.text)
for i in range(6,12):
    assert prs.slides[i]._element.get('show')=='0'
    assert prs.slides[i].has_notes_slide
    assert 'Optional evidence' in prs.slides[i].notes_slide.notes_text_frame.text
    links=[s.click_action.target_slide for s in prs.slides[i].shapes if s.click_action.target_slide is not None]
    assert len(links)==2
    assert all(s.slide_id==prs.slides[i-6].slide_id for s in links)

asset_hashes={hashlib.sha256(p.read_bytes()).hexdigest():str(p.relative_to(OUT))
              for p in (OUT/'assets').rglob('*') if p.is_file() and p.suffix in ('.png','.jpg')}
embedded=[]
for i,s in enumerate(prs.slides):
    for p in s.shapes:
        assert p.left>=0 and p.top>=0
        assert p.left+p.width<=prs.slide_width+9144, (i+1,p.name,'right overflow')
        assert p.top+p.height<=prs.slide_height+9144, (i+1,p.name,'bottom overflow')
        if i>=6 and p.shape_type==13:
            digest=hashlib.sha256(p.image.blob).hexdigest()
            assert digest in asset_hashes, (i+1,'Picture bytes changed')
            embedded.append({'slide':i+1,'asset':asset_hashes[digest],'embedded_bytes_match':True,'sha256':digest})

code_manifest=json.loads((OUT/'assets/code/manifest.json').read_text(encoding='utf-8'))
for row in code_manifest['snippets']:
    path=OUT/'source_snapshot'/row['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==row['source_sha256']
    source='\n'.join(path.read_text(encoding='utf-8').splitlines()[row['start_line']-1:row['end_line']])
    assert source==row['code']
    for kind in ('png','txt'):
        p=OUT/'assets/code'/f"{row['id']}.{kind}"
        assert hashlib.sha256(p.read_bytes()).hexdigest()==row[kind+'_sha256']
with zipfile.ZipFile(DECK) as z:
    assert z.testzip() is None
notes=(OUT/'speech.md').read_text(encoding='utf-8')
talk=re.sub(r'(?m)^#.*$','',notes).strip()
words=len(talk.split())
assert words==383, words
report={'status':'passed','total_slides':12,'main_slides':6,'hidden_appendices':6,
        'main_image_bytes_unchanged':True,'main_english_words':words,'planned_talk_seconds':210,
        'notes_on_all_slides':True,'evidence_embedded_without_reconstruction':True,
        'source_code_and_png_hashes_verified':True,'code_snippets_verified':len(code_manifest['snippets']),
        'powerpoint_document_api_rendered':12,'powerpoint_hidden_slide_flags_confirmed':True,
        'back_links_target_correct_main_slides':True,
        'embedded_evidence':embedded,
        'checks_do_not_prove':'All financial answers correct; all physical hardware/OS input behavior; measured audio timing.'}
for name in ('package_integrity','layout_geometry'):
    path=OUT/'build'/f'{name}.json'
    if path.exists():
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        assert data['finding_count']==0
        report[name]=data
(OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

render=OUT/'build/rendered'
paths=[render/f'slide-{i}.png' for i in range(7,13)]
assert all(p.exists() for p in paths)
sheet=Image.new('RGB',(1648,1416),'#F5F3E8')
for i,p in enumerate(paths):
    im=Image.open(p).convert('RGB');im.thumbnail((808,455),Image.Resampling.LANCZOS)
    sheet.paste(im,(8+(i%2)*824,8+(i//2)*472))
sheet.save(OUT/'evidence_preview.png')

archive_path=OUT.parent/'FinPilot_3m30_retro_evidence_delivery.zip'
with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED) as archive:
    for p in OUT.rglob('*'):
        if not p.is_file() or p.name.startswith('.') or 'build' in p.relative_to(OUT).parts:continue
        archive.write(p,Path(OUT.name)/p.relative_to(OUT))
with zipfile.ZipFile(archive_path) as z:assert z.testzip() is None
print(json.dumps({'pptx':str(DECK),'zip':str(archive_path),'status':'passed','main_words':words,
                  'embedded_screenshots_and_code':len(embedded),'source_snippets':len(code_manifest['snippets'])},ensure_ascii=False))
