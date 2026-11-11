from pathlib import Path
from collections import defaultdict
import hashlib, json, re, zipfile
from PIL import Image
from pptx import Presentation

REPO=Path(__file__).resolve().parents[3]
OUT=REPO/'output/presentations/FinPilot_English_Grouped'
PPTX=OUT/'FinPilot_English_Grouped.pptx'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
prs=Presentation(PPTX);tracks=json.loads((OUT/'talk_tracks.json').read_text(encoding='utf-8'))
assert len(prs.slides)==13 and len(tracks)==13
assert [t['speaker'] for t in tracks]==[1,1,2,2,2,2,3,3,3,4,4,4,4]
assert sum(t['seconds'] for t in tracks)==210
assert (prs.slide_width,prs.slide_height)==(9144000,5143500)
han=re.compile(r'[\u3400-\u9fff]')
for i,s in enumerate(prs.slides):
    assert s._element.get('show')!='0'
    assert s.has_notes_slide
    assert s.notes_slide.notes_text_frame.text.startswith(tracks[i]['text'])
    assert not han.search(s.notes_slide.notes_text_frame.text)
    for p in s.shapes:
        assert p.left>=0 and p.top>=0
        assert p.left+p.width<=prs.slide_width+9144,(i+1,p.name,'right')
        assert p.top+p.height<=prs.slide_height+9144,(i+1,p.name,'bottom')
        if p.has_text_frame:assert not han.search(p.text),(i+1,p.text)

original=Presentation(REPO/'output/presentations/FinPilot_3m30_retro/FinPilot_3m30_retro.pptx')
for new,old in [(1,1),(3,2),(5,3),(7,4),(12,6)]:
    assert prs.slides[new-1].shapes[0].image.blob==original.slides[old-1].shapes[0].image.blob

m=json.loads((OUT/'assets/code/manifest.json').read_text(encoding='utf-8'))
used_colors=set()
for row in m['snippets']:
    path=OUT/'source_snapshot'/row['path']
    assert sha(path)==row['source_sha256']
    code='\n'.join(path.read_text(encoding='utf-8').splitlines()[row['start_line']-1:row['end_line']])
    assert code==row['code']
    assert not han.search(code)
    groups=defaultdict(list)
    for v in row['visual_row_map']:groups[v['source_line']].append(v)
    reconstructed=[]
    for n,parts in groups.items():
        prefix=parts[0].get('removed_common_indent','')
        reconstructed.append(prefix+''.join(v['text'] for v in parts))
    assert '\n'.join(reconstructed)==code
    for ext in ('png','txt'):assert sha(OUT/'assets/code'/f"{row['id']}.{ext}")==row[ext+'_sha256']
    for token in row['syntax_color_runs']:used_colors.add(token['color'])
assert len(used_colors)>=6
for row in m['report_extracts']:
    report_path=OUT/row['packaged_report_snapshot'];assert sha(report_path)==row['report_sha256']
    source=json.loads(report_path.read_text(encoding='utf-8'))
    selected=next(v for v in source['turns'][0]['evidence_values'] if v['id']=='h.change.oi_total')
    assert selected==row['object']
    assert json.loads(row['display_text'])==selected
    assert not han.search(row['display_text'])
    for ext in ('png','txt'):assert sha(OUT/'assets/code'/f"{row['id']}.{ext}")==row[ext+'_sha256']

assets={sha(p):str(p.relative_to(OUT)) for p in (OUT/'assets').rglob('*') if p.suffix.lower() in ('.png','.jpg')}
for s in prs.slides:
    for p in s.shapes:
        if p.shape_type==13:assert hashlib.sha256(p.image.blob).hexdigest() in assets
with zipfile.ZipFile(PPTX) as z:assert z.testzip() is None

render=OUT/'build/rendered';assert all((render/f'slide-{i}.png').exists() for i in range(1,14))
selected=[2,4,6,8,9,11]
preview=Image.new('RGB',(1648,1416),'#F5F3E8')
for i,n in enumerate(selected):
    im=Image.open(render/f'slide-{n}.png').convert('RGB');im.thumbnail((808,455),Image.Resampling.LANCZOS)
    preview.paste(im,(8+(i%2)*824,8+(i//2)*472))
preview.save(OUT/'preview.png')
for name in ('package_integrity','layout_geometry'):
    report=OUT/'build'/f'{name}.json'
    if report.exists():assert json.loads(report.read_text(encoding='utf-8-sig'))['finding_count']==0
validation={'status':'passed','slide_count':13,'all_slides_visible':True,'groups':{'overview':[1,2],'rag':[3,6],'frontend':[7,9],'companion':[10,13]},
    'english_slide_text_and_notes':True,'visible_raster_content_manually_reviewed_in_english':True,
    'colored_code_snippets':len(m['snippets']),'colored_report_extracts':len(m['report_extracts']),
    'source_text_and_wrap_reconstruction_verified':True,'syntax_palette_colors':sorted(used_colors),
    'english_words':sum(t['words'] for t in tracks),'planned_seconds':210,'native_powerpoint_rendered_visible_slides':13,
    'five_original_concept_images_unchanged':True,'avatar_credit_edited_to_english':True,
    'not_claimed':['Measured audio timing','Entire application fully localized','New cloud model or broker acceptance runs']}
(OUT/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
archive=OUT.parent/'FinPilot_English_Grouped_delivery.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in OUT.rglob('*'):
        if p.is_file() and 'build' not in p.relative_to(OUT).parts:z.write(p,Path(OUT.name)/p.relative_to(OUT))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
print(json.dumps({'pptx':str(PPTX),'zip':str(archive),'slides':13,'words':validation['english_words'],'status':'passed'},ensure_ascii=False))
