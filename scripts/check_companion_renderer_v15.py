"""Actual Edge sprite/lifecycle/fallback checks; no API, model or broker calls.

Serves only a disposable harness and the companion directory on loopback.
This verifies actual 2D frames, not new 3D, audio hardware or the native shell.
"""
from datetime import datetime, timezone
import functools
import http.server
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tmp/companion-renderer-v15.html"


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/tmp/companion-renderer-v15.html" or path.startswith("/web/companion/"):
            return super().do_GET()
        self.send_error(404)


def main():
    HARNESS.parent.mkdir(exist_ok=True)
    HARNESS.write_text("""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<link rel="stylesheet" href="/web/companion/renderer.css">
<style>body{margin:0;background:#fafafa;color:#0f172a;font-family:Arial}main{padding:24px}h1{font-size:21px}.stage{width:280px;max-width:100%;box-sizing:border-box;height:320px;border:1px solid #e5d5b0;border-radius:24px;background:radial-gradient(ellipse at center,#fff,#f4f6fb)}p{font-size:13px;color:#64748b;max-width:320px}</style>
<script defer src="/web/companion/renderer.js"></script></head><body><main><h1>FinPilot · 鲸鱼娘 2D</h1><div id="stage" class="stage"></div><p>现成 Q 版动作 · 本地 Sprite 渲染<br>动作表示操作状态，不表示行情或判断可信度。</p></main></body></html>""", encoding="utf-8")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    shots = ROOT / "reports/screenshots/companion-v15"
    shots.mkdir(parents=True, exist_ok=True)
    report = {"checked_at":datetime.now(timezone.utc).isoformat(), "status":"running",
              "scope":"Independent actual Edge Canvas2D renderer; only local asset HTTP responses.",
              "model_calls":0,"broker_calls":0,"checks":[],"viewports":[],"screenshots":[]}
    errors, requests = [], []
    def open_avatar(browser, width=780, height=620, setup=None):
        page = browser.new_page(viewport={"width":width,"height":height},device_scale_factor=1)
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.on("request",lambda request:requests.append(request.url))
        if setup:
            setup(page)
        page.goto(base+"/tmp/companion-renderer-v15.html")
        page.wait_for_function("Boolean(window.FinPilotCompanion)")
        page.evaluate("window.pet=FinPilotCompanion.mount(document.getElementById('stage'),{language:'zh'})")
        return page
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="msedge",headless=True)
            page=open_avatar(browser)
            page.wait_for_function("!pet.getStatus().loading && pet.getStatus().renderer==='canvas2d'")
            initial=page.evaluate("pet.getStatus()")
            assert initial["assetRevision"]=="7661c8b304c5400701f91da01b1a643a207331de"
            assert initial["actualMode"]=="2d" and initial["frames"]>0
            assert page.evaluate("document.querySelector('.fp-companion canvas').getContext('2d').getImageData(0,0,280,320).data.some((v,i)=>i%4===3&&v>0)")
            # Startup is genuinely lazy: no walking/jump/sleep atlas is fetched.
            assert not any("inbetween-" in url for url in requests)
            report["checks"] += ["actual_canvas2d_pixels","pinned_asset_revision","lazy_action_loading"]
            for state in ["listening","thinking","speaking","error","idle"]:
                page.evaluate("s=>pet.setState(s)",state)
                page.wait_for_function("s=>pet.getStatus().activeClip===s",arg=state)
                page.wait_for_timeout(180)
                assert page.locator('.fp-companion').get_attribute('data-state')==state
            report["checks"].append("five_operation_states")
            page.evaluate("pet.playAction('wave')")
            wave_images=[]
            for _ in range(8):
                page.wait_for_timeout(110)
                wave_images.append(page.locator('canvas').evaluate("c=>c.toDataURL()"))
            assert len(set(wave_images))>=3,"Wave must contain actual authored frame changes"
            report["checks"].append("authored_multiframe_wave")
            page.evaluate("pet.playAction('walk-right')")
            walk_images=[]
            for _ in range(8):
                page.wait_for_timeout(95)
                walk_images.append(page.locator('canvas').evaluate("c=>c.toDataURL()"))
            assert len(set(walk_images))>=3
            report["checks"].append("authored_multiframe_walk")
            for action in ['drag','fall','land','sleep','wake']:
                page.evaluate("a=>pet.playAction(a)",action)
                page.wait_for_function("a=>pet.getStatus().activeClip===a",arg=action)
                page.wait_for_timeout(70)
            report["checks"].append("drag_drop_and_rest_poses")
            page.evaluate("pet.playAction('idle');pet.setReducedMotion(true)")
            page.wait_for_timeout(150)
            before=page.evaluate('pet.getStatus().frames')
            page.wait_for_timeout(350)
            assert before==page.evaluate('pet.getStatus().frames')
            page.evaluate("pet.setState('thinking')")
            page.wait_for_timeout(100)
            before=page.evaluate('pet.getStatus().frames')
            page.wait_for_timeout(350)
            assert before==page.evaluate('pet.getStatus().frames')
            report["checks"].append("reduced_motion_stops_animation_but_state_updates")
            page.evaluate("pet.setReducedMotion(false);pet.setState('idle');document.getElementById('stage').style.marginTop='1600px'")
            page.wait_for_function('pet.getStatus().paused')
            before=page.evaluate('pet.getStatus().frames')
            page.wait_for_timeout(350)
            assert before==page.evaluate('pet.getStatus().frames')
            page.evaluate("document.getElementById('stage').style.marginTop='0px';pet.setLanguage('en')")
            page.wait_for_function('!pet.getStatus().paused')
            assert 'financial learning companion' in page.locator('.fp-companion').get_attribute('aria-label')
            report["checks"] += ["real_intersection_pause","accessible_language_label"]
            report["renderer"]=page.evaluate('pet.getStatus()')
            for width in (320,390,1440):
                page.set_viewport_size({"width":width,"height":740})
                page.evaluate("pet.setReducedMotion(true);pet.playAction('idle')")
                page.wait_for_timeout(80)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                shot=shots/f"renderer-{width}.png"
                page.screenshot(path=str(shot),animations="disabled")
                report['screenshots'].append(shot.relative_to(ROOT).as_posix())
                report['viewports'].append({'width':width,'renderer':page.evaluate('pet.getStatus().renderer')})
            report["checks"].append("three_viewports_no_overflow")
            page.evaluate('pet.destroy();pet.setState("idle");pet.destroy()')
            assert page.locator('.fp-companion').count()==0 and page.evaluate('pet.getStatus().destroyed')
            report['checks'].append('idempotent_destroy')
            def block_canvas(page):
                page.add_init_script("const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){return type==='2d'?null:original.call(this,type,...args)}")
            fallback=open_avatar(browser,setup=block_canvas)
            fallback.wait_for_function("!pet.getStatus().loading&&pet.getStatus().renderer==='static-image'")
            assert fallback.evaluate('pet.getStatus().fallbackReason')=='canvas2d_unavailable'
            assert fallback.locator('.fp-companion__portrait').evaluate('i=>i.naturalWidth')>0
            report['checks'].append('canvas_unavailable_static_portrait')
            fallback.close()
            def block_atlas(page):
                page.route('**/assets/dense-wave.webp',lambda route:route.fulfill(status=404,body='not found'))
            bad=open_avatar(browser,setup=block_atlas)
            bad.wait_for_function("pet.getStatus().renderer==='canvas2d'")
            bad.evaluate("pet.playAction('wave')")
            bad.wait_for_function("pet.getStatus().renderer==='static-image'&&pet.getStatus().fallbackReason==='atlas_load_failed'")
            report['checks'].append('action_failure_honest_static_fallback')
            bad.close()
            late=open_avatar(browser)
            late.evaluate('pet.destroy()')
            late.wait_for_timeout(250)
            assert late.locator('.fp-companion').count()==0
            report['checks'].append('destroy_during_async_load')
            late.close()
            assert not errors,errors
            assert all(url.startswith(base+'/web/companion/') or url==base+'/tmp/companion-renderer-v15.html' for url in requests)
            report['checks'] += ['no_page_errors','local_assets_only_no_api_requests']
            report.update(status='passed',page_errors=errors,requests=len(requests),total_checks=len(report['checks']))
            browser.close()
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__,error=str(error)[:1500],page_errors=errors)
        raise
    finally:
        server.shutdown()
        (ROOT/'reports/companion_renderer_v15.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':report['total_checks'],'model_calls':0,'broker_calls':0}))


if __name__ == '__main__':
    main()
