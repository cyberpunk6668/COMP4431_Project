from pathlib import Path
import json, shutil, hashlib
from datetime import datetime, timezone
WORK=Path(__file__).resolve().parent
REPO=WORK.parents[2]
mf=WORK/'assets/code/manifest.json'
m=json.loads(mf.read_text(encoding='utf-8'))
paths=sorted({r['path'] for r in m['snippets']})
frozen=WORK/'source_snapshot'
for rel in paths:
    dest=frozen/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(REPO/rel,dest)
lines=(frozen/'web/app.js').read_text(encoding='utf-8').splitlines()
guard=[i for i,t in enumerate(lines,1) if 'if(sequence===state.calculationSequence)showCalculation(result)' in t]
assert guard==[1217],guard
m['snippets']=[r for r in m['snippets'] if r['id'] not in ('request_guard','request_guard_wide')]
m['source_snapshot_captured_at_utc']=datetime.now(timezone.utc).isoformat()
m['source_snapshot_policy']='Complete whitelisted source files frozen during this update. Slides cite these capture-time line numbers. Later concurrent repository edits do not alter these evidence files.'
for r in m['snippets']:r['source_snapshot_path']='source_snapshot/'+r['path']
mf.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
ui=WORK/'ui_avatar_evidence.json'
j=json.loads(ui.read_text(encoding='utf-8'))
for r in j['primary_snippets']:
    if r['id']=='frontend_stale_calculation':r['start']=1209;r['end']=1220
j['source_update_note']='web/app.js changed concurrently after the saved acceptance run. The unchanged calculation-result guard moved from line 1212 to line 1217. The final slide cites the frozen current-source snapshot, not a claim that prior acceptance reran on this new whole-file hash.'
ui.write_text(json.dumps(j,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'snapshot':str(frozen),'source_files':len(paths),'guard_line':guard[0]},ensure_ascii=False))
