from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[3]
out = Path(__file__).resolve().parent
meta = json.loads((out / 'ui_avatar_evidence.json').read_text(encoding='utf-8'))
parts = ['# Frontend and companion evidence', '', meta['verification_basis'], '']
for snippet in meta['primary_snippets']:
    path = root / snippet['path']
    raw = path.read_text(encoding='utf-8').splitlines()
    code = '\n'.join(raw[snippet['start'] - 1:snippet['end']])
    assert len(code.splitlines()) == snippet['end'] - snippet['start'] + 1
    parts += [f"## {snippet['id']}", '',
              f"Source: `{snippet['path']}:{snippet['start']}–{snippet['end']}`", '',
              f"Caption: {snippet['caption']}", '',
              f"Purpose: {snippet['reason']}", '',
              f"SHA256 of source file: `{hashlib.sha256(path.read_bytes()).hexdigest()}`", '',
              f"```{snippet['language']}", code, '```', '',
              snippet['display_note'], '']
parts += ['## SSE transport alternative', '',
          '`web/companion/client.js:85–94` shows EventSource creation at line 87 and reconnect reconciliation. '
          'Use it as a separately labeled range; do not concatenate it with lines 35–44.', '',
          '## Current report status', '', '```json',
          json.dumps(meta['current_saved_report_status'], ensure_ascii=False, indent=2), '```', '',
          '## Recommended UI evidence without paid calls', '']
for shot in meta['screenshot_recommendations']:
    parts += [f"- `{shot['route']}` — {shot['operation']} {shot['scope']}"]
parts += ['', '## Existing final real-cloud screenshot evidence', '']
for shot in meta['existing_real_cloud_screenshots']:
    parts += [f"- `{shot['path']}` — {shot['caption']} {shot['scope']}"]
parts += ['', '## Correction to earlier deck notes', '', meta['correction_to_previous_presentation'], '']
(out / 'ui_avatar_evidence.md').write_text('\n'.join(parts), encoding='utf-8')
print(out / 'ui_avatar_evidence.md')
