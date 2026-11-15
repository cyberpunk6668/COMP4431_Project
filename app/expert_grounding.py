"""Bounded, auditable claim-facet checks for reviewed expert passages.

This is a rule-based source-support policy, not semantic entailment, a trained
classifier or an accuracy score. It checks explicitly recognized Chinese/English
financial knowledge claims and query facets. Saved numeric observations remain
the caller's responsibility. No network, account, model or chat-module imports.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re


SUPPORT_FACETS = frozenset({
    "volume_vs_oi", "put_call_limits", "oi_reporting_cycle", "iv_direction_limits",
    "option_price_factors", "bid_ask_execution", "historical_permissions",
    "expired_eod_limits", "historical_volume_filtering", "historical_bar_semantics",
    "historical_time_basis", "historical_contract_iv_limits", "contract_comparability",
    "historical_oi_availability",
    "expiry_payoff",
})

EXPERT_GROUNDING_INSTRUCTIONS = """Expert passages have a reviewed supports list.
Each paragraph that makes an explicit financial knowledge claim must cite a
retrieved expert passage whose supports facet covers that claim. Local numeric
IDs support observations, not general expert definitions. A merely valid ID or
a citation elsewhere in the answer is insufficient. Multiple knowledge topics
in a paragraph each need a supporting citation; prefer focused paragraphs.
Put/call counts not identifying people/intention need put_call_limits. Historical
OHLC not being synchronized BBO needs historical_bar_semantics; expired_eod_limits
cannot substitute for either. Missing is not zero is a local data policy.
Cover required_query_facets explicitly with relevant expert citations. Discuss
only relevant supplied topics: do not add unasked historical IV or other side
topics. Use source-review boundaries: a scoped historical-bars OI limitation does
not mean all APIs or vendors lack OI. Sources do not authenticate imported prices.
"""


def _has(pattern, text):
    return bool(re.search(pattern, text, re.I))


def _without_local_exclusions(text):
    """Do not mistake an explicit omitted-cost list for a pricing relation.

    Only finite list items after an exclusion verb are masked for the pricing /
    execution detectors. Other clauses, actual effect/guarantee statements and
    all original text remain subject to the normal claim and quantity checks.
    """
    if not _has(r"试算|本例|教学|(?:this|selected|our).{0,25}(?:trial|calculation|example)|synthetic|expiry trial", text):
        return text
    zh_item = r"(?:手续费|税费|交易费用|费用|融资|股息|利率|滑点|行权|指派|提前指派|分腿执行|提前平仓|保证金)"
    en_item = r"(?:fees?|tax(?:es)?|costs?|funding|dividends?|interest|slippage|exercise|assignment|early assignment|legging|early closing)"
    text = re.sub(r"(?:不含|不包括|未计入|排除)" + zh_item + r"(?:[、，,或及和\s]*" + zh_item + r")*(?:等(?:额外)?(?:影响|风险|成本))?", "", text)
    text = re.sub(r"\b(?:excludes?|does not include|not including)\s+" + en_item + r"(?:[,/\s]*(?:and |or )?" + en_item + r")*", "", text, flags=re.I)
    # This states the application's entered fill assumptions, not a general
    # assertion that a midpoint quote can actually be executed.
    return re.sub(r"(?:自然价|natural)\s*(?:与|和|及|/|and)\s*(?:中间价|midpoint)\s*(?:只是|仅是|仅为|都只是)(?:成交|执行|填单)假设", "", text, flags=re.I)


def _synthetic_metadata_provenance(text):
    """Identify only a local authored-record disclaimer, not historical theory.

    Active solely in the server-approved synthetic-lab context. A paragraph
    introducing general historical intervals, broker timing or receipt/event
    distinctions still requires the historical-time source even if it also
    mentions a synthetic lesson.
    """
    authored = _has(r"合成(?:教学)?(?:记录|样本|数据)|人为构造|人造输入|固定教学日期|synthetic (?:teaching )?(?:record|sample|data)|authored inputs", text)
    deny_current = _has(r"不(?:是|代表|反映|说明|等于|能.{0,8}(?:判断|预测)).{0,14}(?:当前|现在|此刻)|not.{0,18}(?:current|present)|cannot.{0,18}(?:current|predict)", text)
    general_history = _has(r"历史(?:区间|请求|成交条|数据只能|数据不能)|导入时间|接收时间|historical (?:interval|request|bar)|ingestion time|receipt time", text)
    return authored and deny_current and not general_history


def claim_facets(text: str, context_kind="snapshot") -> set[str]:
    """Recognize explicit knowledge relations, including their negations.

    A negation such as 'put volume is not bearish headcount' IS a knowledge
    claim requiring its own source. No paragraph-wide negation exemption exists.
    Mere occurrence of 'put', 'IV' or a local price direction is insufficient.
    """
    if not isinstance(text, str):
        return set()
    text = text[:6000]
    pricing_text = _without_local_exclusions(text)
    facets = set()
    volume = _has(r"成交(?:量|计数|统计)|期间成交|\bvolume\b", text)
    oi = _has(r"未平仓|持仓|(?<![A-Za-z])OI(?![A-Za-z])|open interest|outstanding contracts", text)
    historic = _has(r"历史|盘中|分钟|\bhistor\w*\b|\bOHLC\b|\bbars?\b", text)
    if (volume and oi and _has(r"不同|区别|差别|换算|转换|替代|different|convert|substitut", text)) or (
        volume and _has(r"(?:^|[。；;])\s*成交量(?:是|会|通常)?(?:统计|计数|描述|衡量).{0,25}(?:交易|合约)|(?:^|[.;])\s*volume counts? (?:the )?contracts? (?:traded|trad)|(?:^|[.;])\s*volume measures? (?:trading|activity)", text)) or (
        oi and _has(r"(?:统计|计数|描述).{0,25}(?:未结清|尚未结清|尚未平仓)|counts? (?:the )?(?:outstanding|open) contracts?", text)):
        facets.add("volume_vs_oi")
    if (_has(r"看跌|看涨|合约计数|成交计数|成交统计|\bputs?\b|\bcalls?\b|contract counts?", text) and
        _has(r"人数|多数人|参与人|主动(?:方|买卖|方向)|开平仓|看空的人|对冲|保护|组合策略|多腿|提前行权|headcount|people|majority|aggressor|opening.or.closing|hedg|multi.leg|early.exercise", text)) or _has(r"每笔(?:成交|交易).{0,20}(?:买方|买家|买卖双方)|every trade.{0,30}(?:buyer|seller|two sides)", text):
        facets.add("put_call_limits")
    if _has(r"\b(?:put|call) (?:volume|activity|counts?)\b.{0,45}\b(?:mean\w*|show\w*|imply|implies|prove\w*|indicat\w*|infer\w*)\b.{0,35}\b(?:bullish|bearish|pessimistic|optimistic)\b", text) or _has(r"\b(?:trade|traded contract|contract)\b.{0,20}\b(?:has|have|involves?)\b.{0,15}\b(?:both )?(?:a )?buyer\b.{0,20}\b(?:a )?seller\b", text):
        facets.add("put_call_limits")
    if _has(r"(?:看跌|看涨)(?:成交(?:量)?|成交计数|合约计数).{0,30}(?:说明|表明|意味着|证明|代表|反映|预测).{0,20}(?:看空|看多|涨跌方向|市场情绪)", text):
        facets.add("put_call_limits")
    if oi and _has(r"隔夜|清算|报告周期|统计周期|独立.{0,8}(?:周期|报告时点)|reporting cycle|reconcil|overnight|separate.{0,15}cycle", text):
        facets.add("oi_reporting_cycle")
    # An explicit request to obtain/check independently dated OI is a reporting
    # principle, unlike merely displaying a sample's date or a null field.
    if oi and _has(r"(?:另取|取得|获取)[^。；;]{0,18}(?:带|有|包含)[^。；;]{0,6}独立(?:的)?(?:统计|报告|持仓)日期[^。；;]{0,8}(?:未平仓量|持仓)(?:来源|数据)?|(?:核对|确认|检查)[^。；;]{0,12}(?:未平仓量|持仓)[^。；;]{0,8}独立(?:的)?(?:统计|报告|持仓)日期", text):
        facets.add("oi_reporting_cycle")
    if _has(r"隐含波动|波动率|\bIV\b|implied volatility", text) and _has(r"(?:波动|预期)(?:幅度|尺度)|涨跌方向|不.{0,15}(?:指明|预测|表示).{0,10}方向|either direction|magnitude|fluctuations?|not.{0,15}(?:predict|specify).{0,10}direction", text):
        facets.add("iv_direction_limits")
    if (_has(r"期权(?:价格|定价)|权利金|option (?:price|premium)|premiums?", pricing_text) and _has(r"剩余期限|时间价值|股息|利率|dividend|interest rate|remaining term|time value", pricing_text)) or _has(r"时间价值.{0,30}(?:衰减|侵蚀|到期)|time value.{0,30}(?:erod|decay|expir)", pricing_text):
        facets.add("option_price_factors")
    if _has(r"宽.{0,5}价差|价差.{0,8}(?:越大|较大|变宽)|(?:中间价|midpoint).{0,25}(?:保证|成交|fill)|(?:wider?|large) spreads?.{0,30}(?:slippage|execut|liquidity)|滑点", pricing_text):
        facets.add("bid_ask_execution")
    if historic and _has(r"(?:需要|要求|绕过).{0,15}(?:订阅|权限)|(?:订阅|权限).{0,15}(?:需要|要求)|免费|requires?.{0,25}subscription|bypass.{0,20}permission|free access", text):
        facets.add("historical_permissions")
    if (_has(r"已到期|过期期权|expired options?", text) and _has(r"不可|无法|不提供|不支持|限制|unavailable|not.{0,20}(?:available|support|provide)", text)) or _has(r"期权(?:日终|EOD)|(?:native|option).{0,15}(?:end.of.day|EOD)", text):
        facets.add("expired_eod_limits")
    if historic and _has(r"过滤|压缩|调整|filter|compress|adjust|(?:不同于|不同|差异).{0,20}实时累计|(?:differ|different).{0,25}(?:live|streaming|cumulative)", text):
        facets.add("historical_volume_filtering")
    bar_like = _has(r"(?<![A-Za-z])(?:OHLC|bars?)(?![A-Za-z])|历史(?:成交条|价格条|报价条|报价|BID_ASK)|分钟(?:数据|记录|价格)|盘中成交(?:条|汇总)|(?:区间|所收|历史)成交记录.{0,8}末值|成交条(?:的)?末值|成交条.{0,6}区间(?:汇总|聚合)|(?:interval|received|historical) trade records?.{0,15}end values?", text)
    if bar_like and _has(r"同步.{0,10}(?:报价|双边)|双边报价|时间平均|区间(?:极值|聚合|汇总)|不是.{0,12}(?:结算价|官方收盘)|不能.{0,25}(?:价差|希腊值)|\b(?:BBO|NBBO)\b|synchroni[sz]|time.average|interval aggregates?|not.{0,20}(?:official settlement|settlement prices?|executable quote)", text):
        facets.add("historical_bar_semantics")
    if (_has(r"历史|导入|本地接收|接收时间|保存.{0,5}样本|historical|ingestion|receipt time|saved (?:sample|snapshot)", text) and
        _has(r"不代表.{0,15}(?:当前|现在|此刻)|不能(?:据此|由此)?(?:代表|说明|判断|断定|反映|推断).{0,12}(?:当前|现在|此刻)|不是.{0,12}(?:交易发生|交易时间)|不等于.{0,12}(?:交易|当前)|not.{0,25}(?:current|market event|exchange time)|present market.{0,20}cannot|cannot.{0,20}present", text)) or (
        historic and _has(r"历史请求.{0,20}(?:指定|设置).{0,20}(?:时区|交易时段)|(?:返回时间|时间格式).{0,20}(?:时区|登录)|(?:更新中|未结束).{0,20}(?:价格条|区间)|(?:未完成|未结束).{0,15}(?:不能|不可).{0,15}(?:完成|复盘)|historical requests?.{0,25}(?:specif|timezone)|returned.{0,20}(?:timestamp|time).{0,25}(?:timezone|login)|(?:updating|unfinished).{0,15}bars?", text)):
        facets.add("historical_time_basis")
    if historic and _has(r"(?:不是|并非)(?:当前|现在|此刻)(?:行情|市场状态|市场情绪)|不(?:当作|视为)(?:当前|现在|此刻)(?:行情|市场状态|市场情绪)", text):
        facets.add("historical_time_basis")
    if historic and _has(r"隐含波动|\bIV\b|implied.volatility|希腊值|greeks", text) and _has(r"(?:字段|类型).{0,30}(?:标的|股票|指数|基金)|不等于.{0,20}(?:合约|希腊)|回填|backfill|(?:type|field).{0,30}(?:stock|indice|ETF)|per.contract.{0,20}(?:unavailable|missing)", text):
        facets.add("historical_contract_iv_limits")
    if _has(r"合约(?:身份|范围|规格)|共同样本|样本(?:范围|变化)|contract (?:identity|window|membership|specification|scope)|sample (?:membership|window)", text) and _has(r"跨日期比较.{0,8}(?:应|需|要|必须)|比较(?:前|时)?.{0,12}(?:需要|必须|应|先|要).{0,20}(?:合约|样本|口径)|(?:需要|必须|应当|检查包括[:：]?).{0,12}(?:确认|核对).{0,35}(?:合约|样本)|(?:合约范围|样本范围).{0,25}(?:变化|改变).{0,25}(?:不能|无法|不可).{0,25}(?:解释|当作|比较)|(?:compar|across dates).{0,25}(?:verify|check|match|same)|(?:contract|sample) (?:membership|window).{0,25}chang.{0,25}(?:prevent|not|cannot)|(?:确认|核对).{0,12}(?:合约范围|合约规格|样本范围).{0,12}(?:一致|相同|匹配).{0,8}(?:后再|再|之后).{0,6}(?:比较|对比)|(?:verify|confirm|check).{0,15}(?:matching|same|identical).{0,10}contract (?:scope|window|membership|specification).{0,15}before compar", text):
        facets.add("contract_comparability")
    # A changed paired-strike/contract set invalidates this comparison, not
    # merely a naked observation about which contracts happened to arrive.
    if _has(r"(?:配对)?(?:行权价|合约|样本)(?:集合|范围|成员)(?:发生)?(?:了)?(?:改变|变化|变动).{0,24}(?:不可比|不能(?:直接)?比较|无法(?:直接)?比较|不能.{0,12}(?:增加|减少|增减))", text) or _has(r"\b(?:paired[ -])?(?:strike|contract|sample)[ -](?:sets?|membership|windows?)\b.{0,12}\b(?:changed?|differ\w*)\b.{0,35}\b(?:incomparab\w*|not comparable|cannot be compar\w*|cannot.{0,15}(?:increas\w*|decreas\w*))", text):
        facets.add("contract_comparability")
    if _has(r"(?:确认|核对).{0,40}(?:合约范围|合约规格).{0,12}(?:是否一致|是否相同|一致|匹配).{0,40}(?:只有|仅).{0,15}可比.{0,20}(?:变化|方向|解读)", text):
        facets.add("contract_comparability")
    if _has(r"(?:确认|核对)(?:比较|对比)的?(?:是|是否为|是否是)(?:同一|相同)(?:合约范围|合约规格|样本范围)", text):
        facets.add("contract_comparability")
    if oi and _has(r"reqHistoricalData|whatToShow|历史(?:接口|数据类型|持仓)|历史(?:成交|TRADES)条接口|OI历史条|historical (?:API|type|open interest)|historical bars?", text) and _has(r"不提供|不包含|没有.{0,20}(?:字段|类型)|未列|不支持|不可用|无法|缺少|不能恢复|does not|no.{0,15}(?:type|field)|not.{0,20}(?:available|provide|support)|unavailable", text):
        facets.add("historical_oi_availability")
    if oi and _has(r"历史(?:成交|TRADES)条.{0,100}(?:本身不提供|不提供按日|不包含)[^，。；;：:]{0,12}(?:未平仓|持仓)(?:量)?(?:字段|数据|历史条)", text):
        facets.add("historical_oi_availability")
    # Deliberately limited to explicit terminal-payoff relations. Merely naming
    # a strategy, an evidence-card label or a trial is not a knowledge claim.
    if _has(r"(?:到期(?:净)?盈亏|到期(?:现金)?(?:价值|值|收益)|最大(?:损失|亏损|收益|盈利)|盈亏平衡(?:价|点|标的价)?)[^。；;，,]{0,55}(?:等于|是(?!否)|为(?!什么|何)|取决于|限于|上限|无限|不限|净支付|权利金|加|减)|(?:maximum (?:loss|gain|profit)|break.?even|(?:expiry|expiration|terminal) (?:cash )?(?:payoff|profit|p/l))[^.;,]{0,85}(?:equals?|is |are |limited|unlimited|premium|debit|strike|minus|plus)", text):
        facets.add("expiry_payoff")
    if context_kind == "synthetic_lab" and _synthetic_metadata_provenance(text):
        facets.discard("historical_time_basis")
    return facets


def required_query_facets(question, context_kind="snapshot") -> set[str]:
    text = str(question or "")[:4000]
    result = set()
    oi = _has(r"未平仓|持仓|(?<![A-Za-z])OI(?![A-Za-z])|open interest", text)
    volume = _has(r"成交量|成交计数|\bvolume\b", text)
    historical = context_kind in {"historical", "historical_options", "historical_ibkr", "historical_import", "historical_demo"}
    if context_kind == "synthetic_lab" and _has(r"真实历史|历史(?:区间|数据|请求|成交条)|historical (?:data|interval|request|bar)", text):
        historical = True
    ibkr_history_question = _has(r"IBKR|reqHistoricalData|whatToShow|\bAPI\b|网关|历史接口", text)
    if oi and volume and _has(r"为什么|为何|区别|不同|矛盾|冲突|why|differ|conflict|compare", text):
        result.add("volume_vs_oi")
    if _has(r"看空|看多|情绪|多数人|sentiment|bearish|bullish|majority", text):
        result.add("put_call_limits")
    if historical and _has(r"现在|当前|此刻|实时|\bnow\b|current|present", text):
        result.add("historical_time_basis")
    if oi and _has(r"报告|周期|统计日期|时点|隔夜|as.of|asof|reporting|overnight", text):
        result.add("oi_reporting_cycle")
    if historical and (context_kind not in {"historical_import", "historical_demo"} or ibkr_history_question) and oi and _has(r"(?:为什么|为何).{0,5}(?:没有|缺失|缺少|未提供|未返回|不提供|不支持|不可用|没给|未给|不能(?:返回|提供|获取|查询|下载))|历史.*(?:有没有|可否|支持)|why.{0,30}(?:missing|not (?:available|provided|returned)|unavailable)|historical open interest", text):
        result.add("historical_oi_availability")
    if _has(r"什么是|定义|什么意思|what is|define|definition", text) and _has(r"隐含波动|波动率|\bIV\b|volatility", text):
        result.add("iv_direction_limits")
    if _has(r"价差|滑点|\bspread\b|slippage", text):
        result.add("historical_bar_semantics" if historical and _has(r"bar|OHLC|历史报价|分钟|同步", text) else "bid_ask_execution")
    if historical and _has(r"订阅|权限|免费|subscription|permission|free", text):
        result.add("historical_permissions")
    if _has(r"已到期|过期期权|期权日终|\bEOD\b|expired option", text):
        result.add("expired_eod_limits")
    if historical and _has(r"希腊值|greeks|历史IV|historical (?:contract )?(?:IV|implied volatility)", text):
        result.add("historical_contract_iv_limits")
    if context_kind == "synthetic_lab" and _has(r"试算|到期|盈亏|成本|权利金|收益|损失|亏损|执行价|行权价|trial|payoff|break.?even|cost|premium|max(?:imum)? (?:loss|gain)|strike", text):
        result.add("expiry_payoff")
    return result


def _docs(retrieved):
    values = list(retrieved.values()) if isinstance(retrieved, dict) else list(retrieved or [])
    return {item["id"]: item for item in values if isinstance(item, dict) and isinstance(item.get("id"), str)}


def _validate_expiry_relation(text, cited_sources):
    """Reject a few explicit terminal-payoff contradictions, not general math.

    The numerical formula remains server computed. These checks are deliberately
    bounded to reviewed strategy passages and affirmative relation wording;
    they do not turn the facet allowlist into a general entailment guarantee.
    """
    strategies = {doc.get("strategy") for doc in cited_sources if "expiry_payoff" in doc.get("supports", [])}
    if not strategies:
        return
    if _has(r"(?:最大(?:损失|亏损))(?:是|为|会|将|可以|可能|理论上|没有)*\s*(?:无限|无上限|不受限|不限)|maximum loss\s+(?:is|can be)\s+(?:unlimited|unbounded)", text):
        raise ValueError("Reviewed debit strategies do not have unlimited maximum loss")
    if strategies <= {"long_put", "call_debit_spread"} and _has(r"最大(?:收益|盈利)(?:是|为|会|将|可以|可能|理论上)*\s*(?:无限|无上限|不受限|不限)|maximum (?:gain|profit)\s+(?:is|can be)\s+(?:unlimited|unbounded)", text):
        raise ValueError("Reviewed put or debit-spread maximum gain is finite")
    if strategies == {"long_call"} and _has(r"盈亏平衡(?:标的)?价(?:为|是|等于)执行价减|break.?even\s+is\s+(?:the\s+)?strike\s+minus", text):
        raise ValueError("Long-call breakeven adds premium")
    if strategies == {"long_put"} and _has(r"盈亏平衡(?:标的)?价(?:为|是|等于)执行价加|break.?even\s+is\s+(?:the\s+)?strike\s+plus", text):
        raise ValueError("Long-put breakeven subtracts premium")


def retrieve_expert_context(knowledge, question, context_kind="snapshot", context_facets=(), limit=6, *, preferred_ids=()):
    """Fuse real lexical results with transparent reviewed-facet completion.

    A corpus lookup has NO BM25/character rank or RRF score. Real query ranks
    remain untouched when a ranked result is selected to fill a needed facet.
    """
    limit = max(0, min(int(limit), 6))
    if not limit:
        return []
    ranked = knowledge.search(question, limit=6)
    corpus = _docs(getattr(knowledge, "documents", []))
    by_id = _docs(ranked)
    positions = {doc["id"]: index+1 for index, doc in enumerate(ranked)}
    required = sorted(required_query_facets(question, context_kind))
    requested = required + [facet for facet in context_facets if facet in SUPPORT_FACETS and facet not in required]
    selected, covered = [], set()
    for facet in requested:
        if facet in covered:
            continue
        candidates = [doc for doc in ranked if facet in doc.get("supports", [])]
        candidates += [doc for key, doc in sorted(corpus.items()) if key not in by_id and facet in doc.get("supports", [])]
        # A server-selected strategy can identify its own reviewed definition.
        # This preference never creates a source or changes its support facets.
        candidates.sort(key=lambda doc: doc["id"] not in preferred_ids)
        if not candidates or len(selected) >= limit:
            continue
        doc = deepcopy(candidates[0])
        if doc["id"] in {item["id"] for item in selected}:
            covered.update(doc.get("supports", []))
            continue
        if doc["id"] not in by_id:
            doc["retrieval"] = {"method": "curated_support_facet", "embedding": False,
                                "bm25_rank": None, "char_rank": None, "rrf_score": None,
                                "matched_terms": [], "matched_ngrams": [], "matched_topics": [],
                                "knowledge_version": getattr(knowledge, "version", "unknown"),
                                "corpus_sha256": getattr(knowledge, "corpus_sha256", None)}
        doc.setdefault("retrieval", {}).update(selection_reason="query_facet" if facet in required else "context_facet",
                                               selected_facet=facet, question_rank=positions.get(doc["id"]))
        selected.append(doc)
        covered.update(doc.get("supports", []))
    for item in ranked:
        if len(selected) >= limit:
            break
        if item["id"] in {doc["id"] for doc in selected}:
            continue
        doc = deepcopy(item)
        doc.setdefault("retrieval", {}).update(selection_reason="lexical_rank", question_rank=positions[item["id"]])
        selected.append(doc)
    return selected


def validate_expert_grounding(parts, retrieved, question="", context_kind="snapshot", local_ids=()):
    sources = _docs(retrieved)
    local_ids = set(local_ids or ())
    audits, covered = [], set()
    for index, part in enumerate(parts):
        where = f"paragraph {index+1}: "
        facets = claim_facets(part.get("text", ""), context_kind)
        if (context_kind in {"historical_import", "historical_demo", "synthetic_lab"} and "historical_oi_availability" in facets
                and not _has(r"IBKR|reqHistoricalData|whatToShow|\bAPI\b|网关|历史接口", str(question))):
            raise ValueError(where + "Imported missing fields do not establish an IBKR historical API cause")
        cited = [key for key in part.get("evidence_ids", []) if str(key).startswith("expert.")]
        if any(key not in sources for key in cited):
            raise ValueError(where + "Expert citation was not in the retrieved context")
        if any(key not in sources and key not in local_ids for key in part.get("evidence_ids", [])):
            raise ValueError(where + "Unknown local or expert reference")
        support = {facet for key in cited for facet in sources[key].get("supports", []) if facet in SUPPORT_FACETS}
        missing = facets - support
        if missing:
            raise ValueError(where + "Expert citation does not support claim facets: " + ",".join(sorted(missing)))
        if "expiry_payoff" in facets:
            _validate_expiry_relation(part.get("text", ""), [sources[key] for key in cited])
        unrelated = [key for key in cited if not set(sources[key].get("supports", [])) & facets]
        if unrelated:
            # Echo only known, schema-shaped source IDs. Neither model prose nor
            # unknown/untrusted reference strings enter a repair diagnostic.
            safe_ids = [key for key in unrelated if re.fullmatch(r"expert\.[a-z_]{1,80}", key)]
            raise ValueError(where + "Expert citation is unrelated to recognized claims in its paragraph: " + ",".join(safe_ids or ["known_source"]))
        covered.update(facets)
        audits.append({"part": index, "claim_facets": sorted(facets), "expert_source_ids": cited,
                       "supporting_sources": {facet: [key for key in cited if facet in sources[key].get("supports", [])] for facet in sorted(facets)}})
    required = required_query_facets(question, context_kind)
    if required - covered:
        raise ValueError("Answer omitted requested expert facets: " + ",".join(sorted(required-covered)))
    if _has(r"复盘|总结.{0,8}(?:数据|样本)|review.{0,15}(?:data|sample)|summari[sz]e.{0,15}(?:data|sample)", str(question)) and local_ids:
        if not any(set(part.get("evidence_ids", [])) & local_ids for part in parts):
            raise ValueError("A data review must cite local sample evidence")
    return {"method": "reviewed_support_facets", "scope": "bounded_rule_checks_not_general_entailment",
            "required_query_facets": sorted(required), "covered_facets": sorted(covered), "paragraphs": audits}


def _original_parts(content, *, indexed=False):
    if not isinstance(content, str) or len(content) > 12000:
        return []
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, dict) or not isinstance(parsed.get("response"), list):
        return []
    safe = [(index, part) for index, part in enumerate(parsed["response"][:6])
            if isinstance(part, dict) and isinstance(part.get("text"), str)]
    return safe if indexed else [part for _, part in safe]


def expert_citation_repair_plan(parts, retrieved, allowed_ids, *, context_kind="snapshot"):
    """Return citation-only guidance for every safely parsed original paragraph.

    Does not edit text, citations or answers. Candidates must already be in the
    supplied context AND the repair allowance. Unknown/disallowed references and
    missing facets without candidates remain explicit blocked issues. Raw prose
    and untrusted unknown IDs never enter this structured repair guidance.
    """
    if isinstance(parts, str):
        indexed = _original_parts(parts, indexed=True)
    elif isinstance(parts, list):
        indexed = [(index, part) for index, part in enumerate(parts[:6])
                   if isinstance(part, dict) and isinstance(part.get("text"), str)]
    else:
        return []
    sources = _docs(retrieved)
    allowed = {key for key in (allowed_ids or ()) if isinstance(key, str)} if not isinstance(allowed_ids, str) else set()
    plans = []
    for index, part in indexed:
        facets = claim_facets(part["text"], context_kind)
        raw_refs = part.get("evidence_ids", [])
        malformed = not isinstance(raw_refs, list)
        if not malformed:
            malformed = len(raw_refs) > 64 or any(not isinstance(key, str) for key in raw_refs)
        refs = [key for key in raw_refs[:64] if isinstance(key, str)] if isinstance(raw_refs, list) else []
        expert_refs = [key for key in refs if key.startswith("expert.")]
        provided = [key for key in expert_refs if key in sources]
        supported = {facet for key in provided for facet in sources[key].get("supports", []) if facet in SUPPORT_FACETS}
        missing = sorted(facets - supported)
        by_facet = {facet: sorted(key for key, doc in sources.items()
                        if key in allowed and re.fullmatch(r"expert\.[a-z_]{1,80}", key) and facet in doc.get("supports", []))
                    for facet in missing}
        remove = sorted({key for key in provided if re.fullmatch(r"expert\.[a-z_]{1,80}", key)
                         and not set(sources[key].get("supports", [])) & facets})
        unprovided_count = sum(key not in sources for key in expert_refs)
        disallowed_count = sum(key not in allowed for key in refs)
        unresolved = [facet for facet, candidates in by_facet.items() if not candidates]
        blocked = malformed or bool(unprovided_count or disallowed_count or unresolved)
        plans.append({"paragraph": index+1, "claim_facets": sorted(facets), "missing_facets": missing,
                      "add_candidates": sorted({key for values in by_facet.values() for key in values}),
                      "candidates_by_facet": by_facet, "remove_unrelated": remove,
                      "unresolved_facets": unresolved, "unprovided_expert_reference_count": unprovided_count,
                      "disallowed_reference_count": disallowed_count, "malformed_references": malformed,
                      "status": "blocked" if blocked else "needs_citation_fix" if missing or remove else "supported"})
    return plans


def expert_repair_allowance(content, retrieved, *, context_kind="snapshot") -> set[str]:
    """Permit rebinding existing recognized claims to already supplied sources."""
    facets = set().union(*(claim_facets(part["text"], context_kind) for part in _original_parts(content)))
    return {key for key, doc in _docs(retrieved).items() if set(doc.get("supports", [])) & facets}


def validate_repair_claims(original_content, candidate_parts, retrieved=None, *, context_kind="snapshot"):
    """A source-format repair cannot introduce a new recognized knowledge topic."""
    original = set().union(*(claim_facets(part["text"], context_kind) for part in _original_parts(original_content)))
    candidate = set().union(*(claim_facets(part.get("text", ""), context_kind) for part in candidate_parts))
    if candidate - original:
        raise ValueError("Schema repair introduced new expert claim facets: " + ",".join(sorted(candidate-original)))
    return {"original_facets": sorted(original), "retained_facets": sorted(candidate)}
