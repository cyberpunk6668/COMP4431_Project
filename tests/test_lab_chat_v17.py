"""Owned synthetic fixtures only: no model, broker, user DB or credentials."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.config import Settings
from app.expert_grounding import claim_facets, required_query_facets, validate_expert_grounding
from app.expert_knowledge import DEFAULT_PATH, ExpertKnowledge
from app.history_chat import HistoryChat, _evidence, _lab_context, _validate
from app.options_lab import evaluate


class Provider:
    def __init__(self, output=None):
        self.output, self.calls = output, []

    async def complete(self, messages, **kwargs):
        self.calls.append(deepcopy(messages))
        assert self.output is not None, "Offline tests must never generate an answer"
        return self.output


def report(**kwargs):
    saved = evaluate(kwargs)
    saved["analysis_id"] = "owned-lab-report"
    saved["ingested_at"] = "2026-11-15T01:00:00Z"
    return saved


def service(*, online=False, output=None):
    provider = Provider(output)
    return HistoryChat(Settings(api_key="owned-mocked-key" if online else "", offline=not online), provider), provider


def ask(chat, saved, question="请解释这次试算的成本、到期盈亏和最大损失", language="zh", history=None):
    return asyncio.run(chat.answer(question, history or [], language, "deepseek", saved))


def test_default_corpus_stays_unchanged_and_lab_extension_is_explicit():
    default = ExpertKnowledge()
    lab = ExpertKnowledge(additional_path=DEFAULT_PATH.with_name("options_lab_knowledge.json"))
    assert len(default.documents) == 14 and len(lab.documents) == 17
    assert not any(doc["id"].startswith("expert.expiry_") for doc in default.documents)
    assert default.version != lab.version and default.corpus_sha256 != lab.corpus_sha256
    assert {doc["strategy"] for doc in lab.documents if doc["id"].startswith("expert.expiry_")} == {"long_call", "long_put", "call_debit_spread"}


@pytest.mark.parametrize("mutation", [
    lambda r: r["source"].update(kind="import"),
    lambda r: r["lab_context"].update(synthetic=False),
    lambda r: r["lab_context"]["source"].update(kind="import"),
    lambda r: r["lab_context"]["source"].update(synthetic=False),
    lambda r: r["lab_context"]["trial"].update(strategy="sell_naked_call"),
    lambda r: r["lab_context"]["trial"].update(scenario_id="another"),
    lambda r: r.update(source=None),
])
def test_lab_context_requires_all_server_provenance_and_closed_strategy_markers(mutation):
    saved = report()
    mutation(saved)
    assert _lab_context(saved) is None


def test_safe_lab_snapshot_preserves_exact_inputs_but_drops_bulk_and_extensions():
    saved = report()
    saved["lab_context"]["user_prompt"] = "arbitrary untrusted extension"
    saved["lab_context"]["trial"]["extra"] = "another untrusted extension"
    original = deepcopy(saved)
    safe = _lab_context(saved)
    assert safe["synthetic"] is True
    assert safe["trial"]["cost"] == 360 and safe["trial"]["break_even"] == 103.6
    assert safe["trial"]["pnl"] == 140 and safe["trial"]["payoff"] == 500
    assert safe["trial"]["max_loss"] == 360 and safe["trial"]["max_gain"] is None
    assert safe["trial"]["max_gain_unlimited"] is True
    assert safe["dataset_as_of"] == "2026-11-11T21:00:00Z" and safe["expiry"] == "2026-12-18"
    serialized = json.dumps(safe, allow_nan=False)
    for key in ("curve", "quote_table", "legs", "decimal_strings", "default_trial", "user_prompt", "extra"):
        assert f'"{key}"' not in serialized
    assert saved == original


@pytest.mark.parametrize("strategy,upper", [("long_call", None), ("long_put", None), ("call_debit_spread", 105)])
@pytest.mark.parametrize("language", ["zh", "en"])
def test_offline_answers_explain_saved_trial_with_selected_oic_passage(strategy, upper, language):
    saved = report(strategy=strategy, upper_strike=upper)
    chat, provider = service()
    result = ask(chat, saved, language=language)
    assert provider.calls == [] and result["generation_attempts"] == 0
    assert result["mode"] == "offline" and result["warning"] == "cloud_unconfigured"
    context = result["analysis_context"]
    assert context["lab_context"]["trial"] == _lab_context(saved)["trial"]
    assert context["scopes"][0]["market_data_status"] == "synthetic_demo"
    assert context["grounding"].get("status") != "partial_local_explanation"
    assert "expiry_payoff" in context["grounding"]["covered_facets"]
    assert context["expert_source_ids"] == ["expert.expiry_" + strategy]
    assert {"h.lab.trial.cost", "h.lab.trial.max_loss"} <= set(context["evidence_ids"])
    assert all(item["synthetic"] is True for item in context["evidence"])
    assert "合成" in result["answer"] if language == "zh" else "Synthetic" in result["answer"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("question,ids", [
    ("盈亏平衡价怎么算？", {"h.lab.trial.break_even", "h.lab.trial.strike", "h.lab.trial.net_premium"}),
    ("最大损失是什么？", {"h.lab.trial.max_loss", "h.lab.trial.cost"}),
    ("这个成本代表什么？", {"h.lab.trial.cost", "h.lab.trial.net_premium", "h.lab.trial.contracts"}),
])
def test_targeted_fallback_cites_actual_trial_fields(question, ids):
    chat, provider = service()
    result = ask(chat, report(), question)
    assert ids <= set(result["analysis_context"]["evidence_ids"])
    assert provider.calls == []


def test_saved_answer_snapshot_does_not_change_when_trial_is_replaced():
    chat, _ = service()
    saved = report()
    previous = ask(chat, saved)
    frozen = deepcopy(previous)
    changed = report(expiry_price=90, contracts=2)
    current = ask(chat, changed)
    assert previous == frozen
    assert previous["analysis_context"]["lab_context"]["trial"]["pnl"] == 140
    assert current["analysis_context"]["lab_context"]["trial"]["pnl"] == -720
    assert current["analysis_context"]["lab_context"]["trial"]["contracts"] == 2


def test_synthetic_market_question_does_not_become_real_sentiment():
    chat, provider = service()
    result = ask(chat, report(), "这说明当前市场看空吗？")
    assert provider.calls == []
    assert "不是真实市场历史" in result["answer"]
    assert "当前市场或预测收益" in result["answer"]
    assert "expert.put_call" in result["analysis_context"]["expert_source_ids"]
    assert result["analysis_context"]["grounding"].get("status") != "partial_local_explanation"


def model_reply(text, ids, kind="explanation"):
    return json.dumps({"response": [{"kind": kind, "text": text, "evidence_ids": ids}]}, ensure_ascii=False)


def test_controlled_provider_receives_bounded_trial_and_synthetic_instructions():
    output = model_reply("买入看涨的最大损失限于已支付权利金；到期盈亏平衡标的价为执行价加权利金。", ["h.lab.trial.cost", "h.lab.trial.break_even", "expert.expiry_long_call"])
    chat, provider = service(online=True, output=output)
    saved = report()
    result = ask(chat, saved)
    assert result["mode"] == "deepseek" and len(provider.calls) == 1
    messages = provider.calls[0]
    assert "SERVER-AUTHORED SYNTHETIC" in messages[0]["content"]
    payload = json.loads(messages[-1]["content"])
    assert payload["source_context_kind"] == "synthetic_lab"
    assert payload["lab_context"]["trial"]["cost"] == 360
    assert "curve" not in payload["lab_context"]["trial"]
    assert "quote_table" not in payload["lab_context"]
    assert not any(source["id"] in {"expert.expiry_long_put", "expert.expiry_call_debit_spread"} for source in payload["expert_sources"])


@pytest.mark.parametrize("text,ids", [
    ("最大损失是无限的。", ["expert.expiry_long_call"]),
    ("到期盈亏平衡价为执行价减权利金。", ["expert.expiry_long_call"]),
    ("这次试算净赚140美元。", ["h.lab.trial.pnl"]),
    ("当前市场已经看空。", ["h.lab.put_volume_share"]),
    ("该成本来自输入。", ["h.lab.trial.unknown"]),
    ("最大损失限于已支付权利金。", ["expert.volume_oi"]),
])
def test_lab_does_not_relax_unknown_numeric_market_or_source_checks(text, ids):
    saved = report()
    knowledge = ExpertKnowledge(additional_path=DEFAULT_PATH.with_name("options_lab_knowledge.json"))
    sources = {doc["id"]: doc for doc in knowledge.documents}
    with pytest.raises(ValueError):
        _validate(model_reply(text, ids), _evidence(saved), sources, "成本与最大损失", "synthetic_lab")


def test_explicit_payoff_claims_need_payoff_sources_not_merely_a_valid_expert_id():
    assert "expiry_payoff" in claim_facets("最大损失限于已支付权利金。")
    assert "expiry_payoff" not in claim_facets("请查看最大损失卡。")
    source = next(doc for doc in ExpertKnowledge().documents if doc["id"] == "expert.volume_oi")
    with pytest.raises(ValueError, match="expiry_payoff"):
        validate_expert_grounding([{"kind": "explanation", "text": "最大损失限于已支付权利金。", "evidence_ids": [source["id"]]}], [source])


# Verbatim synthetic-only output from the recorded real provider call in
# options_lab_live_v17-20261115T085341172115Z.json. No user conversation or
# credential is included. This replay makes no network calls.
LIVE_SYNTHETIC_PARTS = [
    {"kind":"explanation","text":"这是一份明确标注的合成教学记录，教学输入日期和假想到期日都来自本地提示，所有行情、报价、波动率和持仓都是人为构造的，不是真实市场历史，也不是当前市场状况或收益预测。下面只解释本次保存的到期试算，不涉及任何实时行情。","evidence_ids":["h.lab.trial.cost","h.lab.trial.expiry_price"]},
    {"kind":"explanation","text":"所选试算是一笔买入看涨的到期现金盈亏：初始净支付就是整组的总成本，每股净权利金乘以固定乘数和每腿份数得到该成本。到期时，标的价高于执行价的部分构成到期现金值，再减去已付成本就是净盈亏；到期盈亏平衡标的价等于执行价加每股净权利金。按买入看涨的到期关系，最大损失限于已支付的权利金，理论最大收益没有上限。","evidence_ids":["h.lab.trial.cost","h.lab.trial.net_premium","h.lab.trial.strike","h.lab.trial.break_even","h.lab.trial.max_loss","h.lab.trial.payoff","h.lab.trial.pnl","expert.expiry_long_call"]},
    {"kind":"limitation","text":"这些数字是到期日的理想化现金试算，不是提前平仓估值，也不是价格预测、胜率或买卖建议。它假定组合保持完整、各腿同一到期日、固定乘数和等量份数，并且不含手续费、税费、融资、股息、滑点、行权或指派等额外影响；自然价与中间价只是成交假设，给定波动率也没有从权利金校准。","evidence_ids":["h.lab.trial.cost","h.lab.trial.break_even","h.lab.trial.max_loss","h.lab.trial.pnl"]},
    {"kind":"next_check","text":"复核时先确认这是合成教学样本而非真实记录，再核对所选执行价、假想到期价、份数和成本口径是否与保存参数一致，并确认比较的是同一合约范围。若关心当前情绪或当前可成交价格，这份合成数据无法回答，需要另取有明确来源和时点的资料。","evidence_ids":["h.lab.trial.strike","h.lab.trial.expiry_price","h.lab.trial.contracts","expert.contract_identity"]},
]


def test_recorded_synthetic_live_response_replays_without_identity_or_assumption_false_positive():
    saved = report(expiry_price=102)
    docs = ExpertKnowledge(additional_path=DEFAULT_PATH.with_name("options_lab_knowledge.json")).documents
    sources = {item["id"]:item for item in docs}
    raw = json.dumps({"response":LIVE_SYNTHETIC_PARTS},ensure_ascii=False)
    parts = _validate(raw,_evidence(saved),sources,"请用白话解释这份合成教学试算的成本、到期盈亏平衡和最大损失。","synthetic_lab")
    assert len(parts) == 4
    assert parts[0]["text"].startswith("这是明确标注的合成教学记录")
    assert parts[1] == LIVE_SYNTHETIC_PARTS[1]  # No formula/claim rewrite.
    assert claim_facets(parts[2]["text"]) == set()
    assert claim_facets(parts[3]["text"]) == {"contract_comparability"}
    # The provider's recorded repair added a pricing citation to an exclusions
    # list. Correct interpretation must not make that padding source valid.
    repaired = deepcopy(parts)
    repaired[2]["evidence_ids"].append("expert.pricing")
    with pytest.raises(ValueError, match="unrelated"):
        _validate(json.dumps({"response":repaired},ensure_ascii=False),_evidence(saved),sources)


@pytest.mark.parametrize("text", [
    "这是一份合约。", "这是一份看涨合约。", "这次持有两份合约。", "成本是三百美元。",
    "已经付了百分之十。", "收益是一半。", "净盈亏变为两倍。", "成本为360美元。",
])
def test_document_identity_cleanup_never_whitelists_actual_amounts(text):
    saved = report()
    with pytest.raises(ValueError, match="Quantities|figures"):
        _validate(model_reply(text,["h.lab.trial.cost"]),_evidence(saved),{})


@pytest.mark.parametrize("text,expected", [
    ("本次到期试算不含手续费、税费、融资、股息、滑点、行权或指派；权利金只取给定输入。", set()),
    ("This expiry trial excludes fees, tax, funding, dividends, slippage, exercise or assignment; premiums are supplied inputs.", set()),
    ("本次到期试算不含手续费、滑点；股息和利率会影响权利金。", {"option_price_factors"}),
    ("本次到期试算不含税费；中间价不保证成交。", {"bid_ask_execution"}),
    ("权利金会受剩余期限、股息和利率影响。", {"option_price_factors"}),
    ("期权价格不包括股息。", {"option_price_factors"}),
    ("Option premiums do not include dividends.", {"option_price_factors"}),
    ("Wider spreads can worsen slippage and execution.", {"bid_ask_execution"}),
])
def test_excluded_cost_list_is_not_a_general_pricing_or_execution_exemption(text,expected):
    assert claim_facets(text) == expected


@pytest.mark.parametrize("index,valid",[(0,True),(1,False),(2,True),(3,False)])
def test_second_recorded_provider_run_replays_all_outputs_with_original_allowlists(index,valid):
    # The recorded report is deliberately preserved as acceptance evidence.
    # Its data and raw answers are synthetic, with no user database reads.
    recorded = json.loads((Path(__file__).parents[1]/"reports"/"options_lab_live_v17-20261115T085909865677Z.json").read_text(encoding="utf-8"))
    which = index//2
    ids = {item["id"] for item in recorded["turns"][which]["result"]["analysis_context"]["retrieval"]["hits"]}
    docs = {doc["id"]:doc for doc in ExpertKnowledge(additional_path=DEFAULT_PATH.with_name("options_lab_knowledge.json")).documents if doc["id"] in ids}
    saved = report(**{key:recorded["trial"][key] for key in ("scenario_id","strategy","strike","upper_strike","expiry_price","contracts","execution","language")})
    raw = recorded["calls"][index]["synthetic_only_raw_response"]
    if valid:
        result = _validate(raw,_evidence(saved),docs,recorded["questions"][which],"synthetic_lab")
        assert len(result) == (4 if index==0 else 5)
        assert all("[h." not in part["text"] and "[expert." not in part["text"] for part in result)
    else:
        # The old repair padded a local parameter-check paragraph with an
        # unrelated expiry definition. Fixing formatting does not legitimize it.
        with pytest.raises(ValueError,match="unrelated"):
            _validate(raw,_evidence(saved),docs,recorded["questions"][which],"synthetic_lab")


def test_synthetic_provenance_is_metadata_but_genuine_historical_definition_still_needs_source():
    text="这份记录是人为构造的合成教学样本，不是真实市场历史，也不代表当前市场状况。"
    assert "historical_time_basis" not in claim_facets(text,"synthetic_lab")
    for kind in ("historical_import","historical_demo","historical_ibkr","historical"):
        assert "historical_time_basis" in claim_facets(text,kind)
    mixed=text+"历史区间只能描述所覆盖的过去样本，不能据此判断此刻市场状态。"
    assert "historical_time_basis" in claim_facets(mixed,"synthetic_lab")
    assert "historical_time_basis" not in required_query_facets("为什么合成试算不能预测当前市场？","synthetic_lab")
    assert "historical_time_basis" in required_query_facets("真实历史数据能代表当前市场吗？","synthetic_lab")
    assert "expiry_payoff" not in claim_facets("确认最大损失是否仍对应所选参数；不要沿用旧结果。")


@pytest.mark.parametrize("text,refs",[
    ("该成本来自保存参数。[h.lab.trial.unknown]",["h.lab.trial.cost"]),
    ("该成本来自保存参数。[h.lab.trial.cost]",[]),
    ("成本为360美元。[h.lab.trial.cost]",["h.lab.trial.cost"]),
    ("成本是三百美元。[h.lab.trial.cost]",["h.lab.trial.cost"]),
    ("<script>执行</script>[h.lab.trial.cost]",["h.lab.trial.cost"]),
    ("这里是[普通方括号]。",["h.lab.trial.cost"]),
])
def test_lab_reference_cleanup_keeps_unknown_undeclared_numeric_and_html_rejection(text,refs):
    with pytest.raises(ValueError):
        _validate(model_reply(text,refs),_evidence(report()),{},context_kind="synthetic_lab")


def test_known_declared_duplicate_inline_id_is_formatting_only_and_lab_scoped():
    raw=model_reply("该成本来自保存参数。[h.lab.trial.cost]",["h.lab.trial.cost"])
    parts=_validate(raw,_evidence(report()),{},context_kind="synthetic_lab")
    assert parts[0]["text"]=="该成本来自保存参数。" and parts[0]["evidence_ids"]==["h.lab.trial.cost"]
    with pytest.raises(ValueError,match="inline references"):
        _validate(raw,_evidence(report()),{},context_kind="historical_import")


def test_lab_continuation_sends_structured_prior_summary_without_ui_citation_header():
    saved=report()
    offline,_=service()
    previous=ask(offline,saved)
    output=model_reply("买入看涨的最大损失限于已支付权利金。",["expert.expiry_long_call","h.lab.trial.max_loss"])
    online,provider=service(online=True,output=output)
    history=[{"role":"user","content":"试算最大损失是什么？","analysis_id":saved["analysis_id"]},
             {"role":"assistant","content":previous["answer"],"analysis_context":previous["analysis_context"]}]
    result=ask(online,saved,"最大损失是什么？",history=history)
    assert result["mode"]=="deepseek" and len(provider.calls)==1
    prior=json.loads(provider.calls[0][2]["content"])
    assert "previous_explanation" in prior and "previous_evidence_ids" in prior
    assert "h.lab.trial.max_loss" in prior["previous_evidence_ids"]
    assert "[h." not in prior["previous_explanation"] and "[expert." not in prior["previous_explanation"]
    assert "2026-11-11" not in prior["previous_explanation"]
    assert history[1]["content"]==previous["answer"]
