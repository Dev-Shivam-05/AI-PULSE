"""
v3-M.1 row 10: the north star and its ladder, plus the search-longevity cohorts
(the review's open point). docs/spec/ai-pulse-v3m1.md.

North star = rolling 28-day ON-DEMAND long-form watch time: the Analytics API's
creatorContentType == VIDEO_ON_DEMAND, read nightly by analytics.collect_m1.
Live / archived-live (LIVE_STREAM) is a separate counter and never counts.

Pure: reads state files only. Display only — nothing here steers the pipeline.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from factverse import learn
from factverse import memory

# --- locked (round 3 §6; RESULT.md row 10) ----------------------------------------
BASELINE_H = 12.11                      # Oct 7 - Nov 3 2026, long-form only
BASELINE_WINDOW = "2026-10-07..2026-11-03"
OUTLIER_SHARE = 0.50                    # largest video above this = outlier-dependent
PILOT_EXPERIMENT = "pilot_a"            # day 0 = first PUBLISHED row of the new contract
# (stage, target hours per 28 days, checkpoint day or None, leading evidence verbatim)
LADDER = (
    ("2x", 24.22, 30, "At least one opening treatment is promising across the stated minimum "
                      "sample; usable evidence supply supports at least 3 eligible tool videos "
                      "per week without lowering safeguards."),
    ("5x", 60.55, 60, "Latest six mature tool uploads have median seven-day watch time at least "
                      "2x the frozen pre-pilot tool median; at least two evidence-backed "
                      "follow-ups have been published and evaluated."),
    ("10x", 121.10, 90, "Latest six mature uploads reach at least 3x that pre-pilot median; growth "
                        "is visible in at least two task families, rather than one repository."),
    ("25x", 302.75, None, "At least three task families have produced repeat performers; "
                          "next-video continuation is measurable rather than inferred."),
    ("50x", 605.50, None, "The level persists across two consecutive non-overlapping 28-day "
                          "windows, with subscriber growth and qualified-hour accumulation "
                          "tracked separately."),
    ("100x", 1211.00, None, "The level persists across two such windows, with multiple "
                            "contributing videos/families and demonstrated continuation or "
                            "repeat viewing."),
)
PERSIST_STAGES = ("50x", "100x")        # need two consecutive non-overlapping windows
# --- delegated ---------------------------------------------------------------------
WINDOW_GAP_TOLERANCE = 1                # days: "consecutive" windows may be 1 day apart
LATEST_SIX = 6


def _vod_hours(ns: dict) -> float | None:
    by = ns.get("by_type") if isinstance(ns, dict) else None
    if not isinstance(by, dict):
        return None
    return learn._num((by.get("VIDEO_ON_DEMAND") or {}).get("minutes")) / 60.0


def windows(snaps: list[dict]) -> list[dict]:
    """Every north-star observation, one per window end (newest snapshot wins),
    oldest first: {start, end, hours, live_h, top, collected}."""
    by_end: dict[str, dict] = {}
    for s in snaps:
        ns = s.get("north_star")
        if not isinstance(ns, dict):
            continue
        start, end = memory._date(ns.get("start")), memory._date(ns.get("end"))
        hours = _vod_hours(ns)
        if not (start and end) or hours is None:
            continue
        by = ns.get("by_type") or {}
        top = s.get("vod_top") if isinstance(s.get("vod_top"), dict) else {}
        vids = [v for v in top.get("videos") or [] if isinstance(v, list) and len(v) >= 2]
        by_end[end.isoformat()] = {
            "start": start, "end": end, "hours": hours,
            "live_h": learn._num((by.get("LIVE_STREAM") or {}).get("minutes")) / 60.0,
            "top": (max(vids, key=lambda v: learn._num(v[1])) if vids else None)
            if top.get("end") == ns.get("end") else None,
            "collected": s.get("collected")}
    return [by_end[k] for k in sorted(by_end)]


def day_zero(rows: list[dict]) -> dt.date | None:
    """The first publication under the new production contract: the first
    PUBLISHED ledger row with experiment == "pilot_a" (its publish date)."""
    for r in rows:
        if (isinstance(r, dict) and r.get("status") == "PUBLISHED"
                and r.get("experiment") == PILOT_EXPERIMENT):
            return learn._date(r.get("publish_at")) or learn._date(r.get("timestamp"))
    return None


def outlier(win: dict | None) -> tuple[float | None, str | None]:
    """(largest video's share of the window's on-demand watch time, its id)."""
    if not win or not win.get("top") or not win["hours"]:
        return None, None
    vid, minutes = win["top"][0], learn._num(win["top"][1])
    return minutes / 60.0 / win["hours"], str(vid)


def _previous(wins: list[dict], cur: dict) -> dict | None:
    """The window that ends right before `cur` starts (non-overlapping, consecutive)."""
    for w in reversed(wins):
        gap = (cur["start"] - w["end"]).days
        if 1 <= gap <= 1 + WINDOW_GAP_TOLERANCE:
            return w
    return None


def stage_status(stage: tuple, day0: dt.date | None, today: dt.date,
                 wins: list[dict]) -> str:
    name, target, day, _ = stage
    if day0 is None:
        return "not started"
    if day is not None:
        due = day0 + dt.timedelta(days=day)
        if today < due:
            return f"pending (day {(today - day0).days} of {day})"
        # judged on the first window that reaches the checkpoint (it ends the day before)
        obs = [w for w in wins if w["end"] >= due - dt.timedelta(days=1)]
        if not obs:
            return "unresolved - insufficient observations"
        w = obs[0]
        if w["hours"] >= target:
            share, _ = outlier(w)
            tail = " - outlier-dependent" if share is not None and share > OUTLIER_SHARE else ""
            return (f"hours met ({w['hours']:.2f} h){tail}; on track only if the leading "
                    f"evidence holds")
        return f"behind plan ({w['hours']:.2f} of {target:.2f} h)"
    if not wins:
        return "unresolved - insufficient observations"
    cur = wins[-1]
    if cur["hours"] < target:
        return "not reached"
    if name in PERSIST_STAGES:
        prev = _previous(wins, cur)
        if prev is None:
            return "met in 1 window; unresolved until the previous window is observed"
        return ("met in 2 consecutive windows" if prev["hours"] >= target
                else "met in 1 window (needs 2 consecutive)")
    return "hours met"


def proxy_hours(rows: list[dict], snaps: list[dict]) -> dict | None:
    """DISPLAY-ONLY estimate while no north-star snapshot exists: the growth of the
    cumulative ledger numbers over 28 days, ledger long-forms only (videos
    published before 2026-08-24 are missing, and snapshot dates are collection
    dates, not data dates)."""
    long_ids = {v["id"] for v in learn.ledger_videos(rows)}
    pts = []
    for s in snaps:
        heads, led = s.get("ledger_headers"), s.get("ledger_videos")
        day = memory._date(s.get("collected"))
        if not (isinstance(heads, list) and isinstance(led, list) and day):
            continue
        try:
            iv, imin = heads.index("video"), heads.index("estimatedMinutesWatched")
        except ValueError:
            continue
        pts.append((day, {str(r[iv]): learn._num(r[imin]) for r in led
                          if isinstance(r, list) and len(r) > max(iv, imin)}))
    if len(pts) < 2:
        return None
    new_day, new = pts[-1]
    older = [p for p in pts if (new_day - p[0]).days >= memory.FOLLOWUP_WINDOW_DAYS]
    if not older:
        return None
    old_day, old = older[-1]
    mins = sum(max(0.0, new.get(v, 0.0) - old.get(v, 0.0)) for v in long_ids)
    return {"from": old_day, "to": new_day, "hours": mins / 60.0}


def leading_signals(rows: list[dict], ages: dict, today: dt.date) -> list[str]:
    """The parts of the leading evidence the state files can answer. The rest is
    a manual read (pilot verdicts in P.2's readout, Studio for continuation)."""
    pub = [r for r in rows if isinstance(r, dict) and r.get("status") == "PUBLISHED"]
    week = [r for r in pub if r.get("format") == "tool" and (learn._date(r.get("publish_at"))
            or learn._date(r.get("timestamp")) or dt.date.min) > today - dt.timedelta(days=7)]
    mature = []
    for r in pub:
        vid = learn.video_id(r.get("youtube_url"))
        p7 = ((ages.get(vid) or {}).get("perf") or {}).get("7d") if vid else None
        if r.get("format") == "tool" and isinstance(p7, dict) and p7.get("complete"):
            mature.append(learn._num(p7.get("minutes")))
    six = sorted(mature[-LATEST_SIX:])
    med = (six[len(six) // 2] if len(six) % 2 else (six[len(six) // 2 - 1] + six[len(six) // 2]) / 2
           ) if six else None
    fu = [r for r in pub if r.get("followup_parent")
          and str(r.get("evidence_source") or "") in memory.ADMISSIBLE_SOURCES]
    fams = {str(r.get("task_family")) for r in pub if r.get("task_family")}
    return [
        f"tool videos published in the last 7 days: {len(week)} (2x asks >= 3 eligible a week)",
        "latest six mature tool uploads, median 7-day watch time: "
        + (f"{med:.0f} min (n={len(six)})" if med is not None else "no 7-day data yet")
        + "; frozen pre-pilot tool median: not frozen yet (v3-P.2)",
        f"evidence-backed follow-ups published: {len(fu)} (5x asks >= 2, evaluated)",
        f"task families with a tool video: {len(fams)} (10x asks >= 2, 25x >= 3 with repeats)",
    ]


def longevity(ages: dict) -> list[dict]:
    """Search capture per video age band, normalised per observed day."""
    out = []
    for lo, hi in memory.AGE_BANDS:
        key = f"{lo}-{hi}"
        per, views, days = [], 0, 0
        for rec in ages.values():
            b = (rec.get("search_bands") or {}).get(key) if isinstance(rec, dict) else None
            if not (isinstance(b, list) and len(b) == 2):
                continue
            v, d = learn._num(b[0]), learn._num(b[1])
            if d <= 0:
                continue
            per.append(v / d)
            views += v
            days += d
        per.sort()
        med = (per[len(per) // 2] if len(per) % 2 else (per[len(per) // 2 - 1] + per[len(per) // 2]) / 2
               ) if per else None
        out.append({"band": key, "videos": len(per), "views": int(views), "days": int(days),
                    "per_day": (views / days) if days else None, "median_per_day": med})
    return out


def block(rows: list[dict], analytics_path: Path | None = None,
          today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    snaps = memory.snapshots(analytics_path)
    wins = windows(snaps)
    day0 = day_zero(rows)
    cur = wins[-1] if wins else None
    lines = ["north star - rolling 28-day ON-DEMAND long-form watch time "
             "(creatorContentType = VIDEO_ON_DEMAND)",
             f"baseline {BASELINE_H:.2f} h ({BASELINE_WINDOW}, Studio, long-form only)"]
    if cur:
        lines.append(f"now: {cur['hours']:.2f} h = {cur['hours'] / BASELINE_H:.2f}x baseline "
                     f"(window {cur['start']}..{cur['end']}, collected {cur['collected']})")
        share, vid = outlier(cur)
        lines.append("largest video share: " + (
            f"{share:.0%} ({vid})" + ("  OUTLIER-DEPENDENT (> 50%)" if share > OUTLIER_SHARE else "")
            if share is not None else "unknown (no per-video window yet)"))
        lines.append(f"live / archived-live (LIVE_STREAM), separate counter: {cur['live_h']:.2f} h")
    else:
        lines.append("now: no north-star observation yet - the first nightly snapshot with "
                     "`north_star` fills it")
        px = proxy_hours(rows, snaps)
        if px:
            lines.append(f"  proxy, display only and NOT comparable with the baseline (ledger "
                         f"long-forms since {learn.DATA_FLOOR} only, collection dates "
                         f"{px['from']}..{px['to']}): {px['hours']:.2f} h")
        lines.append("largest video share: unknown (no per-video window yet)")
        lines.append("live / archived-live (LIVE_STREAM), separate counter: no observation yet")
    lines.append("YPP qualified hours: MANUAL - read Studio > Earn (not in the Analytics API; "
                 "an annualised rate is not accumulated qualified hours)")
    lines.append("day 0: " + (f"{day0} (day {(today - day0).days})" if day0 else
                              f'not started (no PUBLISHED ledger row with experiment == '
                              f'"{PILOT_EXPERIMENT}")'))
    lines += ["", f"{'stage':<7}{'target h':>10}  {'when':<8}status"]
    for st in LADDER:
        when = f"day {st[2]}" if st[2] else "-"
        lines.append(f"{st[0]:<7}{st[1]:>10,.2f}  {when:<8}{stage_status(st, day0, today, wins)}")
    lines += ["", "leading evidence per stage (round 3 §6):"]
    lines += [f"  {st[0]:<5} {st[3]}" for st in LADDER]
    ages = memory.age_records(snaps)
    lines += ["", "leading signals from state (the rest is a manual read):"]
    lines += [f"  - {s}" for s in leading_signals(rows, ages, today)]
    lines += ["", "insufficient observations = unresolved, never on track or failed", "",
              "search longevity - YT_SEARCH views per observed day, by video age (day 1 = "
              "publish day)"]
    lon = longevity(ages)
    if not any(b["videos"] for b in lon):
        lines.append("  no age-band data yet - the first nightly snapshot with `age_bands` fills it")
    else:
        lines.append(f"  {'band':<7}{'videos':>7}{'views':>8}{'days':>7}{'views/day':>11}"
                     f"{'median/day':>12}")
        for b in lon:
            pd_ = f"{b['per_day']:.2f}" if b["per_day"] is not None else "-"
            md = f"{b['median_per_day']:.2f}" if b["median_per_day"] is not None else "-"
            lines.append(f"  {b['band']:<7}{b['videos']:>7}{b['views']:>8}{b['days']:>7}"
                         f"{pd_:>11}{md:>12}")
    return "\n".join(lines) + "\n"
