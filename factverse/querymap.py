"""v3-P.2 query-map packaging for tool videos (review row 13, round 4 Rank 2).

  * Title = entity (+ task): hosted → "RepoName — <Task>: Hosted Demo and Limits",
    author → "RepoName Demo Explained: Requirements and Limits". One canonical
    name; no separate spellings.
  * The description's first sentence names the tool (with its genuinely used
    alias, owner/repo), the task and the evidence status; the command and
    cheat-sheet block sit directly below it (place_description_blocks).
  * Chapters are descriptive and exist only where the section really exists:
    00:00 first, >= 3 timestamps, every section >= 10 s.
  * The ledger gets three timestamps: first detected signal, first admissible
    evidence, publication (state/first_seen.json keeps the first two).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from factverse import config as fv

TITLE_MAX = 95
TASK_MAX_WORDS = 5
TASK_MAX_CHARS = 40
CHAPTER_MIN_GAP = 10          # YouTube: each chapter >= 10 s
CHAPTER_MIN_COUNT = 3
FIRST_SEEN = fv.STATE / "first_seen.json"
FIRST_SEEN_CAP = 3000

_REPO = re.compile(r"https?://(?:www\.)?(?:github\.com|huggingface\.co)/([\w.-]+)/([\w.-]+)")


def name_alias(script) -> tuple[str, str]:
    """(canonical name, alias): the repo/model name and its owner/name form."""
    url = str((script or {}).get("source_url") or "")
    m = _REPO.match(url)
    if not m:
        ev = (script or {}).get("evidence") or {}
        m = _REPO.match(str(ev.get("url") or "")) if isinstance(ev, dict) else None
    if not m:
        return "", ""
    owner, name = m.group(1), re.sub(r"\.git$", "", m.group(2))
    return name, f"{owner}/{name}"


def clean_task(task) -> str:
    """The model's `task` field, coerced: a short noun-ish phrase, no claim
    punctuation, at most TASK_MAX_WORDS words — "" when unusable."""
    t = re.sub(r"[<>\"“”:;|#]", "", str(task or "")).strip(" .-—")
    t = re.sub(r"\s+", " ", t)
    if not t or len(t.split()) > TASK_MAX_WORDS or len(t) > TASK_MAX_CHARS:
        return ""
    if re.search(r"\d+\s*(?:x|×|%)", t, re.I):          # an outcome claim is not a task
        return ""
    return " ".join(w[:1].upper() + w[1:] for w in t.split())


def query_title(script) -> str:
    name, _ = name_alias(script)
    ev = (script or {}).get("evidence") or {}
    if not name or not isinstance(ev, dict):
        return ""
    if ev.get("source") == "hosted":
        task = clean_task(script.get("task"))
        t = f"{name} — {task}: Hosted Demo and Limits" if task else f"{name}: Hosted Demo and Limits"
        return t if len(t) <= TITLE_MAX else f"{name}: Hosted Demo and Limits"[:TITLE_MAX]
    if ev.get("source") == "author":
        return f"{name} Demo Explained: Requirements and Limits"[:TITLE_MAX]
    return ""


def first_sentence(script) -> str:
    """Tool + task + evidence status, one sentence. "" when not applicable."""
    name, alias = name_alias(script)
    ev = (script or {}).get("evidence") or {}
    if not name or not isinstance(ev, dict) or ev.get("source") not in ("hosted", "author"):
        return ""
    task = clean_task(script.get("task")).lower()
    who = f"{name} ({alias})" + (f" for {task}" if task else "")
    status = str(ev.get("wording") or "").rstrip(".")
    status = status[:1].lower() + status[1:]
    if ev.get("source") == "hosted":
        return f"{who}, shown in our hosted-demo run of {ev.get('captured_at', '')}: {status}."
    return f"{who}, shown through the author's own demo: {status}."


def apply(script: dict) -> bool:
    """Set the query-map title (the old one stays first among the alternates)
    and the tags. Never raises; False when nothing applied."""
    try:
        t = query_title(script)
        if not t:
            return False
        name, alias = name_alias(script)
        old = str(script.get("title") or "")
        alts = [x for x in ([old] + list(script.get("titles") or [])) if x and x != t]
        script["title"], script["titles"] = t, [t] + alts[:4]
        tags = [str(x) for x in script.get("tags") or []]
        for extra in (name, alias):
            if extra and extra.lower() not in (x.lower() for x in tags):
                tags.insert(0, extra)
        script["tags"] = tags[:28]
        script["query_map"] = {"name": name, "alias": alias, "task": clean_task(script.get("task"))}
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ query-map title skipped ({type(e).__name__}: {e})")
        return False


def lead_description(desc: str, script) -> str:
    """Put first_sentence() first, as its own paragraph. Idempotent: any earlier
    paragraph opening with the same "Name (alias)" prefix is cut first, so a
    rewrite pass that mangled the sentence cannot leave two of them."""
    s = first_sentence(script)
    if not s:
        return desc
    name, alias = name_alias(script)
    prefix = f"{name} ({alias})"
    paras = [p for p in str(desc or "").split("\n\n") if not p.strip().startswith(prefix)]
    return s + "\n\n" + "\n\n".join(paras).lstrip("\n")


def _mmss(t: float) -> str:
    t = max(0, int(t))
    return f"{t // 60:02d}:{t % 60:02d}"


def chapters(candidates: list[tuple[float, str]]) -> str:
    """Descriptive chapters from (start seconds, label) of sections that EXIST.
    The first is forced to 00:00; a section starting < 10 s after the previous
    kept one is merged into it. Fewer than 3 → "" (no chapters at all)."""
    rows = sorted((max(0.0, float(t)), str(l)) for t, l in candidates if l)
    if not rows:
        return ""
    kept = [(0.0, rows[0][1])]
    for t, label in rows[1:]:
        if t - kept[-1][0] >= CHAPTER_MIN_GAP and label != kept[-1][1]:
            kept.append((t, label))
    if len(kept) < CHAPTER_MIN_COUNT:
        return ""
    return "Chapters:\n" + "\n".join(f"{_mmss(t)} {l}" for t, l in kept)


# ------------------------------------------------------------- three timestamps
def _now() -> str:
    return dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _load_seen(path: Path | None = None) -> dict:
    try:
        d = json.loads(Path(path or FIRST_SEEN).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def note_seen(urls, field: str = "signal", path: Path | None = None, when: str | None = None) -> None:
    """Record the FIRST time each url was seen as a tool signal / with admissible
    evidence. Earliest wins; never raises (it runs before the upload)."""
    try:
        if field not in ("signal", "evidence"):
            return
        d = _load_seen(path)
        stamp = when or _now()
        for u in urls or []:
            u = str(u or "").strip()
            if not u.startswith("http"):
                continue
            e = d.get(u) if isinstance(d.get(u), dict) else {}
            if not e.get(field) or str(stamp) < str(e[field]):
                e[field] = stamp
            d[u] = e
        if len(d) > FIRST_SEEN_CAP:
            keep = sorted(d.items(), key=lambda kv: str((kv[1] or {}).get("signal", "")))[-FIRST_SEEN_CAP:]
            d = dict(keep)
        Path(path or FIRST_SEEN).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ first-seen record skipped ({type(e).__name__}: {e})")


def timestamps(script, publish_at, path: Path | None = None) -> dict:
    """The ledger's three timestamps, coerced strings ("" when unknown)."""
    try:
        e = _load_seen(path).get(str((script or {}).get("source_url") or ""), {})
        e = e if isinstance(e, dict) else {}
        return {"t_signal": str(e.get("signal") or ""), "t_evidence": str(e.get("evidence") or ""),
                "t_publication": str(publish_at or "")}
    except Exception:  # noqa: BLE001
        return {"t_signal": "", "t_evidence": "", "t_publication": str(publish_at or "")}
