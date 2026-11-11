"""Opt-in two-surface real DeepSeek check using an existing IBKR archive.

Default is a zero-call dry run. --live requires the explicitly isolated :8020
backend and the already-running owned native test instance's loopback CDP port.
No broker data is collected, no response is fabricated, no failed turn retried.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.check_history_live_v13 import audit_answer, audit_history, fingerprint, read_response, safe_text
from scripts.check_expert_demo_live_v14 import audit_grounding

QUESTIONS = (
    '这份历史报告中的未平仓量为什么是缺失？只说明这类历史接口提供哪些字段，以及缺失是否等于零，不讨论走势或下一步操作。',
    '接着解释这批历史样本的看跌成交占比。它能说明现在市场看空吗？只说明这批历史样本的局限，不补充操作建议。',
)


def run(base, cdp):
    import httpx
    from playwright.sync_api import sync_playwright, expect

    assert base == 'http://127.0.0.1:8020', 'Only the isolated acceptance server is allowed'
    assert cdp == 'http://127.0.0.1:9438', 'Only the owned native acceptance instance is allowed'
    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
    target = ROOT / 'reports/pet_cloud_v15.json'
    if target.exists():
        target = target.with_stem(target.stem + '-' + stamp)
    shots = ROOT / 'reports/screenshots/pet-cloud-v15' / stamp
    report = dict(checked_at=datetime.now(UTC).isoformat(), status='running', phase='initializing',
        scope='Actual Edge workspace + actual packaged Electron renderer over loopback to real DeepSeek, using archived IBKR bars.',
        ui_input='Playwright renderer input; native mouse/tray checks are a separate report.',
        no_financial_response_mocking=True, new_broker_requests=0, automatic_script_retries=0,
        model_budget={'answer_turns': 2, 'maximum_generations': 4, 'maximum_schema_repairs_per_answer': 1},
        count_visibility='Generation/repair counts are server-reported. Only script-owned turns counted; unrelated manual interaction is excluded.',
        counters={'chat_http_requests': 0, 'confirmed_deepseek_replies': 0}, turns=[], checks=[], screenshots=[],
        questions=list(QUESTIONS))
    import hashlib
    report['source_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
        ('app/history_chat.py','app/options_claims.py','app/expert_grounding.py',
         'web/companion/client.js','web/companion/messages.js','web/pet.js','web/app.js')}
    report['native_focus_suppressed_by_test_harness']=True
    sid, prior, native, browser = None, None, None, None
    try:
        with httpx.Client(base_url=base, timeout=20) as api, sync_playwright() as pw:
            def request(method, path, **kwargs):
                r = api.request(method, path, **kwargs)
                assert r.is_success, f'Owned acceptance API HTTP {r.status_code}'
                return r.json()
            health = request('GET', '/api/health')
            assert health['application'] == 'FinPilot' and health['version'] == '15.0.0'
            assert health['mode'] in ('deepseek', 'online')
            prior = request('GET', '/api/companion/connection')
            catalogue = request('GET', '/api/experts')
            report['phase'] = 'archive_replay_no_gateway'
            record = request('POST', '/api/options/history/sample?language=zh')
            archive = audit_history(record, {'symbol':'AAPL','expiry':'2026-11-13','strike':350.})
            archive['archived_original_capture_history_requests'] = archive.pop('server_reported_history_requests')
            archive['this_run_new_broker_requests'] = 0
            report['archive'] = archive
            report['archive_sha256'] = record['source']['archive_sha256']
            before = fingerprint(record)
            sid = request('POST', '/api/sessions', json={'title':'v15 owned two-surface archive verification'})['id']
            request('PUT', f'/api/sessions/{sid}/analysis', json={'analysis_id':record['analysis_id']})
            request('PUT', '/api/companion/connection', json={'session_id':sid,'engine':'deepseek','language':'zh'})
            native_browser = pw.chromium.connect_over_cdp(cdp)
            candidates = [p for c in native_browser.contexts for p in c.pages if p.url == base+'/pet']
            assert len(candidates) == 1
            native = candidates[0]
            assert native.evaluate('window.finPilotPet.getStatus().native')
            native.wait_for_function('(sid)=>window.finPilotPet.getStatus().sessionId===sid', arg=sid)
            native.evaluate('window.finPilotPet.openPanel()')
            browser = pw.chromium.launch(channel='msedge', headless=True)
            context = browser.new_context(viewport={'width':1440,'height':1000}, locale='zh-CN')
            context.route('**/api/sessions', lambda route: route.fulfill(json={'sessions':[]}) if route.request.method=='GET' else route.abort())
            context.route('https://**/*', lambda route: route.abort())
            page = context.new_page()
            errors=[]
            page.on('pageerror', lambda err: errors.append(safe_text(err)))
            page.goto(base + '/workspace?session=' + sid, wait_until='domcontentloaded')
            expect(page.locator('#message-input')).to_be_enabled()
            expect(page.locator('#companion-connection-status')).to_have_attribute('data-shared','true')
            assert request('GET', f'/api/sessions/{sid}')['messages'] == []
            report['checks'].append('startup_animation_connection_and_sync_do_not_generate')
            shots.mkdir(parents=True)
            for i, (surface, current, input_sel, send_sel) in enumerate([
                ('workspace', page, '#message-input', '#send-button'),
                ('native_pet', native, '#pet-input', '#pet-send'),
            ]):
                report['phase'] = f'turn_{i+1}_{surface}'
                expect(current.locator(input_sel)).to_be_enabled(timeout=15000)
                current.locator(input_sel).fill(QUESTIONS[i])
                with current.expect_response(lambda r: urlsplit(r.url).path=='/api/chat' and r.request.method=='POST', timeout=150000) as pending:
                    current.locator(send_sel).click()
                response = pending.value
                report['counters']['chat_http_requests'] += 1
                body = response.request.post_data_json
                assert body['session_id'] == sid and 'analysis_id' not in body
                reply = read_response(response, report)
                report.setdefault('received_replies',[]).append({
                    'surface':surface,'mode':reply.get('mode'),'warning':reply.get('warning'),
                    'generation_attempts':reply.get('generation_attempts'),
                    'schema_repair_attempts':reply.get('schema_repair_attempts')})
                turn = audit_answer(reply, record, require_data=True)
                turn['surface'] = surface
                turn['grounding_audit'] = audit_grounding(reply, record, QUESTIONS[i], catalogue)
                report['turns'].append(turn)
                report['counters']['confirmed_deepseek_replies'] += 1
                expected = (i+1)*2
                page.wait_for_function('(count)=>document.querySelectorAll("#chat-messages .message[data-message-id]").length===count', arg=expected, timeout=20000)
                native.wait_for_function('(count)=>document.querySelectorAll("#pet-messages [data-message-id]").length===count', arg=expected, timeout=20000)
                saved = request('GET', f'/api/sessions/{sid}')
                ids = [m['id'] for m in saved['messages']]
                assert len(ids)==expected and len(set(ids))==expected
                assert saved['active_analysis_id']==record['analysis_id']
                assert all(m.get('analysis_context',{}).get('analysis_id')==record['analysis_id'] for m in saved['messages'] if m['role']=='assistant')
                report['checks'].append(f'turn_{i+1}_both_surfaces_authoritative_ids_no_duplicate')
                shot = shots/f'{i+1}-{surface}.png'
                try:
                    current.screenshot(path=str(shot), animations='disabled', omit_background=surface=='native_pet',timeout=6000)
                    report['screenshots'].append(shot.relative_to(ROOT).as_posix())
                except Exception:
                    report.setdefault('screenshot_limits',[]).append(surface+': owned renderer screenshot unavailable; no desktop-capture fallback attempted')
            assert before == fingerprint(request('GET','/api/options/analyses/'+record['analysis_id']))
            assert not errors
            report['checks'] += ['immutable_archive_unchanged','historical_times_numeric_evidence_expert_sources_exact','missing_oi_not_zero_and_no_current_sentiment_claim']
            report['server_reported_generations'] = sum(t['server_reported_generation_attempts'] for t in report['turns'])
            report['server_reported_schema_repairs'] = sum(t['server_reported_schema_repair_attempts'] for t in report['turns'])
            report['status']='passed'; report['phase']='complete'
    except Exception as error:
        report['status']='failed'; report['error']=safe_text(error)
    finally:
        # Do not overwrite a new connection selected by a person during the test.
        if sid and prior:
            try:
                import httpx
                with httpx.Client(base_url=base, timeout=10) as api:
                    now=api.get('/api/companion/connection').json()
                    if now.get('session_id')==sid:
                        result=api.put('/api/companion/connection',json={k:prior[k] for k in ('session_id','engine','language')})
                        report['prior_explicit_connection_restored']=result.is_success
                    else:
                        report['prior_explicit_connection_restored']='skipped_person_changed_selection'
                    # Owned test messages remain in isolated test DB for audit.
                    report['owned_records_retained_in_isolated_test_database']=True
            except Exception as error:
                report['cleanup_error']=safe_text(error)
        if browser:
            try: browser.close()
            except Exception: pass
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'phase':report['phase'],'report':str(target),'counters':report['counters'],'error':report.get('error')},ensure_ascii=False))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    if not args.live:
        print('Dry run: zero HTTP, model, browser and broker calls. --live opts into two owned cloud turns.')
    else:
        raise SystemExit(run('http://127.0.0.1:8020','http://127.0.0.1:9438'))
