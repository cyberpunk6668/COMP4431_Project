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
ZIP = ROOT / "dist" / "FinPilot_submission_v14.zip"


def main():
    scratch = (ROOT / "tmp" / "package-check").resolve()
    assert scratch.is_relative_to(ROOT.resolve())
    scratch.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP) as archive:
        names = archive.namelist()
        for name in names:
            assert name.startswith("FinPilot/") and ".." not in Path(name).parts
            assert not name.endswith("/.env") and ".venv/" not in name and ".sqlite" not in name
            assert not re.search(rb"sk-[a-zA-Z0-9_-]{20,}", archive.read(name)), name
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
            env = {**os.environ, "FINPILOT_OFFLINE": "true", "IBKR_ENABLED": "false", "DEEPSEEK_API_KEY": "", "PYTHONIOENCODING": "utf-8"}
            script = """
from fastapi.testclient import TestClient
from app.main import app
c=TestClient(app)
assert c.get('/api/health').json()['mode']=='offline'
assert c.get('/').status_code==200
assert c.get('/static/showcase/media/reference-motion.mp4', headers={'Range': 'bytes=0-31'}).status_code==206
assert c.get('/workspace').status_code==200
assert c.get('/demo').status_code==200
assert c.get('/api/health').json()['version']=='14.0.0'
assert 'workspace-motion-toggle' in c.get('/workspace').text
assert 'options-dialog' in c.get('/workspace').text
assert c.get('/api/options/status').json()['status']=='disabled'
assert '/api/options/analyses/{analysis_id}' in c.get('/openapi.json').json()['paths']
assert c.get('/api/options/expirations?symbol=AAPL').json()['detail']['code']=='ibkr_disabled'
assert c.post('/api/options/analyze',json={'symbol':'AAPL'}).json()['detail']['code']=='ibkr_disabled'
batch=c.post('/api/options/batch',json={'items':[{'symbol':'AAPL'},{'symbol':'MSFT'}]}).json()
assert not batch['reports'] and len(batch['failures'])==2
assert batch['plain_brief']['status']=='limited'
assert c.get('/api/showcase').json()['document_count']==18
r=c.post('/api/chat',json={'message':'什么是复利？'}).json()
assert r['mode']=='offline' and r['sources']
general=c.post('/api/chat',json={'message':'解释一下光合作用。'}).json()
assert general['mode']=='offline' and not general['sources'] and general['warning']=='offline_requested'
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
assert c.get('/api/experts/search',params={'q':'未平仓量不是资金流入'}).json()
experts=c.get('/api/experts').json()
assert len(experts['documents'])==14 and experts['corpus_sha256']
hist_reply=c.post('/api/chat',json={'message':'为什么看跌成交不能说明多数人看空？','analysis_id':historical['analysis_id']}).json()
assert hist_reply['mode']=='offline' and hist_reply['sources'] and hist_reply['analysis_context']['historical_data']
print('Isolated submission startup, snapshot follow-up and offline workflows passed')
"""
            completed = subprocess.run([sys.executable, "-c", script], cwd=extracted, env=env, capture_output=True, text=True, timeout=30)
            assert completed.returncode == 0, completed.stderr
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "passed", "archive": ZIP.name,
              "sha256": hashlib.sha256(ZIP.read_bytes()).hexdigest(), "files": len(names),
              "isolated_extraction_retained_for_audit": True,
              "checks": ["no_credential_patterns", "no_env_or_database", "expected_sources_and_updated_deck_present", "novice_options_and_acceptance_present", "actual_expirations_and_general_chat_acceptance_present", "snapshot_chat_and_acceptance_present", "historical_expert_rag_and_real_workflow_present", "trained_adapter_hash_matches", "isolated_extraction", "offline_startup_media_chat_calculator_batch_and_snapshot_followup", "offline_historical_archive_expert_retrieval_and_followup"],
              "limitation": "Uses current installed Python dependencies; does not simulate an OS with no Python or no package network."}
    report['checks'].extend(['guided_demo_three_viewports', 'real_archived_data_two_model_turns_and_support_audit', 'snapshot_expert_grounding', 'frozen_blind_retrieval_evaluation'])
    (ROOT / "dist" / "package_check_v14.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
