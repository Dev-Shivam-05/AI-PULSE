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
    # v3-D #2: its own try — a bad filter must not cost the two reports above
    try:
        args = ledger_query_args(learn.ledger_ids(learn.read_runs()), today)
        if args:
            led = yta.reports().query(**args).execute()
            snap["ledger_videos"] = led.get("rows", [])
            snap["ledger_headers"] = [h["name"] for h in led.get("columnHeaders", [])]
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ ledger query skipped: {e}")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
