"""
v3-L pilot scorecard — turns the live pilot's session log into a decision
(CONTINUE / REVISE / STOP / INSUFFICIENT DATA), measured against the channel's
own baseline from state/analytics.jsonl.

    py -3 scripts/live_scorecard.py --init      # writes an empty log to fill in
    py -3 scripts/live_scorecard.py             # reads the log, prints the verdict

The log is filled BY HAND from YouTube Studio (the Analytics API this repo uses
does not list live streams: the collector only asks for ledger videos). One row
per session, completed 7 days after the stream, so `watch_hours_7d` includes the
replay. Rules and thresholds: docs/spec/ai-pulse-v3l.md §7 — every number below
is a row there; change it there first.

Targets in that table are TARGETS, not predictions. A CONTINUE verdict says the
pilot beat its bar; it says nothing about YPP acceptance, which is a review.
"""
import argparse
import csv
import json
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "temp" / "live" / "pilot_log.csv"
ANALYTICS = ROOT / "state" / "analytics.jsonl"

COLUMNS = [
    "session", "date", "video_id", "duration_min", "peak_concurrent",
    "watch_hours_7d", "avg_view_duration_s", "subs_gained",
    "stream_health_ok", "policy_notice", "owner_minutes", "notes",
]
REQUIRED = ["session", "date", "duration_min", "peak_concurrent", "watch_hours_7d",
            "subs_gained", "stream_health_ok", "policy_notice"]

# spec §7 (PROPOSED until the owner approves the table)
MIN_SESSIONS = 4                 # §7.1 sessions before any verdict but STOP-on-notice
CONTINUE_MEDIAN_HOURS = 2.0      # §7.2 = the whole channel's mean weekly watch hours
CONTINUE_TOTAL_SUBS = 4          # §7.3 = the whole channel's subs in its last 28 days
STOP_MEDIAN_HOURS = 0.5          # §7.4
STOP_MAX_PEAK = 3                # §7.5
# YPP thresholds, support.google.com/youtube/answer/13429240 and /72851 (2026-10-01)
YPP_HOURS = {"expanded (fan funding)": 3000, "ad revenue": 4000}
BASELINE_DAYS = 28


def _yes(v) -> bool:
    return str(v).strip().lower() in ("yes", "y", "true", "1")


def _num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def parse_rows(rows: list) -> tuple:
    """(sessions, problems). A row missing a required field is reported, not guessed."""
    sessions, problems = [], []
    for i, r in enumerate(rows, start=2):          # line 1 is the header
        if not any((r.get(c) or "").strip() for c in COLUMNS):
            continue
        missing = [c for c in REQUIRED if not (r.get(c) or "").strip()]
        nums = {c: _num(r.get(c)) for c in
                ("duration_min", "peak_concurrent", "watch_hours_7d", "subs_gained")}
        bad = [c for c, v in nums.items() if (r.get(c) or "").strip() and v is None]
        if missing or bad:
            problems.append(f"line {i}: missing {missing} / not a number {bad}")
            continue
        sessions.append({**r, **nums,
                         "health_ok": _yes(r["stream_health_ok"]),
                         "notice": _yes(r["policy_notice"])})
    return sessions, problems


def verdict(sessions: list) -> tuple:
    """(VERDICT, reasons). Pure: the whole decision table of spec §7."""
    if any(s["notice"] for s in sessions):
        return "STOP", ["a policy/copyright notice was received (§7.6) — stop and read it"]
    if len(sessions) < MIN_SESSIONS:
        return "INSUFFICIENT DATA", [f"{len(sessions)} of {MIN_SESSIONS} sessions logged (§7.1)"]
    med = statistics.median(s["watch_hours_7d"] for s in sessions)
    subs = sum(s["subs_gained"] for s in sessions)
    peak = max(s["peak_concurrent"] for s in sessions)
    healthy = all(s["health_ok"] for s in sessions)
    facts = [f"median watch hours/session (7 d) = {med:.2f}",
             f"subs gained in pilot = {subs:g}", f"max peak concurrent = {peak:g}",
             f"every stream healthy = {healthy}"]
    if med < STOP_MEDIAN_HOURS and peak < STOP_MAX_PEAK:
        return "STOP", facts + [f"median < {STOP_MEDIAN_HOURS} h AND peak < {STOP_MAX_PEAK} (§7.4/§7.5)"]
    if med >= CONTINUE_MEDIAN_HOURS and subs >= CONTINUE_TOTAL_SUBS and healthy:
        return "CONTINUE", facts + ["all three CONTINUE bars met (§7.2/§7.3, healthy)"]
    return "REVISE", facts + ["between the bars — change ONE variable (§7.7) and run 4 more"]


def channel_baseline(lines: list, days: int = BASELINE_DAYS) -> dict:
    """Watch hours + subs over the last `days` reported days, latest snapshot wins
    per day. Channel totals include Shorts, so for YPP this is an UPPER bound."""
    by_day = {}
    for line in lines:
        try:
            snap = json.loads(line)
        except ValueError:
            continue
        for d in snap.get("channel_days") or []:
            if isinstance(d, list) and len(d) >= 6:
                by_day[str(d[0])] = d
    if not by_day:
        return {}
    last = max(by_day)
    first = (date.fromisoformat(last) - timedelta(days=days - 1)).isoformat()
    win = [by_day[k] for k in sorted(by_day) if first <= k <= last]
    minutes = sum(_num(d[2]) or 0 for d in win)
    # A day whose average view percentage is over 100% was watched more than
    # end-to-end on average. On this channel those days (08-23, 08-24, 09-02)
    # line up with the self-view period PHASES "Now #0" ended, so the baseline
    # is reported both ways and the excluded days are named, never dropped silently.
    rewatch = [d for d in win if (_num(d[4]) or 0) > 100]
    kept = sum(_num(d[2]) or 0 for d in win if d not in rewatch)
    return {"from": first, "to": last, "days_reported": len(win),
            "watch_hours": round(minutes / 60, 1),
            "watch_hours_excl_rewatch": round(kept / 60, 1),
            "rewatch_days": [str(d[0]) for d in rewatch],
            "subs": int(sum(_num(d[5]) or 0 for d in win))}


def projection(base_hours_28d: float, session_hours: float, sessions_per_28d: int) -> list:
    """[(tier, hours_in_12_months, needed_per_28d, reachable)] at a constant rate.

    YPP counts a ROLLING 12 months, so "months until the threshold" is the wrong
    question: at a constant rate the 12-month total either clears the bar or it
    never does. Arithmetic, not a forecast — nothing compounds, nothing decays."""
    per_28d = base_hours_28d + session_hours * sessions_per_28d
    year = per_28d * 365 / 28
    return [(tier, round(year), round(h * 28 / 365, 1), year >= h)
            for tier, h in YPP_HOURS.items()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--init", action="store_true", help="write an empty log")
    ap.add_argument("--log", default=str(LOG))
    ap.add_argument("--sessions-per-28d", type=int, default=8,
                    help="pilot cadence for the projection (spec §6: 2 per week)")
    a = ap.parse_args(argv)
    log = Path(a.log)
    if a.init:
        if log.exists():
            print(f"{log} already exists — not overwriting")
            return 1
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(COLUMNS)
        print(f"wrote {log}")
        return 0
    rows = []
    if log.exists():
        with log.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    sessions, problems = parse_rows(rows)
    for p in problems:
        print("⚠ " + p)
    base = {}
    if ANALYTICS.exists():
        base = channel_baseline(ANALYTICS.read_text(encoding="utf-8").splitlines())
    if base:
        print(f"baseline {base['from']}..{base['to']} ({base['days_reported']} days reported): "
              f"{base['watch_hours']} watch h, {base['subs']} subs — channel total incl. Shorts")
        if base["rewatch_days"]:
            print(f"  excluding days with average view % > 100 {base['rewatch_days']}: "
                  f"{base['watch_hours_excl_rewatch']} watch h — the projection uses this")
    v, reasons = verdict(sessions)
    print(f"VERDICT: {v}")
    for r in reasons:
        print("  · " + r)
    if sessions and base:
        med = statistics.median(s["watch_hours_7d"] for s in sessions)
        hours = base["watch_hours_excl_rewatch"]
        print(f"projection at {a.sessions_per_28d} sessions/28 d × {med:.2f} h "
              f"+ baseline {hours} h/28 d (arithmetic, not a forecast):")
        for tier, year, need, ok in projection(hours, med, a.sessions_per_28d):
            print(f"  {tier}: {year} h per rolling 12 months vs {YPP_HOURS[tier]} needed "
                  f"({need} h per 28 d) → {'reachable' if ok else 'NOT reachable at this rate'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
