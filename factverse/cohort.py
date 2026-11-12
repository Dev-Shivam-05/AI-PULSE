"""v3-R.4: the recovery cohort's reads — day-14 delivery and day-21 outcome (D13, D14).

docs/spec/ai-pulse-v3r.md. Two jobs:

1. COLLECT (called from analytics.collect, kill switch `cohort_reads`): first-7-day
   audience-retention curves for every cohort long-form once it is old enough, and ONCE
   for the 11 frozen baseline videos (R0). Window = the collector's own `age_bands` "7d"
   ([publish, publish + 6]), so W0 and the curves describe the same 7 days. Stored in the
   snapshot as `cohort_reads`: {video: {"start", "end", "curve": [[ratio, watch], ...],
   "read_on"}}. One failed query costs only that video.

2. READ (`python -m factverse.cohort [--shorts-csv path]`): prints the day-14 delivery
   review and the day-21 outcome review, and writes output/cohort/report.md (output/ is
   gitignored; docs/ is published, so never there). Shorts stayed-to-watch is NOT in any
   public API — the owner exports it from Studio into a CSV (video,feed_impressions,
   stayed_pct), the live_scorecard pattern; without it the Shorts read says "pending".

Everything here is pure except collect() and main(); main() never raises.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

from factverse import config as fv
from factverse import learn

# ---------------------------------------------------------------- frozen (spec)
BASELINE_IDS = ("-zMkp0hnACk", "yjgtYZdEWH8", "JQbzwDs_zgM", "FHfd45OkoRE", "xm2GvY4QttA",
                "wwI1rTpmnrg", "0PXRcVZ6ls4", "-oCxU6iIDak", "4MTEDi4MdnQ", "QFKGh9DhDW4",
                "Q-P_P-Y1-to")
W0_MINUTES = 13.0             # median first-7-day watch time of BASELINE_IDS (frozen 2026-11-12)
R0_TARGET_S = 7.0             # D13: retention read at 0:07
R0_LIFT = 8.0                 # D13: promising = median >= R0 + 8 points
SHORTS_STAYED_MIN = 22.0      # D13: Shorts promising at median stayed >= 22%
FLOOR_LONG, FLOOR_BASE, FLOOR_SHORTS = 4, 4, 4    # D13 evidence floors
SHORTS_MIN_IMPRESSIONS = 50
DELIVERY_DAY, OUTCOME_DAY = 14, 21
PLANNED_LONG, PLANNED_SHORTS = 6, 6
READ_LAG_DAYS = 2             # Analytics data lag before a 7-day window is complete
COHORT_DAYS = 14              # D1: the six long-forms fall inside days 0..13
LONG_WEEKDAYS = (0, 2, 4)     # D1: Mon, Wed, Fri (ai_pipeline.COHORT_LONG_WEEKDAYS)
MAX_READ_ATTEMPTS = 5         # a curve still unusable after this many reads is given up
USABLE_POINTS = 10            # a curve with fewer points is not a curve (pilot.USABLE_POINTS)
REPLY_HOURS = 24              # D11
OUT_DIR = fv.BASE / "output" / "cohort"


def enabled() -> bool:
    return fv.flag("cohort_reads", False)


def start_date() -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(fv.setting("cohort_start", "") or "")[:10])
    except ValueError:
        return None


def _date(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------- the cohort itself
def cohort_rows(rows: list, start: dt.date | None) -> list[dict]:
    """PUBLISHED long-forms whose publish day falls inside the cohort's 14 days."""
    if not start:
        return []
    end = start + dt.timedelta(days=COHORT_DAYS)
    out = []
    for r in rows or []:
        if not isinstance(r, dict) or r.get("status") != "PUBLISHED":
            continue
        d = _date(r.get("publish_at") or r.get("timestamp"))
        if d and start <= d < end and learn.video_id(r.get("youtube_url") or ""):
            out.append(r)
    return out


def missed_days(rows: list, start: dt.date | None, today: dt.date) -> list[str]:
    """Scheduled long-form days (Mon/Wed/Fri inside the window, up to yesterday) with
    no PUBLISHED long-form going public that day — however the day was lost."""
    if not start:
        return []
    published = {_date(r.get("publish_at") or r.get("timestamp")) for r in cohort_rows(rows, start)}
    out = []
    for i in range(COHORT_DAYS):
        d = start + dt.timedelta(days=i)
        if d >= today:
            break
        if d.weekday() in LONG_WEEKDAYS and d not in published:
            out.append(d.isoformat())
    return out


def window(published: dt.date) -> tuple[dt.date, dt.date]:
    """The first-7-day window, the age_bands "7d" definition: [publish, publish + 6]."""
    return published, published + dt.timedelta(days=6)


def due(videos: dict, stored: dict, today: dt.date,
        attempts: dict | None = None) -> list[tuple[str, dt.date, dt.date]]:
    """(video, start, end) for every video whose 7-day window has closed (plus the data
    lag), with no usable curve stored yet and fewer than MAX_READ_ATTEMPTS reads. PURE."""
    out = []
    for vid, pub in sorted(videos.items()):
        if not pub:
            continue
        start, end = window(pub)
        if today < end + dt.timedelta(days=READ_LAG_DAYS):
            continue
        if usable(stored.get(vid)) or (attempts or {}).get(vid, 0) >= MAX_READ_ATTEMPTS:
            continue
        out.append((vid, start, end))
    return out


def read_attempts(snapshots: list) -> dict:
    """video -> how many snapshots carry a read for it."""
    out: dict = {}
    for s in snapshots or []:
        reads = s.get("cohort_reads") if isinstance(s, dict) else None
        for vid in (reads or {}) if isinstance(reads, dict) else []:
            out[vid] = out.get(vid, 0) + 1
    return out


def usable(rd) -> bool:
    return isinstance(rd, dict) and isinstance(rd.get("curve"), list) and len(rd["curve"]) >= USABLE_POINTS


def stored_reads(snapshots: list) -> dict:
    """video -> the latest stored read, a usable one preferred."""
    out: dict = {}
    for s in snapshots or []:
        reads = s.get("cohort_reads") if isinstance(s, dict) else None
        for vid, rd in (reads or {}).items() if isinstance(reads, dict) else []:
            if usable(rd) or not usable(out.get(vid)):
                out[vid] = rd
    return out


def _published(rows: list) -> dict:
    """video id -> publish date, for every PUBLISHED long-form in the ledger."""
    out = {}
    for r in rows or []:
        if isinstance(r, dict) and r.get("status") == "PUBLISHED":
            vid = learn.video_id(r.get("youtube_url") or "")
            if vid:
                out[vid] = _date(r.get("publish_at") or r.get("timestamp"))
    return out


def collect(yta, rows: list, snapshots: list, today: dt.date | None = None) -> dict:
    """The snapshot's `cohort_reads`: every due curve, baseline included. Never raises
    for one video: its read records the error instead."""
    from factverse import pilot  # noqa: PLC0415 — the query shape lives there
    today = today or dt.datetime.utcnow().date()
    pub = _published(rows)
    videos = {v: pub.get(v) for v in BASELINE_IDS}
    videos.update({learn.video_id(r.get("youtube_url") or ""): _date(r.get("publish_at") or r.get("timestamp"))
                   for r in cohort_rows(rows, start_date())})
    out = {}
    for vid, start, end in due(videos, stored_reads(snapshots), today, read_attempts(snapshots)):
        rd = {"start": start.isoformat(), "end": end.isoformat(), "read_on": today.isoformat(),
              "curve": []}
        try:
            r = yta.reports().query(**pilot.retention_args(vid, start, end)).execute()
            rd["curve"] = [row[:2] for row in r.get("rows") or [] if isinstance(row, list)]
        except Exception as e:  # noqa: BLE001
            rd["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        out[vid] = rd
    return out


# ---------------------------------------------------------------- the reads (pure)
def duration_of(vid: str, snapshots: list) -> float | None:
    """A long-form's length from the collector's own per-video numbers:
    averageViewDuration / (averageViewPercentage / 100). Measured on gpu-unlock:
    48 s / 13.73% = 349.6 s against a real 347 s."""
    for s in reversed(snapshots or []):
        heads = s.get("ledger_headers") if isinstance(s, dict) else None
        if not heads or "averageViewDuration" not in heads or "averageViewPercentage" not in heads:
            continue
        ia, ip = heads.index("averageViewDuration"), heads.index("averageViewPercentage")
        for row in s.get("ledger_videos") or []:
            if isinstance(row, list) and row and row[0] == vid:
                try:
                    avd, pct = float(row[ia]), float(row[ip])
                except (TypeError, ValueError, IndexError):
                    continue
                if avd > 0 and pct > 0:
                    return round(avd / (pct / 100.0), 1)
    return None


def retention_at(rd, duration_s, target_s: float = R0_TARGET_S) -> float | None:
    """Retention % at the curve point nearest target_s (pilot.sample)."""
    if not usable(rd) or not duration_s:
        return None
    from factverse import pilot  # noqa: PLC0415
    s = pilot.sample(rd["curve"], float(duration_s), target_s)
    return s[0] if s else None


def first7_minutes(vid: str, snapshots: list) -> float | None:
    """First-7-day watch minutes from the collector's age_bands (complete only)."""
    rec = None
    for s in snapshots or []:
        ab = s.get("age_bands") if isinstance(s, dict) else None
        if isinstance(ab, dict) and isinstance(ab.get(vid), dict):
            rec = ab[vid]
    p = ((rec or {}).get("perf") or {}).get("7d") or {}
    if not p.get("complete"):
        return None
    try:
        return float(p.get("minutes"))
    except (TypeError, ValueError):
        return None


def _median(xs: list):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def delivery(rows: list, replied: dict, start: dt.date | None, today: dt.date | None = None) -> dict:
    """D13 day-14: what was actually delivered."""
    longs = [r for r in cohort_rows(rows, start)]
    tool = [r for r in longs if r.get("format") == "tool"]
    filler = [r for r in longs if r.get("format") != "tool"]
    native = sum(1 for r in longs for s in (r.get("shorts") or [])
                 if isinstance(s, dict) and s.get("engine") == "native")
    crops = sum(1 for r in longs for s in (r.get("shorts") or [])
                if isinstance(s, dict) and s.get("engine") not in ("native", None))
    answered = [v for v in (replied or {}).values() if isinstance(v, dict) and v.get("status") == "answered"]
    on_time = 0
    for v in answered:
        try:
            asked = dt.datetime.fromisoformat(str(v.get("published", "")).replace("Z", "+00:00")).replace(tzinfo=None)
            at = dt.datetime.fromisoformat(str(v.get("at", "")))
            on_time += (at - asked) <= dt.timedelta(hours=REPLY_HOURS)
        except ValueError:
            continue
    misses = missed_days(rows, start, today or dt.datetime.utcnow().date())
    return {"long_forms": len(tool), "planned_long": PLANNED_LONG, "native_shorts": native,
            "planned_shorts": PLANNED_SHORTS, "crop_shorts": crops, "filler": len(filler),
            "logged_misses": len(misses), "missed_days": misses, "replies": len(answered),
            "replies_on_time": on_time}


def outcome(rows: list, snapshots: list, start: dt.date | None,
            shorts: list[dict] | None = None) -> dict:
    """D13 day-21 reads and the D14 verdict, with every upload's numbers shown."""
    reads = stored_reads(snapshots)
    per = []
    for r in cohort_rows(rows, start):
        if r.get("format") != "tool":
            continue
        vid = learn.video_id(r.get("youtube_url") or "")
        dur = duration_of(vid, snapshots)
        per.append({"video": vid, "title": str(r.get("title") or "")[:70],
                    "minutes_7d": first7_minutes(vid, snapshots),
                    "retention_7s": retention_at(reads.get(vid), dur), "duration_s": dur})
    base = []
    for vid in BASELINE_IDS:
        base.append({"video": vid, "retention_7s": retention_at(reads.get(vid), duration_of(vid, snapshots)),
                     "minutes_7d": first7_minutes(vid, snapshots)})
    r0 = _median([b["retention_7s"] for b in base])
    n_curves = sum(1 for p in per if p["retention_7s"] is not None)
    n_base = sum(1 for b in base if b["retention_7s"] is not None)
    med_ret = _median([p["retention_7s"] for p in per])
    med_min = _median([p["minutes_7d"] for p in per])
    res = {"per_video": per, "baseline_curves": n_base, "R0": r0, "W0": W0_MINUTES,
           "median_retention_7s": med_ret, "median_minutes_7d": med_min,
           "uploads_with_curves": n_curves, "uploads": len(per)}
    res["long_verdict"] = verdict(med_ret, med_min, r0, n_curves, n_base)
    res["shorts"] = shorts_read(shorts)
    return res


def verdict(med_ret, med_min, r0, n_curves: int, n_base: int) -> str:
    """D13/D14 for the long-forms. PURE.
    pending: a number is missing; inconclusive: an evidence floor is not met;
    promising: retention >= R0 + 8 AND minutes > W0; stop: both at or below baseline;
    mixed: anything else (revise without scaling)."""
    if med_ret is None or med_min is None or r0 is None:
        return "pending"
    if n_curves < FLOOR_LONG or n_base < FLOOR_BASE:
        return "inconclusive"
    if med_ret >= r0 + R0_LIFT and med_min > W0_MINUTES:
        return "promising"
    if med_min <= W0_MINUTES and med_ret <= r0:
        return "stop"
    return "mixed"


def shorts_read(shorts: list[dict] | None) -> dict:
    """D13 Shorts read from the owner's Studio CSV rows (video, feed_impressions,
    stayed_pct). Every row is shown; the floor counts the exposed ones."""
    if not shorts:
        return {"verdict": "pending", "rows": []}
    exposed = [s for s in shorts if (s.get("feed_impressions") or 0) >= SHORTS_MIN_IMPRESSIONS]
    med = _median([s.get("stayed_pct") for s in exposed])
    if len(exposed) < FLOOR_SHORTS:
        v = "inconclusive"
    else:
        v = "promising" if med is not None and med >= SHORTS_STAYED_MIN else "not yet"
    return {"verdict": v, "median_stayed": med, "exposed": len(exposed), "rows": shorts}


def read_shorts_csv(path) -> list[dict]:
    out = []
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                out.append({"video": str(row.get("video") or "").strip(),
                            "feed_impressions": int(float(row.get("feed_impressions") or 0)),
                            "stayed_pct": float(row.get("stayed_pct") or 0)})
            except (TypeError, ValueError):
                continue
    return out


def format_report(today: dt.date, start: dt.date | None, dl: dict, oc: dict) -> str:
    age = (today - start).days if start else None
    lines = [f"# ToolDojo recovery cohort — read on {today.isoformat()}",
             f"Cohort start {start.isoformat() if start else 'unset'}; day {age if age is not None else '?'} "
             f"(delivery review on day {DELIVERY_DAY}, outcome review on day {OUTCOME_DAY}).", "",
             "## Day-14 delivery (D13)",
             f"- Long-forms: {dl['long_forms']} of {dl['planned_long']}; filler uploads: {dl['filler']}; "
             f"logged misses: {dl['logged_misses']}",
             f"- Native Shorts: {dl['native_shorts']} of {dl['planned_shorts']}; crop Shorts: {dl['crop_shorts']}",
             f"- Viewer questions answered: {dl['replies']} ({dl['replies_on_time']} within {REPLY_HOURS} h)", "",
             "## Day-21 outcome (D13 / D14)",
             f"- W0 = {oc['W0']} min (frozen). R0 = {oc['R0'] if oc['R0'] is not None else 'pending'} % at 0:07 "
             f"({oc['baseline_curves']} of {len(BASELINE_IDS)} baseline curves).",
             f"- Cohort median first-7-day minutes: {oc['median_minutes_7d']}; median retention at 0:07: "
             f"{oc['median_retention_7s']} ({oc['uploads_with_curves']} of {oc['uploads']} curves).",
             f"- **Long-form verdict: {oc['long_verdict']}**",
             f"- **Shorts verdict: {oc['shorts']['verdict']}**"
             + (f" (median stayed {oc['shorts'].get('median_stayed')}%, {oc['shorts'].get('exposed')} "
                f"with {SHORTS_MIN_IMPRESSIONS}+ impressions)" if oc['shorts'].get('rows') else
                " (needs the Studio CSV: video,feed_impressions,stayed_pct)"), "",
             "| Video | Title | 7-day minutes | Retention at 0:07 | Length (s) |",
             "|---|---|---|---|---|"]
    for p in oc["per_video"]:
        lines.append(f"| {p['video']} | {p['title']} | {p['minutes_7d']} | {p['retention_7s']} | {p['duration_s']} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    try:
        argv = list(sys.argv[1:] if argv is None else argv)
        shorts = None
        if "--shorts-csv" in argv:
            shorts = read_shorts_csv(argv[argv.index("--shorts-csv") + 1])
        rows = learn.read_runs()
        snaps = []
        path = fv.STATE / "analytics.jsonl"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    snaps.append(json.loads(line))
                except ValueError:
                    continue
        try:
            from factverse import replies  # noqa: PLC0415
            replied = replies.load_state()
        except Exception:  # noqa: BLE001
            replied = {}
        today = dt.datetime.utcnow().date()
        start = start_date()
        report = format_report(today, start, delivery(rows, replied, start, today),
                               outcome(rows, snaps, start, shorts))
        print(report)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "report.md").write_text(report, encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ cohort read failed: {type(e).__name__}: {str(e)[:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
