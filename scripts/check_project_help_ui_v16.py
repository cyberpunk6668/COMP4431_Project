"""Isolated Edge UI checks with the real reviewed manual and controlled chat.

No application startup, .env, user SQLite, model provider or IBKR access.
The HTTP server serves only public web files and explicit in-memory fixtures.
"""
from copy import deepcopy
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
from urllib.parse import parse_qs, unquote, urlsplit

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.project_help import ProjectHelp

SID = '11111111-1111-4111-8111-111111111111'
AID = '22222222-2222-4222-8222-222222222222'
MANUAL = ProjectHelp()
CALLS = []
SESSION = {}
CONNECTION = {}
CONTEXT = {'analysis_id': AID, 'analysis_kind': 'historical_options',
           'period': {'start': '2026-11-06', 'end': '2026-11-10'},
           'captured_at': '2026-11-11T01:00:00Z', 'source_label': 'Controlled history fixture',
           'historical_data': True, 'notice': '历史样本，不代表当前行情。', 'evidence': []}


def reset():
    SESSION.clear()
    SESSION.update({'id': SID, 'title': 'Controlled guide conversation', 'messages': [],
                    'active_analysis_id': AID, 'active_analysis': deepcopy(CONTEXT), 'analysis_history': []})
    CONNECTION.clear()
    CONNECTION.update({'epoch': 'isolated-help-v16', 'seq': 0, 'generation': 1,
                       'session_id': SID, 'language': 'zh', 'engine': 'offline',
                       'desktop_connected': False, 'activities': []})
    CALLS.clear()


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def translate_path(self, path):
        route = unquote(urlsplit(path).path)
        if route.startswith('/static/'):
            candidate = (ROOT / 'web' / route.removeprefix('/static/')).resolve()
            if candidate.is_relative_to((ROOT / 'web').resolve()):
                return str(candidate)
        return str(ROOT / 'web' / {'/help': 'help.html', '/workspace': 'index.html',
                                   '/pet': 'pet.html', '/demo': 'demo.html'}.get(route, '__missing__'))

    def end_headers(self):
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        super().end_headers()

    def send_json(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urlsplit(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        if not path.startswith('/api/'):
            return super().do_GET()
        CALLS.append(('GET', self.path))
        lang = query.get('language', ['zh'])[0]
        if path == '/api/project-help':
            return self.send_json({'manual_version': '16.0', 'current_version': 16, 'topics': MANUAL.catalogue(lang)})
        if path == '/api/project-help/search':
            return self.send_json({'manual_version': '16.0', 'topics': MANUAL.search(query.get('q', [''])[0], lang)})
        if path.startswith('/api/project-help/topics/'):
            topic = MANUAL.get_topic(path.rsplit('/', 1)[1], lang)
            return self.send_json(topic or {'detail': 'unknown topic'}, 200 if topic else 404)
        if path == '/api/health':
            return self.send_json({'status': 'ok', 'application': 'FinPilot', 'version': '16.0.0', 'mode': 'offline', 'knowledge_documents': 0})
        if path == '/api/models':
            return self.send_json({'default': 'offline', 'models': [{'id': 'offline', 'label': 'Controlled local manual', 'available': True}]})
        if path == '/api/sessions':
            return self.send_json({'sessions': [{'id': SID, 'title': SESSION['title'], 'updated_at': '2026-11-11T00:00:00Z'}]})
        if path == f'/api/sessions/{SID}':
            return self.send_json(SESSION)
        if path == '/api/companion/connection':
            return self.send_json(CONNECTION)
        if path == '/api/companion/events':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            envelope = {'epoch': CONNECTION['epoch'], 'seq': 0, 'generation': 1, 'type': 'reset',
                        'session_id': SID, 'payload': {'connection': CONNECTION}}
            self.wfile.write(('retry: 60000\n\nevent: reset\ndata: ' + json.dumps(envelope) + '\n\n').encode())
            return
        if path == '/api/experts/search':
            return self.send_json([])
        return self.send_json({'detail': 'Unapproved fixture request'}, 400)

    def do_POST(self):
        path = urlsplit(self.path).path
        CALLS.append(('POST', path))
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))) or '{}')
        if path == '/api/options/history/sample':
            return self.send_json({'analysis_id': AID, 'analysis_kind': 'historical_options', 'symbol': 'SPY',
                                   'expiry': '2026-11-06', 'period': CONTEXT['period'], 'source': {'kind': 'demo'},
                                   'quality': {'common_contracts': 2}, 'daily': [{'date': '2026-11-06', 'volume_total': 10,
                                   'put_volume_share': .4, 'oi_total': None, 'oi_asof_date': None}]})
        if path != '/api/chat':
            return self.send_json({'detail': 'Unapproved fixture mutation'}, 400)
        language = body.get('language', 'zh')
        metadata = MANUAL.build_result(['help.history'], language)
        metadata['selector'] = {'engine': 'local-manual', 'status': 'not_needed', 'generation_attempts': 0}
        sources = deepcopy(metadata['sources'])
        sources[0]['project_help'] = deepcopy(metadata)
        SESSION['messages'].extend([{'id': len(SESSION['messages']) + 1, 'role': 'user', 'content': body['message']},
            {'id': len(SESSION['messages']) + 2, 'role': 'assistant', 'content': metadata['answer'], 'mode': 'project-help',
             'sources': sources, 'project_help': metadata, 'analysis_context': None}])
        return self.send_json({'session_id': SID, 'answer': metadata['answer'], 'mode': 'project-help', 'sources': sources,
                              'project_help': metadata, 'analysis_context': None, 'active_analysis': CONTEXT,
                              'analysis_history': []})


def check(browser, base, width, height):
    reset()
    context = browser.new_context(viewport={'width': width, 'height': height}, reduced_motion='reduce')
    page = context.new_page()
    page.set_default_timeout(12000)
    errors, requests = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: requests.append(request.url))
    checks = []
    def record(name):
        checks.append(name)
    def no_overflow():
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')

    page.goto(base + '/help#help.history')
    expect(page.locator('#help-results .project-help-card')).to_have_count(len(MANUAL.catalogue()))
    expect(page.locator('#help-version')).to_have_text('手册 16.0')
    expect(page.locator('[id="help.history"]')).to_contain_text(MANUAL.get_topic('help.history')['title'])
    no_overflow();record('real_reviewed_catalogue_version_anchor_and_responsive_layout')
    page.locator('#help-search').fill('历史复盘')
    expect(page.locator('#help-results .project-help-card')).to_have_count(len(MANUAL.search('历史复盘')))
    expect(page.locator('#help-status')).to_contain_text('本地搜索结果')
    record('debounced_actual_manual_search')
    page.locator('#help-search').fill('NoSuchFeatureZZZ')
    expect(page.locator('#help-empty')).to_be_visible()
    page.locator('#help-empty-reset').click()
    expect(page.locator('#help-results .project-help-card')).to_have_count(len(MANUAL.catalogue()))
    record('unknown_search_empty_state_and_reset')
    before = len([url for method, url in CALLS if '/api/project-help' in url])
    page.locator('#help-search').fill('sk-' + 'x' * 24)
    expect(page.locator('#help-error')).to_contain_text('未被发送')
    assert before == len([url for method, url in CALLS if '/api/project-help' in url])
    assert not any('sk-' in url for url in requests)
    page.locator('#help-reset').click()
    record('credential_like_query_blocked_before_url_or_http')
    page.locator('#help-language').click()
    expect(page.locator('html')).to_have_attribute('lang', 'en')
    expect(page.locator('#help-results .project-help-title').first).to_have_text(MANUAL.catalogue('en')[0]['title'])
    no_overflow();record('english_manual_and_keyboard_search')
    page.locator('#help-search').focus();page.keyboard.type('models');page.keyboard.press('Enter')
    expect(page.locator('#help-status')).to_contain_text('local search results')
    record('search_form_keyboard_submission')
    # The link guard must reject URL tricks and executable/model HTML.
    page.evaluate("""() => {const m={intent:'project_help',manual_version:'16.0',title:'<img onerror=window.unsafe=1>',steps:['<script>window.unsafe=1</script>'],links:[{label:'unsafe',url:'javascript:alert(1)'},{label:'external',url:'https://example.com'},{label:'query',url:'/workspace?view=history&evil=1'},{label:'network',url:'//example.com/help'},{label:'safe',url:'/workspace?view=history'}]}; const card=FinPilotMessages.renderProjectHelp(m);card.id='unsafe-probe';document.body.append(card);} """)
    probe = page.locator('#unsafe-probe')
    assert probe.locator('img,script').count() == 0
    assert probe.locator('a').count() == 1
    expect(probe.locator('a')).to_have_attribute('href', '/workspace?view=history')
    assert not page.evaluate('window.unsafe === 1')
    probe.evaluate('(node)=>node.remove()')
    record('safe_dom_and_exact_project_link_allowlist')
    metadata=MANUAL.build_result(['help.models'])
    metadata['selector']={'engine':'deepseek','status':'validated','generation_attempts':1}
    page.evaluate("metadata=>{const card=FinPilotMessages.renderProjectHelp(metadata,{language:'zh'});card.id='selector-probe';document.body.append(card)}", metadata)
    expect(page.locator('#selector-probe')).to_contain_text('本地手册步骤 · DeepSeek 辅助匹配')
    assert 'RAG' not in page.locator('#selector-probe').inner_text()
    page.locator('#selector-probe').evaluate('(node)=>node.remove()')
    metadata['selector']={'engine':'local-manual','status':'fallback','generation_attempts':1,'reason':'project_help_selection_invalid'}
    page.evaluate("metadata=>{const card=FinPilotMessages.renderProjectHelp(metadata,{language:'zh'});card.id='selector-probe';document.body.append(card)}", metadata)
    expect(page.locator('#selector-probe')).to_contain_text('模型主题匹配未通过校验')
    page.locator('#selector-probe').evaluate('(node)=>node.remove()')
    record('model_topic_matching_and_fallback_never_presented_as_financial_rag')
    financial={'id':900,'role':'assistant','content':'历史样本说明 [h.sample] [expert.put_call]','mode':'deepseek',
               'sources':[{'id':'expert.put_call','title':'Controlled expert reference','url':'https://www.cboe.com/'}],
               'analysis_context':{**CONTEXT,'evidence':[{'id':'h.sample','label':'Sample contracts','value':2,'unit':'contracts'}]}}
    page.evaluate("message=>{const card=FinPilotMessages.renderMessage(message,{language:'zh'});card.id='financial-probe';document.body.append(card)}",financial)
    expect(page.locator('#financial-probe .message-body')).to_be_visible()
    assert page.locator('#financial-probe .project-help-card').count() == 0
    expect(page.locator('#financial-probe .message-analysis-context')).to_contain_text('2026-11-06')
    expect(page.locator('#financial-probe .message-sources')).to_contain_text('Controlled expert reference')
    page.locator('#financial-probe').evaluate('(node)=>node.remove()')
    record('ordinary_financial_body_time_evidence_and_sources_still_render')
    page.locator('#help-reset').click()
    page.wait_for_function("document.querySelectorAll('#help-results .project-help-card').length > 4")
    shots = ROOT / 'reports/screenshots/project-help-v16';shots.mkdir(parents=True, exist_ok=True)
    page.evaluate("history.replaceState(null,'',location.pathname);window.scrollTo(0,0)")
    page.screenshot(path=str(shots / f'help-{width}.png'), animations='disabled')
    assert not any(method == 'POST' for method, _ in CALLS)
    record('manual_view_search_and_language_have_no_chat_or_broker_calls')

    context.add_init_script("localStorage.setItem('finpilot-session','" + SID + "')")
    page.goto(base + '/workspace')
    expect(page.locator('#nav-help')).to_have_attribute('href', '/help')
    expect(page.locator('#workspace-help-prompts [data-help-prompt]')).to_have_count(3)
    page.locator('[data-help-prompt="history"]').click()
    expect(page.locator('#message-input')).to_have_value('FinPilot 怎么做历史复盘？请说明入口、步骤和限制。')
    assert not any(path == '/api/chat' for _, path in CALLS)
    record('workspace_guide_entry_and_three_fill_only_examples')
    page.locator('#send-button').click()
    expect(page.locator('#chat-messages .project-help-card')).to_have_count(1)
    expect(page.locator('#chat-messages .message-mode')).to_have_text('项目指南 · 本地手册')
    expect(page.locator('#chat-messages .project-help-canonical')).to_be_hidden()
    assert page.locator('#chat-messages .project-help-canonical').text_content() == MANUAL.build_result(['help.history'])['answer']
    step=MANUAL.get_topic('help.history')['steps'][0]
    assert page.locator('#chat-messages').inner_text().count(step) == 1
    assert page.locator('#chat-messages .message-sources,#chat-messages .message-analysis-context').count() == 0
    expect(page.locator('#analysis-context-card')).to_be_visible()
    assert SESSION['active_analysis_id'] == AID
    no_overflow();record('bound_report_tutorial_card_is_not_market_rag_and_binding_remains')
    page.evaluate("""() => {Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.__guideCopied=text}}});window.speechSynthesis.speak=utterance=>{window.__guideRead=utterance.text;utterance.onend?.();};}""")
    page.locator('#chat-messages .message-actions button').first.click()
    assert page.evaluate('window.__guideCopied') == MANUAL.build_result(['help.history'])['answer']
    page.locator('#chat-messages .message-actions [data-action="speak"]').click()
    assert page.evaluate('window.__guideRead') == MANUAL.build_result(['help.history'])['answer']
    record('tutorial_steps_visible_once_with_full_canonical_copy_and_stubbed_speech')
    page.screenshot(path=str(shots / f'workspace-{width}.png'), animations='disabled')

    page.goto(base + '/pet')
    page.locator('#pet-character').focus();page.keyboard.press('Enter')
    expect(page.locator('#pet-messages .project-help-card')).to_have_count(1)
    page.locator('#pet-input').fill('我的聊天草稿')
    count = len([1 for method, path in CALLS if method == 'POST' and path == '/api/chat'])
    page.locator('#pet-help-open').click()
    expect(page.locator('#pet-help-view')).to_be_visible()
    expect(page.locator('#pet-help-content .project-help-card')).to_have_count(len(MANUAL.catalogue()))
    assert page.locator('iframe').count() == 0
    assert count == len([1 for method, path in CALLS if method == 'POST' and path == '/api/chat'])
    record('pet_same_panel_manual_no_native_bridge_extension_or_automatic_chat')
    expect(page.locator('#pet-messages .project-help-canonical')).to_be_hidden()
    assert page.locator('#pet-messages').inner_text().count(step) == 1
    page.locator('#pet-help-search').fill('sk-' + 'x' * 24)
    expect(page.locator('#pet-help-status')).to_contain_text('未被发送')
    assert not any('sk-' in url for url in requests)
    page.keyboard.press('Escape')
    expect(page.locator('#pet-help-view')).to_be_hidden()
    expect(page.locator('#pet-panel')).to_be_visible()
    expect(page.locator('#pet-input')).to_have_value('我的聊天草稿')
    record('pet_help_escape_keeps_chat_and_draft_and_blocks_secret_query')
    page.locator('#pet-messages .project-help-sources a').first.click()
    expect(page.locator('#pet-help-view')).to_be_visible()
    expect(page.locator('#pet-help-content .project-help-card')).to_have_count(1)
    no_overflow();record('pet_manual_source_deeplink_in_same_panel')
    page.screenshot(path=str(shots / f'pet-{width}.png'), animations='disabled')

    start = len(CALLS)
    page.goto(base + '/demo')
    expect(page.locator('[data-demo-text="usageGuide"]')).to_have_attribute('href', '/help')
    assert not any(path.startswith('/api/companion') or path.startswith('/api/sessions') for _, path in CALLS[start:])
    page.locator('#demo-load').click()
    expect(page.locator('#demo-archive-result')).to_be_visible()
    page.locator('#demo-search').click()
    expect(page.locator('#demo-expert-results')).to_be_visible()
    page.locator('#demo-chat-input').fill('FinPilot 怎么做历史复盘？')
    page.locator('#demo-explain').click()
    expect(page.locator('#demo-messages .project-help-card')).to_have_count(1)
    expect(page.locator('#demo-messages .message-mode')).to_have_text('项目指南 · 本地手册')
    expect(page.locator('#demo-messages .project-help-canonical')).to_be_hidden()
    assert page.locator('#demo-messages').inner_text().count(step) == 1
    assert page.locator('#demo-messages .demo-actual-sources,#demo-messages .demo-evidence-list').count() == 0
    no_overflow();record('demo_guide_card_and_independent_session_without_companion_connection')
    assert not errors, errors
    record('no_javascript_errors')
    assert not any(not url.startswith(base) and not url.startswith('data:') for url in requests), 'Unexpected external request'
    result = {'width': width, 'height': height, 'status': 'passed', 'checks': checks,
              'fixture_chat_posts': len([1 for method, path in CALLS if method == 'POST' and path == '/api/chat']),
              'external_model_calls': 0, 'broker_requests': 0, 'page_errors': errors}
    context.close()
    return result


def main():
    reset()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True);thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            results = [check(browser, base, w, h) for w, h in [(320, 740), (390, 844), (1440, 1000)]]
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'passed',
              'scope': 'Isolated static HTTP and in-memory controlled chat fixtures with real ProjectHelp catalogue/build_result. Not live model, user database, Windows native hardware or real phone testing.',
              'manual_version': '16.0', 'viewports': results, 'checks_per_viewport': len(results[0]['checks']),
              'external_model_calls': 0, 'broker_requests': 0, 'user_database_reads': 0}
    path = ROOT / 'reports/project_help_ui_v16.json';path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': 'passed', 'viewports': len(results), 'checks_per_viewport': report['checks_per_viewport']}))


if __name__ == '__main__':
    main()
