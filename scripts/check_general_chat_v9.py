"""Check general Q&A in Edge at desktop/mobile sizes against a running v9 app.

The default mode intercepts chat/session endpoints and makes no model request.
Use --live explicitly for exactly two real DeepSeek questions. Each viewport uses
an isolated browser context and its own disposable session. Existing sessions are
never selected or deleted, and their sidebar titles are masked in screenshots.
Existing reports/screenshots are preserved by choosing a timestamped destination.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
CASES = (
    {
        "name": "desktop-zh", "width": 1440, "height": 1000, "language": "zh",
        "prompt": "太阳系最大的行星是哪一颗？请用一句话回答。",
        "fixture_answer": "太阳系最大的行星是木星。",
    },
    {
        "name": "mobile-en", "width": 390, "height": 844, "language": "en",
        "prompt": "Write a short sick-leave email to my manager for today. Use placeholders instead of personal details.",
        "fixture_answer": "Subject: Sick Leave Today\n\nHi [Manager],\n\nI am feeling unwell and need to take sick leave today. I will keep you updated.\n\nThank you for your understanding.\n[Your Name]",
    },
)


def destinations(live: bool) -> tuple[Path, Path]:
    label = "live" if live else "fixture"
    report = ROOT / "reports" / f"general_chat_{label}_v9.json"
    shots = ROOT / "reports" / "screenshots" / "chat-v9" / label
    if report.exists() or shots.exists():
        suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        report = report.with_stem(report.stem + "_" + suffix)
        shots = shots.with_name(shots.name + "-" + suffix)
    report.parent.mkdir(parents=True, exist_ok=True)
    shots.mkdir(parents=True, exist_ok=False)
    return report, shots


def install_fixture(context, base: str, case: dict) -> None:
    sessions = {}

    def handle_session(route):
        request = route.request
        path = urlsplit(request.url).path
        sid = path.removeprefix("/api/sessions/")
        if path == "/api/sessions" and request.method == "GET":
            route.fulfill(json={"sessions": [
                {key: value for key, value in item.items() if key != "messages"}
                for item in sessions.values()
            ]})
        elif path == "/api/sessions" and request.method == "POST":
            stamp = datetime.now(timezone.utc).isoformat()
            item = {"id": str(uuid4()), "title": request.post_data_json["title"],
                    "created_at": stamp, "updated_at": stamp, "messages": []}
            sessions[item["id"]] = item
            route.fulfill(status=201, json=item)
        elif sid in sessions and request.method == "GET":
            route.fulfill(json=sessions[sid])
        elif sid in sessions and request.method == "DELETE":
            del sessions[sid]
            route.fulfill(json={"deleted": True})
        else:
            route.fulfill(status=404, json={"detail": "Session not found"})

    def handle_chat(route):
        body = route.request.post_data_json
        assert body["message"] == case["prompt"]
        assert body["language"] == case["language"] and body["engine"] == "deepseek"
        session = sessions[body["session_id"]]
        result = {"session_id": session["id"], "answer": case["fixture_answer"],
                  "mode": "deepseek", "sources": [], "warning": None, "calculation": None}
        session["messages"] = [
            {"role": "user", "content": body["message"]},
            {"role": "assistant", "content": result["answer"],
             "mode": result["mode"], "sources": [], "warning": None},
        ]
        session["title"] = body["message"][:48]
        route.fulfill(json=result)

    context.route(base + "/api/sessions**", handle_session)
    context.route(base + "/api/chat", handle_chat)


def assert_answer(text: str, language: str) -> None:
    assert text.strip(), "Assistant answer is empty"
    assert not re.search(r"\bsk-[A-Za-z0-9_-]{16,}", text), "Answer contains a credential-like value"
    if language == "zh":
        assert "木星" in text, "Expected the correct factual answer: Jupiter (木星)"
        assert len(text) < 250, "One-sentence factual response is unexpectedly long"
    else:
        assert re.search(r"\b(sick|unwell|ill)\b", text, re.I), "Missing sick-leave content"
        assert re.search(r"\b(hi|dear|hello)\b", text, re.I), "Missing email greeting"
        assert re.search(r"\b(today|leave)\b", text, re.I), "Missing email leave request"
        assert len(text.split()) <= 180, "Requested short email is unexpectedly long"


def assert_rendered(page, case: dict) -> str:
    message = page.locator(".message.assistant")
    expect(message).to_have_count(1)
    body = message.locator(".message-body")
    expect(body).to_be_visible()
    text = body.inner_text()
    assert_answer(text, case["language"])
    expect(message.locator(".message-mode")).to_have_text("DeepSeek")
    expect(message.locator(".source-card, .message-sources, .inline-citation, .message-warning")).to_have_count(0)
    expect(page.locator("#message-input")).to_be_enabled()
    expect(page.locator("#send-button")).to_be_enabled()
    expect(page.locator("#model-select")).to_be_enabled()
    expect(page.locator("#chat-form")).not_to_have_attribute("aria-busy", "true")
    expect(page.locator("body")).to_have_attribute("data-assistant-state", "idle")
    expect(page.locator("#error-banner")).to_be_hidden()
    return text


def layout(page) -> dict:
    result = page.evaluate("""() => ({
      viewport: innerWidth,
      document: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
      answer: (() => {const r = document.querySelector('.message.assistant .message-body').getBoundingClientRect(); return {left:r.left,right:r.right};})()
    })""")
    assert max(result["document"], result["body"]) <= result["viewport"] + 1, result
    assert result["answer"]["left"] >= -1 and result["answer"]["right"] <= result["viewport"] + 1, result
    return result


def session_request(page, path: str, method: str = "GET", body: dict | None = None) -> dict:
    # Fetch in the page so fixture routing also covers creation and cleanup.
    return page.evaluate("""async ({path, method, body}) => {
      const response = await fetch(path, {method, headers:{'Content-Type':'application/json'},
        ...(body ? {body:JSON.stringify(body)} : {})});
      return {status:response.status, ok:response.ok, data:await response.json()};
    }""", {"path": path, "method": method, "body": body})


def check_case(browser, base: str, case: dict, live: bool, shots: Path) -> dict:
    started = time.perf_counter()
    context = browser.new_context(
        viewport={"width": case["width"], "height": case["height"]},
        reduced_motion="reduce", is_mobile=case["width"] < 500,
        has_touch=case["width"] < 500,
    )
    if not live:
        install_fixture(context, base, case)
    # Browser contexts have empty storage; seed only this test's language choice.
    context.add_init_script("localStorage.setItem('finpilot-language', " + json.dumps(case["language"]) + ");")
    page = context.new_page()
    errors, requests = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.post_data_json)
            if urlsplit(request.url).path == "/api/chat" and request.method == "POST" else None)
    sid = None
    result = {"name": case["name"], "width": case["width"], "height": case["height"],
              "language": case["language"], "prompt": case["prompt"], "status": "running"}
    try:
        page.goto(base + "/workspace", wait_until="networkidle")
        page.wait_for_function("state.health?.version && state.models.length > 0")
        assert page.evaluate("state.health.version") == "9.0.0", "Expected running app version 9.0.0"
        assert page.evaluate("localStorage.getItem('finpilot-session')") is None
        assert page.evaluate("state.sessionId") is None, "An existing user session was selected"
        expect(page.locator(".message")).to_have_count(0)

        # Precreate an owned session so a failed/timed-out generation remains cleanable.
        created = session_request(page, "/api/sessions", "POST", {"title": "General chat v9 check: " + case["name"]})
        assert created["status"] == 201, "Could not create disposable test session"
        sid = created["data"]["id"]
        UUID(sid)
        page.evaluate("sid => localStorage.setItem('finpilot-session', sid)", sid)
        page.reload(wait_until="networkidle")
        page.wait_for_function("sid => state.sessionId === sid", arg=sid)
        expect(page.locator(".message")).to_have_count(0)
        expect(page.locator("#model-select")).to_have_value("deepseek")
        expect(page.locator("html")).to_have_attribute("lang", "zh-CN" if case["language"] == "zh" else "en")
        expect(page.locator("#message-input")).to_be_visible()
        page.locator("#message-input").fill(case["prompt"])
        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/chat" and response.request.method == "POST", timeout=90000) as response:
            page.locator("#send-button").click()
        assert response.value.status == 200, f"Chat returned HTTP {response.value.status}"
        data = response.value.json()
        assert len(requests) == 1, "Expected exactly one chat request for this viewport"
        assert requests[0] == {"message": case["prompt"], "session_id": sid,
                               "language": case["language"], "engine": "deepseek"}
        assert data["session_id"] == sid, "Reply belongs to a different session"
        assert data.get("mode") == "deepseek", {"mode": data.get("mode"), "warning": data.get("warning")}
        assert data.get("sources") == [], "General answer must not fabricate financial source cards"
        assert not data.get("warning"), data.get("warning")
        assert_answer(data["answer"], case["language"])
        text = assert_rendered(page, case)
        expect(page.locator("#message-input")).to_have_value("")
        page.locator("#message-input").fill("Editable draft after reply")
        expect(page.locator("#message-input")).to_have_value("Editable draft after reply")
        page.locator("#message-input").fill("")
        before_layout = layout(page)
        page.locator(".message.assistant .message-body").scroll_into_view_if_needed()
        screenshot = shots / (case["name"] + "-answer.png")
        page.screenshot(path=str(screenshot), full_page=True, animations="disabled", mask=[page.locator("#session-list")])

        page.reload(wait_until="networkidle")
        page.wait_for_function("sid => state.sessionId === sid", arg=sid)
        assert assert_rendered(page, case) == text, "Reload changed the displayed answer"
        assert page.evaluate("localStorage.getItem('finpilot-session')") == sid
        after_layout = layout(page)
        page.locator(".message.assistant .message-body").scroll_into_view_if_needed()
        reload_shot = shots / (case["name"] + "-restored.png")
        page.screenshot(path=str(reload_shot), full_page=True, animations="disabled", mask=[page.locator("#session-list")])
        assert len(requests) == 1, "Reload unexpectedly sent another model request"
        assert not errors, errors
        result.update(status="passed", answer=data["answer"], visible_answer=text,
                      mode=data["mode"], sources=data["sources"], warning=data.get("warning"),
                      badge="DeepSeek", layout_before_reload=before_layout, layout_after_reload=after_layout,
                      screenshots=[path.relative_to(ROOT).as_posix() for path in (screenshot, reload_shot)],
                      checks=["isolated_storage_and_owned_session", "general_question_answered",
                              "deepseek_mode_without_sources_or_warning", "visible_answer_and_honest_badge",
                              "composer_and_model_selector_restored", "editable_composer_after_reply",
                              "persisted_answer_and_metadata_after_reload", "no_duplicate_model_request",
                              "no_horizontal_overflow", "no_page_errors"])
    except Exception as error:
        result.update(status="failed", error=str(error))
        try:
            failure = shots / (case["name"] + "-failure.png")
            page.screenshot(path=str(failure), full_page=True, animations="disabled", mask=[page.locator("#session-list")])
            result["failure_screenshot"] = failure.relative_to(ROOT).as_posix()
        except Exception:
            pass
    finally:
        if sid:
            try:
                removed = session_request(page, "/api/sessions/" + sid, "DELETE")
                result["owned_session_removed"] = removed["ok"] and removed["data"].get("deleted") is True
                assert result["owned_session_removed"], "Disposable session cleanup failed"
                assert session_request(page, "/api/sessions/" + sid)["status"] == 404
            except Exception as error:
                result.update(status="failed", cleanup_error=str(error))
        result.update(page_errors=errors, chat_requests=len(requests),
                      live_model_requests=len(requests) if live else 0,
                      elapsed_seconds=round(time.perf_counter() - started, 2))
        context.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--live", action="store_true", help="Explicitly send the two real DeepSeek requests; no retries.")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path or parsed.query:
        parser.error("--base must be a loopback HTTP origin")
    report_path, shots = destinations(args.live)
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "running",
              "mode": "live" if args.live else "fixture", "app_version": "9.0.0", "base": base,
              "browser": "Microsoft Edge (headless Chromium)",
              "scope": "Two real general questions; narrow functional checks, not an overall model accuracy benchmark."
                       if args.live else "Controlled general-answer fixtures; no model connectivity or factual accuracy claim.",
              "privacy": "Independent empty-storage contexts; only owned disposable sessions deleted; existing session titles masked."}
    started = time.perf_counter()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            try:
                report["cases"] = [check_case(browser, base, case, args.live, shots) for case in CASES]
            finally:
                browser.close()
        report["live_model_requests"] = sum(case["live_model_requests"] for case in report["cases"])
        report["status"] = "passed" if all(case["status"] == "passed" for case in report["cases"]) else "failed"
    except Exception as error:
        report.update(status="failed", error=str(error))
    report["elapsed_seconds"] = round(time.perf_counter() - started, 2)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # Ordinary answers are saved in the report; stdout needs only the validation result.
    print(json.dumps({"status": report["status"], "mode": report["mode"],
                      "report": report_path.relative_to(ROOT).as_posix(),
                      "live_model_requests": report.get("live_model_requests", 0),
                      "cases": [{key: case[key] for key in ("name", "status", "chat_requests", "owned_session_removed", "error", "cleanup_error") if key in case}
                                for case in report.get("cases", [])]}, ensure_ascii=True, indent=2))
    return int(report["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
