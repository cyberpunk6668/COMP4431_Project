"""Actual Edge viewports over a private, pure-calculation HTTP fixture.

No normal server, .env, user conversation, model, broker or native UI access.
The fixture returns the real authored scenarios/formulas, but it is not an
acceptance of production persistence or the model/broker API wiring.
"""
from copy import deepcopy
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Event, Thread
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.options_lab import catalogue,build_scenario,evaluate,LabEvaluationRequest

CALLS=[]
SAVED=[]
SESSIONS=[]
BINDINGS=[]
FAULT={}
GATE=Event()


def reset():
    CALLS.clear();SAVED.clear();SESSIONS.clear();BINDINGS.clear();FAULT.clear();GATE.set()


class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
    def translate_path(self,path):
        route=unquote(urlsplit(path).path)
        if route.startswith('/static/'):
            result=(ROOT/'web'/route.removeprefix('/static/')).resolve()
            if result.is_relative_to((ROOT/'web').resolve()):return str(result)
        return str(ROOT/'web'/('learn.html' if route=='/learn' else '__not_found__'))
    def end_headers(self):
        self.send_header('Content-Security-Policy',"default-src 'self';script-src 'self';style-src 'self';img-src 'self' data:;connect-src 'self';font-src 'self';object-src 'none';base-uri 'self';frame-ancestors 'none'")
        super().end_headers()
    def json(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    def do_GET(self):
        p=urlsplit(self.path);q=parse_qs(p.query);language=q.get('language',['zh'])[0]
        if p.path=='/workspace':
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(b'<!doctype html><title>Owned workspace navigation target</title><p>Owned fixture only</p>');return
        if not p.path.startswith('/api/'):return super().do_GET()
        CALLS.append({'method':'GET','path':p.path})
        if p.path=='/api/options-lab/scenarios':return self.json(catalogue(language))
        if p.path.startswith('/api/options-lab/scenarios/'):
            if FAULT.pop('scenario_error',False):return self.json({'detail':'Controlled scenario error'},503)
            return self.json(build_scenario(p.path.rsplit('/',1)[1],language))
        return self.json({'detail':'Unexpected API in private fixture'},400)
    def do_POST(self):
        p=urlsplit(self.path).path;body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or '{}');CALLS.append({'method':'POST','path':p,'body':deepcopy(body)})
        if p in ['/api/options-lab/evaluate','/api/options-lab/save']:
            try:report=evaluate(LabEvaluationRequest.model_validate(body))
            except (ValueError,TypeError):return self.json({'detail':'Invalid trial'},422)
            kind='hold_evaluate' if p.endswith('/evaluate') else 'hold_save'
            if FAULT.pop(kind,False):GATE.wait(7)
            if p.endswith('/save'):
                report['analysis_id']=str(uuid4());SAVED.append(deepcopy(report))
            return self.json(report)
        if p=='/api/sessions':
            item={'id':str(uuid4()),'title':body['title']};SESSIONS.append(item);return self.json(item)
        return self.json({'detail':'Unexpected API mutation'},400)
    def do_PUT(self):
        p=urlsplit(self.path).path;body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or '{}');CALLS.append({'method':'PUT','path':p,'body':deepcopy(body)})
        if p.startswith('/api/sessions/') and p.endswith('/analysis'):
            if FAULT.pop('bind_error',False):return self.json({'detail':'Controlled bind failure'},503)
            BINDINGS.append({'sid':p.split('/')[3],**body});return self.json({'active_analysis_id':body['analysis_id']})
        return self.json({'detail':'Unexpected binding'},400)


def check(browser,base,width,height,shots):
    reset();context=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce');page=context.new_page();page.set_default_timeout(12000)
    errors=[];checks=[];external=[]
    page.on('pageerror',lambda err:errors.append(str(err)))
    page.route('https://**/*',lambda route:(external.append(route.request.url),route.abort()))
    record=lambda name:checks.append(name)
    amount=lambda:page.locator('#lab-pnl').inner_text().replace('US$','$')
    def clean_width():assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    def settled():page.wait_for_function('() => window.finPilotOptionsLab?.getStatus().currentTrial && !window.finPilotOptionsLab.getStatus().loading && !window.finPilotOptionsLab.getStatus().evaluating')
    page.goto(base+'/learn');settled()
    expect(page.locator('.scenario-card')).to_have_count(3);expect(page.locator('#lab-scenarios [aria-pressed=true]')).to_have_attribute('data-scenario-id','put_activity')
    assert amount()=='+$140.00'
    expect(page.locator('#lab-source')).to_contain_text('固定教学时点')
    assert page.locator('#lab-metrics .metric-card').count()==3 and page.locator('#lab-insights .insight-card').count()==3
    assert not page.locator('#lab-professional').evaluate('el=>el.open')
    assert not SAVED and not SESSIONS and not any(c['method']!='GET' for c in CALLS)
    clean_width();record('three_local_scenarios_immediate_default_payoff_and_no_startup_writes')
    record('synthetic_provenance_and_source_time_always_visible')
    chart=page.locator('#lab-chart')
    assert float(chart.get_attribute('data-x-min'))==80 and float(chart.get_attribute('data-x-max'))==125
    assert float(chart.get_attribute('data-full-max'))==200
    expect(page.locator('.payoff-figure figcaption')).to_contain_text('局部显示')
    def chart_geometry(price):
        result=chart.evaluate('''(target) => {const [,,,height]=target.getAttribute('viewBox').split(' ').map(Number),width=Number(target.getAttribute('viewBox').split(' ')[2]);const marker=target.querySelector('.chart-marker'),ys=[...target.querySelectorAll('.chart-y-label')].map(t=>Number(t.getAttribute('y')));return {lo:Number(target.dataset.xMin),hi:Number(target.dataset.xMax),fullLo:Number(target.dataset.fullMin),fullHi:Number(target.dataset.fullMax),finite:[...target.querySelectorAll('*')].every(el=>[...el.attributes].every(a=>!/(?:NaN|Infinity)/.test(a.value))),separated:ys.every((y,i)=>ys.every((other,j)=>i===j||Math.abs(y-other)>=16)),markerInside:!!marker&&Number(marker.getAttribute('cx'))>=56&&Number(marker.getAttribute('cx'))<=width-19&&Number(marker.getAttribute('cy'))>=29&&Number(marker.getAttribute('cy'))<=height-43,pathLength:target.querySelector('.chart-curve').getTotalLength()}}''')
        assert result['fullLo']<=result['lo']<=price<=result['hi']<=result['fullHi']
        assert result['finite'] and result['separated'] and result['markerInside'] and result['pathLength']>0,result
    chart_geometry(105);record('local_strike_break_even_price_domain_zero_label_spacing_and_full_table_scope')
    for structure in ['long_call','long_put','call_debit_spread']:
        page.locator('#lab-strategy').select_option(structure);settled()
        for price in ['0','1000']:
            page.locator('#lab-price').fill(price);settled();chart_geometry(float(price));clean_width()
            sample=evaluate({'strategy':structure,'upper_strike':105 if structure=='call_debit_spread' else None,'expiry_price':price})['lab_context']['trial']
            expect(page.locator('#lab-curve-table tbody tr')).to_have_count(len(sample['curve']))
    page.locator('#lab-strategy').select_option('long_call');settled()
    page.locator('#lab-price').fill('106.13');settled();chart_geometry(106.13)
    assert float(chart.get_attribute('data-x-max'))==126.13
    page.locator('#lab-price').fill('105');settled()
    record('three_strategies_extreme_zero_thousand_and_fractional_domain_finite_current_marker_full_table_retained')
    page.locator('#lab-metrics details').first.locator('summary').click();expect(page.locator('#lab-metrics details').first).to_contain_text('合约')
    page.locator('#lab-professional summary').click();expect(page.locator('#lab-quotes tbody tr')).to_have_count(8)
    expect(page.locator('#lab-evidence')).to_contain_text('h.lab.');clean_width();record('plain_terms_disclosure_and_same_sample_professional_table')
    page.locator('[data-scenario-id=wide_spread]').click();settled();expect(page.locator('#lab-scenario-title')).to_contain_text('不同成本')
    natural=page.locator('#lab-pnl').inner_text();page.locator('#lab-execution').select_option('midpoint');settled();assert page.locator('#lab-pnl').inner_text()!=natural
    expect(page.locator('.form-boundary')).to_contain_text('100 股');record('execution_assumption_changes_cost_and_payoff_without_model')
    page.locator('[data-scenario-id=protection_cost]').click();settled();expect(page.locator('#lab-scenario-title')).to_contain_text('保护')
    page.locator('#lab-strategy').select_option('long_put');settled();assert page.locator('#lab-upper-field').is_hidden()
    page.locator('#lab-strategy').select_option('call_debit_spread');settled();expect(page.locator('#lab-upper-field')).to_be_visible()
    page.locator('#lab-strike').select_option('105');settled();expect(page.locator('#lab-upper')).to_have_value('110')
    assert page.locator('#lab-upper option[value="100"]').evaluate('el=>el.disabled'),page.locator('#lab-upper').evaluate('el=>el.outerHTML')
    assert not page.locator('#lab-trial-metrics').get_by_text('无理论上限',exact=True).count()
    record('all_three_structures_and_ordered_same_expiry_spread_controls')
    page.locator('#lab-contracts').fill('2');settled();expected=evaluate({'scenario_id':'protection_cost','strategy':'call_debit_spread','strike':105,'upper_strike':110,'expiry_price':105,'contracts':2,'execution':'natural'})['lab_context']['trial']
    assert amount().replace(',','')=='-$'+format(abs(expected['pnl']),'.2f')
    page.locator('.curve-details summary').click();expect(page.locator('#lab-curve-table tbody tr')).to_have_count(len(expected['curve']))
    assert len(page.locator('#lab-chart .chart-curve').get_attribute('d'))>150
    assert page.locator('#lab-chart').get_attribute('role')=='img'
    expect(page.locator('#lab-chart-desc')).to_contain_text('概率');clean_width();record('exact_position_total_units_real_curve_and_accessible_table')
    posts=len([c for c in CALLS if c['path'].endswith('/evaluate')]);page.locator('#lab-contracts').fill('1.5');page.wait_for_timeout(450)
    assert len([c for c in CALLS if c['path'].endswith('/evaluate')])==posts
    expect(page.locator('#lab-save')).to_be_disabled();expect(page.locator('#lab-trial-status')).to_contain_text('检查输入')
    page.locator('#lab-contracts').fill('1');settled();record('invalid_quantity_never_updates_or_saves_stale_result')
    page.locator('[data-scenario-id=put_activity]').click();settled()
    FAULT['hold_evaluate']=True;GATE.clear();page.locator('#lab-price').fill('104');page.wait_for_timeout(500)
    page.locator('#lab-price').fill('115');settled();GATE.set();page.wait_for_timeout(180)
    assert amount()=='+$1,140.00';record('late_older_trial_cannot_overwrite_current_input_result')
    FAULT['scenario_error']=True;page.locator('[data-scenario-id=wide_spread]').click();expect(page.locator('#lab-error')).to_be_visible();expect(page.locator('#lab-save')).to_be_disabled()
    page.locator('#lab-retry').click();settled();expect(page.locator('#lab-error')).to_be_hidden();record('failed_scenario_explicit_retry_and_no_stale_save')
    # Language switch preserves a modified trial and only changes reviewed copy.
    page.locator('#lab-price').fill('110');settled();pnl_before=amount()
    page.locator('#lab-language').click();settled();expect(page.locator('html')).to_have_attribute('lang','en')
    expect(page.locator('#lab-price')).to_have_value('110');assert amount()==pnl_before
    clean_width();record('english_copy_preserves_inputs_and_position_arithmetic')
    # Keyboard interaction and all static navigation remain usable at 320px.
    page.locator('#lab-strategy').focus();page.keyboard.press('ArrowDown');page.keyboard.press('Enter');settled();assert page.locator('#lab-strategy').input_value()=='long_put'
    page.locator('#lab-strategy').select_option('long_call');settled();record('keyboard_controls_and_reduced_motion_viewport')
    FAULT['hold_save']=True;GATE.clear();page.locator('#lab-save').click();page.wait_for_timeout(100)
    page.locator('#lab-price').fill('120');settled();GATE.set();page.wait_for_timeout(200)
    assert page.evaluate('window.finPilotOptionsLab.getStatus().saved') is False
    expect(page.locator('#lab-save-status')).to_contain_text('earlier trial');record('save_of_earlier_inputs_never_attaches_to_changed_trial')
    page.locator('#lab-save').click();expect(page.locator('#lab-save-status')).to_contain_text('Current example saved')
    assert SAVED[-1]['lab_context']['trial']['expiry_price']==120
    saves=len(SAVED);FAULT['bind_error']=True;page.locator('#lab-followup').click();expect(page.locator('#lab-error')).to_contain_text('binding')
    assert len(SESSIONS)==1 and len(SAVED)==saves
    record('save_is_explicit_and_failed_binding_retains_one_owned_session')
    # Own-only page screenshots before intentionally navigating to the fixture target.
    page.locator('#lab-trial').scroll_into_view_if_needed();page.screenshot(path=str(shots/f'trial-{width}.png'),animations='disabled')
    page.locator('#lab-scenario-title').scroll_into_view_if_needed();page.screenshot(path=str(shots/f'scenario-{width}.png'),animations='disabled')
    page.locator('#lab-followup').click();page.wait_for_url('**/workspace?session=**')
    target=parse_qs(urlsplit(page.url).query)
    assert target['session']==[SESSIONS[0]['id']] and target['prompt'][0]
    assert len(SESSIONS)==1 and len(SAVED)==saves and BINDINGS[-1]['analysis_id']==SAVED[-1]['analysis_id']
    assert not any('/api/chat' in c['path'] or '/api/companion/' in c['path'] or '/api/options/history/fetch' in c['path'] for c in CALLS)
    assert not any(c['method']=='GET' and c['path'].startswith('/api/sessions') for c in CALLS)
    record('explicit_followup_binds_latest_saved_report_and_prefills_only_no_chat_or_old_reads')
    assert not errors and not external;record('no_javascript_errors_or_external_network_assets')
    context.close();return {'width':width,'height':height,'status':'passed','checks':checks,'external_model_calls':0,'broker_requests':0,'page_errors':errors}


def main():
    stamp=datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ');report={'checked_at':datetime.now(UTC).isoformat(),'status':'running','scope':__doc__,'viewports':[],'external_model_calls':0,'broker_requests':0,'user_database_reads':0}
    target=ROOT/'reports/options_lab_ui_v17.json'
    if target.exists():target=target.with_stem(target.stem+'-'+stamp)
    shots=ROOT/'reports/screenshots/options-lab-v17'/stamp;shots.mkdir(parents=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            for width,height in [(320,740),(390,844),(1440,1000)]:report['viewports'].append(check(browser,f'http://127.0.0.1:{server.server_port}',width,height,shots))
            browser.close()
        report['status']='passed';report['checks_per_viewport']=len(report['viewports'][0]['checks'])
    except Exception as error:
        import traceback
        report['status']='failed';report['error']=str(error);report['error_traceback']=traceback.format_exc()
    finally:
        GATE.set();server.shutdown();server.server_close();thread.join(timeout=2)
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(target),'checks_per_viewport':report.get('checks_per_viewport'),'error':report.get('error')},ensure_ascii=False))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
