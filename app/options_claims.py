"""Shared clause-scoped direction checks; no model or market-data access."""
import re


def _read_as_denial(prefix):
    """Recognize only a denied interpretation governing this direction token.

    The tail permits a metric name and coordinated directions (increase OR
    decrease), not arbitrary intervening prose. 'Cannot be read as a forecast
    and volume increased' therefore remains a factual direction assertion.
    """
    zh_tail = r"(?:(?:实际|真实|明确|可靠|已经发生|成交量|成交|持仓量|持仓|价格|占比|总量|变化量|数值|指标|的|增加|减少|上升|下降|变高|变低|增大|降低|提高|保持相同|保持不变|未变|持平|或|和|与|以及|、|\s))*$"
    zh = re.search(r"(?:不能|无法|不可|不应|不该|不宜|不足以|不)(?:据此|直接|简单地|可靠地|轻易)?(?:被|(?:(?:把|将)(?:它|其|这|这些差异|这些变化|该变化|这一变化|这项变化|该差值|这些数值)))?(?:当作|当成|视为|解读为|解释为|描述为|称为|说成)" + zh_tail, prefix)
    if zh and not re.search(r"(?:不能|无法|不可|并非|不是|并不是)\s*$", prefix[:zh.start()]):
        return True
    en_tail = r"(?:(?:an?|the|any|real|actual|genuine|clear|meaningful|reliable|observed|definite|evidence|of|showing|indicating|volume|price|interest|share|increas\w*|decreas\w*|higher|lower|rose|fell|unchanged|or|and|nor)\s+)*$"
    english = re.search(r"\b(?:cannot|can't|could not|couldn't|should not|shouldn't|must not|mustn't|not)\s+(?:be\s+)?(?:(?:directly|reliably|simply|necessarily)\s+)?(?:read|interpreted|taken|viewed|treated|regarded|construed|described|labelled|labeled)(?:\s+(?:directly|reliably|simply))?\s+as\s+" + en_tail, prefix, re.I)
    return bool(english and not re.search(r"\b(?:cannot|can't|not|never)\s*$", prefix[:english.start()], re.I))


def direction_statements(text):
    """Locate directional assertions; unrelated disclaimers cannot negate them.

    An epistemic denial (cannot establish whether it increased) is different
    from a factual negative (it did not increase). The latter still asserts
    a historical condition and cannot be established by incomparable samples.
    """
    patterns = {
        "increased": r"增加|上升|变高|增大|提高|\b(?:increas\w*|higher|rose)\b",
        "decreased": r"减少|下降|变低|降低|\b(?:decreas\w*|lower|fell|declin\w*)\b",
        "unchanged": r"保持相同|保持不变|未变|持平|\b(?:unchanged|remained equal|stayed the same)\b",
    }
    boundary = r"[。.!?;；，,]|(?:但是|然而|不过|但)|\bbut\b"
    claims = []
    for direction, pattern in patterns.items():
        for match in re.finditer(pattern, text, re.I):
            prefix = re.split(boundary, text[:match.start()], flags=re.I)[-1][-100:]
            suffix = re.split(boundary, text[match.end():], flags=re.I)[0][:70]
            denied = re.search(r"(?:不能|无法|未能|尚不能|不足以|不(?:能|足以)?)(?:据此|直接|可靠地|进一步|就)?(?:确认|判断|认定|比较|证明|说明|表明|推断|确定|得出|支持)", prefix)
            denied = denied or re.search(r"(?:没有|缺乏|并无)(?:充分|可靠|足够)?(?:的)?(?:证据|依据)", prefix)
            denied = denied or re.search(r"(?:是否|能否).{0,12}$", prefix) and re.search(r"^(?:还|尚|目前)?(?:无法|不能|尚未)(?:确认|判断|确定|认定|比较)", suffix)
            denied = denied or re.search(r"\b(?:cannot|can't|could not|couldn't|does not|do not|doesn't|don't|not)\s+(?:(?:directly|reliably|simply|necessarily)\s+)?(?:establish\w*|determine\w*|confirm\w*|infer\w*|prove\w*|conclude\w*|show\w*|say|judge\w*|support\w*|compar\w*)\b", prefix, re.I)
            denied = denied or re.search(r"\b(?:no|insufficient) (?:reliable |sufficient )?evidence\b", prefix, re.I)
            denied = denied or re.search(r"^\s*(?:(?:is|was|can)\s+)?(?:not (?:be )?(?:established|determined|confirmed)|cannot be (?:established|determined|confirmed))\b", suffix, re.I)
            denied = denied or _read_as_denial(prefix)
            if denied:
                continue
            # Do not mechanically reverse a factual negative in a comparable
            # metric. It still remains a claim for the incomparability check.
            factual_negative = bool(re.search(r"(?:没有|并未|未曾|不曾|不)$|\b(?:not|never|didn't|doesn't)\s*$", prefix, re.I))
            claims.append((direction, factual_negative))
    return claims
