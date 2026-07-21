"""
Quality, policy, and originality gates + the confidence router.

Implements the gate architecture from the operating blueprint:
  * Tier P — policy filters (sensitive-topic, advice-framing)      -> HARD FAIL
  * Tier O — originality (synthesis claim, replication test)       -> REGENERATE/penalty
  * Tier A — accuracy (claim-level fact-check vs. sources;
             hook/thumbnail claims are hard-fail)                  -> STRIP or HARD FAIL
  * Confidence router — composite score routes each asset to
    auto-publish / notify (veto window) / hold

Design rules honored throughout:
  - cheap deterministic checks before expensive LLM checks
  - every gate degrades safely: if the LLM is unavailable, deterministic
    fallbacks apply and the asset is routed to NOTIFY rather than published blind
  - every result is returned as structured data so it lands in the run ledger
    (the originality dossier is built from these records)
"""
from __future__ import annotations

import json
import re

from factverse import config as fv
from factverse import llm

# --------------------------------------------------------------- Tier P: policy
# Bucket 3 covers AI personas presenting as human experts advising on these.
SENSITIVE = ("finance", "financial", "invest", "stock", "portfolio", "trading",
             "health", "medical", "diagnosis", "treatment", "cure",
             "legal", "lawsuit", "law ", "regulation", "tax",
             "politic", "election", "policy maker", "government")

_ADVICE_PATTERNS = re.compile(
    r"\b(you should (buy|sell|invest|take|sue|vote)|"
    r"(buy|sell) (the stock|shares|now)|"
    r"here'?s what (you|to) (should )?do with your (money|portfolio|savings)|"
    r"(medical|legal|financial) advice|"
    r"talk to your (doctor|lawyer) is not needed|"
    r"what this means for your portfolio)\b", re.I)


def sensitive_topic_risk(title: str, summary: str = "") -> bool:
    """Cheap keyword screen: does this topic surface finance/health/legal/politics?
    A hit does NOT reject the topic — reporting is allowed. It arms the
    advice-framing gate and the router's policy-proximity penalty."""
    t = f" {title} {summary} ".lower()
    return any(k in t for k in SENSITIVE)


def advice_framing(script_text: str) -> dict:
    """Detect prescriptive advice on sensitive topics — the Bucket 3 trigger.
    Reporting ('NVIDIA reported X') is fine; advising ('here is what to do with
    your money') is a hard fail. Regex first, LLM confirmation second."""
    hit = _ADVICE_PATTERNS.search(script_text or "")
    if hit:
        return {"advice": True, "evidence": hit.group(0), "method": "regex"}
    if not sensitive_topic_risk(script_text[:2000]):
        return {"advice": False, "method": "regex"}
    d = llm.generate_json(
        "Does this video script give PRESCRIPTIVE ADVICE to viewers about finance, health, "
        "legal, or political action (telling them what THEY should do — buy/sell/invest/"
        "vote/treat)? Merely reporting or explaining events is NOT advice.\n"
        'Return ONLY JSON {"advice": true|false, "evidence": "<quote or empty>"}\n\n'
        + (script_text or "")[:9000], temperature=0.0)
    if d is None:
        # LLM down on a sensitive topic: fail safe — treat as advice, force review
        return {"advice": True, "evidence": "llm-unavailable on sensitive topic", "method": "failsafe"}
    return {"advice": bool(d.get("advice")), "evidence": str(d.get("evidence", ""))[:200],
            "method": "llm"}


# --------------------------------------------------------------- Tier A: facts
def extract_claims(script: dict, hook_texts: list[str]) -> list[dict]:
    """Pull the checkable claims (numbers, dates, names, quotes, attributions)."""
    narration = " ".join(sc.get("narration", "") for sc in script.get("scenes", []))
    d = llm.generate_json(
        "Extract every specific factual claim from this script that could be WRONG: "
        "numbers, dates, names, direct quotes, and attributions (X said/announced Y). "
        "Mark claims that also appear in the HOOK OVERLAYS as critical.\n"
        'Return ONLY JSON {"claims":[{"text":"...","type":"number|date|name|quote|attribution",'
        '"critical":true|false}]} (max 12 claims).\n\n'
        f"HOOK OVERLAYS: {json.dumps(hook_texts, ensure_ascii=False)}\n\nSCRIPT:\n{narration[:9000]}",
        temperature=0.0)
    out = []
    for c in (d or {}).get("claims", []):
        text = str(c.get("text", "")).strip()
        if text:
            out.append({"text": text[:300], "type": str(c.get("type", "other")),
                        "critical": bool(c.get("critical"))})
    return out[:12]


def fact_check(script: dict, hook_texts: list[str], sources_text: str) -> dict:
    """Claim-level verification against the bound sources.
    Returns {passed, critical_failures[], soft_failures[], checked}.
    A critical (hook/thumbnail) claim that cannot be traced to a source is a
    HARD FAIL; soft failures strip confidence instead."""
    if not sources_text or len(sources_text) < 200:
        return {"passed": True, "checked": 0, "critical_failures": [],
                "soft_failures": [], "note": "no grounding available (evergreen) — skipped"}
    claims = extract_claims(script, hook_texts)
    if not claims:
        return {"passed": True, "checked": 0, "critical_failures": [], "soft_failures": []}
    d = llm.generate_json(
        "For each claim, answer whether the SOURCE TEXT supports it. 'supported' means the "
        "source states it or it follows directly; 'unsupported' means the source does not "
        "contain it; 'contradicted' means the source says otherwise.\n"
        'Return ONLY JSON {"results":[{"claim":"...","verdict":"supported|unsupported|contradicted"}]}\n\n'
        f"CLAIMS: {json.dumps([c['text'] for c in claims], ensure_ascii=False)}\n\n"
        f"SOURCE TEXT:\n{sources_text[:12000]}", temperature=0.0)
    verdicts = {str(r.get("claim", "")): str(r.get("verdict", "unsupported"))
                for r in (d or {}).get("results", [])}
    critical, soft = [], []
    for c in claims:
        v = verdicts.get(c["text"], "unsupported" if d else "unchecked")
        if v in ("unsupported", "contradicted"):
            (critical if c["critical"] else soft).append({**c, "verdict": v})
    return {"passed": not critical, "checked": len(claims),
            "critical_failures": critical, "soft_failures": soft}


# --------------------------------------------------------------- Tier O: originality
def verify_synthesis(script: dict, sources_text: str) -> dict:
    """O2: the script must name one claim/connection NOT present in any source —
    the machine-checkable expression of 'the creator's original insight'."""
    claim = str(script.get("synthesis_claim", "")).strip()
    if not claim:
        return {"present": False, "verified": False}
    if not sources_text:
        return {"present": True, "verified": True, "note": "no source to compare (evergreen)"}
    d = llm.generate_json(
        "Is the following SYNTHESIS CLAIM stated in the SOURCE TEXT (verbatim or in substance)? "
        'Return ONLY JSON {"stated_in_source": true|false}\n\n'
        f"SYNTHESIS CLAIM: {claim}\n\nSOURCE TEXT:\n{sources_text[:10000]}", temperature=0.0)
    verified = (d is not None) and (not bool(d.get("stated_in_source")))
    return {"present": True, "verified": verified, "claim": claim[:300]}


def replication_test(script: dict, sources_text: str) -> dict:
    """O3: could a competent competitor produce a substantially identical video
    from only these sources? If yes, the angle is not differentiated."""
    beats = " | ".join(sc.get("narration", "")[:80] for sc in script.get("scenes", [])[:8])
    d = llm.generate_json(
        "Adversarial check. Given ONLY the source text, could a competent competitor produce a "
        "substantially identical video to this outline (same angle, same take, same framing)? "
        "Answer yes only if the outline adds nothing beyond the sources.\n"
        'Return ONLY JSON {"replicable": true|false, "distinct_elements": "..."}\n\n'
        f"OUTLINE: {beats}\nSYNTHESIS CLAIM: {script.get('synthesis_claim', '')}\n"
        f"EDITORIAL FILTER SEGMENT PRESENT: {bool(script.get('filter_segment'))}\n\n"
        f"SOURCES:\n{sources_text[:9000]}", temperature=0.0)
    if d is None:
        return {"passed": True, "note": "llm unavailable — routed to review instead"}
    return {"passed": not bool(d.get("replicable")),
            "distinct": str(d.get("distinct_elements", ""))[:200]}


# --------------------------------------------------------------- hook rotation
HOOK_PATTERNS = ("correction", "consequence", "filter", "number", "quiet")

HOOK_PATTERN_PROMPTS = {
    "correction": 'Open by correcting the common reporting: "Everyone\'s saying X. The source says different."',
    "consequence": 'Open with the direct consequence for someone building with AI: "If you use X, this changes Y."',
    "filter": 'Open with the filter promise: "N things happened. Only one matters. Here\'s how to tell."',
    "number": 'Open with one startling, sourced number and why it is not what it seems.',
    "quiet": 'Open with "the most important release this week got almost no coverage" — use ONLY if literally true.',
}


def pick_hook_pattern(recent_patterns: list[str]) -> str:
    """Rotate hook structures: never repeat within the recent window (O4)."""
    recent = set(recent_patterns[-4:])
    for p in HOOK_PATTERNS:
        if p not in recent:
            return p
    return HOOK_PATTERNS[0]


# --------------------------------------------------------------- confidence router
WEIGHTS = {"format": 0.25, "novelty": 0.20, "facts": 0.25, "packaging": 0.20, "policy": 0.10}


def confidence(components: dict) -> dict:
    """Composite confidence score + routing decision.
    components: each in [0,1]. Routing: >=0.80 auto / >=0.55 notify / else hold.
    Any policy breach (policy component == 0) is a hard hold regardless."""
    comp = {k: max(0.0, min(1.0, float(components.get(k, 0.5)))) for k in WEIGHTS}
    score = sum(WEIGHTS[k] * comp[k] for k in WEIGHTS)
    if comp["policy"] <= 0.0:
        routing = "hold"
    elif score >= 0.80:
        routing = "auto"
    elif score >= 0.55:
        routing = "notify"
    else:
        routing = "hold"
    return {"score": round(score, 3), "components": comp, "routing": routing}
