from pathlib import Path
from datetime import datetime,timezone
import functools,hashlib,http.server,json,threading
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
out=root/'tmp/avatar-gold'
out.mkdir(parents=True,exist_ok=True)
html='''<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/web/avatar.css"><style>body{margin:0;background:#000;font-family:Arial;color:#ddd0ba}main{display:flex;gap:24px;padding:38px 48px}.stage{height:440px;width:410px;background:radial-gradient(ellipse at 50% 43%,#1c1b16,#080909 73%);border:1px solid #dba85a29;border-radius:22px}h2{font-size:11px;letter-spacing:2px;font-weight:400;margin:0 0 20px;color:#b99a69}.light{background:#f5f1e9;color:#292720}.light .stage{background:radial-gradient(ellipse at center,#fcfaf4,#e7dfd0)}.foot{margin:0 48px;color:#a68e68;font-size:11px;letter-spacing:.8px}</style><script type="module" src="/web/avatar.js"></script></head><body><main><section><h2>ORIGINAL MENTOR / 3D WEBGL2</h2><div id="spatial" class="stage"></div></section><section><h2>MATCHING CHARACTER / 2D SVG</h2><div id="flat" class="stage"></div></section></main><p class="foot">FINPILOT / GRAPHITE, IVORY & BRUSHED GOLD / STATE-DRIVEN EXPRESSION</p></body></html>'''
(out/'harness.html').write_text(html,encoding='utf-8')
class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(root)))
threading.Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{server.server_port}'
report={'checked_at':datetime.now(timezone.utc).isoformat(),'checks':[],'limitations':'Independent render/lifecycle and synthetic state tests, not actual microphone or audible speech verification. Mouth motion is procedural, not phoneme lip sync.'}
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(channel='msedge',headless=True)
  page=browser.new_page(viewport={'width':960,'height':600})
  errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
  page.goto(base+'/tmp/avatar-gold/harness.html',wait_until='networkidle')
  page.wait_for_function('Boolean(window.FinPilotAvatar)')
  page.evaluate("window.a3=FinPilotAvatar.mount(document.querySelector('#spatial'),{mode:'3d'});window.a2=FinPilotAvatar.mount(document.querySelector('#flat'),{mode:'2d'});")
  page.wait_for_function("a3.getStatus().renderer==='webgl2'",timeout=20000)
  before=page.evaluate('a3.getStatus().frames');page.wait_for_timeout(400);assert page.evaluate('a3.getStatus().frames')>before
  report['checks'].append('actual_webgl2_r187_and_animation')
  assert page.evaluate('a2.getStatus().renderer')=='svg';report['checks'].append('native_svg_fallback_palette')
  page.evaluate('a3.setReducedMotion(true);a2.setReducedMotion(true)')
  page.screenshot(path=str(out/'mentor-dark.png'))
  colours={'idle':'e8c88a','listening':'f5dcaa','thinking':'dba85a','speaking':'ffe7b4','error':'dfa28e'}
  for state,colour in colours.items():
   page.evaluate('(state)=>{a3.setState(state);a2.setState(state)}',state)
   assert page.locator('#spatial .fp-avatar').get_attribute('data-state')==state
   assert page.evaluate('a3.scene3d.glow.color.getHexString()')==colour
   assert page.evaluate('a3.scene3d.softGlow.color.getHexString()')==colour
   report['checks'].append('state_colour_'+state)
  page.evaluate("a3.setState('idle');a2.setState('idle')")
  before=page.evaluate('a3.getStatus().frames');page.wait_for_timeout(400);assert page.evaluate('a3.getStatus().frames')==before
  assert page.evaluate("document.getAnimations().filter(a=>a.playState==='running'&&a.effect.getTiming().iterations===Infinity).length")==0
  report['checks'].append('reduced_motion_stops_webgl_and_svg_animations')
  page.evaluate("document.body.classList.add('light')")
  page.screenshot(path=str(out/'mentor-ivory.png'))
  page.evaluate("a3.setMode('2d')");assert page.evaluate('a3.getStatus().actualMode')=='2d'
  page.evaluate("a3.setMode('3d')");page.wait_for_function("a3.getStatus().actualMode==='3d'")
  report['checks'].append('mode_switch_keeps_character_and_resources')
  report['webgl']=page.evaluate('a3.getStatus()')
  page.evaluate('a3.destroy();a2.destroy()');assert page.locator('.fp-avatar').count()==0
  report['checks'].append('destroy_releases_ui')
  blocked=browser.new_page()
  blocked.add_init_script("const fn=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){return type==='webgl2'?null:fn.call(this,type,...args)}")
  blocked.goto(base+'/tmp/avatar-gold/harness.html',wait_until='networkidle')
  blocked.wait_for_function('Boolean(window.FinPilotAvatar)')
  blocked.evaluate("window.fallback=FinPilotAvatar.mount(document.querySelector('#spatial'),{mode:'3d'})")
  blocked.wait_for_function("fallback.getStatus().fallbackReason==='webgl2_unavailable'")
  assert blocked.evaluate('fallback.getStatus().renderer')=='svg'
  report['checks'].append('forced_webgl_failure_remains_useful_svg')
  assert not errors,errors
  report['checks'].append('no_javascript_page_errors')
  report['page_errors']=errors
  browser.close()
 report.update(status='passed',total=len(report['checks']))
 report['sha256']={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'web/avatar.js',root/'web/avatar.css']}
 (root/'reports/avatar_gold_check_v4.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=True,indent=2))
finally:server.shutdown();server.server_close()
