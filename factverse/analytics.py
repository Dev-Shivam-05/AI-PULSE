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


def collect(yta=None) -> dict:
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
