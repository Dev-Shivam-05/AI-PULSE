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

# v3 tool lane: a hands-on "here is how to run it" video is an ENDORSEMENT, which
# reporting on the same tool would not be. These are the categories this channel
# will not teach — circumventing provenance/authenticity, defeating safety, and
# piracy — because a monetised, unattended channel cannot survive one of them.
#
# The list is split by SURFACE because a term does not mean the same thing in a
# 90-char repo name as in 5,000 chars of prose (spec v3-C.4, measured 2026-08-24).
#
# Terms that identify a tool by what it IS. Matched on the title AND the README:
# they carry no innocent meaning in AI-tool documentation. Edit this list; it is
# deliberately narrow.
UNSUITABLE_TOOL = ("watermark remov", "watermarks remov", "remove watermark",
                   "remove any watermark", "remove all watermark", "unwatermark",
                   "strip provenance", "provenance mark",
                   "ai detector bypass", "detector evasion",
                   "humanize ai text", "humanizer",
                   "uncensored", "abliterated", "obliterated",
                   "voice clon", "clone voice",
                   "undress", "nudify", "deepnude",
                   "nulled", "keygen", "piracy")

# Words that only mean something when they NAME the tool. Title only.
# Measured over 28 flagship AI tools: unsloth's Windows install line is
# `set-executionpolicy -scope process -executionpolicy bypass`, ComfyUI binds
# ctrl+b to "bypass selected nodes", and transformers ships a "wise-cracking
# robot" example prompt. Screening these against a README refuses the tools this
# lane exists to teach; screening them against the name still catches "GPTBypass".
UNSUITABLE_NAME_ONLY = ("bypass", "crack", "torrent", "unfiltered")

# Subjects where the tool that DETECTS the thing is the opposite of the tool that
# DOES it. Blocked UNLESS the text reads as defensive near the term. Measured:
# these four terms refused the official C2PA SDK and CLI (added to stop provenance
# STRIPPERS, they blocked the STANDARD), two deepfake detectors, two NSFW safety
# classifiers, and NVIDIA NeMo-Guardrails. A "how to detect this" video is the
# utility lane's best content, not its worst.
UNSUITABLE_SUBJECT = ("nsfw", "deepfake", "deep fake", "face swap", "faceswap",
                      "c2pa", "synthid", "jailbreak")

# How close a defensive word must sit to the subject term. Measured across the six
# blocked defensive tools the nearest defensive word was 5-69 chars away; in the
# live provenance stripper it was 1,049. 120 covers the observed 69 with ~1.7x
# margin and sits ~9x below the control — the same derivation as TOOL_GROUNDING_MIN.
DETECTOR_WINDOW = 120

_DEFENSIVE = re.compile(r"detector|detection|classif|forensic|verif|validat|"
                        r"display|inspect|moderat|protect|guard|defen|mitigat|benchmark")
# An evasion claim contains a defensive word and inverts it: "undetectable
# deepfake", "anti-detection technology". It cancels the exemption.
_EVASION = re.compile(r"undetect|anti detect|evad|defeat")


def _norm_terms(s: str) -> str:
    """Hyphens, underscores and the owner/name slash are how a repo spells a phrase.
    Matching them as spaces closes a whole class of misses in one line: measured
    2026-08-24, the live `ShadowAqueduct/watermark-remover` PASSED the title screen
    because the list held `watermark remov` (space) and `watermarks-remover`."""
    return re.sub(r"\s+", " ", re.sub(r"[-_/]+", " ", f" {s} ".lower()))


def _reads_as_defensive(text: str, at: int, span: int) -> bool:
    """Does a defensive word sit within DETECTOR_WINDOW of this occurrence, with no
    evasion claim in the same window?"""
    w = text[max(0, at - DETECTOR_WINDOW): at + span + DETECTOR_WINDOW]
    return bool(_DEFENSIVE.search(w)) and not _EVASION.search(w)


def tool_unsuitable(title: str, text: str = "") -> tuple[bool, str]:
    """Should this tool get a hands-on tutorial? Returns (blocked, matched term).

    Unlike sensitive_topic_risk this DOES reject: the tool lane teaches the viewer
    to run the thing, and build_script simply moves to the next candidate."""
    t_title = _norm_terms(title)
    t_all = _norm_terms(f"{title} {text}")
    for k in UNSUITABLE_TOOL:
        if k in t_all:
            return True, k
    for k in UNSUITABLE_NAME_ONLY:
        if k in t_title:
            return True, k
    for k in UNSUITABLE_SUBJECT:
        # A long README names its subject many times; one defensive mention is
        # enough to exempt the document, so only reject when NO occurrence reads
        # as defensive (Falconsai's card mentions "nsfw" 381 chars from the
        # nearest defensive word once, and adjacent to one five times).
        found = [m.start() for m in re.finditer(re.escape(k), t_all)]
        if found and not any(_reads_as_defensive(t_all, i, len(k)) for i in found):
            return True, k
    return False, ""


_ADVICE_PATTERNS = re.compile(
    r"\b(you should (buy|sell|invest|take|sue|vote)|"
    r"(buy|sell) (the stock|shares|now)|"
    r"here'?s what (you|to) (should )?do with your (money|portfolio|savings)|"
    r"(medical|legal|financial) advice|"
    r"talk to your (doctor|lawyer) is not needed|"
    r"what this means for your portfolio)\b", re.I)


# A packaging number: optional $, digits, optional magnitude suffix (K/M/B/X) or %.
# The suffix is INSIDE the token so a strip removes the whole unit — the review
# reproduced "180K STARS" stripping to the residue "K STARS" and burning it on the
# thumbnail. The lookbehind keeps digits glued into a name ("GPT-5") unmatched.
_NUM_TOKEN = re.compile(r"(?<![\w.-])(?:\$ ?)?\d[\d,.]*(?:\s?[KMBX]\b|%)?", re.I)


def _num_core(tok: str) -> str:
    core = re.sub(r"[KMBX]$", "", str(tok).replace(",", "").strip("$% ."), flags=re.I)
    return core.strip()


def _number_support(script: dict) -> set:
    """The number cores a packaging string may carry: spoken, in the grounding, or
    a numeric verified fact (spec v3-E #3)."""
    spoken = " ".join(sc.get("narration", "") for sc in script.get("scenes") or [])
    support_text = (spoken + " " + str(script.get("grounding") or "")).replace(",", "")
    support_text += " " + " ".join(str(v) for v in (script.get("verified_facts") or {}).values()
                                   if isinstance(v, (int, float)))
    return {_num_core(t) for t in _NUM_TOKEN.findall(support_text)}


def title_options(script: dict) -> list[str]:
    """The model's `titles` as list[str], whatever type it actually answered.
    _validate_script coerces it too; this re-coerces because a test or a future
    caller can hand the gates a raw dict (raw LLM output is never type-safe)."""
    raw = script.get("titles")
    if isinstance(raw, str):
        raw = [raw]
    elif not isinstance(raw, (list, tuple)):
        return []
    return [str(t).strip() for t in raw if isinstance(t, (str, int, float)) and str(t).strip()]


def clean_alternate(script: dict, support: set | None = None) -> str:
    """spec v3-G.3 #6/#7: the first `titles` entry whose number tokens are all
    supported and which carries no hype term, or "" when there is none. The
    alternates were written by the same model in the same answer, so they are as
    grounded as the title; this only picks among them, never writes one."""
    if support is None:
        support = _number_support(script)
    current = str(script.get("title") or "")
    for alt in title_options(script):
        if alt == current or hype_terms(alt):
            continue
        if all(_num_core(t) and _num_core(t) in support for t in _NUM_TOKEN.findall(alt)):
            return alt
    return ""


def packaging_payoff(script: dict) -> dict:
    """spec v3-E #3: every number token in title/thumb_text must be supported —
    spoken in the narration, present in the grounding (the contract licenses "a
    number from the source"), or a numeric verified fact. Token-exact comparison,
    not substring: the review showed bare containment lets a fabricated "10" ride
    on any digit pair anywhere in the text. Mutates the script deterministically,
    never raises — this runs inside the unattended publish path.

    Why it exists: the 2026-08-21 run shipped title "Secret AI Cash Cow?" and hook
    "you won't believe how much" over 17 scenes containing zero dollar figures.
    fact_check verifies claims that exist; an ABSENT promised number passed every gate.

    spec v3-G.3 #6: stripping the number shipped 8 of 78 titles as broken leftovers
    ("AI Agents Gone Rogue: Scenarios"). When `honest_titles` is on, a clean
    alternate from the model's own `titles` replaces the title first; only without
    one does the strip below run, byte-identical to before."""
    support = _number_support(script)

    def _ok(tok: str) -> bool:
        core = _num_core(tok)
        return bool(core) and core in support

    fixed, evidence, title_alt = [], [], False
    for field in ("title", "thumb_text"):
        val = str(script.get(field) or "")
        if not val:
            continue
        bad = [t for t in _NUM_TOKEN.findall(val) if not _ok(t)]
        if not bad:
            continue
        if field == "title" and fv.flag("honest_titles", False):
            alt = clean_alternate(script, support)
            if alt:
                evidence.append(f"{field}: {bad} -> alternate {alt!r}")
                script[field] = alt
                fixed.append(field)
                title_alt = True
                continue
        newv = _NUM_TOKEN.sub(lambda m: m.group(0) if _ok(m.group(0)) else " ", val)
        newv = re.sub(r"\s{2,}", " ", newv).strip(" .,:—-")
        if field == "thumb_text" and not any(c.isdigit() for c in newv):
            # a thumb only reaches here when a number was stripped, so digitless
            # residue ("K STARS", "X FASTER") is mangled by definition — blank it
            # and the composers' existing `or title` fallback takes over.
            newv = ""
        # the hands-on template belongs to the tool lane ONLY: the gate runs on
        # every format, and "How to use <outlet> (free)" on a news video would be
        # a wrong-lane title carrying a promise nobody scripted.
        if field == "title" and len(newv.split()) < 4 and script.get("format") == "tool":
            tool = str(script.get("signal_title") or script.get("title") or "").split(":")[0]
            tool = tool.split("/")[-1].strip() or "this tool"
            newv = f"How to use {tool} (free)"
        evidence.append(f"{field}: {bad}")
        script[field] = newv
        fixed.append(field)
    return {"ok": not fixed, "fixed": fixed, "evidence": evidence, "title_alt": title_alt}


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
    # The window used to be script_text[:2000]. A 900-word script is ~5,500 chars,
    # so a finance/health/legal turn in the last two thirds never armed this check.
    # The screen is a keyword scan over a 20-item tuple — the full text is free.
    if not sensitive_topic_risk(script_text or ""):
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


# Below this much readable source text the fact-checker cannot say anything
# useful, so it skips. The story lanes reuse it as their grounding floor: if this
# gate cannot run, there is nothing to write a sourced video from (spec v3-C.2 #2).
FACTCHECK_MIN_CHARS = 200


def facts_lines(facts) -> str:
    """The `- key: value` lines of an official-API facts dict. ONE renderer for the
    writer's prompt and for fact_sources: if the two formatted a number differently
    ("21,102" vs "21102") the checker would disagree with the writer again."""
    if not isinstance(facts, dict):
        return ""
    return "\n".join((f"- {k}: {v:,}" if isinstance(v, int) and not isinstance(v, bool)
                      else f"- {k}: {v}") for k, v in facts.items())


def fact_sources(script: dict) -> str:
    """What fact_check verifies against: the grounding PLUS the verified facts the
    writer was ordered to use. v3-B.2: the tool lane told the writer "these are the
    ONLY numbers you may state", then checked those numbers against the README alone
    — 4 of 4 tool scripts were blocked on their own star/like counts (09-27..09-30).
    Facts go FIRST so fact_check's [:12000] cut can never drop them."""
    grounding = str(script.get("grounding") or "")
    lines = facts_lines(script.get("verified_facts"))
    # v3-P.1: the writer is ordered to state the evidence's observed result, so the
    # checker must read it too ("the checker reads what the writer was ordered to
    # use"). Imported here to keep the module graph one-way.
    from factverse import evidence as _ev
    ev_lines = _ev.fact_lines(script.get("evidence"))
    head = ""
    if lines:
        head += "VERIFIED FACTS (official API):\n" + lines + "\n\n"
    if ev_lines:
        head += "EVIDENCE (captured by the channel):\n" + ev_lines + "\n\n"
    return head + grounding if head else grounding


def fact_check(script: dict, hook_texts: list[str], sources_text: str) -> dict:
    """Claim-level verification against the bound sources.
    Returns {passed, critical_failures[], soft_failures[], checked}.
    A critical (hook/thumbnail) claim that cannot be traced to a source is a
    HARD FAIL; soft failures strip confidence instead."""
    if not sources_text or len(sources_text) < FACTCHECK_MIN_CHARS:
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


# --------------------------------------------------------------- honest titles (v3-G.3a)
# The first eight are from this channel's own published Shorts titles (Studio,
# 2026-09-26); the rest are find_best_moments' own "discounted hype" examples.
HYPE_TERMS = ("mind-blowing", "mind blowing", "exposed", "meltdown", "unleashed", "unlock",
              "secret", "secrets", "shocking", "insane", "game-changing", "game changer",
              "won't believe", "breaks free", "jaw-dropping", "crazy", "nobody is talking",
              "blow your mind")
_HYPE_RE = [(t, re.compile(rf"(?<![\w-]){re.escape(t)}(?![\w-])", re.I)) for t in HYPE_TERMS]


def hype_terms(title: str) -> list[str]:
    """Hype terms a title contains — word-boundary matches, so 'secretary' is clean."""
    t = str(title or "").replace("’", "'")
    return [term for term, rx in _HYPE_RE if rx.search(t)]


# v3-G.3 #8: fear / outrage framing. RECORDED in the ledger (`title_terms`), never
# blocking — the measurement comes before any policy. Same word-boundary match.
FEAR_TERMS = ("rogue", "threat", "threats", "nightmare", "fear", "fears", "worried",
              "crisis", "scary", "existential", "chaos", "outrage")
_FEAR_RE = [(t, re.compile(rf"(?<![\w-]){re.escape(t)}(?![\w-])", re.I)) for t in FEAR_TERMS]


def title_terms(title: str) -> list[str]:
    """Hype terms + fear terms a title contains (the ledger's `title_terms`)."""
    t = str(title or "").replace("’", "'")
    return hype_terms(t) + [term for term, rx in _FEAR_RE if rx.search(t)]


def longform_title_screen(script: dict) -> dict:
    """spec v3-G.3 #7: the long-form title gets the Shorts' hype screen. On a hit
    the first clean alternate from `titles` replaces it; with none the title is
    KEPT (a hype word is not worth a gutted title). Mutates in place, never raises.
    Returns {"terms": [...], "alt": bool}; the `honest_titles` flag off -> no-op."""
    if not fv.flag("honest_titles", False):
        return {"terms": [], "alt": False}
    terms = hype_terms(script.get("title"))
    if not terms:
        return {"terms": [], "alt": False}
    alt = clean_alternate(script)
    if alt:
        script["title"] = alt
    return {"terms": terms, "alt": bool(alt)}


# --------------------------------------------------------------- substantiation (v3-P.1 row 3)
# A STANDARD, not a test (review 2026-11-04 row 3): an outcome claim in the long-form
# title or thumbnail that ToolDojo did not observe is attributed ("Claimed 2× …") or
# dropped. "Observed" = the claim is in evidence.supported_claims of a
# PASSED_FIXED_TEST. "Double Your AI Speed" (10-31) is the case that started it.
TITLE_MAX = 95             # _validate_script's own title cap
THUMB_MAX_CHARS = 26       # _validate_script's own thumb cap
THUMB_MAX_WORDS = 4        # make_tool_thumb burns the first 4 words only
_N = r"\d+(?:[.,]\d+)?\+?"
_GAIN = (r"faster|quicker|cheaper|smaller|lighter|better|more|less|fewer|bigger|larger|boost|"
         r"boosts|gain|gains|cut|cuts|reduction|reduced|lower|higher|improvement|speedup|"
         r"speed-?up|savings?|saved|increase|drop|accuracy")
_CLAIM_RES = [
    # 2x / 2× / 1.5X — not "2x2", not "RTX 4090"
    re.compile(rf"(?<![\w.]){_N}\s?[x×](?![\w×])", re.I),
    # 3 times faster
    re.compile(rf"(?<![\w.]){_N}\s+times\s+(?:{_GAIN})\b", re.I),
    # Double / Triple / Halve (your|the|its) …  — a multiplier said as a verb
    re.compile(r"\b(?:doubles?|doubled|doubling|triples?|tripled|quadruples?|halves|halve|halved)"
               r"(?!-)\b(?:\s+(?:your|the|its|their))?", re.I),
    # 60% Sales Boost / 56% GPU Cost Cut / 40% faster
    re.compile(rf"(?<![\w.]){_N}\s?%(?:\s+[\w-]+){{0,2}}?\s+(?:{_GAIN})\b", re.I),
    # the verb-first form: cuts costs by 40%
    re.compile(rf"\b(?:cuts?|slash(?:es)?|boosts?|reduces?|saves?|improves?|speeds?\s+up)"
               rf"(?:\s+[\w-]+){{0,2}}?\s+(?:by\s+)?{_N}\s?%", re.I),
    # 75+ Hrs Saved / saves 10 hours
    re.compile(rf"(?<![\w.]){_N}\s?(?:hrs?|hours?|minutes?|mins?|days?)\s+(?:[\w-]+\s+)?saved\b", re.I),
    re.compile(rf"\bsaves?\s+(?:you\s+)?{_N}\s?(?:hrs?|hours?|minutes?|mins?|days?)\b", re.I),
    # in 10 seconds / under 200 ms
    re.compile(rf"\b(?:in|under)\s+{_N}\s?(?:s|secs?|seconds?|ms|milliseconds?)\b", re.I),
]
_VERB_MULT = {"double": "2×", "doubles": "2×", "doubled": "2×", "doubling": "2×",
              "triple": "3×", "triples": "3×", "tripled": "3×",
              "quadruple": "4×", "quadruples": "4×",
              "halve": "Half the", "halves": "Half the", "halved": "Half the"}
_CLAUSE_DELIM = re.compile(r"[:;,|?!—–]|\s-\s|\.\s")


def outcome_claims(text: str) -> list[dict]:
    """Outcome claims in a packaging string: [{"start","end","text"}], in order,
    overlapping matches merged. Deterministic, never raises."""
    t = str(text or "")
    spans = []
    for rx in _CLAIM_RES:
        for m in rx.finditer(t):
            spans.append([m.start(), m.end()])
    spans.sort()
    merged = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [{"start": s, "end": e, "text": t[s:e]} for s, e in merged]


def _claim_key(text: str) -> str:
    t = str(text or "").lower().replace("×", "x")
    for verb, mult in _VERB_MULT.items():
        t = re.sub(rf"\b{verb}\b(\s+(your|the|its|their))?", mult.lower().replace("×", "x"), t)
    return re.sub(r"[^a-z0-9%.x ]+", " ", re.sub(r"\s+", " ", t)).strip()


def claim_observed(claim: str, ev) -> bool:
    """True only when a PASSED_FIXED_TEST lists a supported claim containing this
    claim (normalised). An author demo (NOT_RUN) supports nothing."""
    if not isinstance(ev, dict) or ev.get("status") != "PASSED_FIXED_TEST":
        return False
    sup = ev.get("supported_claims")
    if not isinstance(sup, (list, tuple)):
        return False
    key = _claim_key(claim)
    return bool(key) and any(key in _claim_key(s) for s in sup if isinstance(s, str))


def _attribute(text: str, claims: list[dict], word: str) -> str | None:
    """Insert `word` before every claim, converting a verb multiplier to its noun
    ("Double Your AI Speed" -> "Claimed 2× AI Speed"). None when a claim does not
    START its clause — "Make Llama Claimed 3x Faster" is not a sentence, so that
    title is dropped, never mangled."""
    out = text
    for c in sorted(claims, key=lambda c: -c["start"]):
        head = out[:c["start"]]
        last = max([m.end() for m in _CLAUSE_DELIM.finditer(head)] or [0])
        if head[last:].strip() and not re.fullmatch(r"\s*(?:&|and)\s*", head[last:], re.I):
            return None
        span = out[c["start"]:c["end"]]
        m = re.match(r"(?i)(doubles?|doubled|doubling|triples?|tripled|quadruples?|halves|halve|halved)"
                     r"(\s+(?:your|the|its|their))?", span)
        if m:
            span = _VERB_MULT[m.group(1).lower()] + span[m.end():]
        out = out[:c["start"]] + f"{word} " + span + out[c["end"]:]
    return re.sub(r"\s{2,}", " ", out).strip()


def _drop_claims(text: str, claims: list[dict]) -> str:
    """Remove every colon segment that carries a claim; inside a single segment,
    remove the claim clause (to the next delimiter)."""
    segs = [s.strip() for s in str(text).split(":")]
    keep = [s for s in segs if s and not outcome_claims(s)]
    if keep and len(keep) < len(segs):
        return ": ".join(keep).strip(" ,;:—-")
    out = text
    for c in sorted(claims, key=lambda c: -c["start"]):
        m = _CLAUSE_DELIM.search(out, c["end"])
        end = m.start() if m else len(out)
        out = out[:c["start"]] + out[end:]
    return re.sub(r"\s{2,}", " ", out).strip(" ,;:—-.")


def thumb_fits(text: str) -> bool:
    """Burned text is MEASURED, never sized by character count (CLAUDE.md trap):
    the thumb must keep every word through make_tool_thumb's 4-word cut and fit
    both composers' measured budgets at their own fonts."""
    t = " ".join(str(text or "").split())
    if not t:
        return True
    if len(t) > THUMB_MAX_CHARS or len(t.split()) > THUMB_MAX_WORDS:
        return False
    try:
        from PIL import Image, ImageDraw
        from factverse import branding as _br
        from factverse import thumbnail as _th
        lines = _th._wrap_two(t)
        d = ImageDraw.Draw(Image.new("L", (8, 8)))
        budget = _th.W - 2 * 48 - 2 * 28            # make_tool_thumb's own box
        _size, f = _br.fit_font(_th._tool_font, lines, 130, budget,
                                floor=_th._FIT_FLOOR, step=_th._FIT_STEP)
        if max(d.textlength(l, font=f) for l in lines) > budget:
            return False
        _size, f = _th._headline_font(lines)
        return max(d.textlength(l, font=f) for l in lines) <= _th.W - 2 * _th.X_EDGE
    except Exception:
        return True          # the char/word caps above already held


def _fix_thumb(thumb: str, ev) -> tuple[str, list[str]]:
    """(new thumb, unsupported claims). Thumb parts are "."-separated ("2X AI SPEED.
    FREE."). A claim part is attributed if that fits; other parts are shed from the
    end until it fits; if the attributed claim cannot fit, the claim part is dropped
    instead and the rest kept ("" lets the composers fall back to the title)."""
    parts = [p.strip() for p in re.split(r"\.\s*", str(thumb or "")) if p.strip()]
    bad_all, attributed, clean, ok = [], [], [], True
    for p in parts:
        bad = [c for c in outcome_claims(p) if not claim_observed(c["text"], ev)]
        if not bad:
            attributed.append(p)
            clean.append(p)
            continue
        bad_all += [c["text"] for c in bad]
        a = _attribute(p, bad, "CLAIMED" if p.upper() == p else "Claimed")
        if a is None:
            ok = False
        else:
            attributed.append(a)
    if not bad_all:
        return thumb, []
    dot = str(thumb).rstrip().endswith(".")

    def join(ps):
        return (". ".join(ps) + ("." if dot and ps else "")).strip()
    if ok:
        cand = list(attributed)
        while cand and not thumb_fits(join(cand)):
            drop = next((i for i in range(len(cand) - 1, -1, -1) if cand[i] in clean), None)
            if drop is None:
                break
            cand.pop(drop)
        if cand and thumb_fits(join(cand)):
            return join(cand), bad_all
    rest = list(clean)
    while rest and not thumb_fits(join(rest)):
        rest.pop()
    return join(rest), bad_all


def substantiate_claims(script: dict) -> dict:
    """spec v3-P.1 row 3: attribute or drop every unobserved outcome claim in the
    long-form title and thumb_text. Mutates in place, deterministic, never raises.
    Title order: attribute (fits TITLE_MAX and the claim starts its clause) →
    a clean alternate from `titles` → drop the claim's clause. Returns
    {"claims": [...], "fixed": [...], "evidence": [...]}; flag off → no-op."""
    res = {"claims": [], "fixed": [], "evidence": []}
    try:
        if not fv.flag("claim_substantiation", False) or not isinstance(script, dict):
            return res
        ev = script.get("evidence")
        title = str(script.get("title") or "")
        bad = [c for c in outcome_claims(title) if not claim_observed(c["text"], ev)]
        if bad:
            res["claims"] += [c["text"] for c in bad]
            new = _attribute(title, bad, "Claimed")
            how = "attributed"
            if not new or len(new) > TITLE_MAX:
                new, how = "", ""
                for alt in title_options(script):
                    if alt != title and not hype_terms(alt) and not [
                            c for c in outcome_claims(alt) if not claim_observed(c["text"], ev)]:
                        new, how = alt[:TITLE_MAX], "alternate"
                        break
            if not new:
                new, how = _drop_claims(title, bad), "dropped"
                if len(new.split()) < 3 and script.get("format") == "tool":
                    tool = str(script.get("signal_title") or title).split(":")[0]
                    tool = tool.split("/")[-1].strip() or "this tool"
                    new = f"How to use {tool} (free)"[:TITLE_MAX]
            if new and new != title:
                script["title"] = new
                res["fixed"].append("title")
                res["evidence"].append(f"title {how}: {title!r} -> {new!r}")
        thumb = str(script.get("thumb_text") or "")
        new_thumb, tbad = _fix_thumb(thumb, ev)
        if tbad:
            res["claims"] += tbad
            if new_thumb != thumb:
                script["thumb_text"] = new_thumb
                res["fixed"].append("thumb_text")
                res["evidence"].append(f"thumb: {thumb!r} -> {new_thumb!r}")
    except Exception as e:
        res["evidence"].append(f"error: {type(e).__name__}")
    return res


# --------------------------------------------------------------- hook rotation
HOOK_PATTERNS = ("correction", "consequence", "filter", "number", "quiet")

HOOK_PATTERN_PROMPTS = {
    "correction": 'Open by correcting the common reporting: "Everyone\'s saying X. The source says different."',
    "consequence": 'Open with the direct consequence for someone building with AI: "If you use X, this changes Y."',
    "filter": 'Open with the filter promise: "N things happened. Only one matters. Here\'s how to tell."',
    "number": 'Open with one startling, sourced number and why it is not what it seems.',
    "quiet": 'Open with "the most important release this week got almost no coverage" — use ONLY if literally true.',
}


def pick_hook_pattern(recent_patterns: list[str], active=None) -> str:
    """Rotate hook structures: never repeat within the recent window (O4).
    `active` is the learning loop's rotation (v3-D). The window is len(pool) - 1
    so a shrunk pool still rotates — a fixed 4-wide window over 4 patterns would
    exclude all of them and pin the fallback forever."""
    pool = tuple(p for p in HOOK_PATTERNS if active is None or p in active) or HOOK_PATTERNS
    window = len(pool) - 1
    # [-0:] is the WHOLE list, not an empty one
    recent = set(recent_patterns[-window:]) if window > 0 else set()
    for p in pool:
        if p not in recent:
            return p
    return pool[0]


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
