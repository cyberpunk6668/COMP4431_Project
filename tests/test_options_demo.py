"""Replay invariants and model boundary tests; no live model or gateway access."""
import asyncio
from copy import deepcopy
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.llm import ProviderError
from app.options_analytics import analyze_option_snapshot
from app.options_demo import (
    BASE_TIME, DemoRequest, SCENARIO_ID, build_demo_frame,
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
    assert "没有从报价重新反推" in answer["text"]
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
    {"text": "隐含波动率描述期权价格中的波动幅度定价，不给出涨跌方向；这里使用合成模型输入。",
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
