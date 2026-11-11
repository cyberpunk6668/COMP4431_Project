"""Generate an evidence-linked synthesis while keeping all figures local."""
import math
import re

from pydantic import BaseModel, ConfigDict, Field


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=8, max_length=650)
    evidence_ids: list[str] = Field(min_length=1, max_length=16)


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    condition: str = Field(min_length=8, max_length=400)
    implication: str = Field(min_length=8, max_length=500)
    evidence_ids: list[str] = Field(min_length=1, max_length=16)


class Narrative(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: Claim
    observations: list[Claim] = Field(min_length=2, max_length=5)
    conflicts: list[Claim] = Field(max_length=3)
    scenarios: list[Scenario] = Field(min_length=1, max_length=3)
    limitations: list[str] = Field(min_length=1, max_length=8)


SYSTEM = """Write a substantive collective options analysis in the requested language.
The reader is a non-specialist. Use everyday words and short sentences. Explain
what the observations mean for understanding this sample. Define necessary terms
in context once. Avoid unexplained abbreviations such as HHI, OI, IV or Greeks;
say concentration, outstanding contracts, or uncertainty priced into options.
In Chinese, prefer 尚未结清的合约 over 库存. Only concentration shapes are provided:
they do not reveal exact peak strike locations or whether traded and outstanding
contracts occupy different or disjoint strike prices. Do not assert that locations differ.
Call and put are contract types, not counts of optimistic or pessimistic people.
Give a short takeaway before detail and distinguish observation from interpretation.
Use only the supplied anonymized cohort aggregates. Analyze how liquidity, strike
concentration, put/call activity, outstanding inventory and relative IV support or
conflict with each other. Different cohorts may be symbols or expirations.
Do not pool their totals. Explain why opposing signals can coexist.
Delayed or frozen cohorts permit descriptive snapshot analysis only. Quotes were
captured sequentially, not simultaneously. Missing evidence limits conclusions.
Every trade has a buyer and seller; aggregate volume does not label aggressor side
or opening/closing activity. OI is outstanding inventory with a separate
reporting cycle; volume versus OI cannot reveal new positioning. Concentration
does not establish support/resistance, dealer positioning, gamma exposure or max pain.
Do not infer news mood, future prices, probability, or trade recommendations.
Write original, specific reasoning linking several supplied aggregates, not a list
of dictionary definitions. Each summary, observation, conflict and scenario must
cite one or more exact input evidence IDs. State alternatives and what an additional
observation would help distinguish. Leave conflicts empty if no contradiction exists.
Use qualitative prose only: no digits or percent signs anywhere in prose. The UI
displays exact figures from the cited local evidence. Evidence IDs may contain digits.
The supplied cohort identifiers g0, g1, g2 and g3 may appear in prose.
Do not call spreads, IV or activity historically high, low or unusual without an
explicit baseline. Compare observed relative differences and concentration shapes.
Call/put identify option contract types, not aggressor trade direction or bullish/bearish intent.
Different activity shares with equal IV across different underlyings merely coexist:
do not call this a contradiction or say pricing SHOULD diverge or respond.
Never attribute differences primarily to activity, quote conditions, inventory or
time sampling from these observations alone. Frame alternatives as unverified
possibilities. Conditional scenarios should explain how evidence would be reassessed,
not establish why it changed. Refer to selected-expiry ATM IV, never near-month IV:
absolute dates and tenor are deliberately withheld. Only use explicit expiry_order.
Return JSON only with this schema:
{"summary":{"text":"...","evidence_ids":["g0.volume_put_share"]},
"observations":[{"text":"...","evidence_ids":["..."]},{"text":"...","evidence_ids":["..."]}],
"conflicts":[],"scenarios":[{"condition":"If ...","implication":"...","evidence_ids":["..."]}],
"limitations":["..."]}
Provide a concise summary, two to four observations, up to two conflicts, one or two
conditional scenarios, and concrete limitations. Requested language: """


def _aggregate(record: dict) -> bool:
    key = record.get("id", "")
    value = record.get("value")
    if type(value) not in (int, float) or not math.isfinite(value):
        return False
    if any(part in key for part in ("peak_strike", "spot_price", "strike_price", "premium_value")):
        return False
    return any(part in key for part in ("share", "hhi", "total", "coverage", "spread", "gap", "atm_iv", "skew", "straddle", "count"))


def build_model_evidence(reports: list[dict], comparison: dict | None = None) -> dict:
    """Send anonymized aggregate values, with safe IDs that resolve to local evidence."""
    cohorts = []
    for index, report in enumerate(reports):
        collective = report["collective"]
        if collective["assessment"]["status"] != "descriptive":
            continue
        records = []
        for item in collective["evidence"]:
            if _aggregate(item):
                records.append({"id": f"g{index}.{item['id']}", "value": item["value"],
                                "label": item.get("label", item["id"]), "description": item.get("description", ""),
                                "unit": item.get("unit", ""), "scope": f"g{index}"})
        if len(records) >= 2:
            cohorts.append({"id": f"g{index}", "market_data_status": report["quality"]["market_data_status"],
                            "assessment_status": "descriptive", "evidence": records})
    comparisons = []
    for item in (comparison or {}).get("evidence", []):
        if _aggregate(item):
            comparisons.append({"id": f"comparison.{item['id']}", "value": item["value"],
                                "label": item.get("label", item["id"]), "description": item.get("description", ""),
                                "unit": item.get("unit", ""), "scope": "comparison"})
    relations = []
    comparable_terms = {
        (item["near_report_index"], item["far_report_index"])
        for item in (comparison or {}).get("term_structure", []) if item.get("status") == "comparable"
    }
    for index, first in enumerate(reports):
        for second_index, second in enumerate(reports[index + 1:], index + 1):
            first_context, second_context = first["snapshot"], second["snapshot"]
            first_expiry, second_expiry = first_context["expiration"], second_context["expiration"]
            order = "same"
            if first_expiry != second_expiry:
                order = "before" if first_expiry < second_expiry else "after"
            relations.append({
                "first": f"g{index}", "second": f"g{second_index}",
                "same_underlying": first_context["symbol"] == second_context["symbol"],
                "expiry_order": order,
                "term_iv_comparable": (index, second_index) in comparable_terms or (second_index, index) in comparable_terms,
            })
    return {"scope": "Limited selected strike windows; anonymized cohorts captured sequentially.",
            "cohorts": cohorts, "comparisons": comparisons, "cohort_relations": relations}


def read_model_report(content: str, allowed: set[str]) -> dict:
    if len(content) > 15000:
        raise ValueError("Narrative is too large")
    report = Narrative.model_validate_json(content)
    claims = [report.summary, *report.observations, *report.conflicts, *report.scenarios]
    for claim in claims:
        if len(set(claim.evidence_ids)) != len(claim.evidence_ids) or not set(claim.evidence_ids) <= allowed:
            raise ValueError("Unknown or duplicate evidence reference")
    texts = [report.summary.text, *[item.text for item in report.observations],
             *[item.text for item in report.conflicts], *report.limitations]
    texts.extend(text for item in report.scenarios for text in (item.condition, item.implication))
    cohorts = {identifier.split(".")[0] for identifier in allowed if re.match(r"g[0-3]\.", identifier)}
    for text in texts:
        checked_text = text
        for cohort in cohorts:
            checked_text = re.sub(rf"(?<![A-Za-z0-9_]){cohort}(?![A-Za-z0-9_])", "cohort", checked_text)
        if not text.strip() or len(text) > 650 or any(character.isdigit() for character in checked_text) or "%" in text or "％" in text:
            raise ValueError("Numeric claims must be rendered from local evidence")
        if re.search(r"稳赚|必涨|必跌|保证收益|guaranteed profit|buy now|sell now", text, re.I):
            raise ValueError("Unsupported trading claim")
        if re.search(r"应(?:该|当)?出现.{0,8}定价分化|主要来自|主要由.{0,12}导致|近月平值|near.month ATM|primarily caused by", text, re.I):
            raise ValueError("Unsupported causal attribution or tenor")
    return report.model_dump()


def identify_cohorts(report: dict, reports: list[dict]) -> dict:
    """Resolve anonymized prose identifiers locally after validating model output."""
    labels = {
        f"g{index}": f"{item['snapshot']['symbol']}（{item['snapshot']['expiration']}）"
        for index, item in enumerate(reports)
    }

    def replace(text: str) -> str:
        return re.sub(r"(?<![A-Za-z0-9_])g[0-3](?![A-Za-z0-9_])", lambda match: labels.get(match[0], match[0]), text)

    report["summary"]["text"] = replace(report["summary"]["text"])
    for claim in [*report["observations"], *report["conflicts"]]:
        claim["text"] = replace(claim["text"])
    for scenario in report["scenarios"]:
        scenario["condition"] = replace(scenario["condition"])
        scenario["implication"] = replace(scenario["implication"])
    report["limitations"] = [replace(text) for text in report["limitations"]]
    return report


def narrative_text(report: dict) -> str:
    paragraphs = [report["summary"]["text"]]
    paragraphs.extend(item["text"] for item in report["observations"])
    paragraphs.extend(item["text"] for item in report["conflicts"])
    paragraphs.extend(f"{item['condition']} {item['implication']}" for item in report["scenarios"])
    paragraphs.extend(report["limitations"])
    return "\n\n".join(paragraphs)


