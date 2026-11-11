"""Reviewed support facets bind recognized claims to the right local passages."""
from copy import deepcopy
import json

import pytest

from app.expert_grounding import (claim_facets, expert_repair_allowance, required_query_facets,
    retrieve_expert_context, validate_expert_grounding, validate_repair_claims, expert_citation_repair_plan)
from app.expert_knowledge import ExpertKnowledge


@pytest.fixture
def docs():
    return {doc["id"]: doc for doc in ExpertKnowledge().documents}


def part(text, *ids):
    return {"kind": "explanation", "text": text, "evidence_ids": list(ids)}


ACTUAL_BAD_PARAGRAPH = "看涨/看跌成交不是多空人数，每笔成交都有买卖双方；看跌占比偏高也不能识别看空的人、主动方或开平仓。保护、行权或多腿组合只是可能用途，不能当作已确认原因。历史成交 OHLC 不是同步双边报价，不能用来推断当前价差、隐含波动或希腊值。"


def test_actual_v13_incorrect_history_limits_citation_rejected(docs):
    # Verbatim safe excerpt from the real saved v13 answer; ID validity alone
    # previously accepted this unrelated expired/EOD source.
    with pytest.raises(ValueError, match="does not support"):
        validate_expert_grounding([part(ACTUAL_BAD_PARAGRAPH, "expert.history_limits")], docs)
    audit = validate_expert_grounding([part(ACTUAL_BAD_PARAGRAPH, "expert.put_call", "expert.history_bars")], docs)
    assert audit["covered_facets"] == ["historical_bar_semantics", "put_call_limits"]


@pytest.mark.parametrize("text,ids", [
    ("看跌成交不是看空人数。", ["expert.history_limits"]),
    ("不能把历史OHLC当作同步双边报价。", ["expert.put_call"]),
    ("Put volume does not identify bearish people or aggressor intent.", ["expert.history_limits"]),
    ("Historical OHLC is not a synchronized executable quote.", ["expert.put_call"]),
    ("虽然不能预测，但看跌合约计数不等于参与人数。", ["expert.history_limits"]),
])
def test_negation_never_exempts_a_financial_knowledge_claim(text, ids, docs):
    with pytest.raises(ValueError, match="does not support"):
        validate_expert_grounding([part(text, *ids)], docs)


def test_multiple_topics_require_each_supported_source_in_same_paragraph(docs):
    text = "未平仓量在隔夜清算后发布。历史OHLC不是同步双边报价。"
    with pytest.raises(ValueError):
        validate_expert_grounding([part(text, "expert.oi_cycle")], docs)
    assert validate_expert_grounding([part(text, "expert.oi_cycle", "expert.history_bars")], docs)
    with pytest.raises(ValueError):
        validate_expert_grounding([part(text, "expert.oi_cycle"), part("历史OHLC不是同步双边报价。", "expert.history_bars")], docs)


def test_local_price_observation_does_not_need_unrelated_definition(docs):
    assert not claim_facets("所选看涨合约的末值上升，所选看跌合约的末值下降。")
    assert validate_expert_grounding([part("所选合约的所收成交记录末值上升。", "h.contract.0.trade_close")], docs, local_ids={"h.contract.0.trade_close"})
    with pytest.raises(ValueError, match="does not support"):
        validate_expert_grounding([part("看跌成交不是看空人数。", "h.day.put_share")], docs, local_ids={"h.day.put_share"})


def test_unretrieved_and_unrelated_padding_sources_rejected(docs):
    only_limits = {"expert.history_limits": docs["expert.history_limits"]}
    with pytest.raises(ValueError, match="not in the retrieved"):
        validate_expert_grounding([part("看跌成交不是看空人数。", "expert.put_call")], only_limits)
    with pytest.raises(ValueError, match="unrelated"):
        validate_expert_grounding([part("看跌成交不是看空人数。", "expert.put_call", "expert.history_limits")], docs)


@pytest.mark.parametrize("query,expected", [
    ("这些数据能说明现在市场看空吗？未平仓量为什么没有给出？", {"put_call_limits", "historical_time_basis", "historical_oi_availability"}),
    ("未平仓量为什么和成交量不同？", {"volume_vs_oi"}),
    ("历史分钟BID_ASK能算价差吗？", {"historical_bar_semantics"}),
    ("What is implied volatility?", {"iv_direction_limits"}),
])
def test_query_facets_are_specific(query, expected):
    assert required_query_facets(query, "historical") == expected


def test_why_different_is_not_misread_as_missing_historical_oi():
    assert "historical_oi_availability" not in required_query_facets("未平仓持仓日期为什么和成交不同？", "historical")


def test_answer_cannot_delete_requested_topics_to_pass_validation(docs):
    query = "这些数据能说明现在市场看空吗？未平仓量为什么没有给出？"
    good_but_incomplete = [part(docs["expert.put_call"]["text"], "expert.put_call")]
    with pytest.raises(ValueError, match="omitted requested"):
        validate_expert_grounding(good_but_incomplete, docs, query, "historical")
    full = good_but_incomplete + [part(docs[key]["text"], key) for key in ("expert.history_time", "expert.history_oi")]
    assert validate_expert_grounding(full, docs, query, "historical")["required_query_facets"] == sorted(required_query_facets(query, "historical"))


def test_generic_data_review_requires_local_observations_not_only_expert_essay(docs):
    with pytest.raises(ValueError, match="must cite local"):
        validate_expert_grounding([part(docs["expert.history_bars"]["text"], "expert.history_bars")], docs,
                                  "请复盘这些样本", "historical", local_ids={"h.contract.0.trade_close"})


def test_facet_completion_is_transparent_without_fabricated_search_ranks():
    knowledge = ExpertKnowledge()
    original = deepcopy(knowledge.documents)
    question = "请复盘这些样本"
    raw = {doc["id"]: doc for doc in knowledge.search(question, limit=6)}
    selected = retrieve_expert_context(knowledge, question, "historical", ("historical_bar_semantics", "put_call_limits", "oi_reporting_cycle"))
    assert {facet for doc in selected for facet in doc["supports"]} >= {"historical_bar_semantics", "put_call_limits", "oi_reporting_cycle"}
    for doc in selected:
        trace = doc["retrieval"]
        if doc["id"] in raw:
            for key in ("bm25_rank", "char_rank", "rrf_score"):
                assert trace[key] == raw[doc["id"]]["retrieval"][key]
        else:
            assert trace["method"] == "curated_support_facet" and trace["bm25_rank"] is None and trace["char_rank"] is None and trace["rrf_score"] is None
    assert knowledge.documents == original


def test_query_facets_take_priority_over_generic_context_limit():
    selected = retrieve_expert_context(ExpertKnowledge(), "这些历史资料能说明现在市场看空吗？未平仓量为什么没有给出？", "historical",
                                      ("historical_bar_semantics", "historical_volume_filtering", "contract_comparability"), limit=3)
    assert {facet for doc in selected for facet in doc["supports"]} == {"put_call_limits", "historical_time_basis", "historical_oi_availability"}


def test_repair_may_rebind_existing_claim_to_already_supplied_matching_source(docs):
    original = json.dumps({"response": [part(ACTUAL_BAD_PARAGRAPH, "expert.history_limits")]}, ensure_ascii=False)
    allowance = expert_repair_allowance(original, docs)
    assert "expert.put_call" in allowance and "expert.history_bars" in allowance
    assert "expert.volatility" not in allowance and not any(key.startswith("h.") for key in allowance)
    corrected = [part(ACTUAL_BAD_PARAGRAPH, "expert.put_call", "expert.history_bars")]
    assert validate_repair_claims(original, corrected, docs)
    assert validate_expert_grounding(corrected, docs)
    assert "expert.put_call" not in expert_repair_allowance(original, {"expert.history_limits": docs["expert.history_limits"]})


def test_repair_cannot_add_new_known_knowledge_topic(docs):
    original = json.dumps({"response": [part("看跌成交不是看空人数。", "expert.history_limits")]}, ensure_ascii=False)
    with pytest.raises(ValueError, match="new expert claim"):
        validate_repair_claims(original, [part("隐含波动率描述波动幅度，不指明涨跌方向。", "expert.volatility")], docs)


def test_malformed_original_has_no_source_repair_allowance(docs):
    assert expert_repair_allowance("not JSON", docs) == set()


def test_reviewed_core_passages_are_consistent_with_their_support_metadata(docs):
    for key, doc in docs.items():
        assert validate_expert_grounding([part(doc["text"], key)], docs)


@pytest.mark.parametrize("kind", ["historical_import", "historical_demo"])
def test_missing_import_oi_does_not_force_or_authorize_ibkr_cause(kind, docs):
    query = "未平仓量为什么没有给出？"
    assert "historical_oi_availability" not in required_query_facets(query, kind)
    with pytest.raises(ValueError, match="Imported missing fields"):
        validate_expert_grounding([part(docs["expert.history_oi"]["text"], "expert.history_oi")], docs, query, kind)
    assert validate_expert_grounding([part("导入记录未提供持仓数值和对应日期。", "h.day.oi_total")], docs, query, kind, local_ids={"h.day.oi_total"})


def test_ibkr_record_or_explicit_interface_question_requires_scoped_oi_answer(docs):
    query = "未平仓量为什么没有给出？"
    assert required_query_facets(query, "historical_ibkr") == {"historical_oi_availability"}
    assert validate_expert_grounding([part(docs["expert.history_oi"]["text"], "expert.history_oi")], docs, query, "historical_ibkr")
    explicit = "IBKR的reqHistoricalData为什么没有期权OI历史条？"
    assert required_query_facets(explicit, "historical_import") == {"historical_oi_availability"}
    assert validate_expert_grounding([part(docs["expert.history_oi"]["text"], "expert.history_oi")], docs, explicit, "historical_import")


def test_english_meaning_denial_and_two_counterparties_are_put_call_claims(docs):
    text = "Put volume does not mean the market is bearish; a traded contract has both a buyer and a seller."
    assert claim_facets(text) == {"put_call_limits"}
    assert validate_expert_grounding([part(text, "expert.put_call")], docs)
    with pytest.raises(ValueError, match="does not support"):
        validate_expert_grounding([part(text, "expert.history_limits")], docs)


def test_meaning_relation_detection_does_not_override_claim_truth_guard():
    from app.options_chat import _unsafe_claim
    assert claim_facets("Put volume means the market is bearish.") == {"put_call_limits"}
    assert _unsafe_claim("Put volume means the market is bearish.") is True
    assert _unsafe_claim("Put volume does not mean the market is bearish.") is False
    assert "put_call_limits" not in claim_facets("Put prices increased while the commentator is bearish.")


@pytest.mark.parametrize("text", [
    "本次历史bar完整交易时段覆盖未核验。",
    "本样本共同合约范围在提供的历史日期保持一致。",
    "The historical bar session coverage has not been verified for this sample.",
    "This sample contains the same contract window on the supplied dates.",
])
def test_local_metadata_does_not_need_an_expert_to_authenticate_its_truth(text):
    assert not claim_facets(text)
    assert validate_expert_grounding([part(text, "h.meta")], [], local_ids={"h.meta"})


@pytest.mark.parametrize("text,facet", [
    ("导入时间不是交易发生时间，历史记录不代表当前行情。", "historical_time_basis"),
    ("跨日期比较应先确认相同合约范围及合约规格。", "contract_comparability"),
    ("看跌成交量增加并不意味着市场看空。", "put_call_limits"),
    ("Receipt time is not exchange time; a historical sample is not current quotes.", "historical_time_basis"),
])
def test_general_relations_still_require_matching_expert_support(text, facet, docs):
    assert facet in claim_facets(text)
    with pytest.raises(ValueError, match="does not support"):
        validate_expert_grounding([part(text, "h.meta")], docs, local_ids={"h.meta"})


def test_historical_iv_limitation_does_not_accidentally_claim_ohlc_semantics(docs):
    text = "历史隐含波动字段不等于合约历史希腊值，缺失时不能把当前模型字段回填到过去。"
    assert claim_facets(text) == {"historical_contract_iv_limits"}
    assert validate_expert_grounding([part(text, "expert.history_iv")], docs)


@pytest.mark.parametrize("text", [
    "前后对照中，看跌持仓占比和持仓总数因配对行权价集合改变而不可比，不能当作增加或减少来解读。",
    "合约集合发生变化，因此不能直接比较变化量。",
    "The paired strike set changed, so these totals are incomparable and cannot be read as an increase or decrease.",
    "The contract membership changed, making the comparison not comparable.",
])
def test_changed_paired_set_comparison_principle_has_specific_support(text, docs):
    assert claim_facets(text) == {"contract_comparability"}
    assert validate_expert_grounding([part(text, "expert.contract_identity")], docs)
    with pytest.raises(ValueError, match="does not support"):
        validate_expert_grounding([part(text, "expert.history_limits")], docs)


@pytest.mark.parametrize("text", [
    "本次样本的配对行权价集合已改变。",
    "本次样本配对行权价集合保持相同。",
    "The paired strike set remained identical on the supplied dates.",
    "The paired strike set changed on this date.",
])
def test_bare_pair_membership_metadata_is_still_local_evidence(text):
    assert not claim_facets(text)
    assert validate_expert_grounding([part(text, "change.s0.oi_total")], [], local_ids={"change.s0.oi_total"})


def test_actual_snapshot_part_combines_time_and_comparability_sources(docs):
    text = "这份样本是延迟且过期的历史快照，本地接收时间不是交易所时间，也不保证实时性；它只能描述所覆盖的过去样本，不能断定此刻的市场状态。前后对照中，看跌持仓占比和持仓总数因配对行权价集合改变而不可比，不能当作增加或减少来解读。"
    assert claim_facets(text) == {"historical_time_basis", "contract_comparability"}
    assert validate_expert_grounding([part(text, "expert.history_time", "expert.contract_identity", "change.s0.oi_total")], docs,
                                    local_ids={"change.s0.oi_total"})


@pytest.mark.parametrize("text", [
    "先补齐可核验的双边报价与成交配对，并确认合约范围一致后再比较。",
    "Verify matching contract scope before comparing.",
])
def test_verify_matching_scope_before_comparison_has_matching_support(text, docs):
    assert claim_facets(text) == {"contract_comparability"}
    assert validate_expert_grounding([part(text, "expert.contract_identity")], docs)
    with pytest.raises(ValueError, match="does not support"):
        validate_expert_grounding([part(text, "expert.history_limits")], docs)


@pytest.mark.parametrize("text", [
    "本样本合约范围已经确认一致。",
    "The matching contract scope is recorded in this sample.",
])
def test_scope_metadata_without_comparison_rule_does_not_require_source(text):
    assert not claim_facets(text)


def test_grounding_error_identifies_paragraph_and_missing_facets_without_prose(docs):
    marker = "DO_NOT_ECHO_MODEL_PROSE"
    parts = [part("这里先查看样本。"), part("看跌成交不是看空人数。" + marker, "expert.history_limits")]
    with pytest.raises(ValueError) as error:
        validate_expert_grounding(parts, docs)
    message = str(error.value)
    assert message.startswith("paragraph 2: Expert citation does not support claim facets: ")
    assert "put_call_limits" in message and marker not in message


def test_grounding_error_identifies_unrelated_known_sources_without_prose(docs):
    marker = "DO_NOT_ECHO_MODEL_PROSE"
    parts = [part("这是连接文字。") for _ in range(4)]
    parts.append(part("看跌成交不是看空人数。" + marker, "expert.put_call", "expert.history_limits"))
    with pytest.raises(ValueError) as error:
        validate_expert_grounding(parts, docs)
    message = str(error.value)
    assert message.startswith("paragraph 5: Expert citation is unrelated")
    assert "expert.history_limits" in message and "expert.put_call" not in message
    assert marker not in message


@pytest.mark.parametrize("text", [
    "这些只是区间成交记录的末值，不是结算价，也不是同步双边报价。",
    "The interval trade record end values are not settlement prices or synchronized BBOs.",
])
def test_interval_trade_end_value_limitation_has_bar_semantics(text, docs):
    assert claim_facets(text) == {"historical_bar_semantics"}
    assert validate_expert_grounding([part(text, "expert.history_bars")], docs)
    with pytest.raises(ValueError, match="does not support"):
        validate_expert_grounding([part(text, "expert.history_limits")], docs)


def test_same_end_value_without_general_relation_remains_local():
    assert not claim_facets("区间成交记录的末值在证据卡中保留。")


def test_comparison_review_method_is_not_bare_membership_metadata(docs):
    text = "复核时可先确认各日期是否覆盖完整常规交易时段、合约范围是否一致，再核对持仓对应的报告日期；只有状态为可比的变化才做方向解读，其余保持不可比。"
    assert claim_facets(text) == {"contract_comparability"}
    assert validate_expert_grounding([part(text, "expert.contract_identity")], docs)
    assert not claim_facets("本次记录的合约范围是否一致尚未核验。")


def test_repair_plan_collects_every_paragraph_issue_without_editing_answers(docs):
    original = [
        part("这段历史不代表当前行情。", "h.day.0.volume_total"),
        part("区间成交记录的末值不是结算价，也不是同步双边报价。", "expert.history_bars", "h.contract.0.trade_close"),
        part("看跌占比不代表看空人数或主动买卖意图。", "expert.history_volume", "expert.put_call", "expert.oi_cycle"),
        part("跨日期比较应确认合约范围一致。", "expert.history_time", "expert.contract_identity"),
    ]
    unchanged = deepcopy(original)
    allowed = set(docs) | {"h.day.0.volume_total", "h.contract.0.trade_close"}
    plan = expert_citation_repair_plan(original, docs, allowed)
    assert [item["paragraph"] for item in plan] == [1, 2, 3, 4]
    assert plan[0]["missing_facets"] == ["historical_time_basis"]
    assert plan[0]["add_candidates"] == ["expert.history_time"]
    assert plan[1]["status"] == "supported"
    assert plan[2]["remove_unrelated"] == ["expert.history_volume", "expert.oi_cycle"]
    assert plan[3]["remove_unrelated"] == ["expert.history_time"]
    assert original == unchanged and all("text" not in item for item in plan)


def test_repair_plan_raw_json_and_parts_contract_match(docs):
    parts = [part("看跌成交不是看空人数。", "expert.history_limits")]
    allowed = {"expert.history_limits", "expert.put_call"}
    assert expert_citation_repair_plan(json.dumps({"response": parts}, ensure_ascii=False), docs, allowed) == expert_citation_repair_plan(parts, docs, allowed)
    assert expert_citation_repair_plan("not JSON", docs, allowed) == []
    assert expert_citation_repair_plan('{"response":"invalid"}', docs, allowed) == []


def test_repair_candidates_need_both_context_and_existing_allowance(docs):
    parts = [part(ACTUAL_BAD_PARAGRAPH, "expert.history_limits")]
    provided = {key: docs[key] for key in ("expert.history_limits", "expert.put_call", "expert.history_bars")}
    plan = expert_citation_repair_plan(parts, provided, {"expert.history_limits", "expert.put_call"})[0]
    assert plan["add_candidates"] == ["expert.put_call"]
    assert plan["candidates_by_facet"]["historical_bar_semantics"] == []
    assert plan["unresolved_facets"] == ["historical_bar_semantics"] and plan["status"] == "blocked"
    assert "expert.history_bars" not in plan["add_candidates"]
    empty = expert_citation_repair_plan(parts, {}, set(docs))[0]
    assert empty["add_candidates"] == [] and empty["status"] == "blocked"


def test_unknown_citations_are_explicit_blocked_issues_not_silently_removed(docs):
    unknown = "expert.unprovided_reference"
    parts = [part("看跌成交不是看空人数。DO_NOT_COPY_MODEL_TEXT", unknown)]
    item = expert_citation_repair_plan(parts, docs, {unknown, "expert.put_call"})[0]
    assert item["unprovided_expert_reference_count"] == 1 and item["status"] == "blocked"
    assert item["remove_unrelated"] == []
    assert unknown not in json.dumps(item) and "DO_NOT_COPY_MODEL_TEXT" not in json.dumps(item)


def test_plan_never_introduces_a_local_id_or_ignores_unallowed_existing_one(docs):
    item = expert_citation_repair_plan([part("看跌成交不是看空人数。", "h.unknown")], docs, {"expert.put_call"})[0]
    assert item["disallowed_reference_count"] == 1 and item["status"] == "blocked"
    assert item["add_candidates"] == ["expert.put_call"]
    assert all(key.startswith("expert.") for key in item["add_candidates"])


def test_safe_raw_plan_keeps_original_indices_and_six_part_bound(docs):
    raw = {"response": [None, part("看跌成交不是看空人数。", "expert.history_limits")] + [part("连接文字。")]*7}
    plan = expert_citation_repair_plan(json.dumps(raw, ensure_ascii=False), docs, set(docs))
    assert [item["paragraph"] for item in plan] == [2, 3, 4, 5, 6]


def test_bad_reference_shape_is_explicitly_unresolved(docs):
    item = expert_citation_repair_plan([{"text": "看跌成交不是看空人数。", "evidence_ids": "expert.put_call"}], docs, set(docs))[0]
    assert item["malformed_references"] is True and item["status"] == "blocked"


@pytest.mark.parametrize('text', [
    '这里用的是历史成交条：这类历史条只返回开高低收和成交量，本身不提供按日持仓字段。这只限制这里的历史条接口，不代表其他来源没有历史未平仓量。',
    '历史成交条本身不提供按日未平仓量字段。',
])
def test_explicit_historical_trade_bar_oi_type_boundary_needs_its_own_source(text, docs):
    assert 'historical_oi_availability' in claim_facets(text)
    assert validate_expert_grounding([part(text, 'expert.history_oi')], docs, context_kind='historical_ibkr')
    with pytest.raises(ValueError, match='does not support'):
        validate_expert_grounding([part(text, 'expert.oi_cycle')], docs, context_kind='historical_ibkr')


@pytest.mark.parametrize('text', [
    '本次所收历史成交条的未平仓量字段缺失。',
    '历史成交条本身不提供新闻，持仓字段记录在另一张卡中。',
    '历史收入条本身不提供按日工资字段。',
])
def test_missing_sample_field_or_other_domain_does_not_establish_oi_api_boundary(text):
    assert 'historical_oi_availability' not in claim_facets(text)


@pytest.mark.parametrize('text', [
    '另取带独立统计日期的未平仓量来源。',
    '建议先核对区间并确认未平仓量是否有独立报告日期。',
])
def test_normative_independent_oi_date_check_has_cycle_support(text, docs):
    assert claim_facets(text) == {'oi_reporting_cycle'}
    assert validate_expert_grounding([part(text, 'expert.oi_cycle')], docs)
    with pytest.raises(ValueError, match='does not support'):
        validate_expert_grounding([part(text, 'expert.history_oi')], docs)


@pytest.mark.parametrize('text', [
    '未平仓量的独立统计日期已记录在数据卡。',
    '另取带独立统计日期的营业收入来源。',
    '未平仓量独立统计日期能保证未来预测准确。',
    '未平仓量独立统计日期证明资金流入。',
])
def test_oi_date_metadata_and_unrelated_inferences_do_not_unlock_cycle_source(text, docs):
    assert 'oi_reporting_cycle' not in claim_facets(text)
    with pytest.raises(ValueError, match='unrelated'):
        validate_expert_grounding([part(text, 'expert.oi_cycle')], docs)


@pytest.mark.parametrize('text', [
    '成交条是区间汇总，不是同步报价，所以不能据此推断当前价差、隐含波动率或未来方向。',
    '比较的是区间首日与末日各自收到的成交条末值，不是结算价，也不是同一时刻可成交的双边报价。',
])
def test_explicit_trade_bar_aggregate_and_executable_quote_distinction(text, docs):
    assert 'historical_bar_semantics' in claim_facets(text)
    assert validate_expert_grounding([part(text, 'expert.history_bars')], docs)
    with pytest.raises(ValueError, match='does not support'):
        validate_expert_grounding([part(text, 'expert.history_time')], docs)


@pytest.mark.parametrize('text', [
    '这段内容只是历史复盘，不是当前行情。',
    '只把这段记录当作历史样本内的对照，不当作当前市场情绪的依据。',
])
def test_explicit_not_current_history_boundary_has_time_support(text, docs):
    assert claim_facets(text) == {'historical_time_basis'}
    assert validate_expert_grounding([part(text, 'expert.history_time')], docs)
    with pytest.raises(ValueError, match='does not support'):
        validate_expert_grounding([part(text, 'expert.history_oi')], docs)


@pytest.mark.parametrize('text', [
    '另取带独立统计日期的未平仓量来源；未来必涨。',
    '另取带独立统计日期的未平仓量来源；持仓证明资金流入。',
])
def test_related_oi_source_does_not_unlock_forecast_or_fund_flow_claims(text, docs):
    from app.history_chat import _validate
    raw=json.dumps({'response':[{'kind':'explanation','text':text,'evidence_ids':['expert.oi_cycle']}]},ensure_ascii=False)
    with pytest.raises(ValueError,match='Unsupported options claim'):
        _validate(raw,{},docs,context_kind='historical_ibkr')


def test_new_history_synonym_still_cannot_use_an_unknown_reference(docs):
    from app.history_chat import _validate
    raw=json.dumps({'response':[{'kind':'explanation','text':'历史复盘不是当前行情。','evidence_ids':['expert.unknown_history_reference']}]},ensure_ascii=False)
    with pytest.raises(ValueError,match='Unknown'):
        _validate(raw,{},docs,context_kind='historical_ibkr')


@pytest.mark.parametrize('text', [
    '这里用的是历史成交条接口，文档没有列出期权未平仓量的历史条类型。这个限制不代表其他数据商都没有历史未平仓量。',
    '历史TRADES条接口文档没有列出按日期的未平仓量字段。',
])
def test_explicit_historical_trade_bar_interface_type_omission(text, docs):
    assert claim_facets(text)=={'historical_oi_availability'}
    assert validate_expert_grounding([part(text,'expert.history_oi')],docs,context_kind='historical_ibkr')
    with pytest.raises(ValueError,match='does not support'):
        validate_expert_grounding([part(text,'expert.oi_cycle')],docs,context_kind='historical_ibkr')


@pytest.mark.parametrize('text', [
    '历史成交条接口文档列出期权未平仓量字段。',
    '本次历史成交条接口的未平仓量有统计日期。',
    '此处历史成交条接口只描述价格，当前样本未平仓字段为空。',
    '历史账单接口文档没有列出收入类型。',
])
def test_interface_name_alone_or_another_domain_does_not_claim_oi_unavailability(text):
    assert 'historical_oi_availability' not in claim_facets(text)


def test_historical_trade_interface_alias_does_not_override_import_provenance(docs):
    text='历史成交条接口文档没有列出期权未平仓量的历史条类型。'
    with pytest.raises(ValueError,match='Imported missing fields'):
        validate_expert_grounding([part(text,'expert.history_oi')],docs,'这个CSV为什么没有持仓？','historical_import')
