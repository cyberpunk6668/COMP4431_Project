"""Verify the ZIP in an isolated extracted folder, offline, without local .env/DB.

Run package_submission.py first. Uses the current interpreter's installed runtime.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.package_submission import (APPLICATION_VERSION, NATIVE_HOST_VERSION, V16_REQUIRED_FILES, V17_REQUIRED_FILES,
                                        PORTABLE, PORTABLE_BYTES, PORTABLE_SHA256, SECRET_PATTERNS, scan_stream)

ZIP = ROOT / "dist" / "FinPilot_submission_v17.zip"
V15_ACCEPTANCE = ["native_companion_v15.json", "pet_cloud_v15.json", "python_regression_v15.json", "companion_acceptance_v15.json"]
V16_ACCEPTANCE = ["project_help_ui_v16.json", "project_help_live_v16.json", "python_regression_v16.json"]
V17_ACCEPTANCE = ["options_lab_ui_v17.json", "experience_ui_v17.json", "python_regression_v17.json", "options_lab_live_v17.json", "feature_audit_v17.json"]


def archive_sha256(archive, name):
    digest = hashlib.sha256()
    with archive.open(name) as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    scratch = (ROOT / "tmp" / "package-check").resolve()
    assert scratch.is_relative_to(ROOT.resolve())
    scratch.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP) as archive:
        names = archive.namelist()
        assert len(names) == len(set(name.casefold() for name in names)), "Duplicate/case-colliding archive paths"
        for name in names:
            parts = name.split("/")
            assert name.startswith("FinPilot/") and ".." not in parts and "\\" not in name and ":" not in name
            assert not {"node_modules", "win-unpacked", "tmp", ".venv", ".venv-ml", "__pycache__", ".git"}.intersection(parts)
            assert not any(part.lower().startswith(".env") for part in parts) or name == "FinPilot/.env.example"
            assert ".sqlite" not in name.lower() and not name.lower().endswith((".db", ".db-wal", ".db-shm", ".log", ".pyc", ".pfx", ".p12", ".pem", ".key"))
            assert (archive.getinfo(name).external_attr >> 16) & 0o170000 != 0o120000, "Archive symlinks are forbidden"
            with archive.open(name) as stream:
                scan_stream(stream, name)
        assert "FinPilot/.env.example" in names
        assert "FinPilot/data/knowledge.json" in names
        assert "FinPilot/frontend/package-lock.json" in names
        assert "FinPilot/web/showcase/index.html" in names
        assert b'workspace-motion-toggle' in archive.read('FinPilot/web/index.html')
        assert b'coinwise-v5' in archive.read('FinPilot/web/app.js')
        assert 'FinPilot/web/showcase/media/reference-poster.webp' in names
        for scope in ('showcase', 'workspace'):
            assert f'FinPilot/docs/{scope}_design_v5.md' in names
            acceptance = json.loads(archive.read(f'FinPilot/reports/{scope}_check_v5.json'))
            assert acceptance['status'] == 'passed'
        assert 'FinPilot/requirements-options.txt' in names
        assert 'FinPilot/docs/options_analysis_v6.md' in names
        assert json.loads(archive.read('FinPilot/reports/options_browser_v6.json'))['status'] == 'passed'
        assert 'FinPilot/docs/options_collective_v7.md' in names
        assert json.loads(archive.read('FinPilot/reports/options_collective_browser_v7.json'))['status'] == 'passed'
        assert json.loads(archive.read('FinPilot/reports/options_collective_cloud_v7.json'))['status'] == 'passed'
        assert 'FinPilot/docs/options_novice_v8.md' in names
        assert 'FinPilot/app/options_brief.py' in names
        assert json.loads(archive.read('FinPilot/reports/options_novice_browser_v8.json'))['status'] == 'passed'
        assert 'FinPilot/docs/expiry_and_general_chat_v9.md' in names
        assert 'FinPilot/tests/test_service_general.py' in names
        assert json.loads(archive.read('FinPilot/reports/options_expirations_browser_v9.json'))['status'] == 'passed'
        assert json.loads(archive.read('FinPilot/reports/options_expirations_live_v9.json'))['status'] == 'passed'
        assert json.loads(archive.read('FinPilot/reports/general_chat_live_v9.json'))['status'] == 'passed'
        assert 'FinPilot/docs/options_chat_v10.md' in names
        assert 'FinPilot/app/options_chat.py' in names
        assert json.loads(archive.read('FinPilot/reports/options_chat_browser_v10.json'))['status'] == 'passed'
        assert json.loads(archive.read('FinPilot/reports/options_chat_cloud_v10.json'))['status'] == 'passed'
        assert json.loads(archive.read('FinPilot/reports/options_chat_gateway_v10.json'))['status'] == 'passed'
        assert json.loads(archive.read('FinPilot/reports/options_expirations_regression_v10.json'))['status'] == 'passed'
        assert 'FinPilot/docs/options_refresh_v11.md' in names
        assert 'FinPilot/app/options_refresh.py' in names
        assert 'FinPilot/app/options_changes.py' in names
        assert json.loads(archive.read('FinPilot/reports/options_refresh_browser_v11.json'))['status'] == 'passed'
        assert json.loads(archive.read('FinPilot/reports/options_refresh_cloud_v11.json'))['status'] == 'passed'
        assert 'FinPilot/reports/options_refresh_gateway_v11.json' in names
        assert 'FinPilot/reports/options_refresh_gateway_probe_v11.json' in names
        assert 'FinPilot/docs/ibkr_gateway_v12.md' in names
        assert json.loads(archive.read('FinPilot/reports/options_diagnostics_browser_v12.json'))['status'] == 'passed'
        live = json.loads(archive.read('FinPilot/reports/ibkr_browser_live_v12.json'))
        assert live['status'] in {'passed', 'passed_limited'} and live['workflow_status'] == 'passed'
        assert len(live['captures']) == 2 and live['counters']['confirmed_deepseek_replies'] == 2
        assert live['old_snapshot_unchanged'] and live['history_count'] == 2
        assert live['semantic_review']['status'] == 'accepted_limited'
        if live['market_data_level'] == 'limited':
            assert live['status'] == 'passed_limited' and live['full_quote_validation'] is False
        assert 'FinPilot/docs/history_rag_v13.md' in names and 'FinPilot/docs/demo_v13.md' in names
        assert 'FinPilot/data/expert_knowledge.json' in names and 'FinPilot/app/options_history_ibkr.py' in names
        assert json.loads(archive.read('FinPilot/reports/options_history_browser_v13.json'))['status'] == 'passed'
        history = json.loads(archive.read('FinPilot/reports/history_cloud_v13.json'))
        assert history['status'] == 'passed_limited' and history['workflow_status'] == 'passed'
        assert history['counters']['confirmed_deepseek_replies'] == 2 and history['old_snapshot_unchanged']
        assert history['capture']['server_reported_history_requests'] == 3
        assert history['capture']['aggregation']['full_session_verified'] is False
        assert 'FinPilot/docs/innovation_rag_v14.md' in names and 'FinPilot/docs/demo_v14.md' in names
        assert 'FinPilot/web/demo.html' in names and 'FinPilot/app/expert_grounding.py' in names
        catalogue = json.loads(archive.read('FinPilot/data/expert_knowledge.json'))
        assert len(catalogue['documents']) == 14 and all(doc['supports'] for doc in catalogue['documents'])
        assert json.loads(archive.read('FinPilot/reports/guided_demo_browser_v14.json'))['status'] == 'passed'
        demo = json.loads(archive.read('FinPilot/reports/expert_demo_cloud_v14.json'))
        assert demo['status'] == 'passed_limited' and demo['workflow_status'] == 'passed'
        assert demo['new_broker_requests'] == 0 and demo['counters']['confirmed_deepseek_replies'] == 2
        assert demo['original_analysis_unchanged'] and demo['owned_session_persisted_and_exported']
        snapshot = json.loads(archive.read('FinPilot/reports/snapshot_expert_cloud_v14.json'))
        assert snapshot['status'] == 'passed_limited' and snapshot['grounding']['method'] == 'reviewed_support_facets'
        assert snapshot['broker_requests'] == 0 and snapshot['sources']
        holdout = json.loads(archive.read('FinPilot/reports/expert_retrieval_holdout_v14.json'))
        assert holdout['construction']['held_out_from_ranker_tuning'] and holdout['summary']['queries'] == 24
        audit = json.loads(archive.read('FinPilot/reports/innovation_acceptance_v14.json'))
        assert audit['status'] == 'passed_limited' and audit['server_tests']['failures'] == 0
        assert audit['real_model_validation']['final_validated_answers'] == 3
        assert audit['real_model_validation']['first_pass_all_correct'] is False
        # Current release requirements; historical pass reports above remain
        # historical. Native/cloud evidence statuses are surfaced unchanged,
        # never promoted to passed by this packaging/startup check.
        for relative in ["start-desktop.ps1", "desktop/package.json", "desktop/package-lock.json", "desktop/main.cjs",
                         "desktop/preload.cjs", "desktop/geometry.cjs", "desktop/build.cjs", "desktop/README.md", "desktop/tray.png",
                         "web/pet.html", "web/pet.js", "web/pet.css", "app/companion.py", "web/companion/client.js",
                         "web/companion/messages.js", "web/companion/renderer.js", "docs/desktop_pet_v15.md", "docs/demo_v15.md"]:
            assert "FinPilot/" + relative in names, relative
        assert any(name.startswith("FinPilot/desktop/tests/") for name in names)
        portable_name = "FinPilot/" + PORTABLE
        assert archive.getinfo(portable_name).file_size == PORTABLE_BYTES
        assert archive_sha256(archive, portable_name) == PORTABLE_SHA256
        assert [name for name in names if name.startswith("FinPilot/desktop/artifacts/")] == [portable_name]
        desktop = json.loads(archive.read("FinPilot/desktop/package.json"))
        lock = json.loads(archive.read("FinPilot/desktop/package-lock.json"))
        assert desktop["version"] == NATIVE_HOST_VERSION and lock["version"] == NATIVE_HOST_VERSION
        assert desktop["devDependencies"]["electron"] == "45.3.0"
        assert desktop["devDependencies"]["electron-builder"] == "26.18.0"
        assert lock["packages"]["node_modules/electron"]["version"] == "45.3.0"
        assert lock["packages"]["node_modules/electron-builder"]["version"] == "26.18.0"
        provenance = json.loads(archive.read("FinPilot/web/companion/provenance.json"))
        assert provenance["commit"] == "7661c8b304c5400701f91da01b1a643a207331de"
        assert provenance["runtime_image_bytes"] <= 12 * 1024 * 1024
        assert sum(item["bytes"] for item in provenance["outputs"].values()) == provenance["runtime_image_bytes"]
        for filename, item in provenance["outputs"].items():
            asset_name = "FinPilot/web/companion/assets/" + filename
            assert archive.getinfo(asset_name).file_size == item["bytes"]
            assert archive_sha256(archive, asset_name) == item["sha256"]
        for filename in ["ATTRIBUTION.md", "YUNYUESAMA-LICENSE.txt", "UPSTREAM-ASSET_LICENSE.md", "CC-BY-NC-SA-4.0.txt"]:
            assert "FinPilot/web/companion/licenses/" + filename in names
        assert b'/static/companion/licenses/ATTRIBUTION.md' in archive.read("FinPilot/web/index.html")
        for filename in ["desktop_pet_v15.md", "demo_v15.md"]:
            assert b"PENDING_V15_FINAL_VERIFICATION" not in archive.read("FinPilot/docs/" + filename)
        for filename in ["companion_renderer_v15.json", "desktop_build_v15.json", "pet_browser_v15.json", "companion_sync_browser_v15.json", "workspace_companion_v15.json"]:
            assert json.loads(archive.read("FinPilot/reports/" + filename))["status"] == "passed"
        declared_v15_evidence = {}
        for filename in V15_ACCEPTANCE:
            evidence = json.loads(archive.read("FinPilot/reports/" + filename))
            scope = evidence.get("scope") or evidence.get("objective") or evidence.get("verification_scope")
            assert scope and isinstance(evidence.get("status"), str), filename
            declared_v15_evidence[filename] = {"status": evidence["status"], "scope": scope}
        for relative in [*V16_REQUIRED_FILES, *V17_REQUIRED_FILES]:
            assert "FinPilot/" + relative in names, relative
        reviewed_help = json.loads(archive.read("FinPilot/data/project_help.json"))
        assert reviewed_help["current_version"] == 17 and reviewed_help["manual_version"] == "17.0"
        assert any(topic['id']=='help.learning' for topic in reviewed_help['documents'])
        for relative in ['docs/options_learning_v17.md','docs/demo_v17.md']:
            assert b'PENDING_V17' not in archive.read('FinPilot/'+relative)
        assert all(re.fullmatch(r"help\.[a-z_]+", topic["id"]) for topic in reviewed_help["documents"])
        assert len({topic["id"] for topic in reviewed_help["documents"]}) == len(reviewed_help["documents"])
        assert b"PENDING_V16_FINAL_VERIFICATION" not in archive.read("FinPilot/docs/project_help_v16.md")
        declared_v16_evidence = {}
        for filename in V16_ACCEPTANCE:
            evidence = json.loads(archive.read("FinPilot/reports/" + filename))
            scope = evidence.get("scope") or evidence.get("objective") or evidence.get("verification_scope")
            assert scope and isinstance(evidence.get("status"), str), filename
            declared_v16_evidence[filename] = {"status": evidence["status"], "scope": scope}
        declared_v17_evidence = {}
        for filename in V17_ACCEPTANCE:
            evidence = json.loads(archive.read("FinPilot/reports/" + filename))
            assert isinstance(evidence.get('status'),str), filename
            declared_v17_evidence[filename] = {'status':evidence['status'],'scope':evidence.get('scope')}
        assert "FinPilot/output/presentations/FinPilot_Demo_EN.pptx" in names, "PPTX missing"
        assert "FinPilot/output/presentations/FinPilot_Demo_EN_v2.pptx" in names, "Updated PPTX missing"
        manifest = json.loads(archive.read("FinPilot/models/finpilot-lora/training_manifest.json"))
        assert manifest["trained"] and manifest["steps"] > 0
        assert hashlib.sha256(archive.read("FinPilot/models/finpilot-lora/adapter_model.safetensors")).hexdigest() == manifest["adapter_sha256"]
        # Retain this isolated extraction as an audit artifact. Windows may hold
        # a short-lived directory handle after the child exits; auto-cleanup in
        # Python 3.11 can recurse on that PermissionError and hide check results.
        with nullcontext(tempfile.mkdtemp(prefix="isolated-", dir=scratch)) as temporary:
            # Explicitly resolved under the intended workspace; tmp is excluded.
            assert Path(temporary).resolve().is_relative_to(scratch)
            archive.extractall(temporary)
            extracted = Path(temporary) / "FinPilot"
            env = {**os.environ, "FINPILOT_OFFLINE": "true", "IBKR_ENABLED": "false", "DEEPSEEK_API_KEY": "", "PYTHONIOENCODING": "utf-8",
                   "FINPILOT_DB": str(extracted / "data/package-check.sqlite3"),
                   "FINPILOT_ML_PYTHON": str(extracted / "not-installed-local-worker.exe"),
                   "FINPILOT_OPTIONS_MODEL_DIAGNOSTICS": "0"}
            script = """
import asyncio,json,hashlib,re
from pathlib import Path
from fastapi.testclient import TestClient
from app.llm import DeepSeek
from app.local_llm import LocalLoRA
from app.knowledge import KnowledgeRetriever
import httpx
counts={'model_calls':0,'broker_or_network_connections':0}
async def forbid_model(*args,**kwargs):
    counts['model_calls']+=1
    raise AssertionError('Unexpected model invocation in offline package verification')
async def forbid_network(*args,**kwargs):
    counts['broker_or_network_connections']+=1
    raise AssertionError('Unexpected outbound network connection in offline package verification')
DeepSeek.complete=forbid_model
LocalLoRA.complete=forbid_model
asyncio.open_connection=forbid_network
asyncio.BaseEventLoop.create_connection=forbid_network
httpx.AsyncClient.send=forbid_network
from app.main import app
assert app.state.store.path.resolve().is_relative_to(Path.cwd().resolve())
c=TestClient(app)
assert c.get('/api/health').json()['mode']=='offline'
assert c.get('/api/health').json()['application']=='FinPilot'
assert c.get('/').status_code==200
assert c.get('/static/showcase/media/reference-motion.mp4', headers={'Range': 'bytes=0-31'}).status_code==206
assert c.get('/workspace').status_code==200
assert c.get('/demo').status_code==200
assert c.get('/api/health').json()['version']=='17.0.0'
assert c.get('/learn').status_code==200
assert len(c.get('/api/options-lab/scenarios').json()['scenarios'])==3
lab=c.post('/api/options-lab/evaluate',json={'expiry_price':102}).json()
assert lab['lab_context']['trial']['pnl']==-160 and 'analysis_id' not in lab
assert lab['lab_context']['source']['kind']=='synthetic_demo' and lab['source']['kind']=='demo'
assert c.get('/help').status_code==200
help_catalogue=c.get('/api/project-help?language=zh').json()
assert help_catalogue['current_version']==17 and help_catalogue['manual_version']=='17.0'
assert all(source['matches_reviewed'] for entry in help_catalogue['topics'] for source in entry['source_files'])
manual_entries={entry['id']:entry for entry in help_catalogue['topics']}
assert len(manual_entries)==len(help_catalogue['topics']) and 'help.boundaries' in manual_entries
assert all(re.fullmatch(r'help\\.[a-z_]+',key) for key in manual_entries)
assert all(entry['url']=='/help#'+key for key,entry in manual_entries.items())
assert manual_entries['help.boundaries']['known'] is False
help_topic=c.get('/api/project-help/topics/help.history?language=zh').json()
assert help_topic==manual_entries['help.history']
assert any(entry['id']=='help.history' for entry in c.get('/api/project-help/search',params={'q':'历史复盘','language':'zh'}).json()['topics'])
for unknown_path in ('help.not_implemented','.env','%2e%2e%2f.env'):
    rejected=c.get('/api/project-help/topics/'+unknown_path)
    assert rejected.status_code==404 and 'DEEPSEEK_API_KEY' not in rejected.text
assert c.get('/pet').status_code==200
assert 'FinPilotCompanion' in c.get('/static/companion/renderer.js').text
assert c.get('/static/companion/licenses/ATTRIBUTION.md').status_code==200
manifest=c.get('/static/companion/manifest.json').json()
assert manifest['character']=='deepseek-whale-maid' and manifest['runtime_image_bytes']<=12*1024*1024
assert c.get('/api/companion/connection').json()['session_id'] is None
assert c.get('/api/companion/connection').json()['desktop_connected'] is False
assert '/api/companion/events' in c.get('/openapi.json').json()['paths']
assert 'workspace-motion-toggle' in c.get('/workspace').text
assert 'options-dialog' in c.get('/workspace').text
assert c.get('/api/options/status').json()['status']=='disabled'
assert '/api/options/analyses/{analysis_id}' in c.get('/openapi.json').json()['paths']
assert c.get('/api/options/expirations?symbol=AAPL').json()['detail']['code']=='ibkr_disabled'
assert c.post('/api/options/analyze',json={'symbol':'AAPL'}).json()['detail']['code']=='ibkr_disabled'
batch=c.post('/api/options/batch',json={'items':[{'symbol':'AAPL'},{'symbol':'MSFT'}]}).json()
assert not batch['reports'] and len(batch['failures'])==2
assert batch['plain_brief']['status']=='limited'
showcase=c.get('/api/showcase').json()
expected_documents=len(KnowledgeRetriever(Path('data/knowledge.json')).documents)
assert showcase['document_count']==len(showcase['knowledge_sources'])==expected_documents
r=c.post('/api/chat',json={'message':'什么是复利？'}).json()
assert r['mode']=='offline' and r['sources']
general=c.post('/api/chat',json={'message':'解释一下光合作用。'}).json()
assert general['mode']=='offline' and not general['sources'] and general['warning']=='offline_requested'
assert not r.get('project_help') and not general.get('project_help')
chat_calculator=c.post('/api/chat',json={'message':'loan principal=1200 annual_rate=0 years=1'}).json()
assert chat_calculator['mode']=='calculator' and not chat_calculator.get('project_help')
assert chat_calculator['calculation']['values']['monthly_payment']=='100.00'
from datetime import datetime, timezone
stamp=datetime.now(timezone.utc).isoformat()
saved_id=app.state.store.save_analysis({'snapshot':{'symbol':'TEST','expiration':'2030-01-18','received_at':stamp},'analyzed_at':stamp,'quality':{'market_data_status':'delayed','quote_coverage':0},'collective':{'evidence':[],'assessment':{'status':'insufficient'}}})
assert c.get('/api/options/analyses/'+saved_id).json()['analysis_id']==saved_id
follow=c.post('/api/chat',json={'message':'解释这批期权数据','analysis_id':saved_id}).json()
assert follow['mode']=='offline' and follow['analysis_context']['analysis_id']==saved_id
session=c.get('/api/sessions/'+follow['session_id']).json()
assert session['active_analysis_id']==saved_id and session['messages'][-1]['analysis_context']['analysis_id']==saved_id
assert session['analysis_history'][0]['analysis_id']==saved_id
failed_refresh=c.post('/api/sessions/'+follow['session_id']+'/analysis/refresh',json={'analysis_id':saved_id})
assert failed_refresh.status_code in (422,503)
assert c.get('/api/sessions/'+follow['session_id']).json()['active_analysis_id']==saved_id
assert c.put('/api/sessions/'+follow['session_id']+'/analysis',json={'analysis_id':None}).json()['active_analysis'] is None
assert c.post('/api/calculate',json={'kind':'loan','principal':1200,'annual_rate':0,'years':1}).json()['values']['monthly_payment']=='100.00'
assert c.get('/docs').status_code==200
historical=c.post('/api/options/history/sample').json()
assert historical['analysis_kind']=='historical_options' and historical['source']['kind']=='ibkr_historical'
assert historical['bar_basis']=='derived_from_intraday_trades'
historical_fingerprint=hashlib.sha256(json.dumps(historical,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
help_sid=c.post('/api/sessions',json={'title':'isolated v16 manual workflow'}).json()['id']
assert c.put('/api/sessions/'+help_sid+'/analysis',json={'analysis_id':historical['analysis_id']}).status_code==200
help_replies=[]
for index,question in enumerate(('期权分析怎么用？','下一步')):
    guided=c.post('/api/chat',json={'session_id':help_sid,'message':question,'language':'zh'}).json()
    assert guided['mode']=='project-help' and not guided.get('analysis_context')
    context=guided['project_help']
    assert context['intent']=='project_help' and context['known'] is True
    assert context['followup_used'] is (index==1) and 'help.options' in context['topic_ids']
    assert set(context['topic_ids'])<=manual_entries.keys()
    expected_steps=[step for topic_id in context['topic_ids'] for step in manual_entries[topic_id]['steps']]
    assert context['steps']==expected_steps
    for step in expected_steps:
        assert step in guided['answer']
    assert [source['id'] for source in guided['sources']]==context['topic_ids']
    assert all(source['url']=='/help#'+source['id'] for source in guided['sources'])
    assert context['selector']['engine']=='local-manual' and context['selector']['generation_attempts']==0
    assert guided['generation_attempts']==guided['schema_repair_attempts']==0
    assert context['grounding']['model_generated_steps'] is False
    assert guided['active_analysis']['analysis_id']==historical['analysis_id']
    help_replies.append(guided)
help_saved=c.get('/api/sessions/'+help_sid).json()
assert help_saved['active_analysis_id']==historical['analysis_id']
assert len(help_saved['messages'])==len({message['id'] for message in help_saved['messages']})==4
for index,reply in enumerate(help_replies):
    message=help_saved['messages'][index*2+1]
    assert message['mode']=='project-help' and message['analysis_context'] is None
    assert message['project_help']==reply['project_help'] and message['sources']==reply['sources']
unknown_help=c.post('/api/chat',json={'session_id':help_sid,'message':'本项目支持火星电台遥控器吗？'}).json()
assert unknown_help['mode']=='project-help' and unknown_help['project_help']['known'] is False
assert unknown_help['project_help']['topic_ids']==['help.boundaries']
assert unknown_help['project_help']['selector']['generation_attempts']==0
assert c.get('/api/sessions/'+help_sid).json()['active_analysis_id']==historical['analysis_id']
assert not unknown_help.get('analysis_context')
assert hashlib.sha256(json.dumps(c.get('/api/options/analyses/'+historical['analysis_id']).json(),sort_keys=True,ensure_ascii=False).encode()).hexdigest()==historical_fingerprint
assert c.get('/api/experts/search',params={'q':'未平仓量不是资金流入'}).json()
experts=c.get('/api/experts').json()
assert len(experts['documents'])==14 and experts['corpus_sha256']
hist_reply=c.post('/api/chat',json={'message':'为什么看跌成交不能说明多数人看空？','analysis_id':historical['analysis_id']}).json()
assert hist_reply['mode']=='offline' and hist_reply['sources'] and hist_reply['analysis_context']['historical_data']
sid=hist_reply['session_id']
connection=c.put('/api/companion/connection',json={'session_id':sid,'language':'zh','engine':'deepseek'}).json()
assert connection['session_id']==sid and connection['generation']>0
activity={'operation_id':'package-calculator','kind':'calculate','status':'started','session_id':sid,'generation':connection['generation']}
assert c.post('/api/companion/activity',json=activity).status_code==200
assert c.post('/api/companion/activity',json={**activity,'status':'completed'}).status_code==200
assert c.get('/api/companion/connection').json()['activities']==[]
assert c.put('/api/sessions/'+sid+'/analysis',json={'analysis_id':saved_id}).status_code==200
inherited=c.post('/api/chat',json={'message':'用白话解释当前报告的限制','session_id':sid}).json()
assert inherited['mode']=='offline' and inherited['analysis_context']['analysis_id']==saved_id
persisted=c.get('/api/sessions/'+sid).json()
assert persisted['messages'][1]['analysis_context']['analysis_id']==historical['analysis_id']
assert persisted['messages'][-1]['analysis_context']['analysis_id']==saved_id
assert len({m['id'] for m in persisted['messages']})==len(persisted['messages'])==4
assert c.put('/api/companion/connection',json={'session_id':None},headers={'Origin':'https://example.invalid'}).status_code==403
assert c.delete('/api/sessions/'+sid).json()['deleted'] is True
assert c.get('/api/companion/connection').json()['session_id'] is None
assert counts=={'model_calls':0,'broker_or_network_connections':0},counts
print(json.dumps({'status':'passed',**counts,'application_version':'17.0.0','native_host_version':'15.0.0','isolated_database':True,'synthetic_lab_page_and_exact_payoff':True,'shared_report_inheritance_and_immutable_old_reply':True,'project_help_catalogue_search_unknown_exact_steps_persistence_and_bound_history':True,'ordinary_finance_science_and_calculator_routes_preserved':True}))
"""
            completed = subprocess.run([sys.executable, "-c", script], cwd=extracted, env=env, capture_output=True, text=True, timeout=30)
            assert completed.returncode == 0, completed.stderr
            isolated_result = json.loads(completed.stdout.strip().splitlines()[-1])
            assert isolated_result['status'] == 'passed' and isolated_result['model_calls'] == 0 and isolated_result['broker_or_network_connections'] == 0
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "passed", "archive": ZIP.name,
              "application_version": APPLICATION_VERSION, "native_host_version": NATIVE_HOST_VERSION,
              "sha256": hashlib.sha256(ZIP.read_bytes()).hexdigest(), "files": len(names),
              "isolated_extraction_retained_for_audit": True,
              "desktop_portable": {"version": NATIVE_HOST_VERSION, "path": PORTABLE, "bytes": PORTABLE_BYTES, "sha256": PORTABLE_SHA256},
              "python_runtime_bundled": False, "requires_existing_finpilot_python_environment": True,
              "isolated_workflow": isolated_result,
              "v15_declared_evidence": declared_v15_evidence,
              "v16_declared_evidence": declared_v16_evidence,
              "v17_declared_evidence": declared_v17_evidence,
              "status_scope": "v17 package integrity and isolated offline backend workflows only. Application v17 uses the unchanged native host v15. Historical, UI and real-model report statuses above are preserved, not certified as passed by this check.",
              "checks": ["no_credential_patterns", "no_env_or_database", "expected_sources_and_updated_deck_present", "novice_options_and_acceptance_present", "actual_expirations_and_general_chat_acceptance_present", "snapshot_chat_and_acceptance_present", "historical_expert_rag_and_real_workflow_present", "trained_adapter_hash_matches", "isolated_extraction", "offline_startup_media_chat_calculator_batch_and_snapshot_followup", "offline_historical_archive_expert_retrieval_and_followup"],
              "limitation": "Uses current installed Python dependencies; does not simulate an OS with no Python or no package network."}
    report['checks'].extend(['historical_v14_guided_demo_three_viewports_report_present', 'historical_v14_real_archived_data_two_model_turns_and_support_audit_present', 'historical_v14_snapshot_expert_grounding_report_present', 'historical_v14_frozen_blind_retrieval_evaluation_present'])
    report['checks'].extend(['v15_desktop_source_and_exact_reviewed_portable', 'no_installed_or_unpacked_electron', 'pinned_sprite_integrity_and_separate_licenses', 'explicitly_scoped_v15_acceptance_reports_present', 'offline_v15_pet_connection_activity_inherited_report_and_delete_zero_model_or_broker'])
    report['checks'].extend(['v16_manual_sources_page_and_scoped_reports_present', 'offline_manual_catalogue_search_known_topic_unknown_paths_no_file_disclosure', 'offline_manual_exact_steps_and_source_whitelist', 'bound_historical_report_unchanged_and_help_metadata_persisted_without_financial_context', 'ordinary_finance_science_and_calculator_paths_preserved_zero_model_or_broker'])
    (ROOT / "dist" / "package_check_v17.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
