"""
Nightly channel-analytics collector — the learning loop's data source.

Pulls channel-level and per-video performance from the YouTube Analytics API
(using the same OAuth token as the uploader; requires the yt-analytics.readonly
scope, which the auth flow requests) and appends one JSON line per run to
state/analytics.jsonl.

Downstream this joins with state/runs.jsonl (which records each video's format,
title, word count, and viral score) so packaging and topic selection can be
tuned from real CTR/retention instead of guesses.

Failures are NEVER fatal — analytics must not break a publish run.

Run:  python -m factverse.analytics
"""
from __future__ import annotations

import datetime as dt
import json
import pickle
import sys

from factverse import config as fv
from factverse import learn

OUT = fv.STATE / "analytics.jsonl"


def _creds():
    tok = fv.BASE / "youtube_token.pickle"
    if not tok.exists():
        raise RuntimeError("youtube_token.pickle missing")
    with open(tok, "rb") as f:
        creds = pickle.load(f)
    if creds and creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
    return creds


def ledger_query_args(ids: list[str], today: dt.date) -> dict | None:
    """v3-D #1: per-video numbers for every ledger video, cumulative from the
    self-view cutoff. The top-25 report above is crowded out by Shorts, which
    left 11 of the first 33 v3 long-forms unmeasured."""
    ids = [i for i in ids if i][-learn.LEDGER_CAP:]
    if not ids:
        return None
    return dict(ids="channel==MINE", startDate=learn.DATA_FLOOR, endDate=today.isoformat(),
                dimensions="video", filters="video==" + ",".join(ids),
                metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage",
                sort="-views", maxResults=len(ids))


# ------------------------------------------------------------------ v3-M.1
# Query shapes verified 2026-11-04 against the official reference:
#   https://developers.google.com/youtube/analytics/dimensions
#     creatorContentType values: LIVE_STREAM, SHORTS, STORY, VIDEO_ON_DEMAND, UNSPECIFIED
#   https://developers.google.com/youtube/analytics/channel_reports
#     "Traffic source detail": dimension insightTrafficSourceDetail, filter
#     insightTrafficSourceType required, 0 or 1 video filter, sort -views or
#     -estimatedMinutesWatched, maxResults <= 25 REQUIRED.
#     "Traffic source": dimension insightTrafficSourceType (+ day); a video filter
#     with several ids may also be added as a dimension; videos x days <= 50,000.
#     "Top videos": video (+ creatorContentType), sort + maxResults <= 200 required.
#   creatorContentType is a DIMENSION in every report, never a filter.
WINDOW_DAYS = 28            # the north star and the follow-up rule: rolling 28 days
TERMS_MAX_RESULTS = 25      # the report's own maximum
TOP_MAX_RESULTS = 200       # the top-videos report's own maximum
VIDEOS_X_DAYS_MAX = 50000   # the traffic-source report's own limit


def window_28(today: dt.date) -> tuple[str, str]:
    """The 28 days ending YESTERDAY, inclusive — how the 12.11 h baseline was read
    (Oct 7 - Nov 3, read on Nov 4)."""
    end = today - dt.timedelta(days=1)
    return (end - dt.timedelta(days=WINDOW_DAYS - 1)).isoformat(), end.isoformat()


def content_type_args(start: str, end: str) -> dict:
    return dict(ids="channel==MINE", startDate=start, endDate=end,
                dimensions="creatorContentType", metrics="estimatedMinutesWatched,views")


def vod_top_args(start: str, end: str) -> dict:
    """Per-video 28-day watch time, for the largest-video share. Content type is a
    dimension here (it is not a filter anywhere), so VIDEO_ON_DEMAND is kept
    client-side."""
    return dict(ids="channel==MINE", startDate=start, endDate=end,
                dimensions="video,creatorContentType", metrics="estimatedMinutesWatched",
                sort="-estimatedMinutesWatched", maxResults=TOP_MAX_RESULTS)


def search_by_video_args(ids: list[str], start: str, end: str) -> dict | None:
    """28-day views per (video, traffic source) for the ledger's long-forms: ONE
    query that says which videos are worth a search-terms query."""
    ids = [i for i in ids if i][-learn.LEDGER_CAP:]
    if not ids:
        return None
    return dict(ids="channel==MINE", startDate=start, endDate=end,
                dimensions="video,insightTrafficSourceType",
                filters="video==" + ",".join(ids), metrics="views")


def search_terms_args(video: str, start: str, end: str) -> dict:
    """The raw YouTube-search terms of ONE video over the 28-day window."""
    return dict(ids="channel==MINE", startDate=start, endDate=end,
                dimensions="insightTrafficSourceDetail",
                filters=f"video=={video};insightTrafficSourceType==YT_SEARCH",
                metrics="views", sort="-views", maxResults=TERMS_MAX_RESULTS)


def age_args(videos: list[dict], today: dt.date,
             window_days: int | None = None) -> tuple[dict | None, dict]:
    """(args, {video: publish date}) for the per-day report behind the 72h/7d/28d
    snapshots and the search-longevity bands: long-forms published in the last
    `window_days`, from the oldest one's publish day to today."""
    from factverse import memory
    window_days = window_days or memory.AGE_WINDOW_DAYS
    floor = today - dt.timedelta(days=window_days)
    pub = {v["id"]: v["published"] for v in videos
           if isinstance(v.get("published"), dt.date) and floor <= v["published"] <= today}
    if not pub:
        return None, {}
    start = min(pub.values())
    if len(pub) * ((today - start).days + 1) > VIDEOS_X_DAYS_MAX:
        return None, {}
    return dict(ids="channel==MINE", startDate=start.isoformat(), endDate=today.isoformat(),
                dimensions="video,day,insightTrafficSourceType",
                filters="video==" + ",".join(pub), metrics="views,estimatedMinutesWatched"), pub


def _types(resp) -> dict:
    """{creatorContentType: {"minutes", "views"}} from the content-type report."""
    from factverse import memory
    heads, rows = memory._cols(resp)
    try:
        it, imin, iviews = (heads.index("creatorContentType"),
                            heads.index("estimatedMinutesWatched"), heads.index("views"))
    except ValueError:
        return {}
    return {str(r[it]): {"minutes": int(learn._num(r[imin])), "views": int(learn._num(r[iviews]))}
            for r in rows if len(r) > max(it, imin, iviews)}


def _vod_top(resp) -> list[list]:
    from factverse import memory
    heads, rows = memory._cols(resp)
    try:
        iv, it, imin = (heads.index("video"), heads.index("creatorContentType"),
                        heads.index("estimatedMinutesWatched"))
    except ValueError:
        return []
    return [[str(r[iv]), int(learn._num(r[imin]))] for r in rows
            if len(r) > max(iv, it, imin) and str(r[it]) == "VIDEO_ON_DEMAND"]


def collect_m1(yta, today: dt.date, rows: list[dict]) -> dict:
    """The v3-M.1 additions to a snapshot. Every query has its own try: a bad one
    costs only its own key, never the reports beside it."""
    from factverse import memory
    out: dict = {}
    start, end = window_28(today)
    if fv.flag("north_star", False):
        try:
            types = _types(yta.reports().query(**content_type_args(start, end)).execute())
            out["north_star"] = {"start": start, "end": end, "by_type": types}
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ north-star query skipped: {e}")
        try:
            out["vod_top"] = {"start": start, "end": end, "videos": _vod_top(
                yta.reports().query(**vod_top_args(start, end)).execute())}
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ largest-video query skipped: {e}")
    if fv.flag("memory_analytics", False):
        videos = learn.ledger_videos(rows)
        try:
            args = search_by_video_args([v["id"] for v in videos], start, end)
            if args:
                s28 = memory.search28_by_video(yta.reports().query(**args).execute())
                out["search28"] = {"start": start, "end": end, "videos": s28}
                terms = {}
                for vid in memory.pick_term_videos(s28):
                    try:
                        terms[vid] = memory.parse_terms(
                            yta.reports().query(**search_terms_args(vid, start, end)).execute())
                    except Exception as e:  # noqa: BLE001 — one video costs only itself
                        print(f"  ⚠️ search terms for {vid} skipped: {e}")
                out["search_terms"] = {"start": start, "end": end, "videos": terms}
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ search-by-video query skipped: {e}")
        try:
            args, pub = age_args(videos, today)
            if args:
                out["age_bands"] = memory.aggregate_age(yta.reports().query(**args).execute(), pub)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ age-band query skipped: {e}")
    return out


# v3-G.3 #10-11: impressions and thumbnail CTR exist ONLY in the YouTube Reporting
# API (bulk CSV reports), never in the Analytics API queries above.
REACH_TYPE = "channel_reach_basic_a1"
REACH_JOB_NAME = "tooldojo-reach"
REACH_CAP = 35          # reports downloaded per run (the backfill is 30 days)
REACH_HEADERS = ["date", "video_id", "video_thumbnail_impressions",
                 "video_thumbnail_impressions_ctr"]


def _download_report(ytr, url: str) -> bytes:
    """The Reporting API's own download recipe (youtube/api-samples
    retrieve_reports.py): a media request whose uri is the report's downloadUrl."""
    import io
    from googleapiclient.http import MediaIoBaseDownload
    req = ytr.media().download(resourceName=" ")
    req.uri = url
    fh = io.BytesIO()
    dl = MediaIoBaseDownload(fh, req, chunksize=-1)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return fh.getvalue()


def parse_reach_csv(text: str, ids: set) -> list[list]:
    """[[date, video_id, impressions, ctr], ...] for the ledger's videos only.
    CTR is kept exactly as the CSV states it — its scale is not documented."""
    import csv
    import io
    import math
    reader = csv.DictReader(io.StringIO(text))
    cols = set(reader.fieldnames or [])
    missing = [c for c in REACH_HEADERS if c not in cols]
    if missing:
        raise ValueError(f"CSV has no {', '.join(missing)} column")
    out = []
    for r in reader:
        vid = str(r.get("video_id") or "").strip()
        if vid not in ids:
            continue
        day = str(r.get("date") or "").strip()
        if len(day) == 8 and day.isdigit():          # the CSV writes 20261008
            day = f"{day[:4]}-{day[4:6]}-{day[6:]}"
        try:
            ctr = float(r["video_thumbnail_impressions_ctr"])
        except (TypeError, ValueError):
            continue
        if not math.isfinite(ctr):
            continue
        out.append([day, vid, int(learn._num(r.get("video_thumbnail_impressions"))), ctr])
    return out


def collect_reach(ytr=None) -> dict | None:
    """{reach_headers, reach_rows} from the reports not yet stored, or None.
    Fail-soft: any error is one log line and costs only this report."""
    try:
        if ytr is None:
            from googleapiclient.discovery import build
            ytr = build("youtubereporting", "v1", credentials=_creds())
        jobs = ytr.jobs().list().execute().get("jobs") or []
        job = next((j for j in jobs if isinstance(j, dict)
                    and j.get("reportTypeId") == REACH_TYPE), None)
        if job is None:
            job = ytr.jobs().create(body={"reportTypeId": REACH_TYPE,
                                          "name": REACH_JOB_NAME}).execute()
            print(f"  ↷ reach report: job created ({job.get('id')}) — "
                  f"the first report arrives within 48 h")
        reports, token = [], None
        while True:
            kw = {"jobId": job["id"]}
            if token:
                kw["pageToken"] = token
            page = ytr.jobs().reports().list(**kw).execute()
            reports += [r for r in page.get("reports") or [] if isinstance(r, dict)]
            token = page.get("nextPageToken")
            if not token:
                break
        # "Already stored" = a date that has reach rows in an earlier snapshot. Read
        # from the snapshots themselves: no second state file to stash and merge.
        stored = {d for d, _ in learn.reach_metrics(OUT)}
        ids = set(learn.ledger_ids(learn.read_runs()))
        todo, seen = [], set()
        # newest day first, and the newest-created report for a regenerated day
        for r in sorted(reports, key=lambda r: (str(r.get("startTime", "")),
                                                str(r.get("createTime", ""))), reverse=True):
            day = str(r.get("startTime", ""))[:10]
            if not day or day in stored or day in seen or not r.get("downloadUrl"):
                continue
            seen.add(day)
            todo.append(r)
        todo = todo[:REACH_CAP]
        rows = []
        for r in todo:
            try:
                rows += parse_reach_csv(
                    _download_report(ytr, r["downloadUrl"]).decode("utf-8-sig"), ids)
            except Exception as e:  # noqa: BLE001 — one bad report costs only itself
                print(f"  ↷ reach report: {str(r.get('startTime', ''))[:10]} skipped "
                      f"({type(e).__name__}: {e})")
        print(f"  📡 reach report: {len(todo)} new report(s) of {len(reports)}, "
              f"{len(rows)} ledger row(s)")
        return {"reach_headers": list(REACH_HEADERS), "reach_rows": rows}
    except Exception as e:  # noqa: BLE001 — never touches the other reports
        print(f"  ↷ reach report: {type(e).__name__}: {e}")
        return None


def collect(yta=None, ytr=None) -> dict:
    if yta is None:
        from googleapiclient.discovery import build
        yta = build("youtubeAnalytics", "v2", credentials=_creds())
    today = dt.date.today()
    start28 = (today - dt.timedelta(days=28)).isoformat()
    start7 = (today - dt.timedelta(days=7)).isoformat()
    end = today.isoformat()

    channel = yta.reports().query(
        ids="channel==MINE", startDate=start28, endDate=end, dimensions="day",
        metrics=("views,estimatedMinutesWatched,averageViewDuration,"
                 "averageViewPercentage,subscribersGained,likes,comments"),
    ).execute()

    videos = yta.reports().query(
        ids="channel==MINE", startDate=start7, endDate=end, dimensions="video",
        metrics="views,estimatedMinutesWatched,averageViewPercentage",
        sort="-views", maxResults=25,
    ).execute()

    snap = {
        "collected": dt.datetime.now().isoformat(timespec="seconds"),
        "channel_days": channel.get("rows", []),
        "channel_headers": [h["name"] for h in channel.get("columnHeaders", [])],
        "top_videos_7d": videos.get("rows", []),
        "video_headers": [h["name"] for h in videos.get("columnHeaders", [])],
    }
    # v3-M.1: north star, search terms, age bands. Each query has its own try
    # inside; the outer one guards the ledger read. Runs BEFORE the ledger query.
    try:
        snap.update(collect_m1(yta, today, learn.read_runs()))
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ v3-M.1 queries skipped: {e}")
    # v3-D #2: its own try — a bad filter must not cost the two reports above
    try:
        args = ledger_query_args(learn.ledger_ids(learn.read_runs()), today)
        if args:
            led = yta.reports().query(**args).execute()
            snap["ledger_videos"] = led.get("rows", [])
            snap["ledger_headers"] = [h["name"] for h in led.get("columnHeaders", [])]
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ ledger query skipped: {e}")
    # v3-P.2: Pilot A per-video retention at publication age 7 / 14 / 28 (the
    # audience-retention report, video==ONE id). Own try + kill switch: a refused
    # report must cost only the pilot reads, never the snapshot.
    if fv.flag("pilot_retention", False):
        try:
            from factverse import pilot
            prior = []
            if OUT.exists():
                for line in OUT.read_text(encoding="utf-8").splitlines():
                    try:
                        prior.append(json.loads(line))
                    except ValueError:
                        continue
            reads = pilot.collect_reads(yta, learn.read_runs(), prior, today)
            if reads:
                snap["pilot_reads"] = reads
                print(f"  🧪 Pilot A: {len(reads)} retention read(s)")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ pilot reads skipped: {e}")
    # v3-G.3 #10: impressions + CTR; its own seam, kill switch `reach_report`
    if fv.flag("reach_report", False):
        reach = collect_reach(ytr)
        if reach:
            snap.update(reach)
    return snap


def main() -> int:
    try:
        snap = collect()
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(snap, ensure_ascii=False) + "\n")
        days = len(snap["channel_days"])
        print(f"  📈 Analytics snapshot saved ({days} day rows, "
              f"{len(snap['top_videos_7d'])} videos, "
              f"{len(snap.get('ledger_videos', []))} ledger videos)")
    except Exception as e:
        # never fail the pipeline over analytics
        print(f"  ⚠️ analytics skipped: {e}")
    learn.main()  # the v3-D scoreboard in the CI log; fail-soft, always 0
    if fv.flag("pilot_retention", False):
        try:
            from factverse import pilot
            pilot.main([])          # the Pilot A readout in the CI log; never raises
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ pilot readout skipped: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
