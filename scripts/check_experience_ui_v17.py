"""Real FinPilot routes + private SQLite + actual Edge; no user server/data.

This is an offline integration check, not a live model or IBKR acceptance.
The one injected chat 503 is explicitly labelled; every successful API call
uses the real create_app. Artifacts and failures are retained per run.
"""
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sys
from threading import Thread
import time
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    scratch = ROOT / 'tmp/experience-ui-v17' / stamp
    scratch.mkdir(parents=True, exist_ok=False)
    shots = ROOT / 'reports/screenshots/experience-v17' / stamp
    shots.mkdir(parents=True, exist_ok=False)
    report_path = ROOT / 'reports' / ('experience_ui_v17-' + stamp + '.json')
    assert scratch.resolve().is_relative_to((ROOT / 'tmp').resolve())
    # main.py has a module-level app. Guard its import before it can read .env
    # or initialize the ordinary project DB, even though that app is unused.
    os.environ.update(DEEPSEEK_API_KEY='', FINPILOT_OFFLINE='true', IBKR_ENABLED='false',
                      FINPILOT_DB=str(scratch / 'import-only.sqlite3'),
                      FINPILOT_ADAPTER=str(scratch / 'no-local-adapter'),
                      FINPILOT_OPTIONS_MODEL_DIAGNOSTICS='0')
    import dotenv
    dotenv.load_dotenv = lambda *args, **kwargs: False
    blocked, provider_attempts, broker_attempts = [], [], []
    original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex
    original_dns = socket.getaddrinfo

    def allowed(address):
        return (isinstance(address, tuple) and len(address) >= 2 and
                address[0] in {'127.0.0.1', '::1', 'localhost'} and
                isinstance(address[1], int) and address[1] >= 32768)

    def connect(sock, address):
        if not allowed(address):
            blocked.append({'operation':'connect', 'address':str(address)[:140]})
            raise AssertionError('Only owned high-port loopback connections are permitted')
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if not allowed(address):
            blocked.append({'operation':'connect_ex', 'address':str(address)[:140]})
            raise AssertionError('Only owned high-port loopback connections are permitted')
        return original_connect_ex(sock, address)

    def dns(host, *args, **kwargs):
        if host not in {None, '127.0.0.1', '::1', 'localhost'}:
            blocked.append({'operation':'DNS', 'host':str(host)[:100]})
            raise AssertionError('External DNS is forbidden in this check')
        return original_dns(host, *args, **kwargs)

    socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = connect, connect_ex, dns
    from app.config import Settings
    from app.llm import DeepSeek
    from app.local_llm import LocalLoRA

    async def forbidden_provider(*args, **kwargs):
        provider_attempts.append('complete')
        raise AssertionError('Model generation forbidden in offline integration')

    DeepSeek.complete = forbidden_provider
    LocalLoRA.complete = forbidden_provider
    from app.main import create_app

    class NoGateway:
        async def status(self):
            return {'enabled':False, 'connected':False, 'provider':'ibkr', 'read_only':True}
        async def snapshot(self, *args, **kwargs):
            broker_attempts.append('snapshot')
            raise AssertionError('No broker snapshot permitted')
        async def fetch(self, *args, **kwargs):
            broker_attempts.append('history')
            raise AssertionError('No broker history permitted')
        async def list_expirations(self, *args, **kwargs):
            broker_attempts.append('expirations')
            raise AssertionError('No broker contract request permitted')

    app = create_app(Settings(api_key='', offline=True, db_path=scratch / 'owned.sqlite3',
                              adapter_path=scratch / 'no-local-adapter'),
                     options_provider=NoGateway(), history_provider=NoGateway())
    sentinel = app.state.store.create('Private sentinel: do not open automatically')['id']
    app.state.store.append_turn(sentinel, 'PRIVATE_OLD_SESSION_SENTINEL',
                               {'answer':'Private old-session fixture', 'sources':[], 'mode':'offline'})
    # Authored synthetic files owned by this run, never user-selected documents.
    import_rows=[]
    for index, day in enumerate(['2026-11-09','2026-11-10','2026-11-11']):
        for right in ['C','P']:
            close=3.0+index*.25+(0 if right=='C' else .5)
            import_rows.append({'trading_date':day,'strike':100.0,'right':right,
                'open':close,'high':close+.2,'low':close-.2,'close':close,
                'volume':float(100+index*20),'open_interest':None,'oi_asof_date':None})
    buffer=io.StringIO(newline='')
    writer=csv.DictWriter(buffer,fieldnames=list(import_rows[0]));writer.writeheader();writer.writerows(import_rows)
    csv_path=scratch/'owned-synthetic-history.csv';csv_path.write_text(buffer.getvalue(),encoding='utf-8')
    json_path=scratch/'owned-synthetic-history.json'
    json_path.write_text(json.dumps({'label':'Controlled JSON import','symbol':'DEMO','expiry':'2026-12-18',
        'currency':'USD','multiplier':100,'source_label':'Synthetic integration fixture; not broker observations',
        'rows':import_rows},ensure_ascii=False),encoding='utf-8')
    import uvicorn
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    assert port >= 32768 and port != 8000
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
                                          log_level='error', access_log=False, loop='asyncio'))
    thread = Thread(target=lambda:server.run(sockets=[listener]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(.05)
    assert server.started, 'Owned app failed to start'
    base = f'http://127.0.0.1:{port}'
    report = {'checked_at':datetime.now(timezone.utc).isoformat(), 'status':'running',
              'scope':'Actual Edge, real create_app and private SQLite. Offline deterministic explanations; no live model, broker, user DB or normal port 8000.',
              'dotenv_loading_disabled':True, 'server_port':port, 'database':str(app.state.store.path),
              'viewports':[], 'screenshots':str(shots.relative_to(ROOT)),
              'fault_injections':['one owned chat request returns controlled HTTP 503 per viewport']}
    from playwright.sync_api import sync_playwright, expect
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True,
                args=['--disable-background-networking', '--disable-component-update', '--no-first-run'])
            for width, height in [(320,740), (390,844), (1440,1000)]:
                row={'width':width,'height':height,'status':'running','checks':[]}
                report['viewports'].append(row)
                context = browser.new_context(viewport={'width':width,'height':height},
                                              reduced_motion='reduce')
                page = context.new_page()
                page.set_default_timeout(15000)
                errors, calls, external = [], [], []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: calls.append({'method':request.method,
                    'path':urlsplit(request.url).path, 'body':request.post_data if request.method in {'POST','PUT'} else None}))
                def guard(route):
                    target = urlsplit(route.request.url)
                    if target.scheme in {'http','https'} and target.netloc != urlsplit(base).netloc:
                        external.append(route.request.url);route.abort();return
                    route.continue_()
                context.route('**/*', guard)
                def record(name): row['checks'].append(name)
                def no_overflow():
                    assert page.evaluate('() => document.documentElement.scrollWidth <= innerWidth + 1'), page.url
                def chat_count(): return sum(c['path']=='/api/chat' and c['method']=='POST' for c in calls)
                def screenshot(name):
                    page.screenshot(path=str(shots / f'{name}-{width}.png'), animations='disabled')
                def nav(selector):
                    if width < 1024:
                        page.locator('#mobile-menu').click()
                    page.locator(selector).click()
                try:
                    page.goto(base + '/', wait_until='domcontentloaded')
                    primary = page.locator('.hero-actions a[href="/learn"]')
                    expect(primary).to_be_visible();no_overflow();screenshot('home')
                    primary.click()
                    expect(page).to_have_url(base + '/learn')
                    expect(page.locator('#lab-scenarios button')).to_have_count(3)
                    expect(page.locator('#lab-pnl')).to_contain_text('140.00')
                    expect(page.locator('#lab-source')).to_contain_text('2026-11-11')
                    assert not chat_count();no_overflow();screenshot('learn-summary')
                    page.locator('#scenario-section').evaluate("node=>node.scrollIntoView({block:'start'})")
                    screenshot('learn-scenarios')
                    page.locator('#lab-trial').evaluate("node=>node.scrollIntoView({block:'start'})")
                    screenshot('learn-default-chart')
                    record('home_primary_cta_opens_real_synthetic_learning_without_chat_or_gateway')
                    page.locator('#lab-strategy').select_option('call_debit_spread')
                    page.locator('#lab-price').fill('110')
                    page.locator('#lab-calculate').click()
                    page.wait_for_function("() => window.finPilotOptionsLab.getStatus().currentTrial && !window.finPilotOptionsLab.getStatus().evaluating")
                    expect(page.locator('#lab-upper-field')).to_be_visible()
                    page.locator('#lab-trial').evaluate("node=>node.scrollIntoView({block:'start'})")
                    no_overflow();screenshot('learn-trial')
                    record('real_same_expiry_spread_calculation_and_formula_curve')
                    # Deliberately install another existing ID only before the new owned
                    # session handoff. It must not be fetched while selecting explicit SID.
                    page.evaluate("sid=>localStorage.setItem('finpilot-session',sid)", sentinel)
                    page.locator('#lab-save').click()
                    page.wait_for_function('() => window.finPilotOptionsLab.getStatus().saved')
                    saves=[c for c in calls if c['path']=='/api/options-lab/save']
                    assert len(saves)==1
                    checkpoint=len(calls)
                    page.locator('#lab-followup').click()
                    page.wait_for_url('**/workspace?session=**')
                    sid=parse_qs(urlsplit(page.url).query)['session'][0]
                    assert sid != sentinel
                    prompt=parse_qs(urlsplit(page.url).query)['prompt'][0]
                    expect(page.locator('#message-input')).to_have_value(prompt)
                    expect(page.locator('#analysis-context-card')).to_be_visible()
                    assert not chat_count()
                    assert not any(c['path']==f'/api/sessions/{sentinel}' for c in calls[checkpoint:])
                    assert 'PRIVATE_OLD_SESSION_SENTINEL' not in page.locator('#chat-messages').inner_text()
                    stored=app.state.store.get(sid)
                    assert stored['messages']==[] and stored['active_analysis_id']
                    saved_report=app.state.store.get_analysis(stored['active_analysis_id'])
                    assert saved_report['lab_context']['trial']['strategy']=='call_debit_spread'
                    assert saved_report['lab_context']['trial']['expiry_price']==110
                    record('save_persists_exact_trial_new_owned_session_binding_prompt_only_old_local_id_not_read')
                    page.locator('#send-button').click()
                    expect(page.locator('#chat-messages .lab-chat-context')).to_have_count(1)
                    expect(page.locator('#chat-messages .lab-chat-context')).to_contain_text('110')
                    expect(page.locator('#chat-messages .lab-chat-context')).to_contain_text('合成教学试算')
                    expect(page.locator('#chat-messages .message-analysis-context')).to_contain_text('合成教学区间')
                    assert '历史复盘区间' not in page.locator('#chat-messages .message-analysis-context').inner_text()
                    expect(page.locator('#chat-messages .message-analysis-context')).to_contain_text('2026-11-11')
                    assert len(app.state.store.get(sid)['messages'])==2
                    assert chat_count()==1
                    expect(page.locator('#toast')).to_be_hidden(timeout=6000)
                    page.locator('#chat-messages .message.assistant').first.evaluate("node=>node.scrollIntoView({block:'start'})")
                    screenshot('chat-answer')
                    no_overflow();page.locator('#chat-messages .lab-chat-context').scroll_into_view_if_needed();screenshot('chat-lab-context')
                    record('explicit_send_real_offline_explanation_shows_saved_trial_source_time_evidence')
                    draft='这个试算的最大损失是多少？请解释假设。'
                    page.locator('#message-input').fill(draft)
                    def fail_once(route):
                        route.fulfill(status=503,content_type='application/json',body='{"detail":"Controlled offline integration failure"}')
                        page.unroute('**/api/chat', fail_once)
                    page.route('**/api/chat', fail_once)
                    page.locator('#send-button').click()
                    expect(page.locator('#error-banner')).to_be_visible()
                    expect(page.locator('#message-input')).to_have_value(draft)
                    assert len(app.state.store.get(sid)['messages'])==2
                    page.locator('#send-button').click()
                    expect(page.locator('#chat-messages .lab-chat-context')).to_have_count(2)
                    assert len(app.state.store.get(sid)['messages'])==4
                    record('controlled_chat_failure_retains_draft_and_real_retry_keeps_prior_answers')

                    page.evaluate("() => localStorage.removeItem('finpilot-session')")
                    page.goto(base + '/workspace', wait_until='domcontentloaded')
                    expect(page.locator('#welcome .workspace-launcher-card')).to_have_count(3)
                    expect(page.locator('#starter-calculator')).to_be_visible()
                    expect(page.locator('#nav-learn')).to_have_attribute('href','/learn')
                    no_overflow();screenshot('workspace-welcome')
                    record('task_focused_welcome_and_learning_calculator_manual_entries')
                    page.locator('#starter-calculator').click()
                    expect(page.locator('#calculator-dialog')).to_be_visible()
                    for kind in ['compound','loan','budget']:
                        page.locator(f'.calc-tab[data-kind="{kind}"]').click()
                        page.locator('#calculate-button').click()
                        expect(page.locator('#calculation-output')).to_be_visible()
                        expect(page.locator('#calculation-error')).to_be_hidden()
                        assert len(page.locator('#calculation-output').inner_text())>50
                        no_overflow()
                    page.locator('.calc-tab[data-kind="compound"]').click();page.keyboard.press('ArrowRight')
                    expect(page.locator('#tab-loan')).to_have_attribute('aria-selected','true')
                    page.locator('#calc-principal').fill('200000')
                    expect(page.locator('#calculation-output')).to_be_hidden()
                    page.locator('#calculate-button').click()
                    expect(page.locator('#calculation-output')).to_be_visible();screenshot('calculator')
                    page.keyboard.press('Escape')
                    record('three_real_calculators_keyboard_tabs_and_changed_assumptions_hide_old_result')
                    nav('#nav-knowledge')
                    expect(page.locator('#knowledge-list .knowledge-card').first).to_be_visible()
                    assert page.locator('#knowledge-list a').count()>0
                    no_overflow();page.keyboard.press('Escape')
                    record('real_curated_knowledge_sources_readable_without_model')
                    if width>=390:
                        before_preferences=chat_count()
                        preference_draft='切换界面时保留的输入草稿'
                        page.locator('#message-input').fill(preference_draft)
                        page.locator('#language-toggle').click()
                        expect(page.locator('html')).to_have_attribute('lang','en')
                        expect(page.locator('#message-input')).to_have_value(preference_draft)
                        page.locator('#theme-toggle').click()
                        expect(page.locator('html')).to_have_attribute('data-theme','dark')
                        no_overflow();page.reload(wait_until='domcontentloaded')
                        expect(page.locator('html')).to_have_attribute('lang','en')
                        expect(page.locator('html')).to_have_attribute('data-theme','dark')
                        page.locator('#language-toggle').click();page.locator('#theme-toggle').click()
                        expect(page.locator('html')).to_have_attribute('lang','zh-CN')
                        expect(page.locator('html')).to_have_attribute('data-theme','light')
                        assert chat_count()==before_preferences
                        record('english_theme_persistence_and_language_change_preserves_current_draft_without_generation')
                    model_before=chat_count()
                    assert page.locator('#model-select option').count()==2
                    page.locator('#model-select').select_option('deepseek')
                    expect(page.locator('#engine-label')).to_contain_text('离线')
                    if not page.locator('#avatar-character').is_visible():
                        page.locator('#avatar-collapse').click()
                    expect(page.locator('#avatar-character')).to_have_value('whale')
                    page.locator('#avatar-character').select_option('robot')
                    page.locator('#avatar-2d').click()
                    expect(page.locator('#avatar-2d')).to_have_attribute('aria-pressed','true')
                    page.locator('#avatar-character').select_option('whale')
                    expect(page.locator('.avatar-mode-control')).to_be_hidden()
                    assert chat_count()==model_before
                    record('model_availability_and_whale_legacy_2d_entries_no_implicit_generation')
                    if width>=390:
                        page.locator('#avatar-character').select_option('robot')
                        page.locator('#avatar-3d').click()
                        page.wait_for_function("() => {const s=window.finPilotAvatarInstance?.getStatus();return s?.requestedMode==='3d'&&(s.actualMode==='3d'||Boolean(s.fallbackReason))}")
                        avatar=page.evaluate('() => window.finPilotAvatarInstance.getStatus()')
                        if avatar['actualMode']=='3d':
                            assert avatar['renderer']=='webgl2' and avatar['frames']>=1
                            expect(page.locator('#avatar-renderer')).to_have_text('3D / WEBGL')
                        else:
                            assert avatar['renderer']=='svg' and avatar['fallbackReason']
                            expect(page.locator('#avatar-renderer')).to_have_text('2D / SVG')
                            expect(page.locator('#avatar-explanation')).to_contain_text('3D 渲染不可用')
                        row['legacy_3d_status']=avatar
                        page.locator('#avatar-character').select_option('whale')
                        assert chat_count()==model_before
                        record('legacy_3d_renders_real_frame_or_explicit_reasoned_2d_fallback')
                    before_help=chat_count()
                    page.locator('[data-help-prompt="history"]').click()
                    assert '历史复盘' in page.locator('#message-input').input_value()
                    assert chat_count()==before_help
                    page.locator('#send-button').click()
                    expect(page.locator('#chat-messages .project-help-card')).to_have_count(1)
                    assert page.locator('#chat-messages .lab-chat-context').count()==0
                    record('help_chip_prefills_then_manual_send_returns_real_reviewed_tutorial')
                    nav('#nav-options')
                    expect(page.locator('#options-dialog')).to_be_visible()
                    assert not page.locator('#history-panel').evaluate('(node)=>node.open')
                    expect(page.locator('.options-demo-entry')).to_have_attribute('href','/learn')
                    page.keyboard.press('Escape')
                    page.goto(base+'/workspace?view=history',wait_until='domcontentloaded')
                    expect(page.locator('#options-dialog')).to_be_visible()
                    assert page.locator('#history-panel').evaluate('(node)=>node.open')
                    no_overflow();screenshot('history-deep-link');page.keyboard.press('Escape')
                    record('professional_gateway_no_auto_collection_history_collapsed_except_explicit_deep_link')
                    if width>=390:
                        page.goto(base+'/workspace?view=history',wait_until='domcontentloaded')
                        imported_ids=[]
                        before_import_chat=chat_count()
                        for kind,path in [('csv',csv_path),('json',json_path)]:
                            page.locator('#history-file').set_input_files(str(path))
                            expect(page.locator('#history-submit')).to_be_enabled()
                            expect(page.locator('#history-preview tbody tr')).to_have_count(6)
                            if kind=='csv':
                                page.locator('#history-label').fill('Controlled CSV import')
                                page.locator('#history-symbol').fill('DEMO')
                                page.locator('#history-expiry').fill('2026-12-18')
                                page.locator('.history-provenance summary').click()
                                page.locator('#history-source-label').fill('Synthetic integration fixture; not broker observations')
                            else:
                                expect(page.locator('#history-label')).to_have_value('Controlled JSON import')
                                expect(page.locator('#history-symbol')).to_have_value('DEMO')
                            previous=page.locator('#history-result').get_attribute('data-analysis-id')
                            page.locator('#history-submit').click()
                            page.wait_for_function("old=>{const node=document.querySelector('#history-result');return !node.hidden&&node.dataset.analysisId&&node.dataset.analysisId!==old}",arg=previous)
                            expect(page.locator('#history-error')).to_be_hidden()
                            expect(page.locator('#history-result .history-source-badge')).to_contain_text('来源未独立核验')
                            imported_id=page.locator('#history-result').get_attribute('data-analysis-id')
                            imported_ids.append(imported_id)
                            imported=app.state.store.get_analysis(imported_id)
                            assert imported['source']['kind']=='import' and imported['source'].get('verified') is not True
                            assert len(imported['daily'])==3 and all(day['oi_total'] is None for day in imported['daily'])
                            no_overflow()
                        assert len(set(imported_ids))==2 and chat_count()==before_import_chat
                        record('owned_csv_json_preview_real_import_persistence_unverified_provenance_missing_oi_retained_no_model')
                        page.locator('#history-result .history-followup button').click()
                        expect(page.locator('#options-dialog')).to_be_hidden()
                        expect(page.locator('#analysis-context-card')).to_have_attribute('data-analysis-id',imported_ids[-1])
                        assert chat_count()==before_import_chat
                        page.locator('#message-input').fill('这份历史样本的成交量变化说明了什么？没有返回的未平仓量能推断成零吗？')
                        page.locator('#send-button').click()
                        expect(page.locator('#chat-messages .message-analysis-context')).to_have_count(1)
                        expect(page.locator('#chat-messages .message-analysis-context')).to_contain_text('2026-11-09')
                        assert page.locator('#chat-messages .lab-chat-context').count()==0
                        new_history_chat=json.loads([c for c in calls if c['path']=='/api/chat' and c['method']=='POST'][-1]['body'])
                        assert app.state.store.get(new_history_chat['session_id'])['active_analysis_id']==imported_ids[-1]
                        page.locator('#chat-messages .message-analysis-context').scroll_into_view_if_needed();screenshot('imported-history-answer')
                        record('imported_report_explicit_new_chat_bind_prefill_and_real_offline_explanation')
                    page.goto(base+'/help#help.learning',wait_until='domcontentloaded')
                    expect(page.locator('[id="help.learning"]')).to_be_visible()
                    expect(page.locator('[id="help.learning"]')).to_contain_text('演示')
                    assert page.locator('[id="help.learning"] a[href="/learn"]').count()>0
                    no_overflow();screenshot('learning-manual')
                    record('real_v17_learning_manual_steps_and_safe_learn_link')
                    before_demo=len(calls);before_demo_chat=chat_count()
                    page.goto(base+'/demo',wait_until='domcontentloaded')
                    expect(page.locator('#demo-load')).to_be_visible()
                    assert page.locator('#demo-chat-fields').evaluate('(node)=>node.disabled')
                    assert not any(c['path'].startswith('/api/sessions/') for c in calls[before_demo:])
                    assert not any(c['path'].startswith('/api/companion/') for c in calls[before_demo:])
                    assert chat_count()==before_demo_chat
                    no_overflow()
                    record('legacy_demo_initialization_does_not_read_workspace_or_companion_conversation')
                    if width>=390:
                        owned_before_demo={s['id'] for s in app.state.store.list()}
                        page.locator('#demo-load').click()
                        expect(page.locator('#demo-archive-result')).to_be_visible()
                        expect(page.locator('#demo-load-error')).to_be_hidden()
                        archived_id=page.locator('#demo-archive-result').get_attribute('data-analysis-id')
                        archived=app.state.store.get_analysis(archived_id)
                        assert archived['source']['kind']=='ibkr_historical'
                        assert chat_count()==before_demo_chat
                        page.locator('#demo-question').fill('这份期权历史样本的成交量变化说明了什么？缺失的未平仓量有哪些限制？')
                        page.locator('#demo-search').click()
                        expect(page.locator('#demo-expert-results .expert-card').first).to_be_visible()
                        expect(page.locator('#demo-search-error')).to_be_hidden()
                        assert page.locator('#demo-expert-results .expert-source-link').count()>0
                        assert chat_count()==before_demo_chat
                        page.locator('#demo-explain').click()
                        expect(page.locator('#demo-messages .demo-message')).to_have_count(2)
                        expect(page.locator('#demo-ai-error')).to_be_hidden()
                        demo_first=json.loads([c for c in calls if c['path']=='/api/chat' and c['method']=='POST'][-1]['body'])
                        assert demo_first['session_id'] is None and demo_first['analysis_id']==archived_id
                        demo_ids={s['id'] for s in app.state.store.list()}-owned_before_demo
                        assert len(demo_ids)==1
                        demo_sid=next(iter(demo_ids))
                        demo_saved=app.state.store.get(demo_sid)
                        assert demo_saved['active_analysis_id']==archived_id and len(demo_saved['messages'])==2
                        assert demo_saved['messages'][-1]['mode']=='offline'
                        expect(page.locator('#demo-messages .reply-scope')).to_contain_text(archived['period']['start'])
                        page.locator('#demo-chat-input').fill('还有哪些不能确定？请保留数据日期和缺失说明。')
                        page.locator('#demo-explain').click()
                        expect(page.locator('#demo-messages .demo-message')).to_have_count(4)
                        demo_next=json.loads([c for c in calls if c['path']=='/api/chat' and c['method']=='POST'][-1]['body'])
                        assert demo_next['session_id']==demo_sid and len(app.state.store.get(demo_sid)['messages'])==4
                        assert len(app.state.store.get(sid)['messages'])==4
                        no_overflow();page.locator('#demo-messages').scroll_into_view_if_needed();screenshot('legacy-demo-answer')
                        record('legacy_demo_real_archived_replay_expert_search_offline_answer_continuation_owns_isolated_session')
                    assert errors==[],errors
                    assert external==[],external
                    row.update(status='passed',javascript_errors=errors,external_requests=external,
                               api_calls=len([c for c in calls if c['path'].startswith('/api/')]))
                    record('no_javascript_errors_external_assets_provider_or_gateway_calls')
                except Exception as error:
                    row.update(status='failed',error=f'{type(error).__name__}: {error}',url=page.url,
                               javascript_errors=errors,external_requests=external)
                    screenshot('failure')
                    raise
                finally:
                    context.close()
            browser.close()
        assert provider_attempts==[] and broker_attempts==[] and blocked==[]
        report['status']='passed'
    except Exception as error:
        report.update(status='failed',error=f'{type(error).__name__}: {error}')
        raise
    finally:
        server.should_exit=True
        thread.join(timeout=10)
        report.update(provider_attempts=provider_attempts,broker_attempts=broker_attempts,
                      blocked_network_attempts=blocked,server_stopped=not thread.is_alive(),
                      model_requests=0,broker_requests=0,user_database_reads=0,
                      source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in
                                     ['web/learn.js','web/app.js','web/companion/messages.js',
                                      'app/main.py','scripts/check_experience_ui_v17.py']})
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(str(report_path))
        print(report['status'])


if __name__=='__main__':
    main()
