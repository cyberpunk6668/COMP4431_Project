"""Real Edge + private offline app: denied and full browser storage regression.

No provider, broker, existing database, or ordinary development port is used.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import sys
from threading import Thread
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    scratch = ROOT / "tmp" / "storage-resilience" / stamp
    scratch.mkdir(parents=True)
    os.environ.update(DEEPSEEK_API_KEY="", FINPILOT_OFFLINE="true", IBKR_ENABLED="false",
                      FINPILOT_DB=str(scratch / "import.sqlite3"),
                      FINPILOT_ADAPTER=str(scratch / "missing-adapter"))
    import dotenv
    dotenv.load_dotenv = lambda *args, **kwargs: False
    from app.config import Settings
    from app.llm import DeepSeek
    from app.local_llm import LocalLoRA
    from app.main import create_app
    import uvicorn
    from playwright.sync_api import sync_playwright, expect

    attempts = []

    async def forbidden_provider(*args, **kwargs):
        attempts.append("provider")
        raise AssertionError("No model generation permitted")

    DeepSeek.complete = LocalLoRA.complete = forbidden_provider

    class NoGateway:
        async def status(self):
            return {"enabled": False, "connected": False, "provider": "ibkr", "read_only": True}

        async def snapshot(self, *args, **kwargs):
            attempts.append("broker")
            raise AssertionError("No broker request permitted")

        fetch = list_expirations = snapshot

    app = create_app(Settings(api_key="", offline=True, db_path=scratch / "owned.sqlite3",
                              adapter_path=scratch / "missing-adapter"),
                     options_provider=NoGateway(), history_provider=NoGateway())
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                          log_level="error", access_log=False, loop="asyncio"))
    thread = Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(.05)
    assert server.started, "Private offline app did not start"
    base = f"http://127.0.0.1:{port}"
    report = {"status": "running", "checked_at": datetime.now(timezone.utc).isoformat(),
              "scope": "Real Edge + private offline API + fault injection; no model or broker",
              "cases": []}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True,
                args=["--disable-background-networking", "--disable-component-update", "--no-first-run"])
            for mode in ["denied", "full"]:
                context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
                if mode == "denied":
                    context.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw new DOMException('Blocked for test', 'SecurityError')}})")
                else:
                    context.add_init_script("Storage.prototype.setItem = function() {throw new DOMException('Full for test', 'QuotaExceededError')}")

                def guard(route):
                    if urlsplit(route.request.url).netloc != urlsplit(base).netloc:
                        route.abort()
                    else:
                        route.continue_()

                context.route("**/*", guard)
                page = context.new_page()
                page.set_default_timeout(15000)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                checks = []
                page.goto(base + "/", wait_until="domcontentloaded")
                expect(page.locator(".hero-actions a[href='/options-demo']")).to_be_visible()
                expect(page.locator("#planning svg[role='img']")).to_be_visible()
                expect(page.locator(".lab-error")).to_have_count(0)
                page.locator("[data-testid='language-toggle']").click()
                expect(page.locator("html")).to_have_attribute("lang", "en")
                checks.append("home_and_language_switch")

                page.goto(base + "/workspace", wait_until="domcontentloaded")
                expect(page.locator("#model-select option")).not_to_have_count(0)
                page.locator("#theme-toggle").click()
                expect(page.locator("html")).to_have_attribute("data-theme", "dark")
                page.locator("#language-toggle").click()
                expect(page.locator("html")).to_have_attribute("lang", "en")
                page.locator("#message-input").fill("What is diversification?")
                page.locator("#send-button").click()
                expect(page.locator(".message.assistant")).to_have_count(1)
                expect(page.locator("#message-input")).to_have_value("")
                expect(page.locator("#error-banner")).not_to_be_visible()
                session_id = page.evaluate("state.sessionId")
                saved = page.request.get(base + "/api/sessions/" + session_id).json()
                assert len(saved["messages"]) == 2
                assert saved["messages"][-1]["mode"] == "offline"
                page.locator("#top-new").click()
                expect(page.locator(".message.assistant")).to_have_count(0)
                checks.append("workspace_theme_language_chat_persistence_and_new_session")

                page.goto(base + "/learn", wait_until="domcontentloaded")
                expect(page.locator("#lab-scenarios button")).to_have_count(3)
                expect(page.locator("#lab-pnl")).to_contain_text("140.00")
                page.locator("#lab-language").click()
                expect(page.locator("html")).to_have_attribute("lang", "en")
                expect(page.locator("#lab-scenarios button")).to_have_count(3)
                checks.append("learning_catalogue_trial_and_language_switch")

                page.goto(base + "/help", wait_until="domcontentloaded")
                expect(page.locator("#help-results")).to_be_visible()
                assert page.locator("#help-results").evaluate("node => node.children.length") > 0
                checks.append("reviewed_help_catalogue")
                assert not errors, errors
                report["cases"].append({"mode": mode, "checks": checks, "page_errors": errors})
                context.close()
            browser.close()
        assert not attempts, attempts
        report["status"] = "passed"
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        report["forbidden_attempts"] = attempts
        output = ROOT / "reports" / f"storage_resilience_{stamp}.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": report["status"], "report": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
