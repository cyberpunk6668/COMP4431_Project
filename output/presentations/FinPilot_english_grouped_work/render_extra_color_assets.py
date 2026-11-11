"""Add focused frontend snippets and a labelled saved-report object extract."""
from pathlib import Path
from collections import defaultdict
import hashlib, json, re, shutil
from PIL import Image, ImageDraw, ImageFont
from pygments.lexers import TsxLexer, JsonLexer
from pygments.token import Token

WORK=Path(__file__).resolve().parent
REPO=WORK.parents[2]
OUT=WORK/'assets/code'
MANIFEST=OUT/'manifest.json'
SNAPSHOT=WORK/'source_snapshot'
m=json.loads(MANIFEST.read_text(encoding='utf-8'))
PALETTE=m['palette']
BG=m['background'];FG=m['default_color'];DIM=m['line_number_color']
FONT_PATH=Path(m['font_path'])
FONT=ImageFont.truetype(str(FONT_PATH),38)

def sha(data):return hashlib.sha256(data).hexdigest()
def category(tok,rest=''):
    if tok in Token.Comment:return 'comment'
    if tok in Token.Keyword:return 'keyword'
    if tok in Token.Literal.String:return 'string'
    if tok in Token.Literal.Number:return 'number'
    if tok in Token.Name.Function or tok in Token.Name.Builtin or tok in Token.Name.Tag:return 'function_method_builtin'
    if tok in Token.Name and re.match(r'^\s*\(',rest):return 'function_method_builtin'
    if tok in Token.Operator:return 'operator'
    return 'punctuation_identifier'
def lexical_colors(source,lexer):
    tokens=list(lexer.get_tokens_unprocessed(source));assert ''.join(t for _,_,t in tokens)==source
    cats=['punctuation_identifier']*len(source)
    for start,tok,value in tokens:
        cats[start:start+len(value)]=[category(tok,source[start+len(value):])]*len(value)
    return cats
def wrapped(text,width):
    if not text:return ['']
    result=[]
    while text:
        lo,hi,fit=1,len(text),1
        while lo<=hi:
            mid=(lo+hi)//2
            if FONT.getlength(text[:mid])<=width:fit,lo=mid,mid+1
            else:hi=mid-1
        if fit<len(text):
            boundary=[i+1 for i,c in enumerate(text[:fit]) if i+1>=int(fit*.55) and c in ' ,;(){}[]+-=']
            if boundary:fit=boundary[-1]
        result.append(text[:fit]);text=text[fit:]
    return result
def colored_row(draw,text,cats,x,y,row_index,runs,counts):
    start=0
    while start<len(text):
        end=start+1
        while end<len(text) and cats[end]==cats[start]:end+=1
        run=text[start:end];kind=cats[start]
        draw.text((x,y),run,font=FONT,fill=PALETTE[kind]);x+=FONT.getlength(run)
        counts[kind]+=sum(not c.isspace() for c in run)
        runs.append({'visual_row':row_index,'start_character':start,'end_character':end,'category':kind,'color':PALETTE[kind]})
        start=end
    assert x<=1173

for ident,start,end in [('video_timeout',137,141),('video_poster',145,148)]:
    relative='frontend/src/components/Hero.tsx';source_path=SNAPSHOT/relative
    raw=source_path.read_bytes();full=raw.decode('utf-8');all_lines=full.splitlines(keepends=True)
    logical=[s.rstrip('\r\n') for s in all_lines[start-1:end]]
    code='\n'.join(logical)
    common=min(len(s)-len(s.lstrip(' ')) for s in logical if s.strip())
    offsets=[0]
    for s in all_lines:offsets.append(offsets[-1]+len(s))
    cats=lexical_colors(full,TsxLexer())
    row_map=[];rows=[]
    for i,line in enumerate(logical):
        n=start+i;prefix=line[:common] if line.strip() else '';display=line[len(prefix):]
        line_cats=cats[offsets[n-1]+len(prefix):offsets[n-1]+len(line)]
        visual=wrapped(display,1032);assert ''.join(visual)==display
        offset=0
        for j,fragment in enumerate(visual):
            rows.append((str(n) if j==0 else '',fragment,line_cats[offset:offset+len(fragment)]))
            row_map.append({'source_line':n,'continuation':j>0,'removed_common_indent':prefix if j==0 else '', 'text':fragment})
            offset+=len(fragment)
    height=150+54*len(rows)
    image=Image.new('RGB',(1200,height),BG);draw=ImageDraw.Draw(image)
    title=f'{relative}:{start}-{end}'
    draw.text((28,26),title,font=FONT,fill=FG)
    draw.line((28,86,1172,86),fill='#C3CDC7',width=2)
    draw.line((112,112,112,height-24),fill='#D3D8CB',width=2)
    runs=[];counts=defaultdict(int)
    for i,(number,fragment,row_cats) in enumerate(rows):
        y=122+54*i
        if number:draw.text((98-FONT.getlength(number),y),number,font=FONT,fill=DIM)
        colored_row(draw,fragment,row_cats,140,y,i,runs,counts)
    png=OUT/f'{ident}.png';txt=OUT/f'{ident}.txt';image.save(png);txt.write_text(code+'\n',encoding='utf-8',newline='\n')
    reconstructed=[]
    for n in range(start,end+1):
        v=[r for r in row_map if r['source_line']==n]
        reconstructed.append(v[0]['removed_common_indent']+''.join(r['text'] for r in v))
    assert '\n'.join(reconstructed)==code
    assert all(ord(c)<128 for c in code)
    record={'id':ident,'path':relative,'source_absolute_path':str(source_path),'packaged_source_snapshot':'source_snapshot/'+relative,
            'start_line':start,'end_line':end,'source_sha256':sha(raw),'code':code,'lexer':'TSX',
            'txt_path':str(txt),'txt_sha256':sha(txt.read_bytes()),'png_path':str(png),'png_sha256':sha(png.read_bytes()),
            'pixels':[1200,height],'font_size_px':38,'canvas_width_px':1200,'logical_lines':len(logical),'visual_rows':len(rows),
            'common_indent_removed_for_display':common,'visual_row_map':row_map,'syntax_categories_used':dict(counts),
            'syntax_color_runs':runs,'reconstruction_verified':True}
    m['snippets']=[r for r in m['snippets'] if r['id']!=ident]+[record]

report=REPO/'output/presentations/FinPilot_3m30_retro_evidence/evidence_sources/pet_cloud_v15.json'
raw=report.read_bytes();data=json.loads(raw.decode('utf-8'))
values=data['turns'][0]['evidence_values']
matches=[(index,obj) for index,obj in enumerate(values) if obj['id']=='h.change.oi_total']
assert len(matches)==1
index,obj=matches[0]
display=json.dumps(obj,ensure_ascii=False,indent=2)
assert all(ord(c)<128 for c in display)
cats=lexical_colors(display,JsonLexer())
lines=display.splitlines();rows=[];offset=0;visual_map=[]
for line_no,line in enumerate(lines,1):
    fragments=wrapped(line,1120);assert ''.join(fragments)==line
    local=0
    for i,fragment in enumerate(fragments):
        rows.append((fragment,cats[offset+local:offset+local+len(fragment)]))
        visual_map.append({'formatted_object_line':line_no,'continuation':i>0,'text':fragment})
        local+=len(fragment)
    offset+=len(line)+1
height=206+54*len(rows)
image=Image.new('RGB',(1200,height),BG);draw=ImageDraw.Draw(image)
title='pet_cloud_v15.json · $.turns[0].evidence_values'
header_font=ImageFont.truetype(str(FONT_PATH),36)
sub_font=ImageFont.truetype(str(FONT_PATH),28)
assert header_font.getlength(title)<=1144
draw.text((28,26),title,font=header_font,fill=FG)
draw.text((28,83),'Report object extraction · id = h.change.oi_total',font=sub_font,fill=DIM)
draw.line((28,133,1172,133),fill='#C3CDC7',width=2)
runs=[];counts=defaultdict(int)
for i,(fragment,row_cats) in enumerate(rows):
    colored_row(draw,fragment,row_cats,40,164+54*i,i,runs,counts)
png=OUT/'missing_oi_json.png';txt=OUT/'missing_oi_json.txt';image.save(png);txt.write_text(display+'\n',encoding='utf-8',newline='\n')
assert json.loads(txt.read_text(encoding='utf-8'))==obj
reconstructed='\n'.join(''.join(r['text'] for r in visual_map if r['formatted_object_line']==n) for n in range(1,len(lines)+1))
assert reconstructed==display
report_dir=WORK/'evidence_sources';report_dir.mkdir(exist_ok=True)
snapshot=report_dir/'pet_cloud_v15_original_saved.json';shutil.copy2(report,snapshot)
record={'id':'missing_oi_json','kind':'saved_report_object_extract','not_source_file_line_screenshot':True,
        'report_path':str(report.relative_to(REPO)),'report_absolute_path':str(report),
        'packaged_report_snapshot':'evidence_sources/'+snapshot.name,'report_sha256':sha(raw),
        'jsonpath':f'$.turns[0].evidence_values[{index}]','array_jsonpath':'$.turns[0].evidence_values',
        'selection':{'id':'h.change.oi_total'},'object':obj,'display_text':display,
        'display_format':'JSON indent=2; all ASCII; complete object; no invented fields',
        'txt_path':str(txt),'txt_sha256':sha(txt.read_bytes()),'png_path':str(png),'png_sha256':sha(png.read_bytes()),
        'pixels':[1200,height],'font_size_px':38,'canvas_width_px':1200,'lexer':'JSON',
        'visual_row_map':visual_map,'syntax_categories_used':dict(counts),'syntax_color_runs':runs,
        'reconstruction_verified':True,'object_equality_verified':True}
m['report_extracts']=[r for r in m.get('report_extracts',[]) if r['id']!='missing_oi_json']+[record]
temp=MANIFEST.with_name('manifest.next.json')
temp.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(MANIFEST)
print(json.dumps({'assets':[{r['id']:r['pixels']} for r in m['snippets'] if r['id'] in ('video_timeout','video_poster')]+[{'missing_oi_json':record['pixels']}], 'source_snippets':len(m['snippets']),'report_extracts':len(m['report_extracts'])},ensure_ascii=False))
