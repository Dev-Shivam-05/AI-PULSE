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


def collect() -> dict:
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

    return {
        "collected": dt.datetime.now().isoformat(timespec="seconds"),
        "channel_days": channel.get("rows", []),
        "channel_headers": [h["name"] for h in channel.get("columnHeaders", [])],
        "top_videos_7d": videos.get("rows", []),
        "video_headers": [h["name"] for h in videos.get("columnHeaders", [])],
    }


def main() -> int:
    try:
        snap = collect()
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(snap, ensure_ascii=False) + "\n")
        days = len(snap["channel_days"])
        print(f"  📈 Analytics snapshot saved ({days} day rows, "
              f"{len(snap['top_videos_7d'])} videos)")
    except Exception as e:
        # never fail the pipeline over analytics
        print(f"  ⚠️ analytics skipped: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
