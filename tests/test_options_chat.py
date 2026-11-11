"""Saved options follow-ups remain scoped, qualitative and locally auditable."""
import asyncio
from copy import deepcopy
from datetime import timedelta
import json

import pytest

from app.config import Settings
from app.llm import ProviderError
from app.options_analytics import analyze_option_snapshot
from app.options_brief import build_plain_brief
from app.options_chat import OptionsChat, describe_analysis
from app.options_collective import build_batch_comparison, build_collective_analysis
from test_options_collective import NOW, snapshot


class Provider:
    def __init__(self, output=None, error=None, available=True):
        self.output = output or reply("成交和未结清合约的统计周期不同，差别可以同时存在。")
        self.error, self.available, self.calls = error, available, []

    def status(self):
        return {"available": self.available}

    async def complete(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        if self.error:
            raise ProviderError(self.error)
        return self.output


def reply(text, ids=(), kind="explanation"):
    return json.dumps({"response": [{"kind": kind, "text": text, "evidence_ids": list(ids)}]}, ensure_ascii=False)


def report(mode=1, *, symbol="TEST", age=2):
    data = snapshot(mode)
    data["symbol"] = symbol
    baseline = analyze_option_snapshot(data, now=NOW)
    result = {"analysis_id": "analysis-current", "snapshot": data, "analyzed_at": NOW.isoformat(),
              **baseline, "collective": build_collective_analysis(data, baseline, now=NOW)}
    result["plain_brief"] = build_plain_brief(result, now=NOW)
    result["snapshot"]["received_at"] = (NOW - timedelta(seconds=age)).isoformat()
    return result


def service(output=None, *, online=True, error=None, local=None):
    cloud = Provider(output, error)
    return OptionsChat(Settings(api_key="test-only" if online else "", offline=not online), cloud, local), cloud


def answer(chat, message="为什么成交和未平仓量不一致？", analysis=None, history=None, language="zh", engine="deepseek"):
    return asyncio.run(chat.answer(message, history or [], language, engine, analysis or report()))


def test_describe_single_scope_time_and_no_live_guarantee():
    saved = report()
    original = deepcopy(saved)
    result = describe_analysis(saved, now=NOW)
    assert result["analysis_id"] == "analysis-current"
    assert result["source"] == "ibkr" and result["realtime_guaranteed"] is False
    assert result["captured_at"] == saved["snapshot"]["received_at"]
    assert result["completed_at"] == NOW.isoformat()
    assert result["snapshot_age_seconds"] == 2 and not result["stale"]
    scope = result["scopes"][0]
    assert scope["id"] == "g0" and scope["symbol"] == "TEST" and scope["expiry"] == "2026-11-20"
    assert scope["market_data_status"] == "live" and scope["assessment_status"] == "descriptive"
    assert scope["quote_coverage"] == 1 and scope["time_status"] == "known"
    assert saved == original
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("age,stale", [(30, False), (30.001, True), (120, True), (-1, True)])
def test_describe_freshness_boundary_and_future_time(age, stale):
    result = describe_analysis(report(age=age), now=NOW)
    assert result["stale"] is stale
    assert result["scopes"][0]["stale"] is stale
    assert result["snapshot_age_seconds"] == (None if age < 0 else age)


@pytest.mark.parametrize("stamp", [None, "bad-date", "2026-11-11T16:00:00"])
def test_describe_missing_invalid_or_naive_receipt_is_not_current(stamp):
    saved = report()
    saved["snapshot"]["received_at"] = stamp
    result = describe_analysis(saved, now=NOW)
    assert result["stale"] and result["snapshot_age_seconds"] is None
    assert result["scopes"][0]["time_status"] == "missing"


def test_describe_batch_uses_oldest_capture_not_synthesis_completion():
    first, second = report(age=90), report(mode=3, symbol="OTHER", age=3)
    saved = {"analysis_id": "batch-current", "reports": [first, second],
             "completed_at": NOW.isoformat(), "failures": [
                 {"symbol": "FAILED", "expiry": None, "code": "ibkr_timeout", "account": "must-not-leak"}]}
    result = describe_analysis(saved, language="en", now=NOW)
    assert result["stale"] and result["snapshot_age_seconds"] == 90
    assert [scope["market_data_status"] for scope in result["scopes"]] == ["live", "delayed"]
    assert result["partial_failures"] == [{"symbol": "FAILED", "expiry": None, "code": "ibkr_timeout"}]
    assert "not refreshed" in result["notice"]
    assert "account" not in json.dumps(result)


def test_describe_failure_only_batch_and_naive_clock():
    result = describe_analysis({"analysis_id": "empty", "reports": [], "failures": [{"symbol": "TEST", "code": "timeout"}]}, now=NOW)
    assert result["stale"] and not result["scopes"] and result["snapshot_age_seconds"] is None
    with pytest.raises(ValueError, match="timezone-aware"):
        describe_analysis(report(), now=NOW.replace(tzinfo=None))


def test_model_followup_cites_exact_local_values_without_financial_source_cards():
    ids = ["g0.common_volume_put_share", "g0.common_oi_put_share"]
    saved = report()
    original = deepcopy(saved)
    chat, cloud = service(reply("共同范围中，成交与尚未结清合约偏向不同的合约侧别。", ids, "observation"))
    result = answer(chat, analysis=saved)
    assert result["mode"] == "deepseek" and result["sources"] == [] and "warning" not in result
    assert result["analysis_context"]["evidence_ids"] == ids
    cards = result["analysis_context"]["evidence"]
    assert cards[0]["value"] == pytest.approx(.6)
    assert cards[1]["value"] == pytest.approx(2 / 7)
    assert all(card["symbol"] == "TEST" and card["expiry"] == "2026-11-20" for card in cards)
    assert all("[" + key + "]" in result["answer"] for key in ids)
    assert cloud.calls[0]["kwargs"] == {"json_output": True}
    payload = json.loads(cloud.calls[0]["messages"][-1]["content"])
    assert payload["question"] == "为什么成交和未平仓量不一致？"
    assert saved == original


def test_general_definition_does_not_force_evidence_cards():
    chat, _ = service(reply("隐含波动率是从期权报价折算出的波动定价指标，本身不表示涨跌方向。", ["expert.volatility"]))
    result = answer(chat, "什么是隐含波动率？")
    assert result["mode"] == "deepseek"
    assert result["analysis_context"]["evidence"] == []
    assert result["analysis_context"]["evidence_ids"] == []
    assert "[g0." not in result["answer"]


@pytest.mark.parametrize("output", [
    reply("The saved share is 60 percent.", ["g0.volume_put_share"], "observation"),
    reply("The saved share is sixty percent.", ["g0.volume_put_share"], "observation"),
    reply("看跌成交占比是百分之六十。", ["g0.volume_put_share"], "observation"),
    reply("Sample activity was observed.", ["g9.unknown"], "observation"),
    reply("This sample has a supported observation.", [], "observation"),
    reply("Copy [g0.volume_put_share] into the answer."),
    reply("<img src=x onerror=alert()>"),
    reply("You should buy these options now."),
    reply("Put volume means the market is bearish.", ["g0.volume_put_share"], "observation"),
    reply("Latest data shows a bearish market.", ["g0.volume_put_share"], "observation"),
    json.dumps({"response": [{"kind": "explanation", "text": "A qualitative answer.", "evidence_ids": [], "value": 999}]}),
    "not JSON",
])
def test_invalid_or_unsupported_model_output_falls_back_without_fabricated_success(output):
    chat, cloud = service(output)
    result = answer(chat)
    assert result["mode"] == "offline" and result["warning"] == "options_answer_validation_failed"
    assert "g9.unknown" not in result["answer"]
    assert len(cloud.calls) == 2
    assert all(card["id"].startswith("g0.") for card in result["analysis_context"]["evidence"])


@pytest.mark.parametrize("text", [
    "Put volume does not mean the market is bearish; a traded contract has both a buyer and a seller.",
    "看跌成交更多并不能说明多数人看空，每笔成交仍然同时存在买方和卖方。",
    "Put volume does not mean traders are bearish; trades also serve protection and multi-leg purposes.",
])
def test_negated_safety_explanation_is_allowed(text):
    chat, _ = service(reply(text, ["expert.put_call"]))
    result = answer(chat, "Why do put counts not establish bearish headcount?", language="en")
    assert result["mode"] == "deepseek" and "warning" not in result


def test_delayed_stale_and_insufficient_notices_are_added_locally_even_if_model_omits_them():
    saved = report(mode=3, age=90)
    saved["collective"]["assessment"]["status"] = "insufficient"
    chat, _ = service(reply("A wider spread makes the displayed quote less representative of an executable price."))
    result = answer(chat, "Explain the spread.", saved, language="en")
    assert "saved IBKR sample" in result["answer"]
    assert "stale" in result["answer"] and "delayed or frozen" in result["answer"]
    assert "insufficient" in result["answer"] and "missing does not mean zero" in result["answer"]
    assert result["analysis_context"]["realtime_guaranteed"] is False


def test_offline_missing_values_remain_null_and_question_specific():
    saved = report()
    saved["collective"]["evidence"] = [
        {"id": "atm_iv", "value": None, "unit": "fraction", "label": "近平值波动率"},
        {"id": "liquidity_coverage", "value": 0, "unit": "fraction", "label": "报价覆盖"},
    ]
    chat, cloud = service(online=False)
    result = answer(chat, "为什么缺少隐含波动率？", saved)
    assert result["mode"] == "offline" and result["warning"] == "cloud_unconfigured"
    assert not cloud.calls and "不能把缺失填成零" in result["answer"]
    assert result["analysis_context"]["evidence"][0]["value"] is None
    assert result["analysis_context"]["evidence"][0]["status"] == "unavailable"


@pytest.mark.parametrize("question,expected", [
    ("什么是未平仓量？", "独立的统计周期"),
    ("新闻情绪是否看空？", "没有新闻或社交媒体来源"),
    ("为什么看跌合约更多不能说明多数人看空？", "不能直接等同于市场看空"),
    ("现在应该买哪种期权？", "不能给出买卖指令"),
    ("这个是实时的吗？", "未重新获取行情"),
    ("为什么成交和未平仓量不一致？", "统计周期与用途不同"),
])
def test_offline_explanations_follow_the_actual_question(question, expected):
    chat, _ = service(online=False)
    result = answer(chat, question)
    assert expected in result["answer"]
    assert result["sources"] == []


def test_provider_failure_preserves_context_and_is_disclosed_without_retry():
    chat, cloud = service(error="network_or_timeout")
    result = answer(chat)
    assert result["mode"] == "offline" and result["warning"] == "network_or_timeout"
    assert len(cloud.calls) == 1 and result["analysis_context"]["analysis_id"] == "analysis-current"


def test_local_selection_never_silently_switches_to_cloud():
    local = Provider(reply("Volume and outstanding contracts measure different things.", ["expert.volume_oi"]))
    chat, cloud = service(local=local)
    result = answer(chat, engine="local", language="en")
    assert result["mode"] == "local-lora" and not cloud.calls and len(local.calls) == 1
    assert local.calls[0]["kwargs"] == {}
    unavailable = Provider(available=False)
    chat, cloud = service(local=unavailable)
    result = answer(chat, engine="local")
    assert result["mode"] == "offline" and result["warning"] == "local_model_unavailable"
    assert not cloud.calls and not unavailable.calls


def test_unavailable_local_json_is_disclosed_without_cloud_fallback():
    local = Provider("non-JSON local answer")
    chat, cloud = service(local=local)
    result = answer(chat, engine="local")
    assert result["mode"] == "offline" and result["warning"] == "options_answer_validation_failed"
    assert not cloud.calls


def test_only_same_analysis_recent_turns_are_forwarded_and_old_batch_is_a_boundary():
    history = [
        {"role": "user", "content": "OLD BATCH QUESTION"},
        {"role": "assistant", "content": "OLD BATCH ANSWER", "analysis_context": {"analysis_id": "old"}},
        {"role": "user", "content": "SAME BATCH QUESTION"},
        {"role": "assistant", "content": "SAME BATCH ANSWER", "analysis_context": {"analysis_id": "analysis-current"}},
    ]
    chat, cloud = service()
    answer(chat, "为什么？", history=history)
    messages = cloud.calls[0]["messages"]
    assert messages[1:3] == [{"role": "user", "content": "SAME BATCH QUESTION"}, {"role": "assistant", "content": "SAME BATCH ANSWER"}]
    assert "OLD BATCH" not in json.dumps(messages)
    history.append({"role": "assistant", "content": "Another batch", "analysis_context": {"analysis_id": "other"}})
    answer(chat, history=history)
    assert len(cloud.calls[-1]["messages"]) == 2


def test_history_has_a_bounded_context_window():
    history = []
    for index in range(8):
        history.extend([{"role": "user", "content": "QUESTION " + str(index)},
                        {"role": "assistant", "content": "ANSWER " + str(index), "analysis_context": {"analysis_id": "analysis-current"}}])
    chat, cloud = service()
    answer(chat, history=history)
    assert len(cloud.calls[0]["messages"]) == 10
    assert cloud.calls[0]["messages"][1]["content"] == "QUESTION 4"


def test_prompt_does_not_forward_raw_quotes_accounts_or_unknown_metrics():
    saved = report()
    saved["snapshot"]["quotes"] = [{"account": "PRIVATE ACCOUNT", "raw": "RAW QUOTE SENTINEL"}]
    saved["snapshot"]["underlying"]["price"] = "RAW SPOT SENTINEL"
    saved["collective"]["evidence"].append({"id": "spot_price", "value": 12345, "label": "PRIVATE SPOT"})
    saved["interpretation"] = {"text": "OLD MODEL SENTINEL"}
    chat, cloud = service()
    answer(chat, analysis=saved)
    payload = json.dumps(cloud.calls[0]["messages"])
    assert all(value not in payload for value in ("PRIVATE ACCOUNT", "RAW QUOTE SENTINEL", "RAW SPOT SENTINEL", "PRIVATE SPOT", "OLD MODEL SENTINEL"))


def test_batch_comparison_evidence_resolves_to_correct_scope_and_values():
    first, second = report(), report(symbol="OTHER")
    batch = {"analysis_id": "batch-current", "reports": [first, second], "failures": [],
             "comparison": build_batch_comparison([first, second]), "completed_at": NOW.isoformat()}
    reference = "comparison.report_2_put_volume_share"
    chat, _ = service(reply("The second scope contains a larger put activity share than call activity share.", [reference], "observation"))
    result = answer(chat, "Explain this scope.", batch, language="en")
    card = result["analysis_context"]["evidence"][0]
    assert card["scope"] == "comparison" and card["scope_ids"] == ["g1"]
    assert card["symbol"] == "OTHER" and card["value"] == pytest.approx(.6)


def test_credentials_are_not_forwarded_and_no_evidence_is_forced():
    chat, cloud = service()
    result = answer(chat, "Please use sk-" + "z" * 30)
    assert result["warning"] == "sensitive_credential" and result["mode"] == "offline"
    assert not cloud.calls and result["analysis_context"]["evidence"] == []


def test_model_latency_reassesses_freshness_without_recomputing_evidence(monkeypatch):
    import app.options_chat as module
    real_describe = module.describe_analysis
    clocks = iter([NOW, NOW + timedelta(seconds=45)])

    def describe(saved, language="zh", now=None):
        return real_describe(saved, language, now=next(clocks))

    monkeypatch.setattr(module, "describe_analysis", describe)
    chat, _ = service(reply("The sample has a larger put activity share than call activity share.", ["g0.volume_put_share"], "observation"))
    result = answer(chat, language="en")
    assert result["analysis_context"]["stale"]
    assert result["analysis_context"]["snapshot_age_seconds"] == 47
    assert "stale" in result["answer"]
    assert result["analysis_context"]["evidence"][0]["value"] == pytest.approx(.6)


def refreshed(monkeypatch, *, feed_changed=False):
    import app.options_changes as module
    from test_options_changes import capture
    monkeypatch.setattr(module, "_clock", lambda: NOW + timedelta(hours=1))
    previous = capture()

    def changed(data):
        for row in data["quotes"]:
            if row["strike"] == 95:
                row["volume"] = 0 if row["right"] == "C" else 40

    current = capture(10, mode=3 if feed_changed else 1, mutate=changed)
    current["analysis_id"] = "analysis-refreshed"
    current["previous_analysis_id"] = previous["analysis_id"]
    current["refresh_comparison"] = module.build_refresh_comparison(previous, current)
    return previous, current


def test_refresh_metadata_and_change_evidence_preserve_local_before_after_and_delta(monkeypatch):
    previous, current = refreshed(monkeypatch)
    original = deepcopy(current)
    reference = "change.s0.volume_put_share"
    chat, cloud = service(reply("相同配对范围的看跌成交占比较上次增大，但这不能代表市场方向。", [reference], "observation"))
    result = answer(chat, "刷新后相比上次有什么变化？", current)
    assert result["mode"] == "deepseek" and "warning" not in result
    context = result["analysis_context"]
    assert context["previous_analysis_id"] == previous["analysis_id"]
    assert context["refresh_comparison"] == current["refresh_comparison"]
    card = context["evidence"][0]
    assert card["id"] == reference and card["before"] == pytest.approx(.6)
    assert card["after"] == card["value"] == pytest.approx(.7)
    assert card["delta"] == pytest.approx(10) and card["delta_unit"] == "percentage_points"
    assert card["status"] == "comparable"
    assert card["previous_received_at"] == previous["snapshot"]["received_at"]
    assert card["received_at"] == current["snapshot"]["received_at"]
    assert "显式重新采集" in result["answer"]
    payload = json.loads(cloud.calls[0]["messages"][-1]["content"])
    assert payload["saved_snapshot"]["refresh_comparison"] == current["refresh_comparison"]
    assert current == original
    context["refresh_comparison"]["summary"] = "Changed copy"
    assert current == original


@pytest.mark.parametrize("output", [
    reply("The share rose by 10 percentage points.", ["change.s0.volume_put_share"], "observation"),
    reply("The share rose.", ["change.s9.made_up"], "observation"),
    reply("Quote coverage increased, which means the market is bullish.", ["change.s0.quote_coverage"], "observation"),
    reply("Open interest increased, which means fund inflow.", ["change.s0.oi_total"], "observation"),
])
def test_refresh_cannot_accept_model_figures_unknown_ids_or_market_direction_from_coverage(monkeypatch, output):
    _, current = refreshed(monkeypatch)
    chat, _ = service(output)
    result = answer(chat, "前后变化是什么？", current)
    assert result["mode"] == "offline" and result["warning"] == "options_answer_validation_failed"
    assert "change.s9" not in result["answer"]
    assert any(card["id"].startswith("change.") for card in result["analysis_context"]["evidence"])


def test_incomparable_change_claim_is_rejected_and_offline_explains_feed_change(monkeypatch):
    _, current = refreshed(monkeypatch, feed_changed=True)
    chat, _ = service(reply("The put share increased.", ["change.s0.volume_put_share"], "observation"))
    result = answer(chat, "刷新后成交占比变化是什么？", current, language="en")
    assert result["mode"] == "offline"
    card = result["analysis_context"]["evidence"][0]
    assert card["status"] == "incomparable" and card["delta"] is None
    assert card["before"] is not None and card["after"] is not None
    assert card["reason"] == "feed_changed"
    assert "no reliable delta" in result["answer"]


def test_local_unavailable_still_explains_locally_computed_refresh_changes_without_cloud(monkeypatch):
    _, current = refreshed(monkeypatch)
    chat, cloud = service(local=Provider(available=False))
    result = answer(chat, "与上次相比成交有什么变化？", current, engine="local")
    assert result["mode"] == "offline" and result["warning"] == "local_model_unavailable"
    assert not cloud.calls and "累计成交差不等于精确时间间隔内的新增成交" in result["answer"]
    assert result["analysis_context"]["evidence"]


def test_subsequent_refreshed_followup_keeps_comparison_but_drops_previous_batch_history(monkeypatch):
    previous, current = refreshed(monkeypatch)
    chat, cloud = service(reply("看跌成交不能解释成看空人数；这些计数不是多数人的观点。", ["expert.put_call"]))
    old_history = [{"role": "user", "content": "OLD SCOPE"},
                   {"role": "assistant", "content": "OLD ANSWER", "analysis_context": {"analysis_id": previous["analysis_id"]}}]
    first = answer(chat, "前后变化说明什么？", current, old_history)
    assert "OLD SCOPE" not in json.dumps(cloud.calls[0]["messages"])
    history = old_history + [{"role": "user", "content": "前后变化说明什么？"},
                             {"role": "assistant", "content": first["answer"], "analysis_context": first["analysis_context"]}]
    result = answer(chat, "为什么不能说明多数人看空？", current, history)
    assert result["mode"] == "deepseek"
    assert len(cloud.calls[-1]["messages"]) == 4
    payload = json.loads(cloud.calls[-1]["messages"][-1]["content"])
    assert "refresh_comparison" not in payload["saved_snapshot"]
    assert not any(item["id"].startswith("change.") for item in payload["evidence"])
    assert result["analysis_context"]["refresh_comparison"] == current["refresh_comparison"]


@pytest.mark.parametrize("text", ["The put share decreased.", "The put share remained equal."])
def test_single_change_observation_cannot_reverse_local_direction(monkeypatch, text):
    _, current = refreshed(monkeypatch)
    chat, _ = service(reply(text, ["change.s0.volume_put_share"], "observation"))
    result = answer(chat, "前后成交占比变化是什么？", current)
    assert result["mode"] == "offline" and result["warning"] == "options_answer_validation_failed"
    card = next(card for card in result["analysis_context"]["evidence"] if card["id"] == "change.s0.volume_put_share")
    assert card["delta"] == 10 and card["direction"] == "increased"


def test_single_change_observation_uses_local_direction_when_valid(monkeypatch):
    _, current = refreshed(monkeypatch)
    chat, cloud = service(reply("The put share increased.", ["change.s0.volume_put_share"], "observation"))
    result = answer(chat, "Explain the change.", current, language="en")
    assert result["mode"] == "deepseek"
    assert result["analysis_context"]["evidence"][0]["direction"] == "increased"
    data = json.loads(cloud.calls[0]["messages"][-1]["content"])
    assert next(card for card in data["evidence"] if card["id"] == "change.s0.volume_put_share")["direction"] == "increased"


class SequenceProvider(Provider):
    def __init__(self, outputs):
        super().__init__()
        self.outputs = iter(outputs)

    async def complete(self, messages, **kwargs):
        self.calls.append({"messages": deepcopy(messages), "kwargs": kwargs})
        output = next(self.outputs)
        if isinstance(output, Exception):
            raise output
        return output


def test_schema_repair_merges_real_failure_shape_and_keeps_same_saved_evidence():
    reference = "g0.oi_put_share"
    original = json.dumps({"response": [
        {"kind": "explanation", "text": "这是保存的样本。", "evidence_ids": []}
        for _ in range(6)] + [{"kind": "observation", "text": "看跌占比接近一半。", "evidence_ids": [reference]}]}, ensure_ascii=False)
    corrected = reply("样本的未平仓构成可从对应证据卡核对，合约构成不代表参与者方向。", [reference], "observation")
    provider = SequenceProvider([original, corrected])
    chat = OptionsChat(Settings(api_key="test-only", offline=False), provider)
    result = answer(chat)
    assert result["mode"] == "deepseek" and "warning" not in result
    assert result["generation_attempts"] == 2 and result["schema_repair_attempts"] == 1
    assert len(provider.calls) == 2
    first = json.loads(provider.calls[0]["messages"][-1]["content"])
    second = json.loads(provider.calls[1]["messages"][-1]["content"])
    assert second["saved_snapshot"] == first["saved_snapshot"]
    assert second["evidence"] == first["evidence"]
    assert second["question"] == first["question"]
    assert second["schema_repair"]["allowed_evidence_ids"] == [reference]
    assert "at most 6" in second["schema_repair"]["validation_error"]
    assert provider.calls[1]["messages"][-2] == {"role": "assistant", "content": original}
    assert "Do not add a new claim" in provider.calls[1]["messages"][0]["content"]
    assert result["analysis_context"]["evidence_ids"] == [reference]


def test_both_invalid_generations_fall_back_after_exactly_one_schema_repair():
    invalid = reply("The share is 60 percent.", ["g0.volume_put_share"], "observation")
    provider = SequenceProvider([invalid, invalid])
    chat = OptionsChat(Settings(api_key="test-only", offline=False), provider)
    result = answer(chat)
    assert result["mode"] == "offline" and result["warning"] == "options_answer_validation_failed"
    assert result["generation_attempts"] == len(provider.calls) == 2
    assert result["schema_repair_attempts"] == 1


def test_provider_failure_never_triggers_schema_repair_or_network_retry():
    provider = SequenceProvider([ProviderError("network_or_timeout")])
    chat = OptionsChat(Settings(api_key="test-only", offline=False), provider)
    result = answer(chat)
    assert result["generation_attempts"] == len(provider.calls) == 1
    assert result["schema_repair_attempts"] == 0
    assert result["mode"] == "offline" and result["warning"] == "network_or_timeout"


def test_provider_failure_during_repair_stops_without_another_request():
    provider = SequenceProvider([reply("The share is 60 percent.", ["g0.volume_put_share"], "observation"),
                                 ProviderError("rate_limited")])
    chat = OptionsChat(Settings(api_key="test-only", offline=False), provider)
    result = answer(chat)
    assert result["generation_attempts"] == len(provider.calls) == 2
    assert result["schema_repair_attempts"] == 1 and result["warning"] == "rate_limited"
    assert result["mode"] == "offline"


def test_repair_cannot_introduce_new_evidence_claim_even_if_the_id_is_in_the_snapshot():
    invalid = reply("The share is 60 percent.", ["g0.volume_put_share"], "observation")
    replacement = reply("Open interest has a supported sample structure.", ["g0.oi_total"], "observation")
    provider = SequenceProvider([invalid, replacement])
    chat = OptionsChat(Settings(api_key="test-only", offline=False), provider)
    result = answer(chat)
    assert result["mode"] == "offline" and result["warning"] == "options_answer_validation_failed"
    assert len(provider.calls) == 2


def test_selected_local_engine_repairs_locally_without_cloud_switch():
    invalid = reply("The share is 60 percent.", ["g0.volume_put_share"], "observation")
    local = SequenceProvider([invalid, reply("The sample is weighted toward puts.", ["g0.volume_put_share"], "observation")])
    chat, cloud = service(local=local)
    result = answer(chat, engine="local", language="en")
    assert result["mode"] == "local-lora" and result["generation_attempts"] == 2
    assert not cloud.calls and len(local.calls) == 2
    assert all(call["kwargs"] == {} for call in local.calls)


@pytest.mark.parametrize("first_invalid", [False, True])
def test_answer_deadline_bounds_initial_generation_and_schema_repair(monkeypatch, first_invalid):
    import app.options_chat as module
    monkeypatch.setattr(module, "ANSWER_DEADLINE_SECONDS", .01)

    class SlowProvider(Provider):
        async def complete(self, messages, **kwargs):
            self.calls.append({"messages": messages})
            if first_invalid and len(self.calls) == 1:
                return reply("The share is 60 percent.", ["g0.volume_put_share"], "observation")
            await asyncio.sleep(1)
            return reply("A late answer.")

    provider = SlowProvider()
    chat = OptionsChat(Settings(api_key="test-only", offline=False), provider)
    result = answer(chat)
    assert result["mode"] == "offline" and result["warning"] == "network_or_timeout"
    assert result["generation_attempts"] == len(provider.calls) == (2 if first_invalid else 1)
    assert result["schema_repair_attempts"] == (1 if first_invalid else 0)


def test_prompt_does_not_conclude_market_closed_or_all_entitlements_denied_from_missing_bbo():
    chat, cloud = service()
    answer(chat)
    instructions = cloud.calls[0]["messages"][0]["content"]
    assert "Default to\nTWO TO FOUR" in instructions
    assert "do not write 一半" in instructions
    assert "Missing BBOs do not uniquely establish a closed market" in instructions
    assert "Partial subscription notices" in instructions


def test_validation_diagnostics_are_disabled_by_default(monkeypatch, tmp_path):
    import app.options_chat as module
    monkeypatch.delenv("FINPILOT_OPTIONS_MODEL_DIAGNOSTICS", raising=False)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    chat, _ = service("invalid JSON")
    result = answer(chat)
    assert result["warning"] == "options_answer_validation_failed"
    assert not list(tmp_path.rglob("options-validation-v12-*.json"))


def test_opt_in_diagnostics_record_only_failed_model_output_with_credentials_and_accounts_redacted(monkeypatch, tmp_path):
    import app.options_chat as module
    monkeypatch.setenv("FINPILOT_OPTIONS_MODEL_DIAGNOSTICS", "1")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    configured_secret = "configured-server-secret"
    output = json.dumps({"response": [{"kind": "observation", "text": "A model output.",
                                      "evidence_ids": [], "secret": configured_secret + " sk-" + "z" * 24 + " DU1234567 Bearer fake-token"}]})
    provider = SequenceProvider([output, reply("A qualitative conceptual explanation.")])
    chat = OptionsChat(Settings(api_key=configured_secret, offline=False), provider)
    result = answer(chat, "USER_PROMPT_MUST_NOT_BE_LOGGED")
    assert result["mode"] == "deepseek" and result["generation_attempts"] == 2
    files = list((tmp_path / "tmp").glob("options-validation-v12-*.json"))
    assert len(files) == 1
    raw = files[0].read_text(encoding="utf-8")
    trace = json.loads(raw)
    assert set(trace) == {"recorded_at", "attempt", "analysis_id", "validation_error", "model_output"}
    assert trace["attempt"] == 1 and trace["analysis_id"] == "analysis-current"
    assert "Extra inputs are not permitted" in trace["validation_error"]
    assert "input_value" not in trace["validation_error"]
    for private in (configured_secret, "sk-" + "z" * 24, "DU1234567", "fake-token", "USER_PROMPT_MUST_NOT_BE_LOGGED"):
        assert private not in raw
    assert "[credential-redacted]" in trace["model_output"] and "[account-redacted]" in trace["model_output"]


def test_diagnostics_use_distinct_files_for_both_failed_attempts(monkeypatch, tmp_path):
    import app.options_chat as module
    monkeypatch.setenv("FINPILOT_OPTIONS_MODEL_DIAGNOSTICS", "1")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    chat, _ = service("invalid JSON")
    result = answer(chat)
    assert result["mode"] == "offline"
    files = list((tmp_path / "tmp").glob("options-validation-v12-*.json"))
    assert len(files) == 2 and len({file.name for file in files}) == 2
    assert sorted(json.loads(file.read_text(encoding="utf-8"))["attempt"] for file in files) == [1, 2]


@pytest.mark.parametrize("provider_error", [False, True])
def test_successful_generation_and_provider_failures_do_not_write_validation_diagnostics(monkeypatch, tmp_path, provider_error):
    import app.options_chat as module
    monkeypatch.setenv("FINPILOT_OPTIONS_MODEL_DIAGNOSTICS", "1")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    chat, _ = service(error="network_or_timeout" if provider_error else None)
    answer(chat)
    assert not list(tmp_path.rglob("options-validation-v12-*.json"))


def test_unwritable_diagnostic_location_does_not_change_fallback(monkeypatch, tmp_path):
    import app.options_chat as module
    monkeypatch.setenv("FINPILOT_OPTIONS_MODEL_DIAGNOSTICS", "1")
    blocked = tmp_path / "file-instead-of-folder"
    blocked.write_text("existing", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", blocked)
    chat, _ = service("invalid JSON")
    result = answer(chat)
    assert result["mode"] == "offline" and result["generation_attempts"] == 2
    assert blocked.read_text(encoding="utf-8") == "existing"


@pytest.mark.parametrize("text", [
    "前后差异主要反映采集时点不同。",
    "差别主要来自覆盖范围改变，所以市场没有变化。",
    "The differences mainly reflect capture timing.",
    "The difference is primarily caused by sampling times.",
])
def test_unsupported_primary_causal_attribution_is_rejected_without_weakening_evidence_rules(text):
    chat, _ = service(reply(text))
    result = answer(chat)
    assert result["mode"] == "offline" and result["warning"] == "options_answer_validation_failed"


@pytest.mark.parametrize("text", [
    "不能说前后差异主要反映采集时点不同；实际配对范围改变时，差值不可比。",
    "We cannot say the differences mainly reflect capture timing; the paired sample changed.",
    "采集时点不同可能是尚未核验的解释，不能把它当成主要原因。",
])
def test_negated_or_explicitly_unverified_timing_alternative_is_allowed(text):
    chat, cloud = service(reply(text))
    result = answer(chat)
    assert result["mode"] == "deepseek" and len(cloud.calls) == 1
    assert "warning" not in result


@pytest.mark.parametrize("text", [
    "看跌成交量增加并不意味着市场看空。",
    "看跌成交量增加未必说明市场看空。",
    "看跌成交量增加不表明市场看空。",
    "看跌成交量增加不证明市场看空。",
    "看跌成交量增加并不直接意味着市场看空。",
    "看跌成交量增加不足以证明市场看空。",
    "Put volume does not mean the market is bearish.",
])
def test_explicit_relation_negation_is_not_an_unsupported_positive_conclusion(text):
    from app.options_chat import _unsafe_claim
    assert not _unsafe_claim(text)
    chat, cloud = service(reply(text, ["expert.put_call"]))
    result = answer(chat, "Why doesn't put volume establish bearish headcount?")
    assert result["mode"] == "deepseek" and len(cloud.calls) == 1


@pytest.mark.parametrize("text", [
    "看跌成交量增加意味着市场看空。",
    "不但看跌成交量增加意味着市场看空，而且这是确定的。",
    "看跌成交量不但增加，还意味着市场看空。",
    "看跌成交量不仅增加，更证明市场看空。",
    "看跌成交量增加并非不能说明市场看空。",
    "不能忽略这些数据。看跌成交量增加意味着市场看空。",
    "Put volume means the market is bearish.",
    "Not only does put volume increase, it means the market is bearish.",
    "Put volume does not only mean the market is bearish.",
])
def test_positive_inference_cannot_bypass_validation_with_affirmative_negation_words(text):
    from app.options_chat import _unsafe_claim
    assert _unsafe_claim(text)


@pytest.mark.parametrize("text,ids,question", [
    ("这不是保证收益。", [], "这份报告保证收益吗？"),
    ("这不构成保证收益。", [], "这份报告保证收益吗？"),
    ("这不构成任何保证收益。", [], "这份报告保证收益吗？"),
    ("We cannot say that put volume means the market is bearish.", ["expert.put_call"], "What does put volume establish?"),
    ("Put volume cannot prove the market is bearish.", ["expert.put_call"], "What does put volume establish?"),
    ("I do not claim that put volume means the market is bearish.", ["expert.put_call"], "What does put volume establish?"),
])
def test_explicit_guarantee_or_inference_denial_is_allowed(text, ids, question):
    from app.options_chat import _unsafe_claim
    assert not _unsafe_claim(text)
    chat, cloud = service(reply(text, ids))
    result = answer(chat, question)
    assert result["mode"] == "deepseek" and len(cloud.calls) == 1


@pytest.mark.parametrize("text", [
    "这保证收益。",
    "这不但保证收益，而且必涨。",
    "这不是不构成保证收益。",
    "I cannot ignore that put volume means the market is bearish.",
    "I can't ignore that put volume means the market is bearish.",
    "I do not ignore that put volume means the market is bearish.",
    "We cannot overlook that put volume means the market is bearish.",
])
def test_unrelated_negated_verb_does_not_exempt_a_positive_market_inference(text):
    from app.options_chat import _unsafe_claim
    assert _unsafe_claim(text)
