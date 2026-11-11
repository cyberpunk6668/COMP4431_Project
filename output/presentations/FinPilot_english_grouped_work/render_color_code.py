"""Syntax-highlight frozen, verbatim code evidence without changing source text.

Only code-evidence assets are produced here, never complete slide images.
"""
from pathlib import Path
from collections import defaultdict
import hashlib
import json
import re
import shutil

from PIL import Image, ImageDraw, ImageFont
from pygments.lexers import PythonLexer, JavascriptLexer, TsxLexer
from pygments.token import Token

WORK = Path(__file__).resolve().parent
REPO = WORK.parents[2]
ORIGINAL = REPO / 'output/presentations/FinPilot_3m30_retro_evidence'
ORIGINAL_MANIFEST = ORIGINAL / 'assets/code/manifest.json'
SNAPSHOT = WORK / 'source_snapshot'
OUTPUT = WORK / 'assets/code'
OUTPUT.mkdir(parents=True, exist_ok=True)
shutil.copytree(ORIGINAL / 'source_snapshot', SNAPSHOT, dirs_exist_ok=True)
original = json.loads(ORIGINAL_MANIFEST.read_text(encoding='utf-8'))

FONT_PATH = Path('C:/Windows/Fonts/consola.ttf')
BG = '#F5F3E8'
FG = '#253D4A'
DIM = '#708087'
PALETTE = {
    'keyword': '#7A3EB1',
    'function_method_builtin': '#1B63B2',
    'string': '#20794A',
    'number': '#B95D00',
    'comment': '#55766F',
    'operator': '#AE3E56',
    'punctuation_identifier': FG,
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def base_category(token):
    if token in Token.Comment:
        return 'comment'
    if token in Token.Keyword:
        return 'keyword'
    if token in Token.Literal.String:
        return 'string'
    if token in Token.Literal.Number:
        return 'number'
    if token in Token.Name.Function or token in Token.Name.Builtin or token in Token.Name.Tag:
        return 'function_method_builtin'
    if token in Token.Operator:
        return 'operator'
    return 'punctuation_identifier'

def lex_source(source, suffix):
    if suffix == '.py':
        lexer = PythonLexer()
    elif suffix == '.tsx':
        lexer = TsxLexer()
    else:
        lexer = JavascriptLexer()
    tokens = list(lexer.get_tokens_unprocessed(source))
    assert ''.join(content for _, _, content in tokens) == source
    categories = ['punctuation_identifier'] * len(source)
    for offset, token, content in tokens:
        category = base_category(token)
        # Pygments identifies definitions and builtins. Recognize call-site
        # names from lexical Name tokens followed by '(' without changing code.
        if token in Token.Name and category == 'punctuation_identifier':
            if re.match(r'^\s*\(', source[offset + len(content):]):
                category = 'function_method_builtin'
        categories[offset:offset+len(content)] = [category] * len(content)
    return lexer.name, categories

def wrap_text(text, font, max_width):
    if not text:
        return ['']
    parts = []
    remaining = text
    while remaining:
        low, high, fit = 1, len(remaining), 1
        while low <= high:
            middle = (low + high) // 2
            if font.getlength(remaining[:middle]) <= max_width:
                fit, low = middle, middle + 1
            else:
                high = middle - 1
        if fit < len(remaining):
            floor = max(1, int(fit * 0.55))
            boundaries = [i + 1 for i, char in enumerate(remaining[:fit])
                          if i + 1 >= floor and char in ' ,;(){}[]+-=']
            if boundaries:
                fit = boundaries[-1]
        parts.append(remaining[:fit])
        remaining = remaining[fit:]
    assert ''.join(parts) == text
    return parts

manifest = {
    'purpose': 'Syntax-highlighted frozen source-code evidence assets, not completed slides.',
    'renderer': 'Pygments full-source lexical analysis plus Pillow text rendering',
    'font': 'Consolas', 'font_path': str(FONT_PATH),
    'background': BG, 'default_color': FG, 'line_number_color': DIM,
    'palette': PALETTE,
    'source_snapshot_captured_at_utc': original.get('source_snapshot_captured_at_utc'),
    'source_snapshot_policy': original.get('source_snapshot_policy'),
    'display_policy': 'Remove only indentation shared by every nonblank line of the selected snippet. Visual wraps preserve every remaining character. Original source and TXT are unchanged.',
    'wrap_policy': 'Only the first visual row of each original logical source line shows its original line number. No truncation, ellipses or rewritten code.',
    'snippets': [],
}
for entry in original['snippets']:
    ident, relative = entry['id'], entry['path']
    source_path = SNAPSHOT / relative
    raw = source_path.read_bytes()
    assert sha(raw) == entry['source_sha256'], ident
    full_text = raw.decode('utf-8')
    raw_lines = full_text.splitlines(keepends=True)
    logical = [line.rstrip('\r\n') for line in raw_lines[entry['start_line']-1:entry['end_line']]]
    code = '\n'.join(logical)
    assert code == entry['code'], ident
    assert all('\t' not in line for line in logical)
    common_indent = min((len(line)-len(line.lstrip(' ')) for line in logical if line.strip()), default=0)
    displayed = [line[common_indent:] if line.strip() else line for line in logical]
    lexer, full_categories = lex_source(full_text, source_path.suffix)
    offsets = [0]
    for line in raw_lines:
        offsets.append(offsets[-1] + len(line))

    width = 2400 if ident == 'request_guard_wide' else 1200
    size = 44 if ident == 'request_guard_wide' else 38
    font = ImageFont.truetype(str(FONT_PATH), size)
    code_x = 180 if width == 2400 else 140
    number_right = 136 if width == 2400 else 98
    gutter_x = 150 if width == 2400 else 112
    max_width = width - code_x - 28
    line_h = 62 if size == 44 else 54
    rows, row_map = [], []
    colors_used = defaultdict(int)
    for local_index, (original_line, display_line) in enumerate(zip(logical, displayed)):
        line_no = entry['start_line'] + local_index
        removed = original_line[:common_indent] if original_line.strip() else ''
        assert removed + display_line == original_line
        start_offset = offsets[line_no - 1] + len(removed)
        line_categories = full_categories[start_offset:start_offset + len(display_line)]
        assert len(line_categories) == len(display_line)
        position = 0
        for wrap_index, fragment in enumerate(wrap_text(display_line, font, max_width)):
            categories = line_categories[position:position + len(fragment)]
            rows.append((str(line_no) if wrap_index == 0 else '', fragment, categories))
            row_map.append({'source_line': line_no, 'continuation': wrap_index > 0,
                            'removed_common_indent': removed if wrap_index == 0 else '',
                            'text': fragment})
            position += len(fragment)
        assert position == len(display_line)

    height = 150 + len(rows) * line_h
    image = Image.new('RGB', (width, height), BG)
    draw = ImageDraw.Draw(image)
    label = f"{relative}:{entry['start_line']}"
    if entry['end_line'] != entry['start_line']:
        label += f"-{entry['end_line']}"
    assert font.getlength(label) <= width - 56
    draw.text((28, 26), label, font=font, fill=FG)
    draw.line((28, 86, width-28, 86), fill='#C3CDC7', width=2)
    draw.line((gutter_x, 112, gutter_x, height-24), fill='#D3D8CB', width=2)
    y = 122
    token_runs = []
    for visual_index, (number, fragment, categories) in enumerate(rows):
        if number:
            draw.text((number_right-font.getlength(number), y), number, font=font, fill=DIM)
        x = code_x
        begin = 0
        while begin < len(fragment):
            category = categories[begin]
            end = begin+1
            while end < len(fragment) and categories[end] == category:
                end += 1
            run = fragment[begin:end]
            draw.text((x, y), run, font=font, fill=PALETTE[category])
            colors_used[category] += sum(not c.isspace() for c in run)
            token_runs.append({'visual_row': visual_index, 'start_character': begin,
                               'end_character': end, 'category': category, 'color': PALETTE[category]})
            x += font.getlength(run)
            begin = end
        assert x <= width - 27, (ident, visual_index, x)
        y += line_h

    txt_path = OUTPUT / f'{ident}.txt'
    txt_path.write_text(code + '\n', encoding='utf-8', newline='\n')
    png_path = OUTPUT / f'{ident}.png'
    image.save(png_path)
    # Reconstruct each logical line from the manifest, including its removed
    # visual-only indentation, and compare character-for-character to source.
    reconstructed = []
    for line_no in range(entry['start_line'], entry['end_line']+1):
        matches = [row for row in row_map if row['source_line'] == line_no]
        reconstructed.append(matches[0]['removed_common_indent'] + ''.join(row['text'] for row in matches))
    assert '\n'.join(reconstructed) == code
    assert txt_path.read_text(encoding='utf-8') == code + '\n'
    assert sum(amount > 0 for category, amount in colors_used.items() if category != 'punctuation_identifier') >= 1
    record = dict(entry)
    record.update({
        'source_absolute_path': str(source_path),
        'packaged_source_snapshot': 'source_snapshot/' + relative,
        'lexer': lexer, 'common_indent_removed_for_display': common_indent,
        'txt_path': str(txt_path), 'txt_sha256': sha(txt_path.read_bytes()),
        'png_path': str(png_path), 'png_sha256': sha(png_path.read_bytes()),
        'pixels': [width, height], 'font_size_px': size, 'canvas_width_px': width,
        'logical_lines': len(logical), 'visual_rows': len(rows), 'visual_row_map': row_map,
        'syntax_categories_used': dict(colors_used), 'syntax_color_runs': token_runs,
        'reconstruction_verified': True,
    })
    manifest['snippets'].append(record)

(OUTPUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'output': str(OUTPUT), 'count': len(manifest['snippets']), 'snippets': [
    {'id': row['id'], 'pixels': row['pixels'], 'common_indent_removed': row['common_indent_removed_for_display'],
     'colors': [name for name,count in row['syntax_categories_used'].items() if count > 0]}
    for row in manifest['snippets']]}, ensure_ascii=False))
