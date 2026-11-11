"""Real browser model selection -> trained cached model -> avatar -> citations."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    errors = []
    tick = time.perf_counter()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1100}, reduced_motion="reduce")
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:8000/workspace", wait_until="networkidle")
        expect(page.locator('#model-select option[value="local"]')).to_be_enabled()
        page.locator("#theme-toggle").click()
        page.locator("#model-select").select_option("local")
        page.locator("#message-input").fill("什么是复利？请说明限制和引用来源。")
        page.locator("#send-button").click()
        page.wait_for_function("state.avatarState === 'thinking'")
        expect(page.locator(".message.assistant")).to_have_count(1, timeout=70000)
        expect(page.locator(".message-mode")).to_contain_text("LoRA")
        expect(page.locator(".inline-citation").first).to_have_attribute("href", "https://www.investor.gov/financial-tools-calculators/calculators/compound-interest-calculator")
        page.wait_for_function("state.avatarState === 'idle'")
        page.evaluate("scrollTo({top:0,behavior:'instant'})")
        page.screenshot(path=str(ROOT / "reports/screenshots/v2/local-lora-chat.png"), full_page=True, animations="disabled")
        answer = page.locator(".message.assistant .message-body").text_content()
        browser.close()
    assert not errors, errors
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "passed", "total": 4,
              "checks": ["actual_local_model_option_available", "actual_model_selection_and_generation", "thinking_idle_avatar_with_local_request", "local_model_mode_and_verified_citation_rendering"],
              "page_errors": errors, "elapsed_seconds": round(time.perf_counter()-tick, 2), "answer": answer,
              "scope": "Actual browser and local model; no mocked backend and no DeepSeek request. One synthetic finance question, not an accuracy benchmark."}
    (ROOT / "reports/browser_local_check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "answer"}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
