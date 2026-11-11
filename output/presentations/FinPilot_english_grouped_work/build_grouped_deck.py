from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil, re
from PIL import Image
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.xmlchemy import OxmlElement
from pptx.oxml.ns import qn

WORK=Path(__file__).resolve().parent
REPO=WORK.parents[2]
OUT=REPO/'output/presentations/FinPilot_English_Grouped'
OLD=REPO/'output/presentations/FinPilot_3m30_retro'
PREV=REPO/'output/presentations/FinPilot_3m30_retro_evidence'
ASSETS=OUT/'assets'; BUILD=OUT/'build'
for p in (OUT,ASSETS,BUILD,ASSETS/'concept',ASSETS/'ui',OUT/'raw_captures'):p.mkdir(parents=True,exist_ok=True)
shutil.copytree(WORK/'assets/code',ASSETS/'code',dirs_exist_ok=True)
shutil.copytree(WORK/'source_snapshot',OUT/'source_snapshot',dirs_exist_ok=True)
shutil.copytree(WORK/'evidence_sources',OUT/'evidence_sources',dirs_exist_ok=True)
shutil.copytree(OLD/'character_licenses',OUT/'character_licenses',dirs_exist_ok=True)
for p in (WORK/'assets/ui').glob('*.jpg'):shutil.copy2(p,OUT/'raw_captures'/p.name)
for name in ('companion_acceptance_v15.json','expert_retrieval_holdout_v14.json','native_companion_v15.json'):
    shutil.copy2(PREV/'evidence_sources'/name,OUT/'evidence_sources'/name)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest={'created_at_utc':datetime.now(timezone.utc).isoformat(),'visible_language':'English',
    'new_model_calls':0,'new_broker_requests':0,'native_calculator_request':True,
    'page_order':'Overview, RAG, Frontend, Companion. Concept and corresponding evidence are adjacent.',
    'no_hidden_slides':True,'ui_capture_policy':'Actual native English UI regions cropped from real browser captures. Chinese history titles, locale-switch controls and bilingual result summaries are outside the displayed crop. No labels or values repainted.',
    'source_policy':'Frozen whitelisted source files; syntax highlighting changes appearance only. Original TXT and hashes retained.',
    'screenshot_crops':[]}
def crop(source,name,box):
    p=OUT/'raw_captures'/source;dest=ASSETS/'ui'/name
    im=Image.open(p);assert box[2]<=im.width and box[3]<=im.height
    im.crop(box).save(dest)
    manifest['screenshot_crops'].append({'asset':str(dest.relative_to(OUT)),'sha256':sha(dest),'raw_capture':str(p.relative_to(OUT)),
        'raw_sha256':sha(p),'crop_xyxy':list(box),'edit':'Unaltered rectangular crop only'})
    return dest
workspace=crop('workspace_desktop_en_full.jpg','workspace_english_content.png',(238,104,1403,690))
desktop_calc=crop('calculator_desktop_en.jpg','calculator_desktop_english_form.png',(0,0,670,537))
mobile_calc=crop('calculator_mobile_en.jpg','calculator_mobile_english_form.png',(0,0,341,605))
companion=crop('workspace_desktop_en_full.jpg','companion_english_browser.png',(1088,115,1385,684))

original=Presentation(OLD/'FinPilot_3m30_retro.pptx')
concepts={}
for i in (0,1,2,3,5):
    image=original.slides[i].shapes[0].image
    path=ASSETS/'concept'/f'original_{i+1:02d}.{image.ext}';path.write_bytes(image.blob);concepts[i+1]=path
source=Path('C:/Users/ROG/.codex/generated_images/01a1cacd-920f-7220-b930-6edd647e7486/exec-96cd5d56-bdff-412d-afd5-6f162b5772b2.png')
shutil.copy2(source,ASSETS/'concept/avatar_english_credit.png');concepts[5]=ASSETS/'concept/avatar_english_credit.png'
manifest['avatar_credit_edit']={'backend':'built-in image_gen','source_image':'original slide 5',
    'change':'Character credit romanized as Shangshan Wuxing; rest of slide preserved.','output_sha256':sha(concepts[5])}

tracks=json.loads((WORK/'talk_tracks.json').read_text(encoding='utf-8-sig'))
assert len(tracks)==13 and sum(t['seconds'] for t in tracks)==210
prs=Presentation();prs.slide_width=Inches(10);prs.slide_height=Inches(5.625)
BG='F5F3E8';INK='283F4C';MINT='95E1D3';GOLD='F9CA24';MUTED='596C77'
def rect(s,x,y,w,h,fill=None,line=INK,radius=False):
    a=s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,Inches(x),Inches(y),Inches(w),Inches(h))
    if fill:a.fill.solid();a.fill.fore_color.rgb=RGBColor.from_string(fill)
    else:a.fill.background()
    if line:a.line.color.rgb=RGBColor.from_string(line);a.line.width=Pt(1.3)
    else:a.line.fill.background()
    if radius:a.adjustments[0]=.1
    style=a._element.find(qn('p:style'))
    if style is not None:
        effect=style.find(qn('a:effectRef'))
        if effect is not None:effect.set('idx','0')
    a._element.spPr.append(OxmlElement('a:effectLst'));return a
def text(s,content,x,y,w,h,size=14,bold=False,color=INK,font='Arial'):
    a=s.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h));tf=a.text_frame;tf.clear();tf.word_wrap=True
    tf.margin_left=tf.margin_right=Inches(.02);tf.margin_top=tf.margin_bottom=0
    for i,line in enumerate(content.split('\n')):
        p=tf.paragraphs[0] if i==0 else tf.add_paragraph();p.text=line
        p.font.name=font;p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=RGBColor.from_string(color);p.space_after=Pt(4)
    return a
def picture(s,path,x,y,w,h,frame=True):
    im=Image.open(path);iw,ih=im.size;scale=min(w/iw,h/ih);pw,ph=iw*scale,ih*scale;left=x+(w-pw)/2;top=y+(h-ph)/2
    if frame:rect(s,left-.02,top-.02,pw+.04,ph+.04,'FFFFFF')
    return s.shapes.add_picture(str(path),Inches(left),Inches(top),Inches(pw),Inches(ph))
def note(s,index,evidence):
    s.notes_slide.notes_text_frame.text=tracks[index-1]['text']+'\n\nEvidence and delivery notes (not spoken): '+evidence
def page(index,title,subtitle,footer):
    s=prs.slides.add_slide(prs.slide_layouts[6]);s.background.fill.solid();s.background.fill.fore_color.rgb=RGBColor.from_string(BG)
    text(s,title,.35,.27,9.3,.56,29,font='Cooper Black')
    text(s,subtitle,.39,.89,9.1,.31,11,color=MUTED);rect(s,.4,1.21,.5,.05,GOLD,None)
    text(s,footer,.39,5.31,9.15,.22,8,color=MUTED);return s
def concept(index,old):
    s=prs.slides.add_slide(prs.slide_layouts[6]);s.shapes.add_picture(str(concepts[old]),0,0,width=prs.slide_width,height=prs.slide_height)
    note(s,index,'Retro flat illustration concept page. Adjacent pages contain the corresponding original project evidence.');return s
def code(name):return ASSETS/'code'/f'{name}.png'

concept(1,1)
s=page(2,'The actual English workspace','OVERVIEW  /  Real browser content, with the native English interface selected','Live source: /workspace  |  Content-region crop. No messages sent and no new model call.')
picture(s,workspace,.43,1.37,9.10,3.73)
note(s,2,'Actual English workspace welcome content and browser companion, captured without changing the shared conversation. The sidebar history and bilingual locale selector are outside the crop. The React homepage has no English route, so it is not presented as an English homepage. Source coordinates and SHA256 are in evidence_manifest.json.')

concept(3,2)
s=page(4,'Two routes, one ranking','RAG  /  Actual ranking code with syntax highlighting','Code: app/expert_knowledge.py:144-146  |  Report: expert_retrieval_holdout_v14.json')
picture(s,code('rag_rrf'),.42,1.45,6.35,3.62)
text(s,'87.04%',7.0,1.65,2.5,.62,33,font='Cooper Black')
text(s,'Recall@4',7.02,2.36,2.35,.36,20,True)
text(s,'18 relevant queries\n24 questions in total',7.03,2.94,2.4,.72,13)
rect(s,7.03,3.94,2.43,.70,MINT,INK,True);text(s,'Same-team labels.\nRetrieval only.',7.13,4.06,2.23,.50,12,True)
note(s,4,'Consecutive original lines 144-146. Pygments syntax highlighting and common-indent removal only; raw source and TXT unchanged. The frozen retriever hash matches the saved small holdout. Recall@4 is not answer accuracy or predictive skill.')
concept(5,3)
s=page(6,'Missing values remain unavailable','RAG  /  A saved report object and the real citation-support guard','Data object: $.turns[0].evidence_values[3]  |  Code: app/expert_grounding.py:210-214')
picture(s,code('missing_oi_json'),.43,1.42,4.37,3.57)
picture(s,code('rag_support'),5.08,1.42,4.49,3.57)
note(s,6,'Left: exact complete h.change.oi_total object from the saved real-cloud report. Keys and values are original; formatting is a labelled object extraction, not a new market result. Right: consecutive source support-check lines. This guard checks recognized facets and does not establish general semantic entailment. The original report and extraction JSONPath/hash are in the code manifest.')

concept(7,4)
s=page(8,'Real English views, responsive controls','FRONTEND  /  The same calculator form at desktop and narrow viewports','Actual English form crops  |  Request guard: web/app.js:1217  |  Hypothetical inputs, not investment performance')
picture(s,desktop_calc,.43,1.42,4.82,2.36)
picture(s,mobile_calc,5.49,1.42,1.32,2.36)
text(s,'Inputs stay\nusable',7.05,1.65,2.3,.8,23,font='Cooper Black')
text(s,'Clear labels\nWrapping controls\nOrdered responses',7.08,2.68,2.2,.91,13)
text(s,'Only the latest calculation response updates the result',.43,3.92,8.9,.25,11.5,True)
picture(s,code('request_guard_wide'),.43,4.19,9.12,1.01,False)
note(s,8,'Real calculator dialog UI. A deterministic calculation was run, then only the original English form regions were cropped for display. The unlocalized bilingual output announcement is outside these crops. No UI text was translated or repainted. The guard is original frozen source line 1217; visual wraps and colors do not alter it.')
s=page(9,'Motion with a safe fallback','FRONTEND  /  Two small code extracts show how motion can fail safely','Source: frontend/src/components/Hero.tsx:137-141 and 145-148. Separate continuous snippets.')
text(s,'A bounded wait',.45,1.46,4.4,.35,18,True)
text(s,'A persistent poster',5.09,1.46,4.4,.35,18,True)
picture(s,code('video_timeout'),.43,1.98,4.35,2.51)
picture(s,code('video_poster'),5.08,1.98,4.49,2.51)
rect(s,.44,4.71,9.08,.35,MINT,None,True);text(s,'2.5-second timeout     Static fallback     Reduced-motion controls',.57,4.77,8.8,.24,12,True)
note(s,9,'Two separately labelled continuous extracts, not a stitched fake source block. Timeout 2500ms becomes fallback. The poster remains in the JSX and video errors also fall back. This is implementation evidence, not an animation-performance benchmark. The actual homepage currently has Chinese copy, so no invented English homepage screenshot appears here.')

concept(10,5)
s=page(11,'One shared 2D renderer','COMPANION  /  Actual English browser companion and the frame drawing code','UI source: English /workspace companion crop  |  Code: web/companion/renderer.js:142-145')
picture(s,companion,.46,1.42,2.74,3.68)
picture(s,code('atlas_draw_short'),3.47,1.42,6.06,3.68)
note(s,11,'The left is the actual English browser companion crop, not an Electron screenshot. The Electron host reuses this same renderer. The right preserves source-frame bounds and drawImage. Shared renderer architecture is additionally documented in the source snapshot and original project reports. Character credit: YunYueSama / Shangshan Wuxing / ZipZipPipe, with original complete license files retained.')
concept(12,6)
s=page(13,'Guard stale responses, preserve the evidence','COMPANION  /  The connection guard and the saved real-cloud acceptance record','Code: web/companion/client.js:41-44  |  Saved report: companion_acceptance_v15.json')
picture(s,code('session_guard_short'),.43,1.43,5.27,3.66)
text(s,'Saved real-cloud run',5.99,1.48,3.55,.37,17,True)
for i,(label,value) in enumerate([('DeepSeek replies','2 / 2'),('Generations','3'),('Citation / schema repairs','1'),('New IBKR requests','0')]):
    y=2.01+i*.51
    if i%2==0:rect(s,6.00,y,3.52,.45,'E4EEE4',None)
    text(s,label,6.08,y+.10,2.50,.25,11.3);text(s,value,8.78,y+.055,.69,.31,17,True)
rect(s,6.00,4.23,3.52,.70,GOLD,None,True);text(s,'Archived data.\nPhysical input checks have limits.',6.10,4.32,3.30,.50,11,True)
note(s,13,'Original selected-session reread and serial/epoch/generation/SID guard. Right-hand values are extracted from the saved actual-model acceptance report, not newly executed. Its two turns used archived IBKR data and include one repair. Physical input certification remains limited. This production task made zero model or broker requests.')

assert len(prs.slides)==13
for s in prs.slides:s._element.attrib.pop('show',None)
prs.core_properties.title='FinPilot - English grouped presentation'
prs.core_properties.subject='Overview, RAG, frontend and companion with adjacent evidence'
prs.save(OUT/'FinPilot_English_Grouped.pptx')

def clock(t):return f'{t//60}:{t%60:02d}'
speech='# FinPilot - English presenter notes\n\n'
guide='# FinPilot · 四人讲稿与连续页序\n\n所有幻灯片及展示内容使用英语。中文提示只用于排练，不在 PPT 页面展示。13 页全部可见，概念页和证据页按主题放在一起。目标总长 3 分 30 秒，时间为编排估计，需排练校准。代码只指关键判断，不逐行朗读。\n\n| 成员 | 页码 | 内容 | 目标时长 |\n|---|---|---|---|\n| Speaker 1 | 1-2 | 总述与真实英文界面 | 40 秒 |\n| Speaker 2 | 3-6 | RAG 集成、检索与引用约束 | 60 秒 |\n| Speaker 3 | 7-9 | 前端、响应式及视频回退 | 55 秒 |\n| Speaker 4 | 10-13 | 形象、渲染、同步与验收 | 55 秒 |\n\n'
for n in range(1,5):
    individual=f'# Speaker {n}\n\n'
    for i,t in enumerate(tracks,1):
        if t['speaker']!=n:continue
        spoken=f"## Slide {i}: {t['title']}\n\n{t['text']}\n\n"
        speech+=spoken
        section=f"## Slide {i}: {t['title']}\n\n时间：{clock(t['start'])}-{clock(t['end'])}，目标 {t['seconds']} 秒。\n\n### English script\n\n{t['text']}\n\n### 中文指图与换页提示\n\n{t['zh']}\n\n"
        individual+=section;guide+=section
    (OUT/f'speaker_{n}.md').write_text(individual,encoding='utf-8')
(OUT/'speech.md').write_text(speech,encoding='utf-8')
words=sum(t['words'] for t in tracks)
guide+=f'\n英文口述正文共 {words} 词。13 页含更多指图和切换，预留停顿后约 3 分半。建议按40秒、1分40秒、2分35秒、3分30秒四个交接点排练。已有模型验收结果来自保存的报告，本次没有重新调用模型或 IBKR。原主页没有英文版本，本版用实际英文工作台替代；中文历史列表、语言切换按钮及双语计算提示均位于截图裁剪范围之外，未改写截图内容。\n'
(OUT/'speaker_guide.md').write_text(guide,encoding='utf-8')
outline='# FinPilot - grouped English deck\n\nAll 13 slides are visible. Related concept and evidence pages are adjacent.\n\n'
for i,t in enumerate(tracks,1):outline+=f"{i}. {t['title']} - Speaker {t['speaker']}, {clock(t['start'])}-{clock(t['end'])}\n"
(OUT/'outline.md').write_text(outline,encoding='utf-8')
manifest['slides']=[{'number':i,'title':t['title'],'speaker':t['speaker'],'seconds':t['seconds'],'words':t['words']} for i,t in enumerate(tracks,1)]
manifest['total_words']=words;manifest['planned_seconds']=210
(OUT/'evidence_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'talk_tracks.json').write_text(json.dumps(tracks,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'README.md').write_text('''# FinPilot - English grouped edition

13 visible slides in presentation order: overview 1-2, RAG 3-6, frontend 7-9, companion 10-13. Concept and supporting evidence are adjacent. No hidden appendix.

The six retro flat concept pages retain the original design. The avatar credit was edited through the same built-in image tool into romanized English. Native evidence pages preserve that palette and typography. Code evidence uses syntax highlighting while original source, TXT, source line numbers, hashes and wrap reconstruction metadata are retained.

All visible slide text and displayed UI regions are English. Actual native English workspace and calculator regions are used. The Chinese-only homepage and incomplete pet-page localization are not passed off as English products. Crops exclude old Chinese chat titles, locale-switch controls and the bilingual calculator announcement. Full original captures remain in raw_captures for provenance. Screenshots are not repainted.

speaker_guide.md contains four English scripts and Chinese rehearsal cues. speaker_1.md through speaker_4.md are separate scripts. The main target remains 210 seconds including transitions; rehearse with the group. All slide notes contain the script and evidence source details.

Source code is frozen at extraction time in source_snapshot. Existing actual-model reports are saved evidence, not new tests executed on every later source change. This update performs only local deterministic calculation and read-only capture, with no model/broker calls. Character attribution and noncommercial derivative conditions are preserved in character_licenses.
''',encoding='utf-8')
print(json.dumps({'pptx':str(OUT/'FinPilot_English_Grouped.pptx'),'slides':13,'words':words,'seconds':210},ensure_ascii=False))
