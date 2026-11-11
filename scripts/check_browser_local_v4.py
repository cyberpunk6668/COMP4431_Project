"""One real local LoRA generation in the gold workspace; no cloud requests.

Requires the already trained adapter and cached base model. Deletes only the
session created by this check. This is an integration check, not an accuracy
benchmark or a speech-hardware test.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8000'


def main():
    started = time.perf_counter()
    errors, requests = [], []
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'running',
              'scope': 'One real local LoRA generation in Edge. No mocked generation or DeepSeek request; not a financial accuracy benchmark.'}
    session_id = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            context = browser.new_context(viewport={'width':1440, 'height':1000}, reduced_motion='reduce')
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: requests.append(request.post_data_json) if request.url.endswith('/api/chat') else None)
            try:
                page.goto(BASE + '/workspace', wait_until='networkidle')
                page.wait_for_function('state.models.some(model=>model.id==="local" && model.available)')
                page.locator('#model-select').select_option('local')
                expect(page.locator('#model-switch-status')).to_contain_text('下一条')
                page.locator('#message-input').fill('什么是复利？请说明限制和引用来源。')
                with page.expect_response('**/api/chat', timeout=90000) as response:
                    page.locator('#send-button').click()
                    expect(page.locator('body')).to_have_attribute('data-assistant-state', 'thinking')
                    expect(page.locator('#model-select')).to_be_disabled()
                data = response.value.json()
                session_id = data.get('session_id')
                assert data.get('mode') == 'local-lora', {key:data.get(key) for key in ('mode','warning')}
                expect(page.locator('.message.assistant')).to_have_count(1)
                expect(page.locator('.message-mode')).to_contain_text('LoRA')
                expect(page.locator('.inline-citation').first).to_have_attribute('href', 'https://www.investor.gov/financial-tools-calculators/calculators/compound-interest-calculator')
                expect(page.locator('body')).to_have_attribute('data-assistant-state','idle')
                expect(page.locator('#model-select')).to_be_enabled()
                page.locator('#model-select').select_option('deepseek')
                expect(page.locator('#model-name')).to_have_text('DeepSeek')
                expect(page.locator('.message-mode')).to_contain_text('LoRA')
                assert len(requests) == 1 and requests[0]['engine'] == 'local'
                page.evaluate("scrollTo({top:0,behavior:'instant'})")
                shot = ROOT / 'reports/screenshots/workspace-v4/local-lora-chat.png'
                shot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(shot), full_page=True, animations='disabled')
                report.update(answer=data['answer'], screenshot=shot.relative_to(ROOT).as_posix(),
                              checks=['actual_local_option_and_switch_confirmation', 'one_real_local_generation',
                                      'thinking_idle_and_busy_engine_lock', 'actual_local_mode_and_source_rendering',
                                      'switch_back_preserves_previous_response_mode', 'no_cloud_chat_or_page_errors'])
                assert not errors, errors
                report.update(status='passed', total=len(report['checks']))
            finally:
                if session_id:
                    cleanup = context.request.delete(BASE + '/api/sessions/' + session_id)
                    report['test_session_removed'] = cleanup.ok
                browser.close()
    except Exception as error:
        report.update(status='failed', error=str(error))
    report.update(page_errors=errors, elapsed_seconds=round(time.perf_counter()-started,2))
    (ROOT / 'reports/browser_local_check_v4.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='answer'}, ensure_ascii=True, indent=2))
    return int(report['status'] != 'passed')


if __name__ == '__main__':
    raise SystemExit(main())
