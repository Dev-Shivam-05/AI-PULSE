# Spec — v3-D: learning loop v1

Status: **locked** (10 decisions, approved with `go` on 2026-09-26).
Module: NEW `factverse/learn.py` (pure — reads state files, never the network), plus a third
query in `factverse/analytics.py` and a widened `gates.pick_hook_pattern`.

## Why this phase exists — and why v1 is mostly measurement

v3-D was queued as "feed runs.jsonl + analytics.jsonl into topic/packaging choices". It was
blocked on ~2 weeks of data counted from 2026-08-24 (the self-view cutoff). By 2026-09-26
there were 33 days of it. Measured before locking, over the real state files:

- **A long-form video gets 1-43 views; the median is ~4.** Channel traffic is Shorts.
  `estimatedMinutesWatched` is an integer, so on a 2-view video `minutes*60/views` is 0 s.
- **11 of the 33 PUBLISHED videos were never measured at all** — the collector keeps only the
  top 25 videos of the last 7 days by views, Shorts crowd that list, and every long-form from
  2026-09-21 onward is missing from every snapshot.
- **The tool lane published 0 videos** in those 33 days despite `"tool_format": true` — the
  pivot has never run unattended. That is a separate problem (see OUT OF SCOPE).
- **The only tunable lever that exists is the news hook pattern** — a strict rotation of 5
  with a 4-wide no-repeat window, i.e. a fixed cycle.

So v1 fixes the measurement, publishes a scoreboard, and installs ONE guarded lever whose
thresholds keep it inert until the data can carry a decision. On the 2026-09-26 data it
drops nothing, by design.

## Locked decisions

| # | Decision | Value |
|---|----------|-------|
| 1 | Measure every ledger video | Third query in `analytics.collect()`: the ids of every `PUBLISHED` `runs.jsonl` row with a `youtube_url` and a timestamp ≥ `2026-08-24` (most recent 200), `filters=video==id1,id2,…`, `dimensions=video`, `startDate=2026-08-24`, `endDate=today`, metrics `views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage`, `maxResults=len(ids)`. Stored in the snapshot as `ledger_videos` + `ledger_headers`. Args are built by the pure `analytics.ledger_query_args`. |
| 2 | That query failing | Its own `try`: the two existing reports are still written; the log says `⚠️ ledger query skipped: <error>`. |
| 3 | When a video counts ("mature") | ≥ **7** days after its `publish_at` date (falls back to the row's `timestamp` date). |
| 4 | Metric per arm | Views-weighted AVD = `Σ(averageViewDuration_s × views) / Σ views` over mature videos with views > 0. The API's per-video seconds, never `minutes*60/views`. |
| 5 | Trusted arm | ≥ **5** mature videos AND ≥ **100** total views. |
| 6 | The one lever | News hook pattern. A pattern is dropped when it is trusted and its weighted AVD < **0.5 ×** the best trusted pattern's. Needs ≥ **2** trusted patterns; never fewer than **3** active. Worst-first. Recomputed every run from the state files — no stored state. |
| 7 | Rotation that survives a drop | `gates.pick_hook_pattern(recent, active=None)`: no repeat within the last `len(active) − 1` picks (5 active → 4, exactly today's behaviour); never returns a dropped pattern. |
| 8 | Scoreboard | `python -m factverse.learn` prints per format and per hook pattern: videos, mature, views, weighted AVD, share of mature videos with AVD ≥ **120 s** (the v3 target), trusted. Also printed by `python -m factverse.analytics` after the snapshot (the CI "Collect channel analytics" step — no workflow change) and written to `output/demo/learn/scoreboard.txt`. |
| 9 | Where the code lives | NEW `factverse/learn.py`; `analytics.py` (+query, `collect(yta=None)` seam); `gates.py`; one call in `ai_pipeline.build_script`; tests in `tests/test_pipeline_logic.py`. |
| 10 | Bad data | Unreadable/malformed `analytics.jsonl` or `runs.jsonl`, a bad row, or any raise inside `learn` → all 5 patterns active and today's rotation runs unchanged. |

Constants live at the top of `factverse/learn.py`: `DATA_FLOOR`, `MATURE_DAYS`, `MIN_VIDEOS`,
`MIN_VIEWS`, `DROP_RATIO`, `MIN_TRUSTED_ARMS`, `MIN_ACTIVE`, `TARGET_AVD_S`, `LEDGER_CAP`.

## OUT OF SCOPE

- Changing format choice (news / evergreen / tool) — the scoreboard reports formats only.
- CTR / impressions (not exposed by the YouTube Analytics API), Shorts measurement,
  IG / FB / X insights.
- Title / thumbnail A/B.
- Why the tool lane never published — proposed as its own row, **v3-B.1: tool-lane
  diagnosis from CI logs**, and it matters more than this phase.

## ACCEPTANCE CRITERIA

- [ ] The ledger query's args come from a pure function; a test asserts the `video==` filter,
      the `2026-08-24` start and the 200 cap.
- [ ] A test proves that when only the new query raises, the snapshot is still written with
      both existing reports.
- [ ] Tests prove the drop rule: nothing dropped below the thresholds of 5-6, a drop at
      < 0.5 ×, never fewer than 3 active, and a dropped pattern is never picked.
- [ ] Tests prove bad data → all 5 active and `pick_hook_pattern` identical to before.
- [ ] The scoreboard runs over the real state files and its output is read.
- [ ] On the 2026-09-26 real data **no pattern is dropped**.
- [ ] Full suite green; committed and pushed on `v3-phase-d`.

## RISKS

- **The new query cannot be exercised live locally** — no YouTube token on this machine.
  Only the args are asserted. The first CI run's line
  `📈 Analytics snapshot saved (… N ledger videos)` is the real check; decision 2 makes a
  wrong filter cost nothing.
- **At current view counts the lever will stay inert for weeks.** Correct for v1: it ships
  the measurement and the guard rails; the thresholds decide when it acts.
- **Self-view cessation cannot be seen in the data.** If it did not stop, every threshold is
  tuned on fake traffic.
- A dropped pattern stops producing new videos, so it can only return if its old videos'
  cumulative numbers move. Accepted for v1.
