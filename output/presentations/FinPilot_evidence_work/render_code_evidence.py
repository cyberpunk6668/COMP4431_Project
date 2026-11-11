"""Render exact repository source extracts as legible evidence assets.

This script creates source-code screenshots, not completed presentation slides.
Logical source lines remain unchanged in the TXT and JSON. PNGs use visual wraps.
"""
from pathlib import Path
import hashlib
import json
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent / 'source_snapshot'
OUT = Path(__file__).resolve().parent / 'assets' / 'code'
OUT.mkdir(parents=True, exist_ok=True)
FONT_PATH = Path('C:/Windows/Fonts/consola.ttf')
FONT_SIZE = 38
font = ImageFont.truetype(str(FONT_PATH), FONT_SIZE)
header_font = ImageFont.truetype(str(FONT_PATH), FONT_SIZE)
WIDTH = 1200
PAD = 28
CODE_X = 140
RIGHT_PAD = 28
CODE_WIDTH = WIDTH - CODE_X - RIGHT_PAD
LINE_H = 54
HEADER_H = 100
BG = '#F5F3E8'
FG = '#253D4A'
DIM = '#708087'
SPECS = [
    ('rag_rrf', 'app/expert_knowledge.py', 144, 146),
    ('rag_support', 'app/expert_grounding.py', 210, 214),
    ('video_fallback', 'frontend/src/components/Hero.tsx', 137, 148),
    ('request_guard', 'web/app.js', 1217, 1217),
    ('atlas_draw', 'web/companion/renderer.js', 136, 145),
    ('session_guard', 'web/companion/client.js', 35, 44),
    ('sse_transport', 'web/companion/client.js', 85, 94),
    ('atlas_draw_short', 'web/companion/renderer.js', 142, 145),
    ('session_guard_short', 'web/companion/client.js', 41, 44),
    ('request_guard_wide', 'web/app.js', 1217, 1217, {'width': 2400, 'font_size': 44}),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def wrap_pixels(text):
    """Partition raw characters, without inserting or deleting code characters."""
    if not text:
        return ['']
    parts = []
    remaining = text
    while remaining:
        lo, hi = 1, len(remaining)
        fit = 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if font.getlength(remaining[:mid]) <= CODE_WIDTH:
                fit = mid
                lo = mid + 1
            else:
                hi = mid - 1
        # Favor normal whitespace/punctuation boundaries, but retain all chars.
        # Never break early enough to create an almost-empty row.
        if fit < len(remaining):
            floor = max(1, int(fit * .55))
            boundary = [i + 1 for i, ch in enumerate(remaining[:fit])
                        if i + 1 >= floor and ch in ' ,;(){}[]+-=']
            if boundary:
                fit = boundary[-1]
        part, remaining = remaining[:fit], remaining[fit:]
        assert font.getlength(part) <= CODE_WIDTH + 0.001
        parts.append(part)
    assert ''.join(parts) == text
    return parts


manifest_path = OUT / 'manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {
    'purpose': 'Verbatim repository source extraction rendered as evidence assets, not final presentation slides.',
    'font': 'Consolas', 'font_path': str(FONT_PATH), 'font_size_px': FONT_SIZE,
    'canvas_width_px': WIDTH, 'background': BG, 'text_color': FG,
    'wrap_policy': 'Pixel-width visual wraps. Only the first visual row of a logical source line shows its original line number. No code characters are inserted, removed, or joined across original lines.',
    'snippets': []
}
existing_ids = {item['id'] for item in manifest['snippets']}
for spec in SPECS:
    ident, rel, start, end, *options = spec
    if ident in existing_ids:
        continue
    opts = options[0] if options else {}
    WIDTH = opts.get('width', 1200)
    FONT_SIZE = opts.get('font_size', 38)
    font = ImageFont.truetype(str(FONT_PATH), FONT_SIZE)
    header_font = ImageFont.truetype(str(FONT_PATH), FONT_SIZE)
    CODE_X = 180 if WIDTH == 2400 else 140
    NUMBER_RIGHT = 136 if WIDTH == 2400 else 98
    GUTTER_X = 150 if WIDTH == 2400 else 112
    CODE_WIDTH = WIDTH - CODE_X - RIGHT_PAD
    LINE_H = 62 if FONT_SIZE == 44 else 54
    source = ROOT / rel
    raw = source.read_bytes()
    # splitlines preserves every source-line character except line terminators.
    # TXT uses canonical LF and never alters logical line content.
    source_lines = raw.decode('utf-8').splitlines()
    logical = source_lines[start - 1:end]
    assert len(logical) == end - start + 1
    assert all('\t' not in line for line in logical), 'Unexpected tabs require explicit normal tab-stop rendering'
    code = '\n'.join(logical)
    txt = OUT / f'{ident}.txt'
    txt.write_text(code + '\n', encoding='utf-8', newline='\n')
    rows = []
    row_map = []
    for line_no, line in enumerate(logical, start):
        wrapped = wrap_pixels(line)
        for j, fragment in enumerate(wrapped):
            rows.append((str(line_no) if j == 0 else '', fragment))
            row_map.append({'source_line': line_no, 'continuation': j > 0, 'text': fragment})
    height = HEADER_H + 26 + len(rows) * LINE_H + 24
    image = Image.new('RGB', (WIDTH, height), BG)
    draw = ImageDraw.Draw(image)
    label = f'{rel}:{start}' + (f'-{end}' if end != start else '')
    assert header_font.getlength(label) <= WIDTH - 2 * PAD, label
    draw.text((PAD, 26), label, font=header_font, fill=FG)
    draw.line((PAD, 86, WIDTH - PAD, 86), fill='#C3CDC7', width=2)
    draw.line((GUTTER_X, HEADER_H + 12, GUTTER_X, height - 24), fill='#D3D8CB', width=2)
    y = HEADER_H + 22
    for number, fragment in rows:
        if number:
            draw.text((NUMBER_RIGHT - font.getlength(number), y), number, font=font, fill=DIM)
        draw.text((CODE_X, y), fragment, font=font, fill=FG)
        y += LINE_H
    png = OUT / f'{ident}.png'
    image.save(png)
    manifest['snippets'].append({
        'id': ident, 'path': rel, 'source_absolute_path': str(source),
        'start_line': start, 'end_line': end, 'source_sha256': sha(raw),
        'code': code, 'txt_path': str(txt), 'txt_sha256': sha(txt.read_bytes()),
        'png_path': str(png), 'png_sha256': sha(png.read_bytes()),
        'pixels': [WIDTH, height], 'logical_lines': len(logical),
        'font_size_px': FONT_SIZE, 'canvas_width_px': WIDTH,
        'visual_rows': len(rows), 'visual_row_map': row_map,
    })
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'manifest': str(manifest_path), 'assets': [
    {'id': x['id'], 'pixels': x['pixels'], 'visual_rows': x['visual_rows'], 'png': x['png_path']}
    for x in manifest['snippets']]}, ensure_ascii=False))
