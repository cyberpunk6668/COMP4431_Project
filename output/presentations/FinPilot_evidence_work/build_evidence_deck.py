from pathlib import Path
import hashlib
import json
import shutil
import textwrap
import zipfile
from datetime import datetime, timezone
from PIL import Image
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.xmlchemy import OxmlElement
from pptx.oxml.ns import qn

WORK = Path(__file__).resolve().parent
REPO = WORK.parents[2]
OLD = REPO / 'output/presentations/FinPilot_3m30_retro'
OUT = REPO / 'output/presentations/FinPilot_3m30_retro_evidence'
ASSETS = OUT / 'assets'
BUILD = OUT / 'build'
for p in (OUT, ASSETS, BUILD): p.mkdir(parents=True, exist_ok=True)
shutil.copytree(WORK/'assets', ASSETS, dirs_exist_ok=True)
shutil.copytree(WORK/'source_snapshot', OUT/'source_snapshot', dirs_exist_ok=True)
for name in ('rag_evidence.json','rag_evidence.md','ui_avatar_evidence.json','ui_avatar_evidence.md'):
    shutil.copy2(WORK/name, OUT/name)
for name in ('speech.md','speaker_1.md','speaker_2.md','speaker_3.md','speaker_4.md','speaker_guide.md','source_audit.md'):
    shutil.copy2(OLD/name, OUT/name)
shutil.copytree(OLD/'character_licenses', OUT/'character_licenses', dirs_exist_ok=True)

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest = {'created_at_utc':datetime.now(timezone.utc).isoformat(),
    'capture_method':'Current localhost pages captured through browser tool. Saved actual-cloud run screenshots copied from their reported paths.',
    'new_model_calls':0,'new_broker_requests':0,
    'source_snapshot_policy':'Complete whitelisted source files frozen during this update; slide line numbers refer to that capture-time version, not later concurrent edits.',
    'main_slide_count':6,'appendix_slide_count':6,'main_talk_seconds':210,
    'screenshots':[], 'code_extraction_policy':'Original continuous source lines. Visual wrapping only. Line numbers, original text and SHA256 in code manifest.'}
for p in ASSETS.glob('*.jpg'):
    manifest['screenshots'].append({'asset':str(p.relative_to(OUT)), 'sha256':sha(p),'kind':'fresh browser capture','pixels':list(Image.open(p).size),
        'url':'http://127.0.0.1:8000/' if p.name.startswith('homepage') else 'http://127.0.0.1:8000/workspace'})

RUN = REPO/'reports/screenshots/pet-cloud-v15/20261111T125430678673Z'
for source, dest in [('1-workspace.png','cloud_workspace_actual.png'),('2-native_pet.png','cloud_native_actual.png')]:
    shutil.copy2(RUN/source, ASSETS/dest)
    manifest['screenshots'].append({'asset':'assets/'+dest,'sha256':sha(ASSETS/dest),'kind':'saved actual DeepSeek acceptance run',
        'original':str((RUN/source).relative_to(REPO)), 'pixels':list(Image.open(ASSETS/dest).size),
        'scope':'Archived IBKR data; actual packaged Electron renderer or Edge, not a new call made for this deck.'})

def crop_asset(source, target, rect):
    image=Image.open(ASSETS/source); image.crop(rect).save(ASSETS/target)
    manifest['screenshots'].append({'asset':'assets/'+target,'sha256':sha(ASSETS/target),'kind':'unaltered rectangular crop',
        'original_asset':'assets/'+source,'original_sha256':sha(ASSETS/source),'crop_xyxy':list(rect),
        'pixel_editing':'Crop only; no painted labels, changed text or AI reconstruction.'})

crop_asset('cloud_workspace_actual.png','rag_missing_oi_crop.png',(292,280,1085,369))
crop_asset('cloud_workspace_actual.png','rag_source_controls_crop.png',(295,690,1075,819))
native=Image.open(ASSETS/'cloud_native_actual.png')
crop_asset('cloud_native_actual.png','native_host_crop.png',native.getbbox())

sources=OUT/'evidence_sources'; sources.mkdir(exist_ok=True)
for source in ('reports/pet_cloud_v15.json','reports/companion_acceptance_v15.json','reports/native_companion_v15.json','reports/expert_retrieval_holdout_v14.json'):
    shutil.copy2(REPO/source,sources/Path(source).name)
manifest['saved_reports']=[{'path':str(p.relative_to(OUT)),'sha256':sha(p)} for p in sources.iterdir()]
actual=json.loads((sources/'companion_acceptance_v15.json').read_text(encoding='utf-8'))
assert actual['verification']['final_actual_models']['status']=='passed'
cloud=json.loads((sources/'pet_cloud_v15.json').read_text(encoding='utf-8'))
assert cloud['counters']['confirmed_deepseek_replies']==2

code_dir=ASSETS/'code'
def code(name):
    matches=list(code_dir.glob(name+'.png')); assert len(matches)==1,(name,matches)
    return matches[0]

prs=Presentation(OLD/'FinPilot_3m30_retro.pptx')
BG='F5F3E8'; INK='283F4C'; MINT='95E1D3'; CORAL='FF6B6B'; GOLD='F9CA24'; MUTED='596C77'
def rgb(hex):return RGBColor.from_string(hex)
def rect(s,x,y,w,h,fill=None,line=INK,radius=False):
    a=s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill:a.fill.solid();a.fill.fore_color.rgb=rgb(fill)
    else:a.fill.background()
    if line:a.line.color.rgb=rgb(line);a.line.width=Pt(1.5)
    else:a.line.fill.background()
    if radius:a.adjustments[0]=.12
    style=a._element.find(qn('p:style'))
    if style is not None:
        effect=style.find(qn('a:effectRef'))
        if effect is not None:effect.set('idx','0')
    a._element.spPr.append(OxmlElement('a:effectLst'))
    return a
def text(s,content,x,y,w,h,size=14,bold=False,color=INK,font='Arial',fill=None):
    if fill:rect(s,x,y,w,h,fill,None)
    a=s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf=a.text_frame;tf.clear();tf.word_wrap=True
    tf.margin_left=tf.margin_right=Inches(.025);tf.margin_top=tf.margin_bottom=0
    for i,line in enumerate(content.split('\n')):
        p=tf.paragraphs[0] if i==0 else tf.add_paragraph();p.text=line
        p.font.name=font;p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=rgb(color)
        p.space_after=Pt(4)
    return a
def picture(s,path,x,y,w,h,frame=False):
    path=Path(path);iw,ih=Image.open(path).size;scale=min(w/iw,h/ih);pw,ph=iw*scale,ih*scale
    left,top=x+(w-pw)/2,y+(h-ph)/2
    if frame:rect(s,left-.025,top-.025,pw+.05,ph+.05,'FFFFFF',INK,False)
    p=s.shapes.add_picture(str(path), Inches(left), Inches(top), Inches(pw), Inches(ph))
    return p
def note(s,content):s.notes_slide.notes_text_frame.text=content
def page(letter,title,subtitle,back,footer):
    s=prs.slides.add_slide(prs.slide_layouts[6]);s.background.fill.solid();s.background.fill.fore_color.rgb=rgb(BG)
    s._element.set('show','0')
    text(s,title,.35,.27,9.3,.56,size=29,bold=False,font='Cooper Black')
    text(s,subtitle,.39,.89,9.1,.30,size=11,color=MUTED)
    rect(s,.39,1.21,.50,.055,GOLD,None)
    text(s,footer,.39,5.31,8.1,.22,size=7.8,color=MUTED)
    btn=rect(s,8.65,5.26,.96,.25,MINT,INK,True)
    label=text(s,'Back to talk',8.69,5.285,.88,.18,size=8.4,bold=True)
    btn.click_action.target_slide=prs.slides[back-1]
    label.click_action.target_slide=prs.slides[back-1]
    manifest.setdefault('appendices',[]).append({'letter':letter,'slide':len(prs.slides),'title':title,'supports_main_slide':back,'hidden_by_default':True})
    return s

s=page('A','FinPilot, running locally','A  /  Actual project homepage in two viewports',1,'Live source: http://127.0.0.1:8000/  ·  Browser capture during this update')
picture(s,ASSETS/'homepage_desktop_live.jpg',.40,1.40,6.45,3.62,True)
picture(s,ASSETS/'homepage_live.jpg',7.04,1.40,2.54,3.62,True)
text(s,'Desktop homepage',.47,5.10,4,.18,9.5,bold=True)
text(s,'Narrow viewport',7.08,5.10,2.4,.18,9.5,bold=True)
note(s,'Optional evidence for Speaker 1. This is the actual project homepage, not an illustration or recreated UI. The desktop screenshot was captured at a requested 1440×900 viewport; the default narrow viewport capture is 584×849. These images show rendered appearance, not an animation performance benchmark. URL: http://127.0.0.1:8000/. See assets and evidence_manifest.json for original dimensions and hashes.')

s=page('B','RAG: two routes, one ranking','B  /  Source code extracted directly from the current repository',2,'Code: app/expert_knowledge.py:144–146  ·  Evaluation: reports/expert_retrieval_holdout_v14.json')
picture(s,code('rag_rrf'),.40,1.43,6.45,3.66,True)
text(s,'87.04%',7.03,1.68,2.5,.62,33,bold=True,font='Cooper Black')
text(s,'Recall@4',7.05,2.37,2.3,.36,20,bold=True)
text(s,'18 relevant queries\n24 questions in total',7.05,2.91,2.25,.72,13)
rect(s,7.04,3.89,2.4,.72,MINT,INK,True)
text(s,'Same-team labels.\nRetrieval only.',7.13,4.02,2.2,.51,12,bold=True)
note(s,'Optional evidence for Speaker 2. The screenshot displays consecutive original lines 144–146 from app/expert_knowledge.py: independent term and character rankings, then sum(1/(60+rank)) reciprocal rank fusion. Visual wrapping does not change code. The whole retriever SHA256 matches the saved v14 holdout report. Recall@4=0.870370 over 18 relevant queries; six irrelevant queries make 24 total. This is a small same-team-labelled retrieval evaluation, not answer accuracy or an external benchmark. Source and image hashes are in assets/code/manifest.json and rag_evidence.json.')

s=page('C','RAG: evidence behind a claim','C  /  Real saved DeepSeek output alongside the citation-support check',3,'UI: saved actual-model run 2026-11-11  ·  Code: app/expert_grounding.py:210–214')
text(s,'Missing OI stays missing',.43,1.43,4.6,.37,17,bold=True)
picture(s,ASSETS/'rag_missing_oi_crop.png',.43,1.98,4.65,.78,True)
text(s,'Local evidence and expert sources',.43,3.02,4.6,.34,14,bold=True)
picture(s,ASSETS/'rag_source_controls_crop.png',.43,3.47,4.65,.97,True)
text(s,'Unchanged crops from the real archived-report answer.',.43,4.67,4.7,.32,10,color=MUTED)
picture(s,code('rag_support'),5.36,1.43,4.20,3.62,True)
note(s,'Optional evidence for Speaker 2. The two left images are unaltered rectangular crops from reports/screenshots/pet-cloud-v15/20261111T125430678673Z/1-workspace.png. The second paragraph explicitly retains missing open interest as missing, with separate expert and local references. The lower crop shows local evidence and expert-source controls. The code at app/expert_grounding.py:210–214 checks recognized claim facets against cited supports; it is a bounded rule check, not general semantic entailment. Full original screenshot and crop coordinates are included in the evidence package.')

s=page('D','Frontend: responsive by design','D  /  Current workspace at desktop and mobile breakpoints',4,'Live UI: /workspace  ·  Async guard: web/app.js:1217  ·  Video fallback: Hero.tsx:137–148 (source pack)')
picture(s,ASSETS/'workspace_desktop_live.jpg',.40,1.46,4.86,2.38,True)
picture(s,ASSETS/'workspace_mobile_drawer_live.jpg',5.50,1.44,1.28,2.38,True)
text(s,'One workspace,\ntwo layouts',7.05,1.66,2.30,.86,21,bold=True,font='Cooper Black')
text(s,'Desktop columns\nMobile drawer\nCollapsible assistant',7.08,2.79,2.2,1.05,13)
text(s,'Request IDs keep old responses from replacing new input',.43,3.90,8.9,.25,11.5,bold=True)
picture(s,code('request_guard_wide'),.43,4.18,9.12,1.02,False)
note(s,'Optional evidence for Speaker 3. Fresh actual /workspace captures in the current app: desktop viewport requested 1440×900 and mobile drawer 390×844. The saved conversation was read, not newly generated. No /api/chat or broker collection was requested for this update. The source snippet is the single continuous original line web/app.js:1217, including if(sequence===state.calculationSequence)showCalculation(result). It is visually wrapped, not shortened. This unchanged guard moved by five lines during concurrent repository updates; complete whitelisted files are frozen in source_snapshot/. Saved acceptance reports are evidence for their recorded versions, not a claim of rerunning all checks on every concurrent edit. Related complete snippets, including video timeout and persistent poster, are in assets/code.')

s=page('E','Companion: real renderer and host','E  /  Actual packaged Electron capture and the shared Canvas drawing code',5,'Saved host capture: reports/screenshots/pet-cloud-v15/20261111T125430678673Z/2-native_pet.png')
picture(s,ASSETS/'native_host_crop.png',.43,1.42,3.55,3.66,True)
picture(s,code('atlas_draw_short'),4.24,1.42,5.30,3.66,True)
note(s,'Optional evidence for Speaker 4. The left is an alpha-bounds crop of the actual packaged Electron renderer captured in the final real-cloud run. Transparency was cropped only; no other desktop application or user desktop was captured. This image does not prove physical click-through or mouse hardware certification. The right is original web/companion/renderer.js:142–145, showing Canvas drawImage with exact source-frame bounds. The larger 136–145 snippet including lazy atlas loading is preserved in assets/code. The character is attributed reused 2D artwork, not a newly developed 3D model. Credits: YunYueSama / 上善无形 / ZipZipPipe. Underlying character derivatives: CC BY-NC-SA 4.0 plus upstream contribution attribution conditions. See character_licenses/.')

s=page('F','Sync: code and a verified run','F  /  Connection guards with the saved actual-model acceptance report',6,'Code: web/companion/client.js:41–44  ·  Report: reports/companion_acceptance_v15.json')
picture(s,code('session_guard_short'),.42,1.43,5.33,3.70,True)
text(s,'Saved real-cloud run',6.01,1.49,3.55,.37,17,bold=True)
rows=[('DeepSeek replies','2 / 2'),('Generations','3'),('Citation / schema repairs','1'),('New IBKR requests','0')]
for i,(label,value) in enumerate(rows):
    y=2.01+i*.51
    if i%2==0:rect(s,6.01,y,3.52,.45,'E4EEE4',None)
    text(s,label,6.10,y+.10,2.48,.25,11.4)
    text(s,value,8.80,y+.055,.65,.31,17,bold=True)
rect(s,6.02,4.22,3.51,.70,GOLD,None,True)
text(s,'Archived data.\nPhysical input checks remain limited.',6.12,4.31,3.28,.51,11,bold=True)
note(s,'Optional evidence for Speaker 4. Current-source web/companion/client.js:41–44 reloads the selected saved session via HTTP and discards stale epoch/generation/session/serial responses. Full context 35–44 and SSE transport 85–94 are separately extracted in assets/code. The right-hand values are a clearly labelled extraction, not a screenshot of invented JSON: reports/companion_acceptance_v15.json at $.verification.final_actual_models reports passed, 2 answer_turns, 3 generations, 1 schema_repairs and 0 new_ib_requests. reports/pet_cloud_v15.json confirms 2 confirmed DeepSeek replies. The earlier failed run remains historical. This update did not rerun models or broker calls. Native acceptance remains passed_with_manual_hardware_limits and physical_input_certified=false.')

for i in range(6):
    old_note=prs.slides[i].notes_slide.notes_text_frame.text
    prs.slides[i].notes_slide.notes_text_frame.text=old_note+'\n\nEvidence reference (not spoken): appendix '+chr(65+i)+', slide '+str(7+i)+'. Hidden backup slide; optional use during Q&A. Source details and hashes are in the evidence package.'

prs.core_properties.title='FinPilot — project evidence edition'
prs.core_properties.subject='Six-slide talk plus six hidden evidence appendices'
prs.save(OUT/'FinPilot_3m30_retro_evidence.pptx')

guide=(OUT/'speaker_guide.md').read_text(encoding='utf-8')
old='当前代码已实现明确连接 SID、SSE 通知、权威重读及迟到响应过滤。已有受控同步与宿主检查；本次读取的真实云跨端报告在第二轮失败，原生报告是插桩检查，未证明物理鼠标穿透全部成功。因此演讲强调实现机制，不声称最终原生与真实模型验收全部通过。'
new='当前代码已实现明确连接 SID、SSE 通知、权威重读及迟到响应过滤。最新保存的真实云跨端验收已通过：两轮均确认 DeepSeek 回复，合计三次生成、一次修正、零新增 IB 请求。先前失败是保留的历史尝试。原生验收仍有手动硬件限制，physical_input_certified=false，因此不声称物理鼠标穿透、拖动或所有设备全部认证。本次制作只读取报告，未重新运行模型验收。'
assert old in guide
guide=guide.replace(old,new)
guide+='\n## 新增证据页使用方式\n\n主讲仍为第 1–6 页、383 个英文词、目标 3 分 30 秒。第 7–12 页为隐藏证据附录，常规放映自动跳过。需要展示时，在 PowerPoint 放映中输入对应页码并按 Enter；每页右下角可回到对应主讲页。也可在编辑视图取消隐藏。\n\n| 主讲页 | 证据附录 | 内容 |\n|---|---|---|\n| 1 | 7 · A | 当前主页桌面及窄视口真实截图 |\n| 2 | 8 · B | 当前 RRF 排名融合代码与保留集检索指标 |\n| 3 | 9 · C | 真实回答中的缺失字段/引用控件与支持主题校验代码 |\n| 4 | 10 · D | 实际桌面和移动抽屉布局、请求序号代码 |\n| 5 | 11 · E | 实际 Electron 截图、Canvas 图集绘制代码 |\n| 6 | 12 · F | 会话重读与过期响应过滤、最新真实模型验收记录 |\n\n证据页用于指图和答辩，不需要逐行朗读。若在 3 分半内穿插展示，请用对应证据页替代部分主讲页的展示时间，不要在主讲结束后把六页全部再讲一遍。所有截图保持原样，裁剪坐标、代码行号和 SHA256 可在 evidence_manifest.json 与 assets/code/manifest.json 核查。\n'
(OUT/'speaker_guide.md').write_text(guide,encoding='utf-8')
speaker_evidence={1:'第 7 页：真实主页两种视口截图。',2:'第 8 页：RRF 代码及检索指标。第 9 页：真实回答与引用支持校验。',3:'第 10 页：桌面/移动抽屉截图和请求序号代码。',4:'第 11 页：实际 Electron 与 Canvas 代码。第 12 页：会话同步代码和最新真实云验收。'}
for n,description in speaker_evidence.items():
    p=OUT/f'speaker_{n}.md'
    p.write_text(p.read_text(encoding='utf-8')+'\n## 对应证据页（不额外朗读）\n\n'+description+' 放映时按页码再按 Enter，可跳到隐藏附录；点击右下角 Back to talk 回到主讲。主讲英文正文与原时长保持一致。\n',encoding='utf-8')
outline=(OLD/'outline.md').read_text(encoding='utf-8')
outline+='\n## 本次真实证据补充\n\n用户要求在现有项目基础上加入真实界面与仓库代码证据。保留六页主讲图片和3分半讲述，新增六页默认隐藏的证据附录，逐一对应主讲第1至6页。素材使用新截图、既存真实验收截图、连续原代码提取和已保存报告。截图原样直接嵌入，不使用AI重绘。精确映射、路径、裁剪和哈希见 evidence_manifest.json。第7至12页分别为主页、RRF检索、引用校验、前端响应式、原生助手/渲染、同步与真实验收。\n'
(OUT/'outline.md').write_text(outline,encoding='utf-8')
audit=(OUT/'source_audit.md').read_text(encoding='utf-8')
audit=audit.replace('- `reports/pet_cloud_v15-20261111T124026586357Z.json`: failed at second native-pet turn, two HTTP chat requests, one confirmed DeepSeek reply. Avoid a claim of complete real-cloud acceptance.', '- Historical failed attempt: `reports/pet_cloud_v15-20261111T124026586357Z.json`. The newer final `reports/pet_cloud_v15.json` passes both actual DeepSeek turns. `reports/companion_acceptance_v15.json` records 3 generations, 1 repair and 0 new IB requests. Physical pointer/hardware certification remains limited; this deck update did not rerun the tests.')
(OUT/'source_audit.md').write_text(audit,encoding='utf-8')
(OUT/'evidence_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'README.md').write_text('''# FinPilot · 真实证据补充版

正式文件：FinPilot_3m30_retro_evidence.pptx。共 12 页：原有六页主讲 + 六页默认隐藏的技术证据附录。主讲仍为约 3 分半。附录右下角有回到对应主讲页的链接。

沿用 GitHub codex-ppt 制作的原始复古扁平插画主讲页。新增证据页采用同配色和复古标题，原始截图与代码图作为独立图片直接嵌入，避免生图重画证据。原有六张主讲图片的嵌入字节保持一致。新增页正文和标题可以编辑，截图内部文字保持原图。

speaker_guide.md 含四人英文讲稿、中文提示、证据页映射及跳转说明。speaker_1.md 至 speaker_4.md 是每人独立讲稿。speech.md 是六页英文口述正文。每页 PPT 备注含来源说明。

assets/ 为真实截图、裁剪及代码提取图片；代码图片来自连续原始行，允许视觉折行。原始 txt、源文件 SHA256、起止行号和图像 SHA256 均在 assets/code/manifest.json。

evidence_sources/ 保留本次采用的原始验收报告。evidence_manifest.json 保留截图原始路径、类型、裁剪坐标和哈希。rag_evidence.* 和 ui_avatar_evidence.* 是事实核查记录。

最新真实云端验收两轮已通过；原生物理鼠标及硬件覆盖仍有明确限制。本次只读现有报告并截图，不新增模型或 IBKR 调用。截图不会证明金融答案总是正确，检索指标也不是答案准确率。

角色署名与完整素材许可见 character_licenses/。用于本次非商业课程展示。
''',encoding='utf-8')
print(json.dumps({'pptx':str(OUT/'FinPilot_3m30_retro_evidence.pptx'),'slides':len(prs.slides),'hidden_appendices':6,'manifest':str(OUT/'evidence_manifest.json')},ensure_ascii=False))
