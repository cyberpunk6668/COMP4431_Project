"""Workspace/demo integration with actual sprites and bounded controlled APIs.

No chat, broker, existing conversation details or external model calls. The
session list/companion connection are privacy fixtures. Calculator uses the
real deterministic calculation function behind a held HTTP fixture.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.finance import CalculationRequest, calculate
from playwright.sync_api import expect, sync_playwright


def check(browser,base,width,height):
    context=browser.new_context(viewport={"width":width,"height":height},reduced_motion="no-preference")
    page=context.new_page();page.set_default_timeout(12000)
    errors=[];calls=[];held=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    connection={"epoch":"workspace-fixture","seq":0,"generation":0,"session_id":None,"language":"zh","engine":"deepseek","desktop_connected":False,"activities":[]}
    def intercept(route):
        req=route.request;path=urlsplit(req.url).path;calls.append((req.method,path))
        if path=='/api/sessions':return route.fulfill(json={"sessions":[]})
        if path=='/api/companion/connection':return route.fulfill(json=connection)
        if path=='/api/companion/events':return route.fulfill(content_type='text/event-stream',body=': fixture\n\n')
        if path=='/api/calculate':held.append(route);return
        if req.method!='GET' or path.startswith('/api/sessions/') or path.startswith('/api/options/'):
            raise AssertionError('Unexpected mutating/private/broker request: '+path)
        return route.continue_()
    page.route('**/api/**',intercept)
    page.goto(base+'/workspace',wait_until='domcontentloaded')
    if width<=1180:page.locator('#avatar-collapse').click()
    page.locator('#avatar-stage').scroll_into_view_if_needed()
    page.wait_for_function("() => window.finPilotAvatarInstance?.getStatus().renderer==='canvas2d'")
    assert page.locator('#avatar-character').input_value()=='whale'
    assert not page.locator('.avatar-mode-control').is_visible()
    assert page.evaluate("window.finPilotAvatarInstance.getStatus().assetRevision")== '7661c8b304c5400701f91da01b1a643a207331de'
    page.evaluate('window.__oldWhale=window.finPilotAvatarInstance')
    page.locator('#avatar-character').select_option('robot')
    page.wait_for_function("() => ['webgl2','svg'].includes(window.finPilotAvatarInstance?.getStatus().renderer)")
    page.locator('#avatar-2d').click()
    page.wait_for_function("() => window.finPilotAvatarInstance.getStatus().renderer==='svg'")
    assert page.evaluate('window.__oldWhale.getStatus().destroyed')
    page.locator('#avatar-character').select_option('whale')
    page.wait_for_function("() => window.finPilotAvatarInstance?.getStatus().renderer==='canvas2d'")
    page.locator('#reduce-motion').check();page.wait_for_timeout(100)
    frames=page.evaluate('window.finPilotAvatarInstance.getStatus().frames')
    page.wait_for_timeout(180)
    assert page.evaluate('window.finPilotAvatarInstance.getStatus().frames')==frames
    page.locator('#reduce-motion').uncheck()
    if width<=760:page.locator('#mobile-menu').click()
    page.locator('#nav-calculator').click()
    expect(page.locator('#calculator-dialog')).to_be_visible()
    page.locator('#calculate-button').click()
    assert held and page.evaluate("window.finPilotAvatarInstance.getStatus().state==='thinking'")
    route=held.pop();data=calculate(CalculationRequest.model_validate(route.request.post_data_json))
    route.fulfill(json=data)
    expect(page.locator('#calculation-output')).to_be_visible()
    page.wait_for_function("() => window.finPilotAvatarInstance.getStatus().state==='idle'")
    page.locator('#calculator-dialog .close-dialog').click()
    probe={"id":987,"role":"assistant","mode":"offline","warning":"options_answer_validation_failed",
      "content":"<img src=x onerror=alert(1)> **安全文字** [h.missing] [h.zero] [expert.put_call] [expert.bad] [unknown].",
      "sources":[{"id":"expert.put_call","title":"Reviewed source fixture","url":"https://www.cboe.com/","snippet":"<script>window.unsafe=1</script>"},{"id":"expert.bad","url":"javascript:alert(1)","title":"Unsafe URL fixture"}],
      "analysis_context":{"analysis_kind":"historical_options","analysis_id":"11111111-1111-4111-8111-111111111111","period":{"start":"2026-11-06","end":"2026-11-10"},"source_label":"Controlled historical evidence","captured_at":"2026-11-11T01:00:00Z","notice":"历史样本，不代表当前市场。",
        "evidence":[{"id":"h.missing","label":"缺失 OI","value":None,"before":None,"after":9,"delta":None,"status":"incomparable","reason":"missing_value_or_oi_asof","unit":"contracts"},{"id":"h.zero","label":"有效零值","value":0,"unit":"contracts"}]}}
    page.evaluate("data=>{const node=FinPilotMessages.renderMessage(data,{language:'zh'});node.id='safe-message-probe';document.querySelector('#chat-messages').append(node)}",probe)
    article=page.locator('#safe-message-probe')
    assert article.locator('img,script,a[href^="javascript:"]').count()==0
    expect(article.locator('.message-mode')).to_have_text('本地响应')
    article.locator('.analysis-inline-citation[data-evidence-id="h.missing"]').click()
    missing=article.locator('.analysis-evidence-card[data-evidence-id="h.missing"]')
    expect(missing.locator('.analysis-evidence-value')).to_have_text('未提供')
    expect(missing.locator('.analysis-change-values dd').last).to_have_text('不可比')
    expect(article.locator('.analysis-evidence-card[data-evidence-id="h.zero"] .analysis-evidence-value')).to_have_text('0 合约')
    expect(article).to_contain_text('[expert.bad]')
    expect(article).to_contain_text('[unknown]')
    assert not page.evaluate('window.unsafe===1')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    shots=ROOT/'reports/screenshots/workspace-companion-v15';shots.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(shots/f'evidence-{width}.png'),animations='disabled')
    article.evaluate('(node)=>node.remove()')
    page.locator('#avatar-stage').scroll_into_view_if_needed()
    page.screenshot(path=str(shots/f'workspace-{width}.png'),animations='disabled')
    assert not any(path=='/api/chat' for _,path in calls)
    assert not any(path.startswith('/api/sessions/') for _,path in calls)
    # The calculator shortcut used by the native host must really open its tool.
    page.goto(base+'/workspace?view=calculator',wait_until='domcontentloaded')
    expect(page.locator('#calculator-dialog')).to_be_visible()
    page.locator('#calculator-dialog .close-dialog').click()
    calls.clear()
    page.goto(base+'/demo',wait_until='domcontentloaded')
    page.wait_for_function("() => window.finPilotDemoCompanion?.getStatus().renderer==='canvas2d'")
    assert page.locator('#demo-avatar-character').input_value()=='whale'
    assert not page.locator('#demo-legacy-modes').is_visible()
    page.locator('#demo-avatar-character').select_option('robot')
    page.wait_for_function("() => ['webgl2','svg'].includes(window.finPilotDemoCompanion?.getStatus().renderer)")
    page.locator('#demo-avatar-2d').click()
    page.wait_for_function("() => window.finPilotDemoCompanion.getStatus().renderer==='svg'")
    page.locator('#demo-avatar-character').select_option('whale')
    page.wait_for_function("() => window.finPilotDemoCompanion.getStatus().renderer==='canvas2d'")
    page.locator('#demo-language').click()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    assert not any(path.startswith('/api/companion') or path.startswith('/api/sessions') for _,path in calls)
    page.screenshot(path=str(shots/f'demo-{width}.png'),animations='disabled')
    assert not errors,errors
    result={"width":width,"height":height,"status":"passed","checks":24,"page_errors":errors,"new_broker_requests":0,"external_model_calls":0}
    context.close();return result


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://127.0.0.1:8000');args=parser.parse_args()
    report={"checked_at":datetime.now(timezone.utc).isoformat(),"status":"running","scope":__doc__,"viewports":[]}
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            for w,h in [(320,740),(390,844),(1440,1000)]:report['viewports'].append(check(browser,args.base,w,h))
            browser.close()
        report['status']='passed'
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__,error=str(error)[:1500])
    path=ROOT/'reports/workspace_companion_v15.json'
    if path.exists():path=path.with_stem(path.stem+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'viewports':len(report['viewports']),'report':path.name}))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
