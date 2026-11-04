"""
v3-M.1 row 16: the second-slot shadow queue (docs/spec/ai-pulse-v3m1.md).

Every automatic publish run records ONE line in state/shadow_queue.jsonl:
whether a SECOND tool candidate passed the pre-writer gates (eligible source,
grounding floor, suitability screen, evidence.probe) and the run's wall time.
Nothing is written, rendered or uploaded for that candidate — this only
measures supply and headroom.

The evaluator (verbatim, round 4 Rank 5): over a 14-day window, >= 10 days with
a qualified second candidate, p95 job time < 60 min, and no missed primary
uploads -> eligible for the later 1-vs-2 quantity test. That test is spec only.

Fail-soft end to end: `after_run` runs after run() has returned (the ledger row
is already written), inside its own try, under a hard wall-clock budget.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import threading
import time
from pathlib import Path

from factverse import config as fv
from factverse import learn
from factverse import memory

SHADOW_LOG = fv.STATE / "shadow_queue.jsonl"

# --- locked (round 4 Rank 5) -------------------------------------------------------
WINDOW_DAYS = 14
MIN_QUALIFIED_DAYS = 10
P95_MAX_S = 60 * 60
# --- delegated ---------------------------------------------------------------------
MAX_CANDIDATES = 3          # the same cut build_script applies to the primary
BUDGET_S = 60.0             # hard wall clock for all of the shadow's network
README_LIMIT = 5000         # what the writer would read (script_tool's window)


def _norm_url(u) -> str:
    return str(u or "").strip().rstrip("/").lower()


def prewriter_gate(item: dict, ap) -> dict:
    """script_tool's checks BEFORE its writer call, in its order, for one
    candidate. `ap` is the ai_pipeline module (passed in: under `python -m` the
    running module is __main__, and importing factverse.ai_pipeline again would
    load the whole pipeline a second time)."""
    title, url = str(item.get("title") or ""), str(item.get("url") or "")
    chk = {"title": title[:120], "url": url[:300], "title_screen": True, "eligible": False,
           "grounding_chars": 0, "grounding_ok": False, "suitable": False, "term": "",
           "evidence": "", "passed": False, "qualified": False}
    blocked, term = ap.gates.tool_unsuitable(title)
    if blocked:
        chk.update(title_screen=False, term=str(term))
        return chk
    chk["eligible"] = bool(ap.tool_source_eligible(url))
    if not chk["eligible"]:
        return chk
    readme, page = ap._hf_readme_url(url), None
    if readme:
        grounding = (ap.fetch_text(readme, limit=ap.TOOL_README_FETCH) or "")[:README_LIMIT]
    else:
        raw = ap._gh_readme_url(url)
        grounding = ((ap.fetch_text(raw, limit=ap.TOOL_README_FETCH) if raw else "") or "")[:README_LIMIT]
        page = ap.fetch_text(url, limit=README_LIMIT) or ""
        if len(grounding) < ap.TOOL_GROUNDING_MIN:
            grounding = page
    chk["grounding_chars"] = len(grounding)
    chk["grounding_ok"] = len(grounding) >= ap.TOOL_GROUNDING_MIN
    if not chk["grounding_ok"]:
        return chk
    screen = grounding if page is None else f"{grounding} {page}"
    unsuitable, term = ap.gates.tool_unsuitable(title, screen or grounding)
    chk["suitable"], chk["term"] = not unsuitable, str(term or "")
    if unsuitable:
        return chk
    chk["passed"] = True
    label, _ = memory.evidence_probe(item)
    chk["evidence"] = label
    # qualified = every pre-writer gate AND admissible evidence; a missing or failed
    # probe is "unknown", which the evaluator never counts as qualified
    chk["qualified"] = (True if label in memory.ADMISSIBLE_SOURCES
                        else "unknown" if label == "unknown" else False)
    return chk


def second_candidates(ranked: list, primary_url: str) -> list[dict]:
    """Tool signals other than the primary (by URL and by tool name), in rank order."""
    p_url, p_ent = _norm_url(primary_url), memory.norm_query(memory.entity_of(primary_url))
    out = []
    for c in ranked or []:
        if not isinstance(c, dict) or c.get("kind") != "tool":
            continue
        u = _norm_url(c.get("url"))
        if (p_url and u == p_url) or (p_ent and memory.norm_query(memory.entity_of(u)) == p_ent):
            continue
        out.append(c)
    return out


def check(ranked: list, primary_url: str, ap, budget_s: float = BUDGET_S,
          max_candidates: int = MAX_CANDIDATES) -> dict:
    """Gate up to `max_candidates` second candidates and stop at the first qualified
    one. Runs in a daemon thread joined with `budget_s`: requests' timeout is a
    per-read gap, not a deadline, so only a wall clock bounds a slow-drip page."""
    # The no-network screens run BEFORE the cut, as build_script's do (spec v3-B.4):
    # measured live 2026-11-04, three Product Hunt pages ranked ahead of a GitHub
    # repo that passes, and a cut first spent all 3 slots on them.
    others = second_candidates(ranked, primary_url)
    able = [c for c in others if not ap.gates.tool_unsuitable(str(c.get("title") or ""))[0]
            and ap.tool_source_eligible(str(c.get("url") or ""))]
    cands = able[:max_candidates]
    done: list[dict] = []

    def work():
        for c in cands:
            try:
                done.append(prewriter_gate(c, ap))
            except Exception as e:  # noqa: BLE001 — one candidate costs only itself
                done.append({"title": str(c.get("title"))[:120], "error": type(e).__name__,
                             "passed": False, "qualified": False})
            if done[-1].get("qualified") is True:
                break

    t0 = time.monotonic()
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(budget_s)
    checked = list(done)
    best = next((c for c in checked if c.get("qualified") is True), None) \
        or next((c for c in checked if c.get("qualified") == "unknown"), None)
    return {"candidates": len(cands), "screened_out": len(others) - len(able), "checked": checked,
            "qualified": best["qualified"] if best else False,
            "second": best, "network_s": round(time.monotonic() - t0, 1),
            "timed_out": th.is_alive()}


def _primary(today: dt.date, runs_path: Path | None = None) -> dict:
    """Today's newest ledger row (the run that just finished)."""
    for r in reversed(learn.read_runs(runs_path)):
        if isinstance(r, dict) and str(r.get("timestamp", "")).startswith(today.isoformat()):
            return r
    return {}


def after_run(ranked: list, ap, publish: bool, forced, run_s: float,
              path: Path | None = None, runs_path: Path | None = None) -> dict | None:
    """Called once per process from ai_pipeline's __main__, after run() returned.
    Automatic publish runs only; a duplicate-day skip never ranks, so it has no
    `ranked` and records nothing. Returns the row, or None."""
    try:
        if not fv.flag("shadow_queue", False) or not publish or forced or not ranked:
            return None
        today = dt.datetime.utcnow().date()
        prim = _primary(today, runs_path)
        res = check(ranked, str(prim.get("source_url") or ""), ap)
        job_s = None
        try:
            job_s = round(time.time() - float(os.environ["JOB_STARTED_AT"]), 1)
        except (KeyError, ValueError):
            pass
        row = {"date": today.isoformat(),
               "timestamp": dt.datetime.utcnow().isoformat(timespec="seconds"),
               "primary_status": prim.get("status"), "primary_format": prim.get("format"),
               "primary_url": prim.get("source_url") or None,
               "candidates": res["candidates"], "screened_out": res["screened_out"],
               "qualified": res["qualified"],
               "second": res["second"], "checked": res["checked"],
               "network_s": res["network_s"], "timed_out": res["timed_out"],
               "run_s": round(float(run_s), 1), "job_s": job_s}
        with open(path or SHADOW_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        sec = res["second"] or {}
        print(f"  🪞 shadow queue: second candidate {res['qualified']!s} "
              f"({sec.get('title', 'none')[:50]}), {res['network_s']} s network, "
              f"run {row['run_s']} s")
        return row
    except Exception as e:  # noqa: BLE001 — the day is already done; never fail it
        print(f"  ⚠️ shadow queue skipped: {type(e).__name__}: {e}")
        return None


# ------------------------------------------------------------------ the evaluator
def read_log(path: Path | None = None) -> list[dict]:
    p = Path(path or SHADOW_LOG)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict) and memory._date(d.get("date")):
            out.append(d)
    return out


def p95(values: list[float]) -> float | None:
    """Nearest-rank 95th percentile."""
    vals = sorted(v for v in values if math.isfinite(v))
    if not vals:
        return None
    return vals[max(0, math.ceil(0.95 * len(vals)) - 1)]


def evaluate(log: list[dict], rows: list[dict], today: dt.date) -> dict:
    """The 14 days ending today. A window that starts before the first shadow row
    is 'insufficient observations' (unresolved), never eligible or not."""
    start = today - dt.timedelta(days=WINDOW_DAYS - 1)
    days = [start + dt.timedelta(days=i) for i in range(WINDOW_DAYS)]
    first = min((memory._date(r["date"]) for r in log), default=None)
    inwin = [r for r in log if start <= memory._date(r["date"]) <= today]
    qualified = {memory._date(r["date"]) for r in inwin if r.get("qualified") is True}
    unknown = {memory._date(r["date"]) for r in inwin if r.get("qualified") == "unknown"} - qualified
    times = []
    for r in inwin:
        t = r.get("job_s") if r.get("job_s") is not None else r.get("run_s")
        n = learn._num(t)
        if n > 0:
            times.append(n)
    published = {learn._date(r.get("timestamp")) for r in rows
                 if isinstance(r, dict) and r.get("status") == "PUBLISHED"}
    # today is not final until the 14:53 retry cron has had its turn
    missed = [d for d in days if d < today and d not in published]
    out = {"start": start, "end": today, "observed": len({memory._date(r["date"]) for r in inwin}),
           "qualified_days": len(qualified), "unknown_days": len(unknown),
           "p95_s": p95(times), "missed": missed}
    if first is None or first > start:
        out["verdict"] = "unresolved - insufficient observations"
        return out
    reasons = []
    if len(qualified) < MIN_QUALIFIED_DAYS:
        reasons.append(f"{len(qualified)} of {MIN_QUALIFIED_DAYS} qualified days")
    if out["p95_s"] is None or out["p95_s"] >= P95_MAX_S:
        reasons.append("p95 job time not under 60 min")
    if missed:
        reasons.append(f"{len(missed)} missed primary upload(s)")
    out["verdict"] = ("ELIGIBLE for the 1-vs-2 quantity test" if not reasons
                      else "not eligible: " + "; ".join(reasons))
    return out


def block(rows: list[dict], path: Path | None = None, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    log = read_log(path)
    ev = evaluate(log, rows, today)
    p = f"{ev['p95_s'] / 60:.1f} min" if ev["p95_s"] is not None else "-"
    lines = [f"shadow queue (second daily long-form) - window {ev['start']}..{ev['end']}",
             f"  rows logged: {len(log)} total; days observed in window: {ev['observed']} of "
             f"{WINDOW_DAYS}",
             f"  days with a qualified second candidate: {ev['qualified_days']} "
             f"(needs >= {MIN_QUALIFIED_DAYS}); evidence unknown: {ev['unknown_days']}",
             f"  p95 job time: {p} (needs < 60 min); missed primary uploads: {len(ev['missed'])}",
             f"  verdict: {ev['verdict']}"]
    return "\n".join(lines) + "\n"
