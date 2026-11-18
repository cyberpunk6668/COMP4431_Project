"""Replay invariants and model boundary tests; no live model or gateway access."""
import asyncio
from copy import deepcopy
import json
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.llm import ProviderError
from app.options_analytics import analyze_option_snapshot
from app.options_demo import (
    API_CONTRACT, BASE_TIME, DemoRequest, SCENARIO_ID, build_demo_frame,
    create_demo_router, replay_snapshot, run_demo,
)


class NoProvider:
    calls = 0

    async def complete(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("An offline/local replay must not request a model")


class Provider:
    def __init__(self, raw=None, error=None):
        self.raw, self.error, self.calls = raw, error, []

    async def complete(self, messages, **kwargs):
        self.calls.append({"messages": deepcopy(messages), **kwargs})
        if self.error:
            raise self.error
        return self.raw


def settings(online=False):
    return Settings(api_key="test-only-key" if online else "", offline=not online)


def client_for(config=None, provider=None):
    app = FastAPI()
    app.include_router(create_demo_router(config or settings(), provider or NoProvider()))
    return TestClient(app)


def metric(result, identifier):
    return next(item["value"] for item in result["evidence"] if item["id"] == identifier)


def test_scenario_exposes_honest_identity_and_safe_configuration():
    client = client_for(settings(True))
    result = client.get("/api/options-demo/scenario").json()
    assert result["scenario"]["id"] == SCENARIO_ID
    assert result["source_kind"] == "synthetic_replay"
    assert result["gateway_connected"] is False
    assert result["cloud_configured"] is True
    assert isinstance(result["configured_model"], str)
    assert "test-only-key" not in json.dumps(result)
    assert len(result["questions"]) == 4
    assert result["frames"][0]["recorded_at"] == BASE_TIME.isoformat()


def test_public_contract_identifies_language_capability_and_accepts_english_payload():
    """A current static client can detect an older still-running API process."""
    client = client_for()
    properties = client.get("/openapi.json").json()["components"]["schemas"]["DemoRequest"]["properties"]
    assert properties["language"]["enum"] == ["zh", "en"]
    for language in ("zh", "en"):
        metadata = client.get("/api/options-demo/scenario", params={"language": language}).json()
        assert metadata["api_contract"] == API_CONTRACT == "options-demo.v2"
        assert metadata["supported_languages"] == ["zh", "en"]
        assert metadata["language"] == language
        assert [item["frame"] for item in metadata["display_catalogue"]["frames"]] == [0, 1]
        response = client.post("/api/options-demo/run", json={"frame": 0, "engine": "local", "language": language})
        assert response.status_code == 200
        result = response.json()
        assert result["api_contract"] == metadata["api_contract"]
        assert result["language"] == result["answer"]["language"] == language
        assert result["provenance"]["model_called"] is False


def test_default_local_replay_never_calls_network_or_gateway(monkeypatch):
    from app.options_ibkr import IBKROptionsProvider

    async def no_gateway(*args, **kwargs):
        raise AssertionError("Demo must not connect to IBKR")

    monkeypatch.setattr(IBKROptionsProvider, "snapshot", no_gateway)
    monkeypatch.setattr(IBKROptionsProvider, "status", no_gateway)
    provider = NoProvider()
    # Even a configured key cannot make the backend default call the provider.
    result = client_for(settings(True), provider).post("/api/options-demo/run", json={}).json()
    assert result["answer"]["mode"] == "local"
    assert "本地规则" in result["answer"]["notice"]
    assert result["provenance"]["gateway_connected"] is False
    assert result["provenance"]["model_called"] is False
    assert provider.calls == 0


def test_default_interpretation_leads_with_volatility_and_keeps_market_boundaries():
    result = asyncio.run(run_demo(DemoRequest(), settings(), NoProvider()))
    answer = result["answer"]
    assert answer["text"].startswith("隐含波动率")
    assert "风险溢价" in answer["text"]
    assert "没有从这些报价重新反推" in result["limitations"][-1]
    assert "下行侧的波动率定价相对更高" in answer["text"]
    assert "不能判断整体波动率是否异常高低" in answer["text"]
    assert "不能推出全市场宏观结论" in answer["text"]
    assert "平值跨式" in answer["text"] and "发生概率或保证的未来波动区间" in answer["text"]
    assert "put_call_volume" not in answer["evidence_ids"]
    principles = {item["id"]: item for item in result["evidence"] if item["id"].startswith("knowledge.")}
    assert set(principles) == {"knowledge.iv_definition", "knowledge.skew_limits", "knowledge.straddle_limits"}
    assert all(item["source_kind"] == "interpretation_reference" for item in principles.values())
    assert all(item["source_url"].startswith("https://") for item in principles.values())
    assert set(principles) <= set(answer["evidence_ids"])


@pytest.mark.parametrize(("frame", "puts", "calls", "ratio", "iv", "atm", "coverage"), [
    (0, 1200, 800, 1.5, 8, 4.8, 100),
    (1, 2000, 1000, 2, 12, 5.4, 83.3333),
])
def test_actual_calculator_values_match_known_raw_inputs(frame, puts, calls, ratio, iv, atm, coverage):
    result = build_demo_frame(frame)
    assert metric(result, "volume_put") == puts
    assert metric(result, "volume_call") == calls
    assert metric(result, "put_call_volume") == ratio
    assert metric(result, "iv_skew_25_delta") == pytest.approx(iv)
    assert metric(result, "atm_straddle") == pytest.approx(atm)
    assert metric(result, "quote_coverage") == pytest.approx(coverage)
    assert metric(result, "open_interest_ratio") == 0.8
    assert result["quality"]["market_data_status"] == "synthetic_replay"
    assert result["quality"]["llm_market_data_eligible"] is False
    assert result["quality"]["paired_volume_strikes"] == 3
    assert len(result["snapshot"]["quotes"]) == 6
    json.dumps(result, allow_nan=False)


def test_missing_quotes_stay_null_and_do_not_become_zero_or_last_price():
    result = build_demo_frame(1)
    row = next(row for row in result["snapshot"]["quotes"] if row["strike"] == 105 and row["right"] == "P")
    assert row["bid"] is None and row["ask"] is None and row["last"] is None
    assert metric(result, "missing_bbo") == 1
    # Volume for that same contract is still available; independent fields survive.
    assert row["volume"] == 350
    assert result["quality"]["valid_quote_contracts"] == 5
    assert metric(result, "volume_put") == 2000


def test_default_overview_distinguishes_no_activity_from_missing_volume(monkeypatch):
    from app import options_demo

    original = options_demo.replay_snapshot
    volume = 0

    def changed_snapshot(frame):
        snapshot = original(frame)
        for row in snapshot["quotes"]:
            row.update(volume=volume, bid=None, ask=None)
        return snapshot

    monkeypatch.setattr(options_demo, "replay_snapshot", changed_snapshot)
    zero = asyncio.run(run_demo(DemoRequest(question="请分析这批样本的成交结构"), settings(), NoProvider()))
    assert "未观察到看涨或看跌成交活动" in zero["answer"]["text"]
    assert "未返回有效双边报价" in zero["answer"]["text"]
    assert metric(zero, "volume_put") == metric(zero, "volume_call") == 0

    volume = None
    missing = asyncio.run(run_demo(DemoRequest(question="请分析这批样本的成交结构"), settings(), NoProvider()))
    assert "成交量字段不完整" in missing["answer"]["text"]
    assert "未观察到看涨或看跌成交活动" not in missing["answer"]["text"]
    assert metric(missing, "volume_put") is None
    assert missing["answer"]["mode"] == "local"


def test_volatility_interpretation_does_not_replace_missing_pricing_with_zero(monkeypatch):
    from app import options_demo

    original = options_demo.replay_snapshot

    def missing_pricing(frame):
        snapshot = original(frame)
        for row in snapshot["quotes"]:
            row.update(implied_volatility=None, bid=None, ask=None)
        return snapshot

    monkeypatch.setattr(options_demo, "replay_snapshot", missing_pricing)
    result = asyncio.run(run_demo(DemoRequest(), settings(), NoProvider()))
    assert metric(result, "iv_skew_25_delta") is None
    assert metric(result, "atm_straddle") is None
    assert "缺少可比的两翼隐含波动率" in result["answer"]["text"]
    assert "没有足够的有效输入计算平值跨式成本" in result["answer"]["text"]
    assert "下行侧的波动率定价相对更高" not in result["answer"]["text"]


def test_replay_uses_teaching_clock_without_rewriting_old_dates():
    result = asyncio.run(run_demo(DemoRequest(), settings(), NoProvider()))
    assert result["snapshot"]["received_at"] == BASE_TIME.isoformat()
    assert result["provenance"]["recorded_at"] == BASE_TIME.isoformat()
    assert result["quality"]["calculated_at_scenario_time"] == BASE_TIME.isoformat()
    # Existing analytics at wall clock would reject freshness; demo does not
    # claim those old records became fresh when processed again.
    from datetime import timedelta
    old = analyze_option_snapshot(result["snapshot"], now=BASE_TIME + timedelta(days=2))
    assert old["metrics"]["put_call_volume"]["value"] is None
    assert old["quality"]["llm_eligible"] is False


def test_frames_and_answers_are_independent_and_have_no_hidden_refresh():
    client = client_for()
    baseline = client.post("/api/options-demo/run", json={"frame": 0}).json()
    saved = deepcopy(baseline)
    next_frame = client.post("/api/options-demo/run", json={"frame": 1, "question": "哪些变化可以比较？"}).json()
    repeated = client.post("/api/options-demo/run", json={"frame": 0}).json()
    assert metric(next_frame, "put_call_volume") == 2
    assert metric(repeated, "put_call_volume") == 1.5
    assert baseline == saved
    assert repeated["snapshot"] == baseline["snapshot"]
    assert baseline["changes"] == []
    ratio_change = next(item for item in next_frame["changes"] if item["id"] == "put_call_volume")
    assert (ratio_change["before"], ratio_change["after"]) == (1.5, 2)
    assert "同一" in ratio_change["detail"]
    assert "不是人数" in next_frame["evidence"][0]["detail"]


@pytest.mark.parametrize("body", [
    {"frame": 2}, {"frame": -1}, {"frame": True}, {"frame": "1"},
    {"engine": "ibkr"}, {"question": " "}, {"question": "x" * 1001},
    {"symbol": "SPY"}, {"refresh": True},
])
def test_request_cannot_turn_replay_into_an_unbounded_gateway_request(body):
    assert client_for().post("/api/options-demo/run", json=body).status_code == 422


@pytest.mark.parametrize(("question", "frame", "fragment"), [
    ("看跌成交更多，能说明多数人在看空吗？", 0, "份数不是人数"),
    ("缺少报价会怎样影响分析？", 1, "保留为空"),
    ("哪些变化可以比较？", 0, "当前只有起始批次"),
    ("请帮我规划出国旅行", 0, "本地规则支持"),
    ("隐含波动率能直接说明股价会涨还是跌吗？", 0, "隐含波动率通常"),
    ("平值跨式成本是未来价格波动的概率吗？", 0, "不是年化波动率、发生概率"),
    ("这部分期权数据不能说明哪些市场背景？", 0, "不能代表整个市场或宏观经济状态"),
])
def test_local_answer_limits_and_topics_are_visible(question, frame, fragment):
    result = asyncio.run(run_demo(DemoRequest(question=question, frame=frame), settings(), NoProvider()))
    assert fragment in result["answer"]["text"]
    assert result["answer"]["evidence_ids"]


def test_explicit_cloud_without_configuration_is_visible_local_fallback():
    result = asyncio.run(run_demo(DemoRequest(engine="deepseek"), settings(), NoProvider()))
    assert result["answer"]["mode"] == "local_fallback"
    assert result["answer"]["fallback_reason"] == "cloud_unconfigured"
    assert result["provenance"]["model_called"] is False


VALID_ANSWER = {"response": [
    {"text": "隐含波动率描述期权价格中的波动幅度定价，包含风险定价因素，不给出涨跌方向。",
     "evidence_ids": ["scope", "knowledge.iv_definition"]},
    {"text": "所选两翼的相对波动率定价存在差异；局部样本无法确定整体市场原因。",
     "evidence_ids": ["iv_skew_25_delta", "knowledge.skew_limits"]},
]}


def test_explicit_cloud_receives_partial_raw_data_and_returns_auditable_mode():
    provider = Provider(json.dumps(VALID_ANSWER, ensure_ascii=False))
    result = asyncio.run(run_demo(DemoRequest(engine="deepseek", frame=1), settings(True), provider))
    assert result["answer"]["mode"] == "deepseek"
    assert result["provenance"]["model_called"] is True
    assert result["provenance"]["gateway_connected"] is False
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call["json_output"] is True
    supplied = json.loads(call["messages"][1]["content"])
    assert len(supplied["current_partial_raw_sample"]["quotes"]) == 6
    assert supplied["source_kind"] == "synthetic_replay"
    assert supplied["previous_frame_comparison"][0]["before"] == 1.5
    assert supplied["previous_frame_comparison"][0]["after"] == 2
    assert supplied["current_partial_raw_sample"]["quotes"][-1]["bid"] is None
    principles = {item["id"]: item for item in supplied["current_evidence"] if item["id"].startswith("knowledge.")}
    assert "knowledge.iv_definition" in principles
    assert "risk pricing" in call["messages"][0]["content"]
    assert "did NOT solve IV" in call["messages"][0]["content"]
    assert "95 put with the 105 call: DIFFERENT strikes" in call["messages"][0]["content"]
    assert "Never call that wing comparison matched-strike, same-strike" in call["messages"][0]["content"]
    assert "put DO share the 100 strike and expiration" in call["messages"][0]["content"]
    assert principles["knowledge.iv_definition"]["supporting_url"].startswith("https://www.bis.org/")
    assert "api_key" not in json.dumps(supplied)


@pytest.mark.parametrize("raw", [
    "not JSON", "{}",
    json.dumps({"response": [{"text": "教学数据已经涨了 99%。", "evidence_ids": ["scope"]}]}),
    json.dumps({"response": [{"text": "合成样本出现新消息。", "evidence_ids": ["unknown_news"]}]}),
    json.dumps({"response": [{"text": "合成样本建议买入。", "evidence_ids": ["scope"]}]}),
    json.dumps({"response": [{"text": "这就是当前市场表现。", "evidence_ids": ["scope"]}]}),
    json.dumps({"response": [{"text": "合成样本包含八份。", "evidence_ids": ["scope"]}]}),
    json.dumps({"response": [{"text": "合成样本。", "evidence_ids": []}]}),
    json.dumps({"response": [{"text": "合成样本已连接IBKR。", "evidence_ids": ["scope"]}]}),
    json.dumps({"response": [{"text": "合成样本中看涨成交更多。", "evidence_ids": ["put_call_volume"]}]}),
    json.dumps({"response": [{"text": "合成样本中看跌IV低于看涨。", "evidence_ids": ["iv_skew_25_delta"]}]}),
    json.dumps({"response": [{"text": "两翼隐含波动率比较使用相同行权价。", "evidence_ids": ["iv_skew_25_delta"]}]}),
])
def test_invalid_model_output_falls_back_without_claiming_success(raw):
    provider = Provider(raw)
    result = asyncio.run(run_demo(DemoRequest(engine="deepseek"), settings(True), provider))
    assert result["answer"]["mode"] == "local_fallback"
    assert result["answer"]["fallback_reason"] == "model_validation_failed"
    assert result["provenance"]["model_called"] is True
    assert "不代表模型成功" in result["answer"]["notice"]
    assert len(provider.calls) == 1


@pytest.mark.parametrize("error", [ProviderError("authentication_failed"), TimeoutError()])
def test_provider_failure_is_honest_and_does_not_retry_or_leak_error(error):
    provider = Provider(error=error)
    result = asyncio.run(run_demo(DemoRequest(engine="deepseek"), settings(True), provider))
    assert result["answer"]["mode"] == "local_fallback"
    assert result["answer"]["fallback_reason"] == "provider_unavailable"
    assert len(provider.calls) == 1


def test_replay_snapshot_is_new_mutable_data_every_time():
    first = replay_snapshot(0)
    first["quotes"][0]["volume"] = 999999
    assert replay_snapshot(0)["quotes"][0]["volume"] == 200
    with pytest.raises(ValueError):
        replay_snapshot(True)


def test_english_catalogue_localizes_all_display_metadata_without_generation():
    provider = NoProvider()
    client = client_for(settings(True), provider)
    english = client.get("/api/options-demo/scenario?language=en").json()
    chinese = client.get("/api/options-demo/scenario?language=zh").json()
    assert english["language"] == "en"
    assert english["questions"][0] == "What do these option prices tell us about AAPL's volatility and risk?"
    assert english["frames"][0]["label"] == "Initial sample"
    assert not re.search(r"[\u3400-\u9fff]", json.dumps(english, ensure_ascii=False))
    for en_frame, zh_frame in zip(english["display_catalogue"]["frames"], chinese["display_catalogue"]["frames"]):
        assert en_frame["frame"] == zh_frame["frame"]
        assert {item["id"]: item["value"] for item in en_frame["metrics"]} == {
            item["id"]: item["value"] for item in zh_frame["metrics"]
        }
        assert {item["id"] for item in en_frame["evidence"]} == {item["id"] for item in zh_frame["evidence"]}
        assert en_frame["provenance_label"].startswith("Synthetic sample")
    assert provider.calls == 0


def test_english_local_analysis_preserves_numbers_source_and_recorded_time():
    english = asyncio.run(run_demo(DemoRequest(language="en", frame=1), settings(), NoProvider()))
    chinese = asyncio.run(run_demo(DemoRequest(frame=1), settings(), NoProvider()))
    assert english["answer"]["language"] == english["language"] == "en"
    assert english["answer"]["text"].startswith("Implied volatility")
    assert "synthetic" in english["answer"]["notice"]
    assert "risk premiums" in english["answer"]["text"]
    assert not re.search(r"[\u3400-\u9fff]", json.dumps(english, ensure_ascii=False))
    for key in ("put_call_volume", "iv_skew_25_delta", "atm_straddle", "quote_coverage"):
        assert metric(english, key) == metric(chinese, key)
    assert english["provenance"]["recorded_at"] == chinese["provenance"]["recorded_at"]
    assert english["provenance"]["gateway_connected"] is False
    assert english["provenance"]["model_called"] is False
    assert english["snapshot"]["quotes"][-1]["bid"] is None


def test_english_missing_iv_and_quotes_remain_missing_not_zero(monkeypatch):
    from app import options_demo
    original = options_demo.replay_snapshot

    def missing(frame):
        result = original(frame)
        for row in result["quotes"]:
            row.update(implied_volatility=None, bid=None, ask=None)
        return result

    monkeypatch.setattr(options_demo, "replay_snapshot", missing)
    result = asyncio.run(run_demo(DemoRequest(language="en"), settings(), NoProvider()))
    assert metric(result, "iv_skew_25_delta") is None
    assert metric(result, "atm_straddle") is None
    assert "Comparable wing-IV inputs are missing" in result["answer"]["text"]
    assert "Valid inputs are insufficient" in result["answer"]["text"]
    assert "relatively higher downside" not in result["answer"]["text"]


VALID_ANSWER_EN = {"response": [
    {"text": "Implied volatility describes movement priced into options, including risk pricing, rather than future price direction.",
     "evidence_ids": ["scope", "knowledge.iv_definition"]},
    {"text": "The selected put wing has higher relative volatility pricing, but the partial sample cannot establish a whole-market cause.",
     "evidence_ids": ["iv_skew_25_delta", "knowledge.skew_limits"]},
]}


def test_english_cloud_uses_requested_language_and_localized_grounding():
    provider = Provider(json.dumps(VALID_ANSWER_EN))
    result = asyncio.run(run_demo(DemoRequest(language="en", engine="deepseek"), settings(True), provider))
    assert result["answer"]["mode"] == "deepseek"
    assert result["answer"]["language"] == "en"
    assert len(provider.calls) == 1
    messages = provider.calls[0]["messages"]
    assert "ENGLISH ONLY" in messages[0]["content"]
    assert "in Chinese" not in messages[0]["content"]
    assert "95 put with the 105 call: DIFFERENT strikes" in messages[0]["content"]
    assert "Never call that wing comparison matched-strike, same-strike" in messages[0]["content"]
    payload = json.loads(messages[1]["content"])
    assert payload["requested_language"] == "en"
    assert payload["question"] == "What do these option prices tell us about AAPL's volatility and risk?"
    assert set(payload["allowed_evidence_ids"]) == {entry["id"] for entry in payload["current_evidence"]}
    assert not re.search(r"[\u3400-\u9fff]", json.dumps(payload, ensure_ascii=False))
    assert "not a successful" not in result["answer"]["notice"]


@pytest.mark.parametrize("raw", [
    json.dumps(VALID_ANSWER, ensure_ascii=False),
    json.dumps({"response": [{"text": "Synthetic data has six contracts.", "evidence_ids": ["scope"]}]}),
    json.dumps({"response": [{"text": "Synthetic sample IV is 99 percent.", "evidence_ids": ["scope"]}]}),
    json.dumps({"response": [{"text": "Synthetic data suggests you should buy puts.", "evidence_ids": ["scope"]}]}),
    json.dumps({"response": [{"text": "Synthetic put IV is lower than call IV.", "evidence_ids": ["iv_skew_25_delta"]}]}),
    json.dumps({"response": [{"text": "This is the current market performance.", "evidence_ids": ["scope"]}]}),
    json.dumps({"response": [{"text": "The same-strike wing comparison shows higher put IV.", "evidence_ids": ["iv_skew_25_delta"]}]}),
])
def test_english_invalid_model_answers_fall_back_in_english(raw):
    result = asyncio.run(run_demo(DemoRequest(language="en", engine="deepseek"), settings(True), Provider(raw)))
    assert result["answer"]["mode"] == "local_fallback"
    assert result["answer"]["fallback_reason"] == "model_validation_failed"
    assert result["answer"]["language"] == "en"
    assert not re.search(r"[\u3400-\u9fff]", json.dumps(result, ensure_ascii=False))


@pytest.mark.parametrize("online", [True, False])
def test_english_provider_failure_or_missing_configuration_has_english_notice(online):
    provider = Provider(error=ProviderError("authentication_failed"))
    result = asyncio.run(run_demo(DemoRequest(language="en", engine="deepseek"), settings(online), provider))
    assert result["answer"]["mode"] == "local_fallback"
    assert result["provenance"]["model_called"] is online
    assert len(provider.calls) == int(online)
    assert "local rules" in result["answer"]["notice"]
    assert not re.search(r"[\u3400-\u9fff]", result["answer"]["notice"])


def test_language_is_validated_on_get_and_post():
    client = client_for()
    assert client.get("/api/options-demo/scenario?language=fr").status_code == 422
    assert client.post("/api/options-demo/run", json={"language": "fr"}).status_code == 422
    assert client.post("/api/options-demo/run", json={"language": None}).status_code == 422


@pytest.mark.parametrize("language", ["zh", "en"])
def test_default_local_analysis_focuses_on_results_with_separate_source_disclosure(language):
    result = asyncio.run(run_demo(DemoRequest(language=language), settings(), NoProvider()))
    text = result["answer"]["text"]
    assert not re.search(r"教学|演示|合成|模拟|synthetic|teaching|demo|replay|simulated|IBKR", text, re.I)
    assert result["quality"]["source_kind"] == result["provenance"]["source_kind"] == "synthetic_replay"
    assert result["provenance"]["gateway_connected"] is False
    assert ("合成" if language == "zh" else "synthetic") in result["answer"]["notice"]
    assert "IBKR" in result["provenance"]["label"]
    assert "IBKR" in result["limitations"][0]


@pytest.mark.parametrize(("language", "raw"), [("zh", VALID_ANSWER), ("en", VALID_ANSWER_EN)])
def test_model_analysis_without_repeated_provenance_is_accepted(language, raw):
    provider = Provider(json.dumps(raw, ensure_ascii=False))
    result = asyncio.run(run_demo(DemoRequest(language=language, engine="deepseek"), settings(True), provider))
    assert result["answer"]["mode"] == "deepseek"
    assert not re.search(r"合成|教学|synthetic|teaching", result["answer"]["text"], re.I)
    assert result["answer"]["evidence_ids"]
    assert "IBKR" in result["answer"]["notice"]
    assert result["provenance"]["model_called"] is True
    assert len(provider.calls) == 1


@pytest.mark.parametrize(("language", "question", "disclosure"), [
    ("zh", "这些期权数据来自哪里，连接 IBKR 了吗？", "当前数据来自合成输入，不是真实行情，也不是实时行情；未连接 IBKR。"),
    ("en", "Where do these option quotes come from? Is IBKR connected?", "The inputs are synthetic, not live market data. IBKR is not connected."),
])
@pytest.mark.parametrize("engine", ["local", "deepseek"])
def test_source_questions_explicitly_disclose_synthetic_non_live_disconnected_data(language, question, disclosure, engine):
    provider = Provider(json.dumps({"response": [{"text": disclosure, "evidence_ids": ["scope"]}]}, ensure_ascii=False))
    result = asyncio.run(run_demo(DemoRequest(language=language, question=question, engine=engine), settings(True), provider))
    assert result["answer"]["mode"] == engine
    text = result["answer"]["text"]
    if language == "zh":
        assert "合成" in text and "不是实时行情" in text
        assert "未连接 IBKR" in text or "没有连接 IBKR" in text
    else:
        assert "synthetic" in text and "not live" in text
        assert "IBKR is not connected" in text
    assert len(provider.calls) == int(engine == "deepseek")


@pytest.mark.parametrize(("language", "question", "raw"), [
    ("zh", "这些期权数据是真实行情吗？", VALID_ANSWER),
    ("en", "Is this live market data?", VALID_ANSWER_EN),
])
def test_model_source_answer_cannot_omit_source_disclosure(language, question, raw):
    result = asyncio.run(run_demo(DemoRequest(language=language, engine="deepseek", question=question), settings(True), Provider(json.dumps(raw, ensure_ascii=False))))
    assert result["answer"]["mode"] == "local_fallback"
    assert result["answer"]["fallback_reason"] == "model_validation_failed"
    assert ("合成" if language == "zh" else "synthetic") in result["answer"]["text"]
    assert "IBKR" in result["answer"]["text"]
