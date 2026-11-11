"""Independent avatar acceptance. No LLM call, API key, microphone or live server needed.

Requires requirements-ui-tests.txt and Microsoft Edge on this Windows machine.
The local temporary HTTP server serves only this workspace and stops on completion.
"""
from pathlib import Path
from datetime import datetime,timezone
import threading,http.server,json,time,functools
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
(root/'tmp').mkdir(exist_ok=True)
(root/'reports/screenshots').mkdir(parents=True,exist_ok=True)
html='''<!doctype html><html><head><link rel="stylesheet" href="/web/avatar.css"><style>body{margin:0;background:#f8f9f5;font-family:Arial;color:#234538}main{display:flex;gap:24px;padding:48px}.stage{height:350px;width:350px;background:radial-gradient(ellipse at center,#f4f8eb,#e3ebdd);border:1px solid #d6e2cc;border-radius:24px}h2{font-size:18px;font-weight:400}button{padding:10px;margin:5px}</style><script type="module" src="/web/avatar.js"></script></head><body><main><section><h2>Genuine WebGL2 / Three.js r187</h2><div id="spatial" class="stage"></div></section><section><h2>Original SVG / 2D fallback</h2><div id="flat" class="stage"></div></section></main></body></html>'''
(root/'tmp/avatar_harness.html').write_text(html)
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(root)))
threading.Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{server.server_port}'
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':850,'height':520})
    errors=[];page.on('pageerror',lambda x:errors.append(str(x)))
    page.goto(base+'/tmp/avatar_harness.html',wait_until='networkidle')
    page.wait_for_function('Boolean(window.FinPilotAvatar)')
    page.evaluate("window.mentor3d=FinPilotAvatar.mount(document.querySelector('#spatial'),{mode:'3d',language:'en'});window.mentor2d=FinPilotAvatar.mount(document.querySelector('#flat'),{mode:'2d',language:'zh'})")
    page.wait_for_function("mentor3d.getStatus().renderer === 'webgl2' || mentor3d.getStatus().fallbackReason",timeout=15000)
    page.wait_for_timeout(650)
    print(json.dumps({'initial3d':page.evaluate('mentor3d.getStatus()'),'initial2d':page.evaluate('mentor2d.getStatus()'),'errors':errors},indent=2))
    assert page.evaluate('mentor3d.getStatus().renderer')=='webgl2'
    assert page.evaluate('mentor2d.getStatus().renderer')=='svg'
    page.screenshot(path=str(root/'reports/screenshots/avatar-preview.png'))
    result={'checked_at':datetime.now(timezone.utc).isoformat(),'status':'passed','browser':'Microsoft Edge (headless Chromium)','webgl':page.evaluate('mentor3d.getStatus()'),'states':[]}
    for state in ['listening','thinking','speaking','error','idle']:
        page.evaluate('(state)=>{mentor3d.setState(state);mentor2d.setState(state)}',state)
        assert page.locator('#spatial .fp-avatar').get_attribute('data-state')==state
        assert page.locator('#flat .fp-avatar').get_attribute('data-state')==state
        result['states'].append(state)
    page.evaluate('mentor3d.setReducedMotion(true)')
    page.wait_for_timeout(150)
    before=page.evaluate('mentor3d.getStatus().frames')
    page.wait_for_timeout(250)
    after=page.evaluate('mentor3d.getStatus().frames')
    assert before==after,(before,after)
    result['reducedMotionFrameStable']=True
    page.evaluate("mentor3d.setMode('2d')")
    assert page.evaluate('mentor3d.getStatus().renderer')=='svg'
    page.evaluate("mentor3d.setMode('3d')")
    page.wait_for_function("mentor3d.getStatus().renderer === 'webgl2'")
    page.evaluate('mentor3d.destroy();mentor2d.destroy()')
    assert page.locator('.fp-avatar').count()==0
    result['modeSwitchAndDestroy']=True
    # Explicitly blocked WebGL2: fallback must still create a useful avatar.
    blocked=browser.new_page()
    blocked.add_init_script("const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){if(type==='webgl2')return null;return original.call(this,type,...args)}")
    blocked.goto(base+'/tmp/avatar_harness.html',wait_until='networkidle')
    blocked.wait_for_function('Boolean(window.FinPilotAvatar)')
    blocked.evaluate("window.avatar=FinPilotAvatar.mount(document.querySelector('#spatial'),{mode:'3d'})")
    blocked.wait_for_function("avatar.getStatus().fallbackReason === 'webgl2_unavailable'")
    assert blocked.evaluate('avatar.getStatus().renderer')=='svg'
    result['forcedWebGLFallback']=blocked.evaluate('avatar.getStatus()')
    assert not errors,errors
    result['checks']=['genuine_webgl2_renderer','native_svg_mode','five_state_transitions','reduced_motion_stops_render_loop','2d_3d_switch','destroy_removes_ui','forced_webgl2_failure_falls_back','no_javascript_page_errors']
    result['total']=len(result['checks'])
    result['page_errors']=errors
    result['limitations']='Synthetic state drivers verify rendering and lifecycle. Actual speech/microphone integration is tested separately; mouth motion is approximate, not phoneme lip synchronization.'
    (root/'reports/avatar_check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'total':result['total'],'renderer':result['webgl']['renderer'],'revision':result['webgl']['threeRevision']},indent=2))
    browser.close()
server.shutdown()
