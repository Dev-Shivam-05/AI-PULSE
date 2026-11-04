"""v3-K.1: the task-based evidence catalogue (review rows 12 + 14).

"Which tool should I use for this job, under these conditions, today?" A hub page
per task family answers that ONLY from first-hand comparative evidence: two or more
hosted tests run on the same fixed input. Author demos appear as candidate profiles
and never get a tested position. Until that supply exists every function here
returns nothing, so the catalogue is dormant by data, not by a flag.

Everything in this module is PURE (no I/O, no network, no LLM, no clock — `today`
is always a parameter) so the hub, its history and the alerts are 100% derived
from `state/tools_index.json`. That is the CLAUDE.md "derived artifact" rule: CI
regenerates the hubs after `state_merge` instead of stashing them, and the change
history needs no second state file because it is replayed from the catalog.

The catalog is merged state read back off origin/main, and `evidence` arrives from
run(), whose inputs include a model grounded in a third-party README. Every field
is therefore coerced again here (`clean_evidence`), every URL passes the scheme
guard, and nothing here raises.

Spec: docs/spec/ai-pulse-v3k1.md
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import math
import re

from factverse import config as fv

# ------------------------------------------------------------------ contract
# docs/spec/ai-pulse-v3-growth.md, shared interface (v3-P.1 writes it, we read it)
SOURCES = ("hosted", "author", "sandbox", "none")
LABELS = {"hosted": "Hosted test", "author": "Author demo", "sandbox": "Sandbox test", "none": ""}
WORDING = {                                      # verbatim, review round 3
    "NOT_RUN": "Not independently tested.",
    "PASSED_FIXED_TEST": "Passed this specific test.",
    "FAILED_FIXED_TEST": "This test failed under these conditions.",
    "TIMED_OUT": "Did not complete within our 120-second execution limit.",
    "INCONCLUSIVE": "We could not establish a result.",
}
RIGHTS_KEYS = ("path", "commit", "license", "copyright", "notice", "modified")

# K.1 row 3: a status that IS a result on the fixed input. NOT_RUN and INCONCLUSIVE
# are not results, so they never enter a comparison (they still show as evidence).
RESULT_STATUSES = ("PASSED_FIXED_TEST", "FAILED_FIXED_TEST", "TIMED_OUT")
MIN_COMPARABLE = 2            # review row 12: ">= 2 comparable hosted tests"
OUTDATED_DAYS = 30            # K.1 row 5 (delegated): the review's "review monthly"
ALERT_MAX_DAYS = 2            # K.1 row 11 (delegated): today or yesterday only
ALERT_KINDS = ("recommendation_changed", "now_passes")       # K.1 row 10

# K.1 row 1 (delegated): the fixed family list, chosen from the 2026-11-04 supply
# research (HF Spaces API: which tasks have running, CPU-hosted Gradio demos).
# Terms are matched as whole words on a normalised string (lowercase, every
# non-alphanumeric run -> one space), on SHORT surfaces only: the title, the tool
# name and the one-sentence "what". Never the README — a keyword means different
# things on a name and in a document (the C.4 lesson).
FAMILIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "speech-to-text": ("Speech to text", (
        "speech to text", "speech recognition", "transcribe", "transcribes",
        "transcription", "transcriber", "asr", "stt", "whisper")),
    "text-to-speech": ("Text to speech", (
        "text to speech", "tts", "speech synthesis", "voice cloning", "voice clone")),
    "ocr": ("Image to text (OCR)", (
        "ocr", "optical character recognition", "text recognition")),
    "background-removal": ("Background removal", (
        "background removal", "remove background", "removes background",
        "remove the background", "background remover", "rembg")),
    "image-upscaling": ("Image upscaling", (
        "upscale", "upscaler", "upscaling", "super resolution")),
    "pdf-tables": ("PDF table extraction", (
        "pdf table", "pdf tables", "table extraction", "extract tables")),
}


# ------------------------------------------------------------------ helpers
def _str(v, limit: int = 400) -> str:
    return " ".join(str(v if v is not None else "").split())[:limit]


def _link(url) -> str:
    """The one scheme guard (site.safe_link). Imported lazily: site imports us."""
    from factverse.site import safe_link
    return safe_link(url)


def _date(v) -> _dt.date | None:
    s = str(v or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return None
    try:
        return _dt.date.fromisoformat(s)
    except ValueError:
        return None


def _norm(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip() + " "


# ------------------------------------------------------------------ family
def task_family(entry: dict) -> str:
    """The one family this entry belongs to, or "" (K.1 row 1).

    Deterministic and conservative: exactly one family must match. Two families
    matching ("speech-to-text and text-to-speech toolkit") is ambiguous, and an
    ambiguous tool must never land on a comparison it may not belong to."""
    try:
        e = entry if isinstance(entry, dict) else {}
        hay = _norm(" ".join(_str(e.get(k), 600) for k in ("title", "tool", "what")))
        hits = [fam for fam, (_, terms) in FAMILIES.items()
                if any(f" {_norm(t).strip()} " in hay for t in terms)]
        return hits[0] if len(hits) == 1 else ""
    except Exception:
        return ""


def family_of(entry: dict) -> str:
    """The stored family when it is one of ours, else recomputed (older rows)."""
    e = entry if isinstance(entry, dict) else {}
    fam = str(e.get("task_family") or "")
    return fam if fam in FAMILIES else task_family(e)


def label(family: str) -> str:
    return FAMILIES.get(family, (family, ()))[0]


def hashtag(family: str) -> str:
    """Telegram hashtags are letters, digits and underscores (K.1 row 9)."""
    return "#" + re.sub(r"[^a-z0-9]+", "_", str(family or "").lower()).strip("_")


def hub_name(family: str) -> str:
    return f"{family}.html" if family in FAMILIES else ""


# ------------------------------------------------------------------ evidence
def clean_evidence(ev) -> dict | None:
    """The shared-interface dict, re-coerced, WITHOUT `clip` (a runner-local path).

    The label and the wording are recomputed from source/status rather than
    trusted, so a value nobody approved can never reach the page. An author demo
    or "none" can never carry a test result: its status is forced to NOT_RUN."""
    if not isinstance(ev, dict):
        return None
    try:
        source = str(ev.get("source") or "").strip().lower()
        source = source if source in SOURCES else "none"
        status = str(ev.get("status") or "").strip().upper()
        status = status if status in WORDING else "NOT_RUN"
        if source in ("author", "none"):
            status = "NOT_RUN"
        try:
            secs = float(ev.get("clip_seconds") or 0.0)
        except (TypeError, ValueError):
            secs = 0.0
        claims = ev.get("supported_claims")
        if isinstance(claims, str):
            claims = [claims]
        claims = [_str(c, 200) for c in (claims if isinstance(claims, (list, tuple)) else [])
                  if _str(c, 200)][:5]
        rights = ev.get("rights")
        if isinstance(rights, dict):
            def _r(v):
                if isinstance(v, bool):
                    return "yes" if v else "no"
                return _str(v, 300)
            rights = {k: _r(rights.get(k)) for k in RIGHTS_KEYS}
            rights = rights if any(rights.values()) else None
        else:
            rights = None
        when = _date(ev.get("captured_at"))
        return {
            "source": source,
            "status": status,
            "label": LABELS[source],
            "wording": WORDING[status],
            "clip_seconds": secs if math.isfinite(secs) and secs > 0 else 0.0,
            "url": _link(ev.get("url")),
            "captured_at": when.isoformat() if when else "",
            "input": _str(ev.get("input"), 300),
            "observed": _str(ev.get("observed"), 400),
            "supported_claims": claims,
            "rights": rights,
        }
    except Exception:
        return None


def is_outdated(ev: dict | None, today: _dt.date) -> bool:
    """A TEST result older than OUTDATED_DAYS. An untested entry is not "outdated"."""
    if not isinstance(ev, dict) or ev.get("status") not in RESULT_STATUSES:
        return False
    when = _date(ev.get("captured_at"))
    return bool(when and (today - when).days > OUTDATED_DAYS)


def tool_name(entry: dict) -> str:
    """The display name: the signal title up to its " — trending …" tail."""
    e = entry if isinstance(entry, dict) else {}
    tool = re.split(r"\s+[—–-]\s+", _str(e.get("tool"), 200), maxsplit=1)[0].strip()
    return tool or _str(e.get("title"), 120) or "Unnamed tool"


def _tool_key(entry: dict, ev: dict) -> str:
    """One identity per tool: the demo URL (scheme-less, lowercase) or the name."""
    url = re.sub(r"^https?://(www\.)?", "", str(ev.get("url") or "").lower()).rstrip("/")
    return url or tool_name(entry).lower()


# ------------------------------------------------------------------ hub (pure)
def _rows(entries, family: str) -> list[dict]:
    out = []
    for e in entries or []:
        if not isinstance(e, dict) or family_of(e) != family:
            continue
        ev = clean_evidence(e.get("evidence"))
        if not ev:
            continue
        out.append({"entry": e, "ev": ev, "key": _tool_key(e, ev), "name": tool_name(e)})
    out.sort(key=lambda r: (r["ev"]["captured_at"], str(r["entry"].get("date", "")),
                            str(r["entry"].get("page", ""))))
    return out


def comparable(rows: list[dict]) -> tuple[str, list[dict]]:
    """K.1 row 3: hosted results on the SAME non-empty fixed input, from >= 2 tools.

    Returns (input, rows) for the input that has the most distinct tools (ties: the
    most recent test, then the input text), or ("", []) when no input qualifies."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        ev = r["ev"]
        if ev["source"] == "hosted" and ev["status"] in RESULT_STATUSES \
                and ev["input"] and ev["captured_at"]:
            groups.setdefault(ev["input"], []).append(r)
    best = ("", [])
    best_key = None
    for inp, rs in groups.items():
        tools = {r["key"] for r in rs}
        if len(tools) < MIN_COMPARABLE:
            continue
        k = (len(tools), max(r["ev"]["captured_at"] for r in rs), inp)
        if best_key is None or k > best_key:
            best_key, best = k, (inp, rs)
    return best


def _latest(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:                                   # rows are sorted oldest first
        out[r["key"]] = r
    return out


def _passed(latest: dict[str, dict]) -> tuple[str, ...]:
    return tuple(sorted(r["name"] for r in latest.values()
                        if r["ev"]["status"] == "PASSED_FIXED_TEST"))


def history(rows: list[dict]) -> list[dict]:
    """Replay the comparable results date by date (K.1 row 6). Oldest first.

    kind: "first_answer" | "recommendation_changed" | "now_passes" | "checked_again".
    "checked again" = a new result whose answer is the same as before; a new star
    count or a new repo can never produce an event, because only a test does."""
    events: list[dict] = []
    latest: dict[str, dict] = {}
    prev: tuple[str, ...] | None = None
    dates = sorted({r["ev"]["captured_at"] for r in rows})
    for d in dates:
        todays = [r for r in rows if r["ev"]["captured_at"] == d]
        flipped = []
        for r in todays:
            old = latest.get(r["key"])
            if old and old["ev"]["status"] != "PASSED_FIXED_TEST" \
                    and r["ev"]["status"] == "PASSED_FIXED_TEST":
                flipped.append(r["name"])
            latest[r["key"]] = r
        if len(latest) < MIN_COMPARABLE:
            continue                                  # no comparison exists yet
        ans = _passed(latest)
        if prev is None:
            kind = "first_answer"
        elif flipped:
            kind = "now_passes"
        elif ans != prev:
            kind = "recommendation_changed"
        else:
            kind = "checked_again"
        events.append({"date": d, "kind": kind, "answer": list(ans),
                       "previous": list(prev) if prev is not None else [],
                       "flipped": sorted(flipped), "tested": len(latest),
                       "trigger": todays[-1]})
        prev = ans
    return events


def answer_text(passed: list[str], tested: int) -> str:
    """The conditional answer (review row 12): never "best", always "among these"."""
    names = list(passed)
    if not names:
        return (f"None of the {tested} options we tested passed our fixed test on this "
                "input, so we cannot recommend one yet.")
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return f"Among the {tested} options we tested on this input, {joined} passed our fixed test."


def hub(entries, family: str, today: _dt.date, withdrawn=()) -> dict | None:
    """The hub for one family, or None when it has < 2 comparable hosted tests."""
    try:
        if family not in FAMILIES:
            return None
        rows = _rows(entries, family)
        inp, group = comparable(rows)
        if not group:
            return None
        latest = _latest(group)
        tested = sorted(latest.values(), key=lambda r: (r["ev"]["status"] != "PASSED_FIXED_TEST",
                                                        r["name"].lower()))
        newest = max(r["ev"]["captured_at"] for r in group)
        passed = list(_passed(latest))
        in_group = {id(r) for r in group}
        candidates = [r for r in rows if id(r) not in in_group]
        # one profile per tool: the newest row wins
        seen, profiles = set(), []
        for r in reversed(candidates):
            if r["key"] in seen or r["key"] in latest:
                continue
            seen.add(r["key"])
            profiles.append(r)
        nd = _date(newest)
        if family in set(withdrawn or ()):
            state = "withdrawn"
        elif nd and (today - nd).days > OUTDATED_DAYS:
            state = "outdated"
        elif not passed:
            state = "inconclusive"
        else:
            state = "current"
        return {
            "family": family, "label": label(family), "name": hub_name(family),
            "hashtag": hashtag(family), "state": state, "input": inp,
            "passed": passed, "tested": tested, "candidates": profiles,
            "history": history(group), "newest": newest,
            "answer": answer_text(passed, len(latest)),
        }
    except Exception:
        return None


def hubs(entries, today: _dt.date, cap: int | None = None, withdrawn=None) -> list[dict]:
    """Every hub that may render, capped (K.1 row 7). Never raises.

    Ordered by comparable-tool count, then newest test, then family name. A
    withdrawn hub does not count against the cap: it is an existing URL being
    kept stable with a withdrawal notice, not a new page."""
    try:
        if not fv.flag("task_hubs", True):
            return []
        if cap is None:
            try:
                cap = int(fv.setting("task_hubs_max", 1))
            except (TypeError, ValueError):
                cap = 1
        if withdrawn is None:
            raw = fv.setting("task_hubs_withdrawn", []) or []
            withdrawn = [str(x) for x in raw] if isinstance(raw, (list, tuple)) else []
        found = []
        for fam in FAMILIES:
            try:
                h = hub(entries, fam, today, withdrawn)
            except Exception:
                h = None
            if h:
                found.append(h)
        # most comparable tools first, then the newest test; the family name only
        # breaks an exact tie, so the choice is deterministic
        live = sorted((h for h in found if h["state"] != "withdrawn"),
                      key=lambda h: (len(h["tested"]), h["newest"], h["family"]), reverse=True)
        out = live[:max(0, cap)] + [h for h in found if h["state"] == "withdrawn"]
        return sorted(out, key=lambda h: h["family"])
    except Exception:
        return []


# ------------------------------------------------------------------ follow + alerts
def follow_channel() -> str:
    """The public Telegram channel username from config, validated, or "".

    Telegram usernames are 5-32 chars of letters, digits and underscores and start
    with a letter. Anything else hides the offer instead of linking garbage."""
    try:
        raw = str(fv.setting("task_follow_channel", "") or "").strip().lstrip("@")
        return raw if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", raw) else ""
    except Exception:
        return ""


def event_id(family: str, inp: str, ev: dict) -> str:
    """Stable identity for one alert: the same event always has the same id."""
    h = hashlib.sha1(inp.encode("utf-8")).hexdigest()[:8]
    return "|".join((family, h, ev["date"], ev["kind"], ",".join(ev["answer"])))


def alert_events(entries, today: _dt.date) -> list[dict]:
    """Material changes that may be announced now, newest first (K.1 rows 10-11)."""
    out = []
    try:
        for h in hubs(entries, today):
            if h["state"] in ("withdrawn", "outdated"):
                continue
            for ev in h["history"]:
                d = _date(ev["date"])
                if ev["kind"] not in ALERT_KINDS or not d:
                    continue
                if not (0 <= (today - d).days < ALERT_MAX_DAYS):
                    continue
                out.append(dict(ev, id=event_id(h["family"], h["input"], ev), hub=h))
    except Exception:
        return []
    out.sort(key=lambda e: (e["date"], e["id"]), reverse=True)
    return out
