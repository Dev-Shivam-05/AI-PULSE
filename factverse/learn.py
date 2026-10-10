"""
v3-D learning loop v1 (docs/spec/ai-pulse-v3d.md).

Joins the run ledger (state/runs.jsonl) with the per-video numbers the nightly
collector stores (state/analytics.jsonl -> "ledger_videos") and answers two
questions: how is each format / hook pattern actually doing (the scoreboard),
and which news hook patterns should stay in rotation (the one lever v1 pulls).

Pure: reads state files, never the network. Every public entry point is
fail-soft — the daily run must never die because of learning.

Run:  python -m factverse.learn
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import sys
from pathlib import Path

from factverse import config as fv
from factverse import gates

RUNS_LOG = fv.STATE / "runs.jsonl"
ANALYTICS = fv.STATE / "analytics.jsonl"
SCOREBOARD_OUT = fv.BASE / "output" / "demo" / "learn" / "scoreboard.txt"

# All locked in the spec — do not change without a spec row.
DATA_FLOOR = "2026-08-24"   # self-view cutoff: nothing earlier is real traffic
MATURE_DAYS = 7             # a video counts once it has had a week
MIN_VIDEOS = 5              # trusted arm: >= 5 mature videos ...
MIN_VIEWS = 100             # ... and >= 100 views (no single viewer > 1% of the arm)
DROP_RATIO = 0.5            # drop a pattern below half the best trusted pattern
MIN_TRUSTED_ARMS = 2        # a comparison needs two sides
MIN_ACTIVE = 3              # never shrink the rotation below this
TARGET_AVD_S = 120          # the v3 target metric (AVD >= 2:00)
LEDGER_CAP = 200            # the Analytics API's per-query maximum

_ID = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/)([\w-]{11})")


def video_id(url) -> str | None:
    m = _ID.search(url) if isinstance(url, str) else None
    return m.group(1) if m else None


def _date(value) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _num(value) -> float:
    # rows come from JSON written by another process: coerce, never trust the type.
    # json.loads accepts Infinity/NaN, and int(inf) raises — finite only.
    try:
        n = float(value)
    except (TypeError, ValueError):
        return 0.0
    return n if math.isfinite(n) and n > 0 else 0.0


def read_runs(path: Path | None = None) -> list[dict]:
    rows = []
    for line in Path(path or RUNS_LOG).read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict):
            rows.append(d)
    return rows


def ledger_videos(rows: list[dict]) -> list[dict]:
    """PUBLISHED long-forms since DATA_FLOOR, one entry per video id, oldest first."""
    floor = _date(DATA_FLOOR)
    out, seen = [], set()
    for r in rows:
        if not isinstance(r, dict) or r.get("status") != "PUBLISHED":
            continue
        vid = video_id(r.get("youtube_url"))
        stamped = _date(r.get("timestamp"))
        if not vid or vid in seen or stamped is None or stamped < floor:
            continue
        seen.add(vid)
        hook = r.get("hook_pattern")
        out.append({"id": vid,
                    "format": str(r.get("format") or "-"),
                    "hook_pattern": hook if hook in gates.HOOK_PATTERNS else None,
                    "published": _date(r.get("publish_at")) or stamped})
    return out


SHORT_MATURE_DAYS = 2      # v3-G.1 row 13: a Short gets most of its views in 48 h
AB_PAIRS, AB_BUILD, AB_STOP = 10, 8, 5   # v3-G.1 row 14


def ledger_shorts(rows: list[dict]) -> list[dict]:
    """v3-G.1: the Shorts a PUBLISHED row recorded as {url, engine}, with the row
    they belong to (a pair is one row = one day, both arms)."""
    floor = _date(DATA_FLOOR)
    out, seen = [], set()
    for k, r in enumerate(rows):
        if not isinstance(r, dict) or r.get("status") != "PUBLISHED":
            continue
        stamped = _date(r.get("timestamp"))
        items = r.get("shorts")
        if stamped is None or stamped < floor or not isinstance(items, list):
            continue
        for it in items:
            vid = video_id(it.get("url")) if isinstance(it, dict) else None
            eng = it.get("engine") if isinstance(it, dict) else None
            if vid and vid not in seen and eng in ("storyboard", "crop"):
                seen.add(vid)
                out.append({"id": vid, "engine": eng, "row": k,
                            "published": _date(r.get("publish_at")) or stamped})
    return out


def ledger_ids(rows: list[dict], cap: int = LEDGER_CAP) -> list[str]:
    """Long-forms AND the A/B Shorts, in ledger order, most recent `cap`."""
    shorts_by_row: dict[int, list[str]] = {}
    for s in ledger_shorts(rows):
        shorts_by_row.setdefault(s["row"], []).append(s["id"])
    long_ids = {v["id"] for v in ledger_videos(rows)}
    ids, seen = [], set()
    for k, r in enumerate(rows):
        vid = video_id(r.get("youtube_url")) if isinstance(r, dict) else None
        for i in ([vid] if vid in long_ids else []) + shorts_by_row.get(k, []):
            if i not in seen:
                seen.add(i)
                ids.append(i)
    return ids[-cap:]


def latest_metrics(path: Path | None = None) -> dict[str, dict]:
    """Per-video numbers from the NEWEST snapshot carrying `ledger_videos`. Each
    query is cumulative from DATA_FLOOR, so the newest one supersedes the rest."""
    lines = Path(path or ANALYTICS).read_text(encoding="utf-8").splitlines()
    for line in reversed(lines):
        try:
            snap = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(snap, dict) or not snap.get("ledger_videos"):
            continue
        heads = snap.get("ledger_headers") or []
        try:
            iv, iviews, iavd = (heads.index("video"), heads.index("views"),
                                heads.index("averageViewDuration"))
        except (ValueError, AttributeError):
            continue
        iavp = heads.index("averageViewPercentage") if "averageViewPercentage" in heads else None
        out = {}
        for row in snap["ledger_videos"]:
            if isinstance(row, list) and len(row) > max(iv, iviews, iavd):
                out[str(row[iv])] = {"views": _num(row[iviews]), "avd_s": _num(row[iavd]),
                                     "avp": _num(row[iavp]) if iavp is not None and len(row) > iavp else 0.0}
        return out
    return {}


def reach_metrics(path: Path | None = None) -> dict[tuple, dict]:
    """v3-G.3 #11-12: thumbnail impressions + CTR per (date, video_id), from the
    `reach_rows` of EVERY snapshot (each Reporting API report is one day, stored
    once). A (date, video) seen twice keeps the newest snapshot's numbers. CTR is
    raw — its scale (0-1 or 0-100) is whatever the CSV says."""
    p = Path(path or ANALYTICS)
    if not p.exists():
        return {}
    out: dict[tuple, dict] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            snap = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(snap, dict) or not isinstance(snap.get("reach_rows"), list):
            continue
        heads = snap.get("reach_headers")
        if not isinstance(heads, list):
            continue
        try:
            idate, ivid, iimp, ictr = (heads.index("date"), heads.index("video_id"),
                                       heads.index("video_thumbnail_impressions"),
                                       heads.index("video_thumbnail_impressions_ctr"))
        except (ValueError, AttributeError):
            continue
        for row in snap["reach_rows"]:
            if isinstance(row, list) and len(row) > max(idate, ivid, iimp, ictr):
                out[(str(row[idate]), str(row[ivid]))] = {"impr": _num(row[iimp]),
                                                          "ctr": _num(row[ictr])}
    return out


def reach_by_format(rows: list[dict], reach: dict[tuple, dict]) -> dict[str, dict]:
    """'format:<f>' -> {impr, ctr}: CTR = sum(impr x ctr) / sum(impr). Display only."""
    fmt_of = {v["id"]: v["format"] for v in ledger_videos(rows)}
    acc: dict[str, list[float]] = {}
    for (_, vid), m in reach.items():
        if vid in fmt_of:
            a = acc.setdefault(f"format:{fmt_of[vid]}", [0.0, 0.0])
            a[0] += m["impr"]
            a[1] += m["impr"] * m["ctr"]
    return {k: {"impr": int(a[0]), "ctr": (a[1] / a[0]) if a[0] else None}
            for k, a in sorted(acc.items())}


def shorts_ab(rows: list[dict], metrics: dict[str, dict], today: dt.date | None = None) -> dict:
    """v3-G.1 rows 13-14: views-weighted % viewed per arm, and the daily pairs."""
    today = today or dt.date.today()
    arms = {"storyboard": [], "crop": []}
    by_row: dict[int, dict[str, dict]] = {}
    for s in ledger_shorts(rows):
        m = metrics.get(s["id"], {})
        item = {"mature": (today - s["published"]).days >= SHORT_MATURE_DAYS,
                "views": _num(m.get("views")), "avp": _num(m.get("avp"))}
        arms[s["engine"]].append(item)
        by_row.setdefault(s["row"], {})[s["engine"]] = item
    out = {}
    for eng, items in arms.items():
        mature = [i for i in items if i["mature"] and i["views"] > 0]
        views = sum(i["views"] for i in mature)
        out[f"short:{eng}"] = {"videos": len(items), "mature": len(mature), "views": int(views),
                               "wavp": (sum(i["avp"] * i["views"] for i in mature) / views) if views else 0.0}
    pairs = wins = 0
    for day in by_row.values():
        a, b = day.get("storyboard"), day.get("crop")
        if a and b and a["mature"] and b["mature"] and a["views"] > 0 and b["views"] > 0:
            pairs += 1
            wins += a["avp"] > b["avp"]
    verdict = ""
    if pairs >= AB_PAIRS:
        verdict = ("build v3-G.2" if wins >= AB_BUILD else
                   "stop and rethink" if wins <= AB_STOP else "run 10 more pairs")
    out["pairs"], out["wins"], out["verdict"] = pairs, wins, verdict
    return out


def _arm(items: list[dict]) -> dict:
    mature = [i for i in items if i["mature"]]
    counted = [i for i in mature if i["views"] > 0]
    views = sum(i["views"] for i in counted)
    wavd = (sum(i["avd_s"] * i["views"] for i in counted) / views) if views else 0.0
    hit = sum(1 for i in mature if i["avd_s"] >= TARGET_AVD_S)
    return {"videos": len(items), "mature": len(mature), "views": int(views),
            "wavd": wavd, "share_target": (hit / len(mature)) if mature else 0.0,
            "trusted": len(mature) >= MIN_VIDEOS and views >= MIN_VIEWS}


def score(rows: list[dict], metrics: dict[str, dict],
          today: dt.date | None = None) -> dict[str, dict]:
    """Arms keyed 'format:<f>' and 'hook:<p>' -> _arm stats."""
    today = today or dt.date.today()
    groups: dict[str, list[dict]] = {}
    for v in ledger_videos(rows):
        m = metrics.get(v["id"], {})
        item = {"mature": (today - v["published"]).days >= MATURE_DAYS,
                "views": _num(m.get("views")), "avd_s": _num(m.get("avd_s"))}
        groups.setdefault(f"format:{v['format']}", []).append(item)
        if v["hook_pattern"]:
            groups.setdefault(f"hook:{v['hook_pattern']}", []).append(item)
    return {k: _arm(g) for k, g in sorted(groups.items())}


def dropped_patterns(stats: dict[str, dict]) -> list[str]:
    """Hook patterns to take out of rotation, worst first (spec decision 6)."""
    trusted = {p: stats[f"hook:{p}"] for p in gates.HOOK_PATTERNS
               if stats.get(f"hook:{p}", {}).get("trusted")}
    if len(trusted) < MIN_TRUSTED_ARMS:
        return []
    best = max(s["wavd"] for s in trusted.values())
    if best <= 0:
        return []
    losers = sorted((p for p, s in trusted.items() if s["wavd"] < DROP_RATIO * best),
                    key=lambda p: trusted[p]["wavd"])
    room = len(gates.HOOK_PATTERNS) - MIN_ACTIVE
    return losers[:max(0, room)]


def active_hook_patterns(runs_path: Path | None = None, analytics_path: Path | None = None,
                         today: dt.date | None = None) -> tuple[str, ...]:
    """The news hook rotation for today. Any failure -> every pattern (decision 10)."""
    try:
        stats = score(read_runs(runs_path), latest_metrics(analytics_path), today)
        drop = dropped_patterns(stats)
        if drop:
            print("  🧠 Learning loop dropped hook pattern(s): " + ", ".join(
                f"{p} ({stats['hook:' + p]['wavd']:.0f}s)" for p in drop))
        return tuple(p for p in gates.HOOK_PATTERNS if p not in drop)
    except Exception as e:  # noqa: BLE001 — learning must never cost the day
        print(f"  ⚠️ learning loop skipped: {e}")
        return gates.HOOK_PATTERNS


def _mmss(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 60}:{s % 60:02d}"


def scoreboard(runs_path: Path | None = None, analytics_path: Path | None = None,
               today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    metrics = latest_metrics(analytics_path)
    rows = read_runs(runs_path)
    stats = score(rows, metrics, today)
    drop = dropped_patterns(stats)
    ab = shorts_ab(rows, metrics, today)
    lines = [f"v3-D scoreboard - {today.isoformat()}  (data from {DATA_FLOOR}; a video "
             f"matures {MATURE_DAYS} days after publish; trusted = >={MIN_VIDEOS} mature "
             f"and >={MIN_VIEWS} views)",
             f"per-video numbers for {len(metrics)} ledger video(s)",
             "",
             f"{'group':<22}{'videos':>7}{'mature':>9}{'views':>8}{'wAVD':>7}"
             f"{'>=2:00':>8}  trusted"]
    for arm, s in stats.items():
        wavd = _mmss(s["wavd"]) if s["views"] else "-"
        lines.append(f"{arm:<22}{s['videos']:>7}{s['mature']:>9}{s['views']:>8}{wavd:>7}"
                     f"{s['share_target']:>8.0%}  {'yes' if s['trusted'] else 'no'}")
    active = [p for p in gates.HOOK_PATTERNS if p not in drop]
    lines += ["", "active hook patterns: " + ", ".join(active)
              + f"  (dropped: {', '.join(drop) if drop else 'none'})"]
    # v3-G.3 #12: thumbnail impressions + CTR per format (Reporting API). Display only.
    try:
        reach = reach_by_format(rows, reach_metrics(analytics_path))
    except Exception as e:  # noqa: BLE001 — a reach parse bug must not cost the scoreboard
        print(f"  ⚠️ reach columns skipped: {e}")
        reach = {}
    lines += ["", f"{'reach':<22}{'impr':>9}{'CTR':>9}"]
    for arm in (k for k in stats if k.startswith("format:")):
        r = reach.get(arm, {"impr": 0, "ctr": None})
        ctr = f"{r['ctr']:.4g}" if r["ctr"] is not None else "-"
        lines.append(f"{arm:<22}{r['impr']:>9}{ctr:>9}")
    # v3-G.1 rows 13-14: the storyboard A/B (Shorts mature after 2 days)
    lines += ["", f"{'shorts A/B':<22}{'videos':>7}{'mature':>9}{'views':>8}{'%viewed':>9}"]
    for arm in ("short:storyboard", "short:crop"):
        s = ab[arm]
        pct = f"{s['wavp']:.1f}%" if s["views"] else "-"
        lines.append(f"{arm:<22}{s['videos']:>7}{s['mature']:>9}{s['views']:>8}{pct:>9}")
    lines.append(f"A/B pairs: {ab['pairs']} · storyboard wins: {ab['wins']}"
                 + (f"  → {ab['verdict']}" if ab["verdict"] else f"  (verdict at {AB_PAIRS})"))
    return "\n".join(lines) + "\n"


def main() -> int:
    try:
        text = scoreboard()
        print(text)
        SCOREBOARD_OUT.parent.mkdir(parents=True, exist_ok=True)
        SCOREBOARD_OUT.write_text(text, encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ scoreboard skipped: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
