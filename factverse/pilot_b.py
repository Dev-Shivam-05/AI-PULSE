"""
v3-S.1 Pilot B: native concept Short vs crop excerpt (docs/spec/ai-pulse-v3s1.md, row 8).

Six production-day pairs (12 Shorts). Each production day D publishes one native
Short and one crop excerpt, at exactly 18:45 UTC on D and 01:30 UTC on D+1. Which
format takes 18:45 alternates daily from a random first draw (recorded), so each
format gets each slot 3 times in a batch of 6.

State: `state/pilot_b.json`, a TRACKED file the publish run writes, so it has the
both-halves treatment (state_merge.FILES with dict semantics AND publish.yml's
stash list). Shape:
    {"experiment": "pilot_b",
     "batches": {"1": {"first_native_slot": "18:45", "drawn_at": "...", "method": "..."}},
     "days":    {"2026-11-05": {pair entry, see record()}}}

Readout: the primary measure, Studio's "Stayed to watch", is NOT in the YouTube
Analytics or Reporting APIs (spec "API finding"), so the readout reads CSVs the
owner exports from Studio. `python -m factverse.pilot_b readout <dir>`.

Every function used by run() fails soft and never raises.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import random
import re
import statistics
import sys
from pathlib import Path

from factverse import config as fv

EXPERIMENT = "pilot_b"
STATE_FILE = fv.STATE / "pilot_b.json"
SLOTS = ("18:45", "01:30")              # D and D+1, UTC (round 3 §4)
PAIRS_PER_BATCH = 6                     # round 3 §4
# readout (round 3 §4, verbatim values)
BASELINE_CROP_MEDIAN, BASELINE_N = 16.9, 18
FLOOR_IMPRESSIONS = 100
OBSERVATION_DAYS = 7
PROMISING_MEDIAN, PROMISING_ADV, PROMISING_WINS = 22.0, 5.0, 5
STOP_WINS, STOP_DISADV = 1, 5.0
SECOND_BATCH_PAIRS, SECOND_BATCH_MAX_WINS = 12, 6
GUARDRAIL_DECLINE = 0.10


# ------------------------------------------------------------------ state
def empty_state() -> dict:
    return {"experiment": EXPERIMENT, "batches": {}, "days": {}}


def load_state(path: Path | None = None) -> dict:
    """The pilot state, coerced; a missing or corrupt file is an empty pilot."""
    p = Path(path or STATE_FILE)
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        d = {}
    out = empty_state()
    if isinstance(d, dict):
        if isinstance(d.get("batches"), dict):
            out["batches"] = {str(k): v for k, v in d["batches"].items() if isinstance(v, dict)}
        if isinstance(d.get("days"), dict):
            out["days"] = {str(k): v for k, v in d["days"].items() if isinstance(v, dict)}
    return out


def save_state(state: dict, path: Path | None = None) -> bool:
    try:
        p = Path(path or STATE_FILE)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"   ⚠️ pilot_b state not saved: {type(e).__name__}")
        return False


def merge(theirs, ours) -> dict:
    """state_merge semantics. `batches`: origin/main's draw wins — earlier days were
    assigned under it, a second draw must never replace it. `days`: union by date;
    on the same date the later `recorded_at` wins."""
    a = theirs if isinstance(theirs, dict) else {}
    b = ours if isinstance(ours, dict) else {}
    out = empty_state()
    for side in (b, a):                     # a (theirs) written last -> wins
        batches = side.get("batches") if isinstance(side.get("batches"), dict) else {}
        for k, v in batches.items():
            if isinstance(v, dict):
                out["batches"][str(k)] = v
    for side in (a, b):
        days = side.get("days") if isinstance(side.get("days"), dict) else {}
        for k, v in days.items():
            if not isinstance(v, dict):
                continue
            cur = out["days"].get(str(k))
            if cur is None or str(v.get("recorded_at", "")) >= str(cur.get("recorded_at", "")):
                out["days"][str(k)] = v
    return out


# ------------------------------------------------------------------ assignment
def _other(slot: str) -> str:
    return SLOTS[1] if slot == SLOTS[0] else SLOTS[0]


def assign(state: dict, day: str, max_batches: int = 1, rng=None) -> dict | None:
    """Today's pair assignment, or None when every allowed batch is complete.

    Production days are counted, not calendar days: index k is the number of days
    already recorded in the batch. Native takes the batch's first-drawn slot on
    even k and the other slot on odd k, so 6 days give each format each slot 3
    times. A day already recorded returns its own assignment (a retry run)."""
    days = state.setdefault("days", {})
    if day in days:
        d = days[day]
        keys = ("pair_id", "batch", "index", "native_slot", "crop_slot")
        return {k: d.get(k) for k in keys} | {"day": day}
    batches = state.setdefault("batches", {})
    for b in range(1, max(0, int(max_batches)) + 1):
        used = sorted(k for k, v in days.items() if int(v.get("batch") or 0) == b)
        if len(used) >= PAIRS_PER_BATCH:
            continue
        info = batches.get(str(b))
        if not info or info.get("first_native_slot") not in SLOTS:
            info = {"first_native_slot": (rng or random.SystemRandom()).choice(SLOTS),
                    "drawn_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                    "method": "random.SystemRandom().choice(('18:45', '01:30'))"}
            batches[str(b)] = info
        k = len(used)
        native = info["first_native_slot"] if k % 2 == 0 else _other(info["first_native_slot"])
        return {"pair_id": f"B{b}-{k + 1:02d}", "batch": b, "index": k, "native_slot": native,
                "crop_slot": _other(native), "day": day}
    return None


def schedule(first_native_slot: str, start: dt.date, n: int = PAIRS_PER_BATCH) -> list[dict]:
    """The batch's plan over n consecutive production days (display / tests)."""
    first = first_native_slot if first_native_slot in SLOTS else SLOTS[0]
    out = []
    for k in range(n):
        d = start + dt.timedelta(days=k)
        native = first if k % 2 == 0 else _other(first)
        out.append({"pair_id": f"B1-{k + 1:02d}", "day": d.isoformat(),
                    "18:45": f"{d.isoformat()} 18:45Z " + ("native" if native == "18:45" else "crop"),
                    "01:30": f"{(d + dt.timedelta(days=1)).isoformat()} 01:30Z "
                             + ("native" if native == "01:30" else "crop")})
    return out


# ------------------------------------------------------------------ composition (run())
def compose(crops: list, hooks: list, native: dict | None, native_index: int) -> dict:
    """The day's Shorts in SLOT order (index 0 = 18:45, 1 = 01:30).

    Native present: native in `native_index`, the control (crop 1) in the other.
    Native skipped: the slot gets the second crop excerpt (delegated: the channel
    keeps two Shorts; the pair is unevaluable), and the control keeps its slot."""
    crops = [str(c) for c in (crops or [])]
    hooks = [str(h) for h in (hooks or [])] + [""] * max(0, len(crops) - len(hooks or []))
    idx = 0 if native_index == 0 else 1
    if native and native.get("path"):
        items = [(native["path"], str(native.get("spec", {}).get("headline", "")))]
        if crops:
            ctrl = (crops[0], hooks[0])
            items = [items[0], ctrl] if idx == 0 else [ctrl, items[0]]
    else:
        items = list(zip(crops[:2], hooks[:2]))
        if len(items) == 2 and idx == 0:
            items = [items[1], items[0]]    # the control keeps the crop slot
    return {"shorts": [p for p, _ in items], "hooks": [h for _, h in items]}


def plan_day(day: str, crops: list, hooks: list, native: dict | None, native_skip: str = "",
             pilot: bool = True, max_batches: int = 1, state: dict | None = None,
             parity_index: int = 0) -> dict:
    """Everything run() needs for the day, in one never-raising call."""
    try:
        st = state if state is not None else load_state()
        a = assign(st, day, max_batches) if pilot else None
        idx = (0 if a["native_slot"] == SLOTS[0] else 1) if a else (0 if parity_index == 0 else 1)
        c = compose(crops, hooks, native, idx)
        spec = (native or {}).get("spec") or {}
        return {**c, "state": st, "assignment": a, "native_index": idx,
                "native_ok": bool(native and native.get("path")),
                "native_skip": "" if native else (native_skip or "not attempted"),
                "native_title": str(spec.get("title") or ""),
                "native_summary": _native_summary(native),
                "crop_hook": str((hooks or [""])[0] if hooks else ""),
                "match": (native or {}).get("match") or ""}
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ pilot_b plan failed: {type(e).__name__} — today's Shorts as rendered")
        return {"shorts": list(crops) if isinstance(crops, list) else [],
                "hooks": list(hooks) if isinstance(hooks, list) else [], "assignment": None,
                "native_index": None, "native_ok": False, "native_skip": "plan failed",
                "state": None}


def _native_summary(native: dict | None) -> dict:
    if not native:
        return {}
    m = native.get("measured") or {}
    spec = native.get("spec") or {}
    return {"question": spec.get("question", ""), "headline": spec.get("headline", ""),
            "template": spec.get("template", ""), "attempts": native.get("attempts"),
            "duration": m.get("duration"), "first_speech": m.get("first_speech"),
            "sentence_ends": m.get("sentence_ends"), "words": m.get("script_words"),
            "timed_by": m.get("source"), "min_px": native.get("min_px")}


def ledger_fields(plan: dict | None) -> dict:
    """The long-form row's experiment fields; {} outside the pilot."""
    try:
        a = (plan or {}).get("assignment")
        if not a:
            return {}
        arm = f"native@{a['native_slot']}" if plan.get("native_ok") else f"native_skipped@{a['native_slot']}"
        return {"experiment": EXPERIMENT, "pair_id": a["pair_id"], "arm": arm,
                "slot": a["native_slot"]}
    except Exception:  # noqa: BLE001
        return {}


def record(plan: dict | None, short_rows: list, long_url: str | None, slots_ok: bool,
           path: Path | None = None) -> bool:
    """Write the day's pair into the state file. Post-upload zone: never raises.
    Every assigned day is recorded, including a skipped native (unevaluable)."""
    try:
        a = (plan or {}).get("assignment")
        st = (plan or {}).get("state")
        if not a or st is None:
            return False
        rows = [r for r in (short_rows or []) if isinstance(r, dict)]
        nat = next((r for r in rows if r.get("engine") == "native"), None)
        crop = next((r for r in rows if r.get("engine") == "crop" and r.get("slot") == a["crop_slot"]),
                    None) or next((r for r in rows if r.get("engine") == "crop"), None)
        reasons = []
        if not plan.get("native_ok"):
            reasons.append(f"native skipped: {plan.get('native_skip', '')}"[:200])
        elif not nat:
            reasons.append("native upload failed")
        if not crop:
            reasons.append("no crop control uploaded")
        if not slots_ok:
            reasons.append("pilot slots unavailable; published on the normal grid")
        st.setdefault("days", {})[a["day"]] = {
            "pair_id": a["pair_id"], "batch": a["batch"], "index": a["index"],
            "native_slot": a["native_slot"], "crop_slot": a["crop_slot"],
            "native": {"url": (nat or {}).get("url"), "slot": (nat or {}).get("slot"),
                       "status": "published" if nat else ("skipped" if not plan.get("native_ok")
                                                          else "upload_failed"),
                       **(plan.get("native_summary") or {})},
            "crop": {"url": (crop or {}).get("url"), "slot": (crop or {}).get("slot"),
                     "hook": plan.get("crop_hook", "")},
            "match": plan.get("match") or ("" if not plan.get("native_ok") else "concept_family"),
            "slots_ok": bool(slots_ok), "long_url": long_url,
            "evaluable_by_design": not reasons, "unevaluable_reason": "; ".join(reasons),
            "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        return save_state(st, path)
    except Exception as e:  # noqa: BLE001
        print(f"   ⚠️ pilot_b record failed: {type(e).__name__}")
        return False


# ------------------------------------------------------------------ readout
def _num(v) -> float | None:
    s = str(v if v is not None else "").replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _col(header: list[str], *needles: str) -> int | None:
    for i, h in enumerate(header):
        hl = h.strip().lower()
        if any(n in hl for n in needles):
            return i
    return None


def parse_studio_csv(path: Path) -> dict[str, dict]:
    """Studio "Table data.csv" -> {video_id: {shown, stayed, engaged, watch_h}}.
    Columns found by name (case-insensitive); the "Total" row is skipped."""
    out: dict[str, dict] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return out
    h = rows[0]
    ci = _col(h, "content", "video id")
    cs = _col(h, "shown in feed")
    cst = _col(h, "stayed to watch", "viewed (vs. swiped away)", "viewed vs swiped")
    ce = _col(h, "engaged views")
    cw = _col(h, "watch time (hours)")
    if ci is None:
        return out
    for r in rows[1:]:
        if len(r) <= ci or not r[ci].strip() or r[ci].strip().lower() == "total":
            continue

        def g(c):
            return _num(r[c]) if c is not None and c < len(r) else None
        shown, stayed, engaged = g(cs), g(cst), g(ce)
        if stayed is None and shown and engaged is not None:
            stayed = 100.0 * engaged / shown          # Studio's own definition, reconstructed
        out[r[ci].strip()] = {"shown": shown, "stayed": stayed, "engaged": engaged, "watch_h": g(cw)}
    return out


def _vid(url) -> str | None:
    from factverse import learn  # noqa: PLC0415
    return learn.video_id(url)


def collect(state: dict, csv_dir: Path, as_of: dt.date) -> list[dict]:
    """One row per ASSIGNED pair (none silently dropped), with its evaluability."""
    csv_dir = Path(csv_dir)
    combined: dict[str, dict] = {}
    if csv_dir.exists():
        for p in sorted(csv_dir.glob("*.csv")):
            if not re.fullmatch(r"B\d+-\d+(_feed)?", p.stem):   # pair files are read per pair
                combined.update(parse_studio_csv(p))
    out = []
    for day, d in sorted((state.get("days") or {}).items()):
        nid, cid = _vid((d.get("native") or {}).get("url")), _vid((d.get("crop") or {}).get("url"))
        own = csv_dir / f"{d.get('pair_id')}.csv"
        data, window = ({}, "")
        if own.exists():
            data, window = parse_studio_csv(own), "7-day pair export"
        elif nid in combined or cid in combined:
            data, window = combined, "combined export (window not per pair)"
        feed_p = csv_dir / f"{d.get('pair_id')}_feed.csv"
        feed = parse_studio_csv(feed_p) if feed_p.exists() else {}
        n, c = data.get(nid or "", {}), data.get(cid or "", {})
        row = {"pair_id": d.get("pair_id"), "batch": int(d.get("batch") or 0), "day": day,
               "native_slot": d.get("native_slot"), "match": d.get("match") or "-",
               "native_id": nid, "crop_id": cid, "window": window,
               "native": n.get("stayed"), "crop": c.get("stayed"),
               "native_shown": n.get("shown"), "crop_shown": c.get("shown"),
               "native_watch_h": (feed.get(nid or "") or {}).get("watch_h"),
               "crop_watch_h": (feed.get(cid or "") or {}).get("watch_h"),
               "native_feed_shown": (feed.get(nid or "") or {}).get("shown"),
               "crop_feed_shown": (feed.get(cid or "") or {}).get("shown")}
        why = []
        if not d.get("evaluable_by_design", True):
            why.append(d.get("unevaluable_reason") or "not evaluable by design")
        if not nid or not cid:
            why.append("missing upload")
        elif not n or not c:
            why.append("no Studio row")
        else:
            if (n.get("shown") or 0) < FLOOR_IMPRESSIONS or (c.get("shown") or 0) < FLOOR_IMPRESSIONS:
                why.append(f"below {FLOOR_IMPRESSIONS} feed impressions")
            if n.get("stayed") is None or c.get("stayed") is None:
                why.append("no stayed-to-watch value")
        try:
            ready = dt.date.fromisoformat(day) + dt.timedelta(days=1 + OBSERVATION_DAYS)
        except ValueError:
            ready = as_of
        if as_of < ready:
            why.append(f"observation window open until {ready.isoformat()} (provisional)")
        row["evaluable"], row["why"] = not why, "; ".join(why)
        row["adv"] = (row["native"] - row["crop"]) if row["native"] is not None and row["crop"] is not None else None
        out.append(row)
    return out


def _agg(rows: list[dict], arm: str) -> float | None:
    w = sum(r[f"{arm}_shown"] for r in rows)
    return sum(r[arm] * r[f"{arm}_shown"] for r in rows) / w if w else None


def summarize(rows: list[dict]) -> dict:
    """Round 3's numbers over the EVALUABLE pairs. Pure."""
    ev = [r for r in rows if r.get("evaluable")]
    s = {"evaluable": len(ev), "assigned": len(rows)}
    if not ev:
        return s
    adv = [r["adv"] for r in ev]
    s.update(native_median=statistics.median(r["native"] for r in ev),
             crop_median=statistics.median(r["crop"] for r in ev),
             median_adv=statistics.median(adv), wins=sum(1 for a in adv if a > 0),
             native_agg=_agg(ev, "native"), crop_agg=_agg(ev, "crop"))
    s["agg_adv"] = s["native_agg"] - s["crop_agg"]
    pos = [r for r in ev if r["adv"] > 0]
    s["outlier_dependent"] = False
    if pos:
        top = max(pos, key=lambda r: r["adv"])
        rest = [r for r in ev if r is not top]
        s["largest_winner"] = top["pair_id"]
        s["median_adv_wo"] = statistics.median(r["adv"] for r in rest) if rest else None
        s["agg_adv_wo"] = (_agg(rest, "native") - _agg(rest, "crop")) if rest else None
        flips = ((s["median_adv"] > 0 and (s["median_adv_wo"] is None or s["median_adv_wo"] <= 0))
                 or (s["agg_adv"] > 0 and (s["agg_adv_wo"] is None or s["agg_adv_wo"] <= 0)))
        s["outlier_dependent"] = bool(flips)
    # watch-time guardrail: seconds watched per Shorts-feed impression, only where measured
    g = [r for r in ev if r.get("native_watch_h") is not None and r.get("crop_watch_h") is not None
         and r.get("native_feed_shown") and r.get("crop_feed_shown")]
    if g:
        n = sum(r["native_watch_h"] for r in g) * 3600 / sum(r["native_feed_shown"] for r in g)
        c = sum(r["crop_watch_h"] for r in g) * 3600 / sum(r["crop_feed_shown"] for r in g)
        s["guardrail"] = {"pairs": len(g), "native_s_per_impr": n, "crop_s_per_impr": c,
                          "change": (n - c) / c if c else None}
    return s


def overall_verdict(s: dict) -> str:
    """Round 3's rule after a second batch, over ALL evaluable pairs."""
    if s.get("evaluable", 0) < SECOND_BATCH_PAIRS:
        return f"second-batch rule not reached ({s.get('evaluable', 0)} of {SECOND_BATCH_PAIRS} evaluable pairs)"
    if s["median_adv"] <= 0 and s["wins"] <= SECOND_BATCH_MAX_WINS:
        return "stop scaling this native implementation"
    return "second-batch stop rule not met"


def verdict(s: dict) -> str:
    """Round 3's decision rules for one batch, in its own words."""
    if s.get("evaluable", 0) < PAIRS_PER_BATCH:
        return f"audience effect unresolved (fewer than {PAIRS_PER_BATCH} evaluable pairs)"
    if (s["native_median"] >= PROMISING_MEDIAN and s["median_adv"] >= PROMISING_ADV
            and s["wins"] >= PROMISING_WINS):
        g = s.get("guardrail") or {}
        if g.get("change") is not None and g["change"] < -GUARDRAIL_DECLINE:
            return f"revise, not scale (watch-time guardrail: {g['change']:+.0%} per feed impression)"
        return "promising: repeat"
    if s["wins"] <= STOP_WINS and s["median_adv"] <= -STOP_DISADV:
        return "stop this native package (keep crop while redesigning native)"
    return "revise"


def _f(v, fmt="{:.1f}") -> str:
    return "-" if v is None else fmt.format(v)


def format_readout(rows: list[dict], as_of: dt.date) -> str:
    lines = [f"Pilot B readout - {as_of.isoformat()}  (stayed-to-watch, %; floor {FLOOR_IMPRESSIONS} "
             f"feed impressions per Short; crop baseline median {BASELINE_CROP_MEDIAN}% n={BASELINE_N})",
             "", f"{'pair':<7}{'day':<12}{'native@':<8}{'native':>8}{'crop':>8}{'adv':>8}"
             f"{'n_impr':>8}{'c_impr':>8}  match / status"]
    for r in rows:
        lines.append(f"{r['pair_id']:<7}{r['day']:<12}{str(r['native_slot']):<8}{_f(r['native']):>8}"
                     f"{_f(r['crop']):>8}{_f(r['adv'], '{:+.1f}'):>8}{_f(r['native_shown'], '{:.0f}'):>8}"
                     f"{_f(r['crop_shown'], '{:.0f}'):>8}  {r['match']} / "
                     + ("evaluable" if r["evaluable"] else f"UNEVALUABLE: {r['why']}")
                     + (f" [{r['window']}]" if r.get("window") else ""))
    for b in sorted({r["batch"] for r in rows}):
        s = summarize([r for r in rows if r["batch"] == b])
        lines += ["", f"batch {b}: {s['evaluable']} of {s['assigned']} assigned pairs evaluable"]
        if s["evaluable"]:
            lines += [f"  native median {_f(s['native_median'])}% | crop median {_f(s['crop_median'])}% | "
                      f"median paired advantage {_f(s['median_adv'], '{:+.1f}')} pts | native wins "
                      f"{s['wins']} of {s['evaluable']}",
                      f"  exposure-weighted: native {_f(s['native_agg'])}% vs crop {_f(s['crop_agg'])}% "
                      f"({_f(s['agg_adv'], '{:+.1f}')} pts)"]
            if s.get("largest_winner"):
                lines.append(f"  without the largest winner ({s['largest_winner']}): median advantage "
                             f"{_f(s.get('median_adv_wo'), '{:+.1f}')} pts, weighted "
                             f"{_f(s.get('agg_adv_wo'), '{:+.1f}')} pts"
                             + ("  -> OUTLIER-DEPENDENT" if s["outlier_dependent"] else ""))
            g = s.get("guardrail")
            lines.append("  watch-time guardrail: " + (
                f"native {g['native_s_per_impr']:.2f} s vs crop {g['crop_s_per_impr']:.2f} s per feed "
                f"impression ({g['change']:+.0%}, {g['pairs']} pairs)" if g and g.get("change") is not None
                else "not available (no Shorts-feed watch-time export)"))
        lines.append(f"  verdict: {verdict(s)}"
                     + ("  [outlier-dependent]" if s.get("outlier_dependent") else ""))
    if len({r["batch"] for r in rows}) > 1:
        lines += ["", f"all batches: {overall_verdict(summarize(rows))}"]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ CLI
def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "status"

    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default
    state = load_state(Path(opt("--state")) if opt("--state") else None)
    if cmd == "schedule":
        start = dt.date.fromisoformat(opt("--start", dt.date.today().isoformat()))
        first = opt("--first") or (state["batches"].get("1") or {}).get("first_native_slot") or "(not drawn yet)"
        print(f"Pilot B batch 1 - first native slot: {first}")
        for d in schedule(first if first in SLOTS else SLOTS[0], start):
            print(f"  {d['pair_id']}  D={d['day']}  {d['18:45']:<32}{d['01:30']}")
        return 0
    if cmd == "readout" and len(argv) > 1:
        as_of = dt.date.fromisoformat(opt("--as-of", dt.date.today().isoformat()))
        text = format_readout(collect(state, Path(argv[1]), as_of), as_of)
        sys.stdout.write(text)
        return 0
    print(json.dumps({"batches": state["batches"], "days": sorted(state["days"])}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
