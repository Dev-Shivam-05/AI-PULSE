"""
v3-M.1 row 9: the per-video memory record and the one follow-up rule
(docs/spec/ai-pulse-v3m1.md).

The record connects viewer question -> evidence -> video -> outcome -> next
unanswered question (round 3 §5). It is BUILT, never stored: every field comes
from a file that already exists (state/runs.jsonl, state/analytics.jsonl,
state/tools_index.json), so there is no new state file to stash and merge.

The follow-up rule (verbatim, round 3 §5): a canonical query family with >= 50
attributed search views in the last 28 days (never lifetime), plus a specific
question the original left unanswered, plus admissible evidence, becomes ONE
follow-up candidate. 14-day cooldown per family unless it corrects an error or
documents a material change. A candidate is not an upload: it is handed to the
tool lane's candidate list and still passes every gate there.

Pure except `evidence_probe` (the v3-P.1 seam, which may touch the network) and
the file readers. Every public entry point the pipeline calls is fail-soft.

Run:  python -m factverse.memory [n]   (prints the records of the last n videos)
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

from factverse import config as fv
from factverse import learn

TOOLS_INDEX = fv.STATE / "tools_index.json"

# --- locked by the 2026-11-04 review (round 3 §5, round 4 Rank 2) -----------------
FOLLOWUP_MIN_VIEWS = 50          # attributed search views of one query family ...
FOLLOWUP_WINDOW_DAYS = 28        # ... in the last 28 days, never lifetime
FOLLOWUP_COOLDOWN_DAYS = 14      # per family
COOLDOWN_EXEMPT = ("correction", "material_change")
AGE_BANDS = ((1, 7), (8, 14), (15, 28), (29, 56))       # search-longevity cohorts
PERF_SPANS = (("72h", 3), ("7d", 7), ("28d", 28))       # performance snapshots

# --- delegated (spec table "Delegated decisions") ---------------------------------
QUESTION_MAX_CHARS = 200
QUESTIONS_OPEN_MAX = 3
TERMS_MIN_VIDEO_VIEWS = 25       # a video's 28-day search views before its terms are fetched
TERMS_MAX_VIDEOS = 10            # traffic-source-detail queries per nightly collection
TERMS_STALE_DAYS = 7             # older search-term data never fires a candidate
FOLLOWUPS_PER_RUN = 1            # candidates handed to one build_script call
AGE_WINDOW_DAYS = 63             # 56-day band + 7 days for the Analytics data lag
ADMISSIBLE_SOURCES = ("hosted", "author", "sandbox")    # the v3-P.1 evidence sources
SEARCH = "YT_SEARCH"


# ------------------------------------------------------------------ coercion
def coerce_question(v) -> str:
    """One question as one line. Raw LLM output is never type-safe: a dict, a list
    or null becomes "", and newlines are collapsed because the value is later put
    into a writer prompt (follow-up) and a one-line log."""
    if isinstance(v, bool) or not isinstance(v, (str, int, float)):
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()[:QUESTION_MAX_CHARS]


def coerce_questions(v) -> list[str]:
    """deliverable._as_list's rule (a string is split on lines, never iterated as
    characters), then each entry coerced like coerce_question."""
    if isinstance(v, str):
        v = v.splitlines() or [v]
    elif not isinstance(v, (list, tuple)):
        return []
    out = []
    for x in v:
        q = coerce_question(x)
        if q and q not in out:
            out.append(q)
    return out[:QUESTIONS_OPEN_MAX]


def norm_query(q) -> str:
    """The canonical query family: case, spaces, hyphens, underscores and dots
    folded away, so "nv-uefi-unlocker" and "nv uefi unlocker" are one entity.
    The raw spellings are kept beside it, never replaced."""
    return re.sub(r"[\s\-_.]+", "", str(q or "").lower())


def entity_of(url) -> str:
    """The canonical tool name of a source URL: the repo (GitHub) or model (HF)."""
    m = re.match(r"https?://(?:github\.com|huggingface\.co)/[\w.-]+/([\w.-]+?)/?$",
                 str(url or "").strip())
    return m.group(1) if m else ""


# ------------------------------------------------------------------ ledger fields
def ledger_fields(script) -> dict:
    """The memory fields the ledger row stores. Computed BEFORE the upload and
    never raising: record_run's keyword arguments are evaluated in the
    double-publish zone."""
    try:
        if not isinstance(script, dict):
            return {}
        out = {"question_answered": coerce_question(script.get("question_answered")),
               "questions_open": coerce_questions(script.get("questions_open")),
               "source_url": str(script.get("source_url") or "")[:300]}
        fu = script.get("followup")
        if isinstance(fu, dict):
            out["followup_parent"] = str(fu.get("parent") or "")[:20]
            out["followup_family"] = str(fu.get("family") or "")[:80]
            out["followup_question"] = coerce_question(fu.get("question"))
        return out
    except Exception as e:  # noqa: BLE001 — never in the double-publish zone
        print(f"   ⚠️ memory fields skipped: {type(e).__name__}: {e}")
        return {}


def followup_of(item) -> dict | None:
    """The script's `followup` dict for a candidate that came from the rule, else
    None. run() owns this key: it is popped in _validate_script and carried."""
    if not isinstance(item, dict) or not item.get("followup_question"):
        return None
    return {"parent": str(item.get("followup_parent") or ""),
            "family": str(item.get("followup_family") or ""),
            "question": coerce_question(item.get("followup_question"))}


def followup_prompt(item) -> str:
    """The ONE writer-prompt line a follow-up candidate adds to script_tool."""
    q = coerce_question(item.get("followup_question")) if isinstance(item, dict) else ""
    if not q:
        return ""
    return (f"FOLLOW-UP: viewers searching for this tool found an earlier {fv.CHANNEL_NAME} "
            f"video that left this question open. Make answering it the video's subject: {q}")


# ------------------------------------------------------------------ API rows
def _cols(resp) -> tuple[list[str], list]:
    if not isinstance(resp, dict):
        return [], []
    heads = [h.get("name") for h in resp.get("columnHeaders") or [] if isinstance(h, dict)]
    rows = [r for r in resp.get("rows") or [] if isinstance(r, list)]
    return heads, rows


def _date(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def search28_by_video(resp) -> dict[str, dict]:
    """{video: {traffic source: views}} from the video x insightTrafficSourceType
    report. The full source mix is kept: it is the record's traffic-source mix."""
    heads, rows = _cols(resp)
    try:
        iv, isrc, iviews = heads.index("video"), heads.index("insightTrafficSourceType"), \
            heads.index("views")
    except ValueError:
        return {}
    out: dict[str, dict] = {}
    for r in rows:
        if len(r) > max(iv, isrc, iviews):
            out.setdefault(str(r[iv]), {})[str(r[isrc])] = int(learn._num(r[iviews]))
    return out


def pick_term_videos(search28: dict, min_views: int = TERMS_MIN_VIDEO_VIEWS,
                     cap: int = TERMS_MAX_VIDEOS) -> list[str]:
    """The only videos whose search terms are worth a query: >= min_views search
    views in the window (half the trigger, so a family split across two videos is
    still seen), most first, at most `cap` (the quota rule)."""
    scored = [(int(learn._num((m or {}).get(SEARCH))), v) for v, m in search28.items()
              if isinstance(m, dict)]
    return [v for n, v in sorted(scored, key=lambda t: (-t[0], t[1])) if n >= min_views][:cap]


def parse_terms(resp) -> list[list]:
    """[[raw search term, views], ...] most first."""
    heads, rows = _cols(resp)
    try:
        it, iviews = heads.index("insightTrafficSourceDetail"), heads.index("views")
    except ValueError:
        return []
    out = [[str(r[it]), int(learn._num(r[iviews]))] for r in rows
           if len(r) > max(it, iviews) and str(r[it]).strip()]
    return sorted(out, key=lambda t: -t[1])


def aggregate_age(resp, published: dict) -> dict[str, dict]:
    """Per video, from the video x day x insightTrafficSourceType report:
      perf:          views + watch minutes over days 1-3 / 1-7 / 1-28 of its life,
                     `complete` once the data reaches that age;
      search_bands:  YT_SEARCH views and OBSERVED days per age band 1-7 / 8-14 /
                     15-28 / 29-56, so a band can be normalised per day.
    Day 1 is the publish date (UTC). `through` is the newest day in the answer —
    the API lags, so it is not today."""
    heads, rows = _cols(resp)
    try:
        iv, iday, isrc = heads.index("video"), heads.index("day"), \
            heads.index("insightTrafficSourceType")
        iviews, imin = heads.index("views"), heads.index("estimatedMinutesWatched")
    except ValueError:
        return {}
    pub = {str(k): d for k, d in published.items() if isinstance(d, dt.date)}
    parsed, through = [], None
    for r in rows:
        if len(r) <= max(iv, iday, isrc, iviews, imin):
            continue
        vid, day = str(r[iv]), _date(r[iday])
        if vid not in pub or day is None:
            continue
        parsed.append((vid, day, str(r[isrc]), learn._num(r[iviews]), learn._num(r[imin])))
        through = day if through is None or day > through else through
    if through is None:
        return {}
    out: dict[str, dict] = {}
    for vid, p in pub.items():
        age_through = (through - p).days + 1
        if age_through < 1:
            continue
        out[vid] = {
            "published": p.isoformat(), "through": through.isoformat(),
            "perf": {n: {"views": 0, "minutes": 0, "complete": age_through >= span}
                     for n, span in PERF_SPANS},
            "search_bands": {f"{lo}-{hi}": [0, max(0, min(hi, age_through) - lo + 1)]
                             for lo, hi in AGE_BANDS}}
    for vid, day, src, views, mins in parsed:
        rec = out.get(vid)
        age = (day - pub[vid]).days + 1
        if rec is None or age < 1:
            continue
        for n, span in PERF_SPANS:
            if age <= span:
                rec["perf"][n]["views"] += int(views)
                rec["perf"][n]["minutes"] += int(mins)
        if src == SEARCH:
            for lo, hi in AGE_BANDS:
                if lo <= age <= hi:
                    rec["search_bands"][f"{lo}-{hi}"][0] += int(views)
    return out


# ------------------------------------------------------------------ snapshot readers
def snapshots(path: Path | None = None) -> list[dict]:
    p = Path(path or learn.ANALYTICS)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict):
            out.append(d)
    return out


def newest(snaps: list[dict], key: str):
    for s in reversed(snaps):
        if isinstance(s.get(key), dict):
            return s[key]
    return None


def age_records(snaps: list[dict]) -> dict[str, dict]:
    """Every video's newest age record. A video that left the 63-day query window
    keeps the last record that had it — by then all four bands were observed."""
    out: dict[str, dict] = {}
    for s in snaps:
        ages = s.get("age_bands")
        if isinstance(ages, dict):
            for vid, rec in ages.items():
                if isinstance(rec, dict):
                    out[str(vid)] = rec
    return out


def tools_index(path: Path | None = None) -> dict[str, dict]:
    """video id -> tools_index entry (source_url, tool) for rows older than M.1's
    `source_url` ledger field."""
    try:
        data = json.loads(Path(path or TOOLS_INDEX).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, list):
        return {}
    return {str(e["video_id"]): e for e in data if isinstance(e, dict) and e.get("video_id")}


# ------------------------------------------------------------------ the follow-up rule
def families(terms_snap) -> dict[str, dict]:
    """canonical family -> {views, raw: [[term, views, video]], parent, name}.
    Views are summed across every video the family reached; the parent is the
    video that took the most of them; `name` is the most-viewed raw spelling."""
    out: dict[str, dict] = {}
    vids = (terms_snap or {}).get("videos") if isinstance(terms_snap, dict) else None
    if not isinstance(vids, dict):
        return {}
    for vid, terms in vids.items():
        if not isinstance(terms, list):
            continue
        for t in terms:
            if not (isinstance(t, list) and len(t) >= 2):
                continue
            fam = norm_query(t[0])
            if not fam:
                continue
            f = out.setdefault(fam, {"views": 0, "raw": [], "by_video": {}})
            n = int(learn._num(t[1]))
            f["views"] += n
            f["raw"].append([str(t[0]), n, str(vid)])
            f["by_video"][str(vid)] = f["by_video"].get(str(vid), 0) + n
    for f in out.values():
        f["parent"] = max(f["by_video"].items(), key=lambda kv: (kv[1], kv[0]))[0]
        f["raw"].sort(key=lambda r: -r[1])
        f["name"] = f["raw"][0][0]
    return out


def _published_rows(rows) -> dict[str, dict]:
    out = {}
    for r in rows:
        vid = learn.video_id(r.get("youtube_url")) if isinstance(r, dict) else None
        if vid and r.get("status") == "PUBLISHED" and vid not in out:
            out[vid] = r
    return out


def last_followup(rows, family: str) -> dt.date | None:
    """Newest PUBLISHED follow-up of this family (the cooldown clock). Read from
    the ledger, so the cooldown needs no state file of its own."""
    last = None
    for r in rows:
        if (isinstance(r, dict) and r.get("status") == "PUBLISHED"
                and norm_query(r.get("followup_family")) == family and family):
            d = learn._date(r.get("publish_at")) or learn._date(r.get("timestamp"))
            if d and (last is None or d > last):
                last = d
    return last


def evidence_probe(item) -> tuple[str, dict | None]:
    """The v3-P.1 seam, called inside a try. ("hosted"|"author"|"sandbox", result)
    when admissible evidence could exist; ("none", result) when the probe answered
    no; ("unknown", None) when the module is missing, raised, or answered None —
    a fail-soft seam's None is "did not work", never "no evidence"."""
    try:
        from factverse import evidence  # v3-P.1; absent on this branch
    except Exception:  # noqa: BLE001
        return "unknown", None
    try:
        res = evidence.probe(item)
    except Exception:  # noqa: BLE001 — the seam promises never to raise; trust nothing
        return "unknown", None
    if not isinstance(res, dict):
        return "unknown", None
    src = str(res.get("source") or "none")
    return (src if src in ADMISSIBLE_SOURCES else "none"), res


def evaluate_followups(rows, terms_snap, today: dt.date, probe=evidence_probe,
                       exempt: dict | None = None, index: dict | None = None) -> list[dict]:
    """Every family at or above the trigger, each with its verdict. Status is one of
    stale_window | no_open_question | no_source | cooldown | evidence_unknown |
    no_evidence | candidate. The checks run cheapest first: the probe (network,
    in P.1) is reached only by a family that cleared everything else."""
    out = []
    if not isinstance(terms_snap, dict):
        return out
    start, end = _date(terms_snap.get("start")), _date(terms_snap.get("end"))
    span_ok = bool(start and end and 1 <= (end - start).days + 1 <= FOLLOWUP_WINDOW_DAYS)
    fresh = bool(end and (today - end).days <= TERMS_STALE_DAYS)
    pub = _published_rows(rows)
    index = index if index is not None else {}
    exempt = exempt or {}
    fams = sorted(families(terms_snap).items(), key=lambda kv: (-kv[1]["views"], kv[0]))
    for fam, f in fams:
        if f["views"] < FOLLOWUP_MIN_VIEWS:
            continue
        ev = {"family": fam, "name": f["name"], "views": f["views"], "raw": f["raw"],
              "parent": f["parent"], "window": [terms_snap.get("start"), terms_snap.get("end")],
              "question": "", "evidence": "", "status": ""}
        out.append(ev)
        if not (span_ok and fresh):
            ev["status"] = "stale_window"      # never lifetime, never an old 28 days
            continue
        row = pub.get(f["parent"]) or {}
        qs = coerce_questions(row.get("questions_open"))
        if not qs:
            ev["status"] = "no_open_question"
            continue
        ev["question"] = qs[0]
        src = str(row.get("source_url") or (index.get(f["parent"]) or {}).get("source_url") or "")
        if not src:
            ev["status"] = "no_source"
            continue
        ev["source_url"] = src
        ev["tool"] = str((index.get(f["parent"]) or {}).get("tool") or entity_of(src) or f["name"])
        last = last_followup(rows, fam)
        reason = exempt.get(fam)
        if (last and (today - last).days < FOLLOWUP_COOLDOWN_DAYS
                and reason not in COOLDOWN_EXEMPT):
            ev["status"] = "cooldown"
            ev["last_followup"] = last.isoformat()
            continue
        if reason in COOLDOWN_EXEMPT:
            ev["exempt"] = reason
        item = {"title": ev["tool"], "url": src, "kind": "tool"}
        label, _ = probe(item)
        ev["evidence"] = label
        if label == "unknown":
            ev["status"] = "evidence_unknown"
        elif label not in ADMISSIBLE_SOURCES:
            ev["status"] = "no_evidence"
        else:
            ev["status"] = "candidate"
    return out


def candidate_item(ev: dict) -> dict:
    """What the tool lane's loop receives. `kind` = tool so the loop takes it;
    the title is the tool, so gates.tool_unsuitable screens the tool, not the
    question."""
    return {"title": str(ev.get("tool") or ev.get("name"))[:120], "url": ev.get("source_url", ""),
            "source": f"{fv.CHANNEL_NAME} follow-up (search demand)", "kind": "tool",
            "fit_score": None, "followup_question": ev.get("question", ""),
            "followup_parent": ev.get("parent", ""), "followup_family": ev.get("family", "")}


def followup_items(today: dt.date | None = None, runs_path: Path | None = None,
                   analytics_path: Path | None = None, probe=evidence_probe) -> list[dict]:
    """build_script's seam: at most FOLLOWUPS_PER_RUN candidate items, else [].
    Kill switch `followup_candidates`. Any failure costs only the candidate."""
    try:
        if not fv.flag("followup_candidates", False):
            return []
        today = today or dt.datetime.utcnow().date()
        rows = learn.read_runs(runs_path)
        terms = newest(snapshots(analytics_path), "search_terms")
        evs = evaluate_followups(rows, terms, today, probe=probe, index=tools_index())
        for ev in evs:
            print(f"  🧠 follow-up family {ev['name']!r}: {ev['views']} search views / 28 d "
                  f"-> {ev['status']}")
        return [candidate_item(ev) for ev in evs if ev["status"] == "candidate"][:FOLLOWUPS_PER_RUN]
    except Exception as e:  # noqa: BLE001 — memory must never cost the day
        print(f"  ⚠️ follow-up candidates skipped: {type(e).__name__}: {e}")
        return []


# ------------------------------------------------------------------ the record
def build_record(row: dict, rows: list[dict], snaps: list[dict], script: dict | None = None,
                 index: dict | None = None, today: dt.date | None = None,
                 evaluations: list[dict] | None = None) -> dict:
    """The round-3 §5 record for one PUBLISHED long-form. Missing data stays
    empty/None — never estimated."""
    vid = learn.video_id(row.get("youtube_url")) or ""
    index = index if index is not None else {}
    ix = index.get(vid) or {}
    src = str(row.get("source_url") or ix.get("source_url") or "")
    ages = age_records(snaps).get(vid) or {}
    metrics = _latest_metrics_from(snaps)     # cumulative since learn.DATA_FLOOR
    terms_snap = newest(snaps, "search_terms") or {}
    raw_terms = ((terms_snap.get("videos") or {}).get(vid)
                 if isinstance(terms_snap.get("videos"), dict) else None) or []
    s28 = newest(snaps, "search28") or {}
    mix = ((s28.get("videos") or {}).get(vid) if isinstance(s28.get("videos"), dict) else None) or {}
    ev_script = (script or {}).get("evidence") if isinstance((script or {}).get("evidence"), dict) else None
    evidence = {}
    if ev_script:
        evidence = {k: ev_script.get(k) for k in ("source", "status", "url", "captured_at",
                                                  "input", "observed", "supported_claims", "rights")}
    elif row.get("evidence_source") or row.get("evidence_status"):
        evidence = {"source": str(row.get("evidence_source") or ""),
                    "status": str(row.get("evidence_status") or "")}
    evs = [e for e in (evaluations or []) if e.get("parent") == vid]
    fams: dict[str, int] = {}
    for t in raw_terms:
        if isinstance(t, list) and len(t) >= 2:
            fams[norm_query(t[0])] = fams.get(norm_query(t[0]), 0) + int(learn._num(t[1]))
    return {
        "identity": {
            "video_id": vid,
            "published_utc": row.get("publish_at") or row.get("timestamp"),
            "format": "long", "lane": row.get("format"),
            "topic_family": row.get("task_family"),
            "canonical_tool": entity_of(src) or None,
            "source_url": src or None,
            "experiment": row.get("experiment"), "pair_id": row.get("pair_id"),
            "arm": row.get("arm"), "slot": row.get("slot"),
            "template_version": row.get("template_version"),
            "title": row.get("title")},
        "viewer_need": {
            "question_answered": coerce_question(row.get("question_answered")) or None,
            "questions_open": coerce_questions(row.get("questions_open")),
            "parent_id": row.get("followup_parent") or None,
            "followup_ids": [learn.video_id(r.get("youtube_url")) for r in rows
                             if isinstance(r, dict) and r.get("status") == "PUBLISHED"
                             and vid and r.get("followup_parent") == vid]},
        "evidence": evidence,
        "delivery": {k: row.get(k) for k in ("duration_s", "first_result_s", "first_step_s",
                                             "answer_s", "opening_gate")},
        "performance": {
            **{n: (ages.get("perf") or {}).get(n) for n, _ in PERF_SPANS},
            "data_through": ages.get("through"),
            "cumulative_since_floor": metrics.get(vid),
            "traffic_sources_28d": mix or None},
        "demand": {
            "search_window": ([terms_snap.get("start"), terms_snap.get("end")]
                              if raw_terms else None),
            "raw_queries": raw_terms,
            "query_families": dict(sorted(fams.items(), key=lambda kv: -kv[1])),
            "search_bands": ages.get("search_bands"),
            "followup": [{k: e.get(k) for k in ("family", "views", "status", "question")}
                         for e in evs]},
    }


def _latest_metrics_from(snaps: list[dict]) -> dict:
    """learn.latest_metrics over already-parsed snapshots (it reads a path)."""
    for snap in reversed(snaps):
        if not snap.get("ledger_videos"):
            continue
        heads = snap.get("ledger_headers") or []
        try:
            iv, iviews, iavd = (heads.index("video"), heads.index("views"),
                                heads.index("averageViewDuration"))
        except (ValueError, AttributeError):
            continue
        imin = heads.index("estimatedMinutesWatched") if "estimatedMinutesWatched" in heads else None
        out = {}
        for r in snap["ledger_videos"]:
            if isinstance(r, list) and len(r) > max(iv, iviews, iavd):
                out[str(r[iv])] = {"views": int(learn._num(r[iviews])),
                                   "avd_s": int(learn._num(r[iavd])),
                                   "minutes": (int(learn._num(r[imin]))
                                               if imin is not None and len(r) > imin else None),
                                   "collected": snap.get("collected")}
        return out
    return {}


def records(n: int = 3, runs_path: Path | None = None, analytics_path: Path | None = None,
            today: dt.date | None = None, ids: list[str] | None = None) -> list[dict]:
    """The records of the last `n` PUBLISHED long-forms, or of the given video ids.
    Display only: a probe is never called here (evidence shows as "unknown")."""
    today = today or dt.date.today()
    rows = learn.read_runs(runs_path)
    snaps = snapshots(analytics_path)
    index = tools_index()
    evs = evaluate_followups(rows, newest(snaps, "search_terms"), today,
                             probe=lambda item: ("unknown", None), index=index)
    pub = [r for r in rows if isinstance(r, dict) and r.get("status") == "PUBLISHED"
           and learn.video_id(r.get("youtube_url"))]
    if ids:
        pub = [r for r in pub if learn.video_id(r.get("youtube_url")) in set(ids)]
    else:
        pub = pub[-n:]
    return [build_record(r, rows, snaps, index=index, today=today, evaluations=evs)
            for r in pub]


def main(argv: list[str]) -> int:
    """`python -m factverse.memory [n | id id ...]`"""
    try:
        if argv and not argv[0].isdigit():
            out = records(ids=argv)
        else:
            out = records(int(argv[0]) if argv else 3)
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ memory records skipped: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
