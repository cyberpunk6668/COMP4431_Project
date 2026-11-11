"""Historical facts stay local; expert citations do not verify imported data."""
import asyncio
from copy import deepcopy
import json

import pytest

from app.config import Settings
from app.history_chat import HistoryChat, describe_history, _evidence, _validate
from app.llm import ProviderError


def record():
    return {"analysis_kind": "historical_options", "analysis_id": "hist-current", "label": "Imported review",
            "symbol": "TEST", "expiry": "2026-11-20", "currency": "USD", "ingested_at": "2026-11-11T01:00:00+00:00",
            "source": {"kind": "import", "label": "User CSV", "verified": False},
            "period": {"start": "2026-11-06", "end": "2026-11-10"}, "daily": [], "changes": [],
            "contract_changes": [], "limitations": ["所选样本；未核验导入来源。"], "brief": [],
            "evidence": [
                {"id": "h.change.volume_total", "label": "共同样本成交", "value": 140, "unit": "contracts", "before": 100, "after": 140,
                 "delta": 40, "delta_unit": "contracts", "status": "comparable", "reason": None, "direction": "increased"},
                {"id": "h.change.put_volume_share", "label": "看跌成交占比", "value": .7, "unit": "fraction", "before": .6, "after": .7,
                 "delta": 10, "delta_unit": "percentage_points", "status": "comparable", "reason": None, "direction": "increased"},
                {"id": "h.day.oi_total", "label": "持仓缺失", "value": None, "unit": "contracts", "trading_date": "2026-11-10"},
                {"id": "h.day.zero_volume", "label": "实际零成交", "value": 0, "unit": "contracts", "trading_date": "2026-11-10"},
            ]}


def reply(text="共同样本内的成交统计增加，但不能据此判断市场方向。", ids=("h.change.volume_total",), kind="observation"):
    return json.dumps({"response": [{"kind": kind, "text": text, "evidence_ids": list(ids)}]}, ensure_ascii=False)


class Provider:
    def __init__(self, outputs=None, error=None, available=True):
        self.outputs = outputs or [reply()]
        self.error, self.available, self.calls = error, available, []

    def status(self):
        return {"available": self.available}

    async def complete(self, messages, **kwargs):
        self.calls.append({"messages": deepcopy(messages), "kwargs": kwargs})
        if self.error:
            raise ProviderError(self.error)
        return self.outputs[min(len(self.calls)-1, len(self.outputs)-1)]


def service(outputs=None, *, online=True, error=None, local=None):
    cloud = Provider(outputs, error)
    return HistoryChat(Settings(api_key="test-only" if online else "", offline=not online), cloud, local), cloud


def answer(chat, message="为什么共同样本成交量变化？", analysis=None, history=None, language="zh", engine="deepseek"):
    return asyncio.run(chat.answer(message, history or [], language, engine, analysis or record()))


@pytest.mark.parametrize("kind,verified,label", [("import", False, "未经独立核验"), ("demo", True, "合成"), ("ibkr_historical", True, "本地网关返回")])
def test_metadata_is_historical_not_live_staleness(kind, verified, label):
    saved = record()
    saved["source"].update(kind=kind, verified=verified)
    saved["ingested_at"] = "2000-01-01T00:00:00Z"
    original = deepcopy(saved)
    meta = describe_history(saved)
    assert meta["analysis_kind"] == "historical_options" and meta["historical_data"] is True
    assert meta["stale"] is False and meta["snapshot_age_seconds"] is None and meta["realtime_guaranteed"] is False
    assert meta["period"] == saved["period"] and meta["captured_at"] == "2000-01-01T00:00:00+00:00"
    assert meta["scopes"][0]["market_data_status"] == "historical" and meta["scopes"][0]["time_status"] == "known"
    assert label in meta["source_label"] and label in meta["notice"]
    assert not meta["source_verified"] if kind == "demo" else meta["source_verified"] is verified
    assert saved == original


def test_gateway_verification_scope_is_not_exchange_or_complete_session_validation():
    saved = record()
    saved["source"].update(kind="ibkr_historical", verified=True,
                           verification_scope="Returned by Gateway; not independently exchange-verified")
    result = describe_history(saved)
    assert result["verification_scope"] == saved["source"]["verification_scope"]
    assert "未经独立交易所校准" in result["notice"] and "时段完整性未核验" in result["notice"]
    assert "来源标记已核验" not in result["source_label"]


@pytest.mark.parametrize("stamp", [None, "bad", "2026-11-11T00:00:00"])
def test_missing_timestamp_does_not_invent_time_or_call_history_stale(stamp):
    saved = record()
    saved["ingested_at"] = stamp
    meta = describe_history(saved, "en")
    assert meta["captured_at"] is None and meta["scopes"][0]["time_status"] == "missing"
    assert meta["stale"] is False and "not current" in meta["notice"]


def test_local_figures_preserved_and_experts_separate_from_numeric_cards():
    text = reply("共同样本内的成交统计增加；成交量描述交易期间的合约活动。", ("h.change.volume_total", "expert.volume_oi"))
    chat, provider = service([text])
    saved = record()
    original = deepcopy(saved)
    result = answer(chat, analysis=saved)
    assert result["mode"] == "deepseek" and "warning" not in result and len(provider.calls) == 1
    assert result["generation_attempts"] == 1 and result["schema_repair_attempts"] == 0
    context = result["analysis_context"]
    assert context["evidence_ids"] == ["h.change.volume_total"] and context["expert_source_ids"] == ["expert.volume_oi"]
    card = context["evidence"][0]
    assert (card["before"], card["after"], card["delta"]) == (100, 140, 40)
    assert card["market_data_status"] == "historical" and card["scope"] == "history"
    assert result["sources"][0]["publisher"].startswith("OCC") and result["sources"][0]["snippet"]
    assert context["retrieval"]["method"] == "bm25_char_ngram_rrf" and context["retrieval"]["hits"]
    assert "100" not in result["answer"] and "140" not in result["answer"]
    assert saved == original
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("invalid", [
    reply("共同样本增加了百分之十。"),
    reply("共同样本成交量增加40份。"),
    reply(ids=("h.unknown",)),
    reply(ids=("expert.unknown",)),
    reply("成交量反映活动。", ("expert.volume_oi",)),
    reply("共同样本成交量下降。"),
    reply("当前市场已经转向。"),
    reply("看跌成交量增加意味着市场看空。"),
    reply("建议你立即买入。"),
])
def test_invalid_model_prose_or_reference_falls_back_after_at_most_one_repair(invalid):
    chat, provider = service([invalid, invalid])
    result = answer(chat)
    assert result["mode"] == "offline" and result["warning"] == "options_answer_validation_failed"
    assert len(provider.calls) == 2 and result["generation_attempts"] == 2 and result["schema_repair_attempts"] == 1
    assert result["analysis_context"]["historical_data"] is True
    assert all(source["id"].startswith("expert.") for source in result["sources"])


def test_single_schema_repair_retains_identical_saved_evidence_and_sources():
    chat, provider = service([reply("成交增加40份。"), reply()])
    result = answer(chat)
    assert result["mode"] == "deepseek" and len(provider.calls) == 2
    initial = json.loads(provider.calls[0]["messages"][-1]["content"])
    repaired = provider.calls[1]["messages"]
    retained_payload = json.loads(next(item["content"] for item in repaired if item["role"] == "user"))
    assert initial == retained_payload
    assert json.loads(repaired[-1]["content"])["schema_repair"]["allowed_evidence_ids"] == ["h.change.volume_total"]


def test_repair_cannot_add_an_originally_uncited_but_known_claim():
    chat, provider = service([reply("成交增加40份。"), reply(ids=("h.change.put_volume_share",))])
    result = answer(chat)
    assert result["mode"] == "offline" and len(provider.calls) == 2


def test_provider_failure_never_triggers_network_retry():
    chat, provider = service(error="rate_limited")
    result = answer(chat)
    assert result["warning"] == "rate_limited" and result["mode"] == "offline"
    assert len(provider.calls) == 1 and result["schema_repair_attempts"] == 0


def test_total_deadline_is_bounded(monkeypatch):
    chat, provider = service()
    async def slow(messages, **kwargs):
        provider.calls.append({"messages": messages})
        await asyncio.sleep(1)
        return reply()
    provider.complete = slow
    monkeypatch.setattr("app.history_chat.ANSWER_DEADLINE_SECONDS", .005)
    result = answer(chat)
    assert result["warning"] == "network_or_timeout" and len(provider.calls) == 1


def test_local_selection_never_falls_through_to_cloud():
    chat, cloud = service(local=Provider(available=False))
    result = answer(chat, engine="local")
    assert result["mode"] == "offline" and result["warning"] == "local_model_unavailable" and not cloud.calls
    local = Provider([reply()])
    chat, cloud = service(local=local)
    result = answer(chat, engine="local")
    assert result["mode"] == "local-lora" and len(local.calls) == 1 and not cloud.calls
    assert not local.calls[0]["kwargs"]


def test_cloud_unconfigured_has_readable_expert_fallback_not_success():
    chat, cloud = service(online=False)
    result = answer(chat, "看跌成交量变化能说明多数人看空吗？")
    assert result["mode"] == "offline" and result["warning"] == "cloud_unconfigured" and not cloud.calls
    assert "多数人" in result["answer"] or "参与人数" in result["answer"]
    assert "expert.put_call" in [source["id"] for source in result["sources"]]


def test_current_credential_rejected_and_unrelated_private_record_fields_never_sent():
    chat, provider = service()
    result = answer(chat, "sk-" + "a"*30)
    assert result["warning"] == "sensitive_credential" and not provider.calls
    saved = record()
    saved["account_number"] = "PRIVATE-ACCOUNT"
    saved["private_quotes"] = {"sensitive": "DO-NOT-SEND"}
    answer(chat, analysis=saved)
    serialized = json.dumps(provider.calls)
    assert "PRIVATE-ACCOUNT" not in serialized and "DO-NOT-SEND" not in serialized


def test_history_is_scoped_to_current_immutable_record():
    chat, provider = service()
    history = [
        {"role": "user", "content": "OLD-QUESTION"},
        {"role": "assistant", "content": "OLD-ANSWER", "analysis_context": {"analysis_id": "old"}},
        {"role": "user", "content": "CURRENT-QUESTION"},
        {"role": "assistant", "content": "CURRENT-ANSWER", "analysis_context": {"analysis_id": "hist-current"}},
    ]
    answer(chat, history=history)
    messages = json.dumps(provider.calls[0]["messages"])
    assert "CURRENT-QUESTION" in messages and "OLD-QUESTION" not in messages and "OLD-ANSWER" not in messages


def test_short_followup_retrieval_retains_same_history_topic():
    chat, provider = service([reply("未平仓量有独立报告周期。成交量统计期间交易，未平仓量统计尚未结清合约，不能直接换算。", ("expert.oi_cycle", "expert.volume_oi"), "explanation")])
    history = [{"role": "user", "content": "未平仓持仓日期为什么和成交不同？"},
               {"role": "assistant", "content": "看报告日期。", "analysis_context": {"analysis_id": "hist-current"}}]
    result = answer(chat, "为什么？", history=history)
    assert result["mode"] == "deepseek" and result["sources"][0]["id"] == "expert.oi_cycle"


def test_null_is_not_zero_and_incomparable_delta_is_never_fabricated():
    saved = record()
    local = _evidence(saved)
    assert local["h.day.zero_volume"]["value"] == 0 and local["h.day.oi_total"]["value"] is None
    _validate(reply("样本有记录，具体数值请查看证据。", ("h.day.zero_volume",)), local, {})
    with pytest.raises(ValueError, match="Missing"):
        _validate(reply("样本持仓有明显活动。", ("h.day.oi_total",)), local, {})
    saved["evidence"][0].update(status="incomparable", reason="sample_changed")
    local = _evidence(saved)
    assert local["h.change.volume_total"]["delta"] is None
    with pytest.raises(ValueError, match="Incomparable"):
        _validate(reply("样本成交量增加。"), local, {})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_invalid_numbers_not_sent_or_returned(value):
    saved = record()
    saved["evidence"][0]["value"] = value
    assert _evidence(saved)["h.change.volume_total"]["value"] is None


def test_duplicate_local_ids_are_unusable_not_arbitrarily_selected():
    saved = record()
    saved["evidence"].append(deepcopy(saved["evidence"][0]))
    assert "h.change.volume_total" not in _evidence(saved)


def test_incomparable_offline_review_preserves_before_after_and_explains_limit():
    saved = record()
    for item in saved["evidence"][:2]:
        item.update(status="incomparable", delta=None, direction="unavailable", reason="sample_changed")
    chat, _ = service(online=False)
    result = answer(chat, analysis=saved)
    card = result["analysis_context"]["evidence"][0]
    assert card["before"] is not None and card["after"] is not None and card["delta"] is None
    assert "不可比" in result["answer"] and "增加" not in result["answer"].split("[h.change")[0]


def test_english_offline_explanation_uses_expert_provenance():
    chat, _ = service(online=False)
    result = answer(chat, "What is implied volatility?", language="en")
    assert "Historical review period" in result["answer"]
    assert result["sources"] and all(source["publisher"] for source in result["sources"])


@pytest.mark.parametrize("direction,text", [("increase", "共同样本成交量增加。"), ("decrease", "共同样本成交量减少。")])
def test_historical_server_direction_enum_preserved(direction, text):
    saved = record()
    item = saved["evidence"][0]
    item.update(direction=direction, delta=40 if direction == "increase" else -40)
    chat, _ = service([reply(text)])
    result = answer(chat, analysis=saved)
    assert result["mode"] == "deepseek"
    assert result["analysis_context"]["evidence"][0]["direction"] == direction
    offline, _ = service(online=False)
    assert answer(offline, analysis=saved)["mode"] == "offline"


def test_actual_server_demo_record_runs_without_schema_adaptation():
    from app.options_history import HistoryDataset, analyze_history, demo_dataset
    saved = analyze_history(HistoryDataset.model_validate(demo_dataset()), source_kind="demo")
    saved["analysis_id"] = "real-server-demo"
    original = deepcopy(saved)
    chat, _ = service(online=False)
    result = answer(chat, "这几天共同样本的成交量变化说明什么？", analysis=saved)
    assert result["analysis_context"]["analysis_id"] == "real-server-demo"
    assert result["analysis_context"]["source"] == "demo" and "合成" in result["analysis_context"]["source_label"]
    assert result["analysis_context"]["evidence"]
    assert all(item["id"].startswith("h.") for item in result["analysis_context"]["evidence"])
    assert saved == original


@pytest.mark.parametrize("text", [
    "样本成交量增加。",
    "这些资料不能用于预测，但样本成交量增加。",
    "这些资料不代表当前市场，但样本成交量增加。",
    "不能断言市场方向。样本成交量增加。",
    "Sample volume increased.",
    "These data cannot predict prices, but sample volume increased.",
    "These data do not show current sentiment; sample volume increased.",
    "We cannot ignore that sample volume increased.",
    "样本成交量没有增加。",
    "Sample volume did not increase.",
])
def test_unrelated_disclaimer_does_not_authorize_incomparable_direction(text):
    saved = record()
    saved["evidence"][0].update(status="incomparable", delta=None, direction="unavailable")
    with pytest.raises(ValueError, match="Incomparable"):
        _validate(reply(text), _evidence(saved), {})


@pytest.mark.parametrize("text", [
    "无法确认样本成交量增加。",
    "不能据此判断样本成交量上升。",
    "没有充分证据认定样本成交量增加。",
    "样本成交量是否增加无法确认。",
    "We cannot establish whether sample volume increased.",
    "These data do not prove that sample volume increased.",
    "There is insufficient evidence that sample volume increased.",
    "An increase cannot be established.",
])
def test_direction_itself_is_explicitly_not_established(text):
    saved = record()
    saved["evidence"][0].update(status="incomparable", delta=None, direction="unavailable")
    assert _validate(reply(text, kind="limitation"), _evidence(saved), {})


def test_comparable_opposite_direction_not_hidden_by_prediction_disclaimer():
    with pytest.raises(ValueError, match="reverses"):
        _validate(reply("这些资料不能用于预测，但共同样本成交量下降。"), _evidence(record()), {})


def test_history_diagnostics_default_off_and_opt_in_redacted(tmp_path, monkeypatch):
    monkeypatch.setattr("app.options_chat.ROOT", tmp_path)
    monkeypatch.delenv("FINPILOT_OPTIONS_MODEL_DIAGNOSTICS", raising=False)
    chat, _ = service([reply("成交增加40份。"), reply("成交增加40份。")])
    answer(chat)
    assert not list(tmp_path.rglob("*.json"))
    monkeypatch.setenv("FINPILOT_OPTIONS_MODEL_DIAGNOSTICS", "1")
    secret = "sk-" + "s"*30
    chat, _ = service([reply("成交增加40份。" + secret + " U1234567"), reply("成交增加40份。")])
    answer(chat)
    paths = list((tmp_path / "tmp").glob("options-validation-v12-*.json"))
    assert len(paths) == 2
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    assert {item["attempt"] for item in reports} == {1, 2}
    assert all(set(item) == {"recorded_at", "attempt", "analysis_id", "validation_error", "model_output"} for item in reports)
    assert secret not in json.dumps(reports) and "U1234567" not in json.dumps(reports)
    assert all("prompt" not in item and "messages" not in item for item in reports)


@pytest.mark.parametrize("text", ["一份合约的末值上升。", "两份合约的末值上升。", "两份成交合约的末值上升。", "一半成交合约的末值上升。", "每一天的持仓记录缺失。"])
def test_real_trace_numeric_classifier_wording_remains_rejected(text):
    with pytest.raises(ValueError, match="Quantities"):
        _validate(reply(text), _evidence(record()), {})


@pytest.mark.parametrize("text", ["该看涨合约的末值上升。", "所选合约的末值上升。", "各日期的持仓记录缺失。"])
def test_qualitative_alternatives_to_real_trace_classifier_failures(text):
    assert _validate(reply(text), _evidence(record()), {})


def test_prompt_and_repair_explain_actual_classifier_failure_without_weakening_rule():
    chat, provider = service([reply("两份合约的成交增加。"), reply("该合约的成交增加。")])
    result = answer(chat)
    assert result["mode"] == "deepseek" and len(provider.calls) == 2
    prompt = provider.calls[0]["messages"][0]["content"]
    repair = provider.calls[1]["messages"][0]["content"]
    assert "同一份" in prompt and "各日期" in prompt
    assert "同一份 -> 该" in repair and "每一天 -> 各日期" in repair


@pytest.mark.parametrize("identity", ["同一份合约", "同一份看涨合约", "同一份看跌合约", "同一份期权合约", "同一份看涨期权合约", "同一份看跌期权合约"])
def test_exact_contract_identity_is_normalized_and_returned(identity):
    text = identity + "的成交统计增加。"
    parts = _validate(reply(text), _evidence(record()), {})
    assert parts[0]["text"] == text.replace("同一份", "该")
    assert parts[0]["evidence_ids"] == ["h.change.volume_total"]


def test_identity_normalization_does_not_delete_nearby_real_quantity():
    with pytest.raises(ValueError, match="Quantities"):
        _validate(reply("同一份看涨合约有两份成交记录。"), _evidence(record()), {})


def _fixed_experts(chat, *identifiers):
    from app.expert_knowledge import ExpertKnowledge
    docs = {doc["id"]: doc for doc in ExpertKnowledge().documents}
    selected = [{**docs[key], "retrieval": {"method": "controlled_test_fixture", "embedding": False,
                 "bm25_rank": None, "char_rank": None, "rrf_score": None}} for key in identifiers]
    chat.knowledge.search = lambda query, limit=6: deepcopy(selected[:limit])


def test_wrong_known_citation_can_be_rebound_to_supported_already_provided_sources():
    text = "看跌成交不是看空人数；历史OHLC不是同步双边报价。"
    chat, provider = service([reply(text, ("expert.history_limits",), "explanation"),
                              reply(text, ("expert.put_call", "expert.history_bars"), "explanation")])
    _fixed_experts(chat, "expert.history_limits", "expert.put_call", "expert.history_bars")
    result = answer(chat, "解释这个段落的金融知识依据。")
    assert result["mode"] == "deepseek" and len(provider.calls) == 2
    assert result["analysis_context"]["grounding"]["covered_facets"] == ["historical_bar_semantics", "put_call_limits"]
    assert [doc["id"] for doc in result["sources"]] == ["expert.put_call", "expert.history_bars"]
    allowed = json.loads(provider.calls[1]["messages"][-1]["content"])["schema_repair"]["allowed_evidence_ids"]
    assert set(allowed) == {"expert.history_limits", "expert.put_call", "expert.history_bars"}


def test_citation_repair_cannot_add_new_topic_even_if_original_wrong_id_would_allow_it():
    chat, provider = service([reply("看跌成交不是看空人数。", ("expert.volatility",), "explanation"),
                              reply("隐含波动率描述波动幅度，不指明涨跌方向。", ("expert.volatility",), "explanation")])
    _fixed_experts(chat, "expert.volatility", "expert.put_call")
    result = answer(chat, "解释这个句子的知识依据。")
    assert result["mode"] == "offline" and len(provider.calls) == 2
    assert result["warning"] == "options_answer_validation_failed"


def test_grounding_repair_cannot_use_unretrieved_source():
    chat, provider = service([reply("看跌成交不是看空人数。", ("expert.history_limits",), "explanation"),
                              reply("隐含波动率描述波动幅度，不指明涨跌方向。", ("expert.volatility",), "explanation")])
    _fixed_experts(chat, "expert.history_limits", "expert.put_call")
    result = answer(chat, "解释这个句子的知识依据。")
    assert result["mode"] == "offline" and len(provider.calls) == 2
    assert result["warning"] == "options_answer_validation_failed"


def test_history_context_uses_real_corpus_version_hash_and_transparent_facet_completion():
    chat, _ = service(online=False)
    result = answer(chat, "用白话复盘这几天的历史数据，并给出专家依据。")
    context = result["analysis_context"]
    assert context["retrieval"]["knowledge_version"] == chat.knowledge.version
    assert context["retrieval"]["corpus_sha256"] == chat.knowledge.corpus_sha256
    assert context["retrieval"]["hits"]
    assert all(hit["selection_reason"] for hit in context["retrieval"]["hits"])


def test_import_missing_field_answer_is_not_forced_to_assert_an_ibkr_api_cause():
    chat, provider = service([reply("导入记录未提供持仓数值和对应日期。", ("h.day.oi_total",), "limitation")])
    result = answer(chat, "未平仓量为什么没有给出？")
    assert result["mode"] == "deepseek" and len(provider.calls) == 1
    payload = json.loads(provider.calls[0]["messages"][-1]["content"])
    assert payload["source_context_kind"] == "historical_import"
    assert "historical_oi_availability" not in payload["required_query_facets"]
