"""v3-P.2 Pilot A: proof-first vs context-first long-form openings (review row 6).

spec docs/spec/ai-pulse-v3p2.md. Round 3 §4 as amended in round 4 (A1-A3):

  * 6 pre-assigned pairs, matched on evidence source x intent type
    (install-and-run / use-a-hosted-demo / decide-before-installing); task
    family, publication date, duration and traffic-source mix are covariates.
  * Arm order is drawn ONCE, at freeze time, before any performance exists, and
    stored in state/pilot_a.json. A video takes the next slot by arrival: it
    closes an open pair of its own stratum, else opens the next pair with that
    pair's pre-drawn first arm. Nothing about performance ever touches this.
  * Readout: per-video retention from the YouTube Analytics API
    (dimensions=elapsedVideoTimeRatio, metrics=audienceWatchRatio, filters
    video==ID — https://developers.google.com/youtube/analytics/channel_reports
    "Audience retention": the video filter takes ONE id; 100 points, ratio
    0.01..1.0, each value the exclusive END of its interval). Read at
    publication age 7, then 14, then 28 days; a pair compares both videos at the
    SAME age, the first age at which both have a usable curve.
  * AVD guardrail (A2): the frozen unweighted median of eligible pre-pilot tool
    videos' first-7-day average view duration, from state/analytics.jsonl
    snapshots per video — never lifetime numbers.

Everything here is pure or fail-soft; nothing raises into run().
"""
from __future__ import annotations

import datetime as dt
import json
import random
import statistics
import sys
from pathlib import Path

from factverse import config as fv

EXPERIMENT = "pilot_a"
STATE = fv.STATE / "pilot_a.json"
ARMS = ("proof", "context")
INTENTS = ("install-and-run", "use-a-hosted-demo", "decide-before-installing")
PAIRS = 6                              # A1: 6 pairs instead of 3

# locked (round 3 §4 + A1)
CHECK_AGES = (7, 14, 28)               # read day 7, then 14, then 28
TARGETS = {7: 65.0, 30: 45.0, 60: 38.0}   # treatment medians at ~0:07 / ~0:30 / ~1:00
PROMISING_WINS = 5                     # of 6 pairs favour proof-first
PROMISING_ADV = 8.0                    # median paired advantage at ~0:07, points
STOP_DISADV = 5.0                      # round 3: "all pairs favour context first, >= 5 pts"
FLAT_STOP_POSITIVES = 2                # round 3: after the extra batch, <= 2 positive pairs

# delegated (spec)
READ_LAG_DAYS = 2                      # YouTube: retention processing normally takes 1-2 days
READ_RETRY_DAYS = 14                   # keep asking for an empty curve this long, then give up
USABLE_POINTS = 10                     # a "curve" with fewer points is not usable
AVD_AGE = 7
_HEAVY = ("gpu", "cuda", "vram", "nvidia", "rtx", "docker", "api key", "api_key", "apikey",
          "gb of ram", "gb ram", "16gb", "24gb", "32gb", "48gb", "80gb", "a100", "h100")


def _today() -> dt.date:
    return dt.date.today()


def _date(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _num(v) -> float | None:
    """Finite float or None (JSON from another process: Infinity parses)."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n and n not in (float("inf"), float("-inf")) else None


def _vid(url) -> str:
    from factverse import learn
    return learn.video_id(url) or ""


# ============================================================ design + state
def new_design(seed: int | None = None, batch: int = 1, today: dt.date | None = None) -> dict:
    """The pre-registration: pair ids and each pair's FIRST arm (= which arm
    publishes first; the second member gets the other). Drawn once."""
    seed = int(seed if seed is not None else random.SystemRandom().randrange(2 ** 31))
    rng = random.Random(seed)
    pairs = [{"pair_id": f"B{batch}P{k}", "first_arm": rng.choice(ARMS)} for k in range(1, PAIRS + 1)]
    return {"experiment": EXPERIMENT, "batch": int(batch), "seed": seed,
            "frozen_at": (today or _today()).isoformat(), "pairs": pairs, "members": []}


def load(path: Path | None = None) -> dict | None:
    try:
        d = json.loads(Path(path or STATE).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) and isinstance(d.get("pairs"), list) else None
    except (OSError, ValueError):
        return None


def save(design: dict, path: Path | None = None) -> None:
    Path(path or STATE).write_text(json.dumps(design, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")


def intent_of(ev: dict, grounding: str = "") -> str:
    """A3 intent type, deterministic: a hosted test is "use-a-hosted-demo"; an
    author demo whose source names a heavy prerequisite (GPU / CUDA / VRAM /
    Docker / API key / large RAM) is "decide-before-installing"; else
    "install-and-run"."""
    if not isinstance(ev, dict):
        return ""
    if ev.get("source") == "hosted":
        return "use-a-hosted-demo"
    if ev.get("source") != "author":
        return ""
    g = str(grounding or "").lower()
    return "decide-before-installing" if any(k in g for k in _HEAVY) else "install-and-run"


def members(design: dict | None, runs: list[dict] | None = None) -> list[dict]:
    """Every recorded pilot video: the state file's members plus PUBLISHED ledger
    rows carrying the experiment fields (one bookkeeping write can fail; the
    union cannot lose a member). Keyed by (pair_id, arm), first record wins."""
    out, seen = [], set()
    rows = list((design or {}).get("members") or [])
    for r in runs or []:
        if isinstance(r, dict) and r.get("experiment") == EXPERIMENT and r.get("status") == "PUBLISHED":
            rows.append({"pair_id": r.get("pair_id"), "arm": r.get("arm"), "slot": r.get("slot"),
                         "stratum": r.get("pilot_stratum"), "video_id": _vid(r.get("youtube_url")),
                         "published_at": r.get("publish_at"), "duration_s": r.get("duration_s"),
                         "task": r.get("pilot_task"), "title": r.get("title")})
    for m in rows:
        if not isinstance(m, dict) or m.get("arm") not in ARMS or not m.get("pair_id"):
            continue
        key = (str(m["pair_id"]), m["arm"])
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


def assign(ev: dict, grounding: str = "", design: dict | None = None,
           runs: list[dict] | None = None) -> dict | None:
    """The slot this candidate takes, or None (no design / pilot full / not
    eligible). PURE given its inputs. Arrival order only — never performance."""
    if not isinstance(design, dict) or not isinstance(ev, dict):
        return None
    source, intent = str(ev.get("source") or ""), intent_of(ev, grounding)
    if source not in ("hosted", "author") or not intent:
        return None
    stratum = f"{source}|{intent}"
    mem = members(design, runs)
    by_pair: dict[str, list[dict]] = {}
    for m in mem:
        by_pair.setdefault(str(m["pair_id"]), []).append(m)
    pairs = [p for p in design.get("pairs") or [] if isinstance(p, dict) and p.get("pair_id")]
    for p in pairs:                                   # close an open pair of this stratum
        got = by_pair.get(str(p["pair_id"]), [])
        if len(got) == 1 and got[0].get("stratum") == stratum:
            arm = "context" if got[0]["arm"] == "proof" else "proof"
            return {"experiment": EXPERIMENT, "pair_id": p["pair_id"], "arm": arm, "slot": 2,
                    "stratum": stratum, "intent": intent, "source": source,
                    "partner_seconds": _num(got[0].get("duration_s"))}
    for p in pairs:                                   # else open the next unused pair
        if not by_pair.get(str(p["pair_id"])):
            arm = p.get("first_arm") if p.get("first_arm") in ARMS else "proof"
            return {"experiment": EXPERIMENT, "pair_id": p["pair_id"], "arm": arm, "slot": 1,
                    "stratum": stratum, "intent": intent, "source": source,
                    "partner_seconds": None}
    return None


def ledger_fields(script) -> dict:
    """The growth spec's experiment fields, coerced (None when not a pilot video)."""
    p = script.get("pilot") if isinstance(script, dict) else None
    if not isinstance(p, dict) or p.get("experiment") != EXPERIMENT:
        return {"experiment": None, "pair_id": None, "arm": None, "slot": None}
    slot = p.get("slot")
    return {"experiment": EXPERIMENT, "pair_id": str(p.get("pair_id") or ""),
            "arm": p.get("arm") if p.get("arm") in ARMS else None,
            "slot": slot if slot in (1, 2) else None,
            "pilot_stratum": str(p.get("stratum") or ""),
            "pilot_intent": str(p.get("intent") or "")}


def record_member(script: dict, video_id: str, publish_at, duration_s, path: Path | None = None) -> bool:
    """Append the published member to state/pilot_a.json. Called inside run()'s
    post-upload try — and it never raises itself."""
    try:
        p = script.get("pilot")
        design = load(path)
        if not isinstance(p, dict) or design is None or not video_id:
            return False
        design.setdefault("members", []).append({
            "pair_id": p.get("pair_id"), "arm": p.get("arm"), "slot": p.get("slot"),
            "stratum": p.get("stratum"), "intent": p.get("intent"), "video_id": video_id,
            "title": str(script.get("title") or "")[:100],
            "task": str((script.get("query_map") or {}).get("task") or ""),
            "published_at": publish_at, "duration_s": duration_s,
            "recorded_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"})
        save(design, path)
        return True
    except Exception as e:  # noqa: BLE001 — post-upload zone
        print(f"  ⚠️ pilot member record failed ({type(e).__name__}: {e})")
        return False


# ============================================================ AVD baseline (A2)
def avd_baseline(runs: list[dict], snapshots: list[dict], before: dt.date | None = None) -> dict:
    """Unweighted median of eligible pre-pilot tool videos' first-7-day AVD.

    Per video: the LAST snapshot collected on calendar day publish+7 whose
    `ledger_videos` lists the video (that query is cumulative from DATA_FLOOR, so
    at age 7 it is exactly the [publish, publish+7] window). Eligible: a
    PUBLISHED tool long-form published before `before`, views > 0 and
    averageViewDuration > 0 in that snapshot. Never a lifetime number."""
    before = before or _today()
    vids, excluded = [], []
    seen = set()
    for r in runs:
        if not (isinstance(r, dict) and r.get("status") == "PUBLISHED" and r.get("format") == "tool"):
            continue
        vid, pub = _vid(r.get("youtube_url")), _date(r.get("publish_at") or r.get("timestamp"))
        if not vid or pub is None or vid in seen or pub >= before:
            continue
        seen.add(vid)
        want = pub + dt.timedelta(days=AVD_AGE)
        hit = None
        for s in snapshots:
            if not isinstance(s, dict) or _date(s.get("collected")) != want:
                continue
            heads = s.get("ledger_headers") or []
            if "averageViewDuration" not in heads:
                continue
            for row in s.get("ledger_videos") or []:
                if isinstance(row, list) and row and row[0] == vid:
                    hit = (s.get("collected"), dict(zip(heads, row)))   # later snapshot wins
        if hit is None:
            excluded.append({"video": vid, "published": pub.isoformat(),
                             "why": f"no snapshot collected on {want.isoformat()}"})
            continue
        views, avd = _num(hit[1].get("views")) or 0, _num(hit[1].get("averageViewDuration")) or 0
        if views <= 0 or avd <= 0:
            excluded.append({"video": vid, "published": pub.isoformat(),
                             "why": f"views={views:g} avd={avd:g} at age 7 (watch time not processed)"})
            continue
        vids.append({"video": vid, "published": pub.isoformat(), "snapshot": hit[0],
                     "views": int(views), "avd_s": avd})
    value = statistics.median([v["avd_s"] for v in vids]) if vids else None
    return {"status": "frozen" if value is not None else "unverified",
            "value_s": value, "n": len(vids), "videos": vids, "excluded": excluded,
            "rule": ("unweighted median of first-7-day averageViewDuration; per video the last "
                     "state/analytics.jsonl snapshot collected on publish_date+7 (ledger_videos, "
                     "cumulative from DATA_FLOOR = the first 7 days); views>0 and AVD>0")}


# ============================================================ Analytics reads
def retention_args(video_id: str, start: dt.date, end: dt.date) -> dict:
    """The audience-retention report (channel_reports "Audience retention"):
    required dimension elapsedVideoTimeRatio, required filter video==ONE id."""
    return dict(ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
                dimensions="elapsedVideoTimeRatio",
                metrics="audienceWatchRatio,relativeRetentionPerformance",
                filters=f"video=={video_id}")


def totals_args(video_id: str, start: dt.date, end: dt.date) -> dict:
    return dict(ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
                dimensions="video", metrics="views,estimatedMinutesWatched,averageViewDuration",
                filters=f"video=={video_id}")


def traffic_args(video_id: str, start: dt.date, end: dt.date) -> dict:
    return dict(ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
                dimensions="insightTrafficSourceType", metrics="views",
                filters=f"video=={video_id}")


def stored_reads(snapshots: list[dict]) -> dict:
    """(video, age) -> the latest stored read with a usable curve (else the latest)."""
    out = {}
    for s in snapshots:
        for rd in (s.get("pilot_reads") or []) if isinstance(s, dict) else []:
            if not isinstance(rd, dict):
                continue
            key = (str(rd.get("video")), int(_num(rd.get("age")) or 0))
            if usable(rd) or not usable(out.get(key)):
                out[key] = rd
    return out


def usable(rd) -> bool:
    return isinstance(rd, dict) and isinstance(rd.get("curve"), list) and len(rd["curve"]) >= USABLE_POINTS


def due_reads(mem: list[dict], stored: dict, today: dt.date) -> list[tuple[str, int, dt.date, dt.date]]:
    """(video, age, start, end) to query today: the window [publish, publish+age]
    once it has had READ_LAG_DAYS to process, until it has a usable curve or
    READ_RETRY_DAYS have passed."""
    due = []
    for m in mem:
        vid, pub = str(m.get("video_id") or ""), _date(m.get("published_at"))
        if not vid or pub is None:
            continue
        for age in CHECK_AGES:
            end = pub + dt.timedelta(days=age)
            if not (end + dt.timedelta(days=READ_LAG_DAYS) <= today
                    <= end + dt.timedelta(days=READ_LAG_DAYS + READ_RETRY_DAYS)):
                continue
            if usable(stored.get((vid, age))):
                continue
            due.append((vid, age, pub, end))
    return due


def collect_reads(yta, runs: list[dict], snapshots: list[dict], today: dt.date | None = None) -> list[dict]:
    """Query every due (video, age). One failed query costs only that read."""
    today = today or _today()
    mem = members(load(), runs)
    out = []
    for vid, age, start, end in due_reads(mem, stored_reads(snapshots), today):
        rd = {"video": vid, "age": age, "start": start.isoformat(), "end": end.isoformat(),
              "read_on": today.isoformat(), "curve": [], "totals": None, "traffic": []}
        try:
            r = yta.reports().query(**retention_args(vid, start, end)).execute()
            rd["curve"] = [row[:3] for row in r.get("rows") or [] if isinstance(row, list)]
            t = yta.reports().query(**totals_args(vid, start, end)).execute()
            rows = t.get("rows") or []
            rd["totals"] = rows[0][1:4] if rows else None
            tr = yta.reports().query(**traffic_args(vid, start, end)).execute()
            rd["traffic"] = [row[:2] for row in tr.get("rows") or [] if isinstance(row, list)]
        except Exception as e:  # noqa: BLE001
            rd["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        out.append(rd)
    return out


# ============================================================ readout
def sample(curve: list, duration_s: float, target_s: float) -> tuple[float, float] | None:
    """(retention %, ACTUAL sampled seconds) at the curve point nearest target_s.
    A point's ratio is the exclusive END of its interval, so its time is
    ratio x duration."""
    best = None
    for row in curve or []:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        r, a = _num(row[0]), _num(row[1])
        if r is None or a is None:
            continue
        t = r * float(duration_s)
        if best is None or abs(t - target_s) < abs(best[1] - target_s):
            best = (round(a * 100.0, 2), round(t, 2))
    return best


def _pair_points(m: dict, rd: dict) -> dict:
    d = _num(m.get("duration_s")) or 0.0
    pts = {}
    for target in (7, 30, 60):
        s = sample(rd.get("curve"), d, target) if d else None
        pts[target] = s
    tot = rd.get("totals") or []
    views = _num(tot[0]) if tot else None
    avd = _num(tot[2]) if len(tot) > 2 else None
    return {"points": pts, "views": views, "avd": avd, "traffic": rd.get("traffic") or []}


def evaluate_pairs(design: dict, mem: list[dict], stored: dict, at_age: int | None = None) -> list[dict]:
    """One row per pre-assigned pair: its checkpoint (first common usable age,
    or `at_age` for the day-28 recheck), both arms' samples and the advantage."""
    out = []
    for p in design.get("pairs") or []:
        pid = str(p.get("pair_id"))
        arms = {m["arm"]: m for m in mem if str(m.get("pair_id")) == pid}
        row = {"pair_id": pid, "stratum": next((m.get("stratum") for m in arms.values()), None),
               "videos": {a: arms[a].get("video_id") for a in arms}, "age": None,
               "evaluable": False, "why": ""}
        if set(arms) != set(ARMS):
            row["why"] = "missing " + ", ".join(a for a in ARMS if a not in arms)
            out.append(row)
            continue
        ages = [at_age] if at_age else list(CHECK_AGES)
        for age in ages:
            a = stored.get((str(arms["proof"].get("video_id")), age))
            b = stored.get((str(arms["context"].get("video_id")), age))
            if usable(a) and usable(b):
                pa, pb = _pair_points(arms["proof"], a), _pair_points(arms["context"], b)
                if pa["points"][7] and pb["points"][7]:
                    row.update(age=age, evaluable=True, proof=pa, context=pb,
                               advantage=round(pa["points"][7][0] - pb["points"][7][0], 2))
                    break
        if not row["evaluable"]:
            row["why"] = "no common usable curve" + (f" at day {at_age}" if at_age else " yet")
        out.append(row)
    return out


def decide(rows: list[dict], avd_baseline_s: float | None, treatment_avds: list,
           batch: int = 1) -> dict:
    """Round 3 §4 + A1/A2 decision. Order: unresolved, stop, promising, revise
    delivery, flat, revise hypothesis."""
    ev = [r for r in rows if r.get("evaluable")]
    adv = [r["advantage"] for r in ev]
    res = {"evaluable": len(ev), "missing": [r["pair_id"] for r in rows if not r.get("evaluable")]}
    if adv:
        res["median_advantage"] = round(statistics.median(adv), 2)
        res["wins_proof"] = sum(1 for a in adv if a > 0)
        w = [((r["proof"]["views"] or 0) + (r["context"]["views"] or 0), r["advantage"]) for r in ev]
        tw = sum(x for x, _ in w)
        res["exposure_weighted_advantage"] = round(sum(x * a for x, a in w) / tw, 2) if tw else None
        med = {}
        for t in (7, 30, 60):
            vals = [r["proof"]["points"][t][0] for r in ev if r["proof"]["points"].get(t)]
            med[t] = round(statistics.median(vals), 2) if vals else None
        res["treatment_medians"] = med
    avds = [a for a in (treatment_avds or []) if _num(a)]
    if avd_baseline_s is None or len(avds) < PAIRS:
        res["avd_guardrail"] = "unverified"
    else:
        res["treatment_avd_median"] = round(statistics.median(avds), 1)
        res["avd_guardrail"] = "breached" if res["treatment_avd_median"] < avd_baseline_s else "ok"
    if len(ev) < PAIRS:
        res["decision"] = "unresolved"
        res["why"] = f"{len(ev)} of {PAIRS} pairs evaluable; missing pairs are reported, never replaced"
        return res
    m, wins = res["median_advantage"], res["wins_proof"]
    med = res["treatment_medians"]
    targets_met = {t: (med.get(t) is not None and med[t] >= TARGETS[t]) for t in (7, 30, 60)}
    if all(a < 0 for a in adv) and m <= -STOP_DISADV:
        res["decision"], res["why"] = "stop", "all pairs favour context-first, median disadvantage >= 5 pts"
    elif batch >= 2 and m <= 0 and wins <= FLAT_STOP_POSITIVES:
        res["decision"], res["why"] = "stop", "flat after the extra batch: median <= 0, <= 2 positive pairs"
    elif wins >= PROMISING_WINS and m >= PROMISING_ADV and all(targets_met.values()) \
            and res["avd_guardrail"] != "breached":
        res["decision"], res["why"] = "promising", "repeat: >= 5/6 wins, median >= 8 pts, 65/45/38 met"
    elif (wins >= PROMISING_WINS and m >= PROMISING_ADV) or res["avd_guardrail"] == "breached":
        res["decision"] = "revise delivery"
        res["why"] = ("AVD below the frozen pre-pilot median" if res["avd_guardrail"] == "breached"
                      else "proof-first won the pairs, but a treatment median missed 65/45/38")
    elif m <= 0:
        res["decision"], res["why"] = "flat", "median advantage <= 0: run one more 6-pair batch"
    else:
        res["decision"], res["why"] = "revise hypothesis", "mixed, or median advantage above 0 but below 8 pts"
    return res


def readout(design: dict | None = None, runs: list[dict] | None = None,
            snapshots: list[dict] | None = None) -> dict:
    """The whole readout: per pair, the decision, the outlier check and the
    day-28 recheck. Never raises (returns {"error": ...})."""
    try:
        design = design if design is not None else load()
        if not design:
            return {"error": "no pilot design (state/pilot_a.json)"}
        mem = members(design, runs or [])
        stored = stored_reads(snapshots or [])
        rows = evaluate_pairs(design, mem, stored)
        base = (design.get("avd_baseline") or {}).get("value_s")
        tavd = []
        for m in mem:
            if m.get("arm") == "proof":
                rd = stored.get((str(m.get("video_id")), 7))
                tot = (rd or {}).get("totals") or []
                tavd.append(_num(tot[2]) if len(tot) > 2 else None)
        res = decide(rows, _num(base), tavd, int(_num(design.get("batch")) or 1))
        ev = [r for r in rows if r.get("evaluable")]
        if len(ev) >= 2:
            top = max(ev, key=lambda r: r["advantage"])
            alt = [r["advantage"] for r in ev if r is not top]
            alt_med = round(statistics.median(alt), 2)
            res["without_largest_winner"] = {"pair": top["pair_id"], "median_advantage": alt_med,
                                             "wins_proof": sum(1 for a in alt if a > 0)}
            # "outlier-dependent" (round 3 §4): removing one winner reverses the
            # apparent advantage — the sign flips, or a promising median drops below 8
            res["outlier_dependent"] = bool(
                (res["median_advantage"] > 0 >= alt_med)
                or (res.get("decision") == "promising" and alt_med < PROMISING_ADV))
        res["pairs"] = rows
        res["day28"] = [{"pair_id": r["pair_id"], "evaluable": r["evaluable"],
                         "advantage": r.get("advantage")}
                        for r in evaluate_pairs(design, mem, stored, at_age=28)]
        return res
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def format_readout(res: dict) -> str:
    if res.get("error"):
        return f"Pilot A readout: {res['error']}"
    lines = [f"Pilot A readout — decision: {res.get('decision')} ({res.get('why', '')})",
             f"  evaluable pairs {res.get('evaluable')}/{PAIRS}; missing: {res.get('missing') or '-'}",
             f"  median advantage at ~0:07: {res.get('median_advantage')} pts; proof wins "
             f"{res.get('wins_proof')}; exposure-weighted {res.get('exposure_weighted_advantage')}",
             f"  treatment medians ~0:07/0:30/1:00: {res.get('treatment_medians')}",
             f"  AVD guardrail: {res.get('avd_guardrail')} "
             f"(treatment median {res.get('treatment_avd_median')})"]
    w = res.get("without_largest_winner")
    if w:
        lines.append(f"  without largest winner ({w['pair']}): median {w['median_advantage']}, "
                     f"proof wins {w['wins_proof']}" +("  ** outlier-dependent **" if res.get("outlier_dependent") else ""))
    for r in res.get("pairs") or []:
        if r.get("evaluable"):
            p, c = r["proof"]["points"], r["context"]["points"]
            lines.append(f"  {r['pair_id']} day {r['age']}: proof {p[7]} vs context {c[7]} "
                         f"(pct, sampled s) → {r['advantage']:+.1f} pts  "
                         f"[0:30 {p[30]} / {c[30]}; 1:00 {p[60]} / {c[60]}]")
        else:
            lines.append(f"  {r['pair_id']}: not evaluable ({r.get('why')})")
    return "\n".join(lines)


def _read_jsonl(path: Path) -> list[dict]:
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict):
                out.append(d)
    except OSError:
        pass
    return out


def main(argv: list[str]) -> int:
    """`python -m factverse.pilot freeze [--seed N]` (once) | `readout` (any time)."""
    runs = _read_jsonl(fv.STATE / "runs.jsonl")
    snaps = _read_jsonl(fv.STATE / "analytics.jsonl")
    if argv[:1] == ["freeze"]:
        if load() is not None:
            print("Pilot A is already frozen — refusing to redraw the assignment.")
            return 1
        seed = int(argv[argv.index("--seed") + 1]) if "--seed" in argv else None
        d = new_design(seed)
        d["avd_baseline"] = avd_baseline(runs, snaps)
        d["avd_baseline"]["frozen_at"] = d["frozen_at"]
        save(d)
        print(json.dumps({k: d[k] for k in ("seed", "pairs")}, indent=1))
        print("AVD baseline:", d["avd_baseline"]["status"], d["avd_baseline"]["value_s"],
              f"(n={d['avd_baseline']['n']})")
        return 0
    print(format_readout(readout(load(), runs, snaps)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
