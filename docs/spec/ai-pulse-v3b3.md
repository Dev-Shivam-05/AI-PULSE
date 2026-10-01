# Spec — v3-B.3: the blocked-day fallback chain is bounded

Status: **locked** (owner picked "Cap at 3 attempts", 2026-10-01).

## Why this phase exists

B.1 decision 2 says a fallback drops to evergreen **one level only**. The ledger shows the chain
going deeper than that. Measured from `state/runs.jsonl` on origin/main:

| Date | Attempt 1 | Attempt 2 | Attempt 3 |
|------|-----------|-----------|-----------|
| 09-28 | tool `FACTCHECK_BLOCKED` | evergreen request → news `PUBLISHED` | — |
| 09-29 | tool `FACTCHECK_BLOCKED` | evergreen request → news `FACTCHECK_BLOCKED` | evergreen request → news `PUBLISHED` |
| 09-30 | tool `FACTCHECK_BLOCKED` | evergreen request → news `FACTCHECK_BLOCKED` | evergreen request → news `PUBLISHED` |

The mechanism (`factverse/ai_pipeline.py`):

- `build_script("evergreen")` falls through to news when `pick_evergreen_topic` returns no topic.
- `run()` re-binds `fmt` to the script's own format (correct, so the ledger is honest), which
  makes the evergreen fallback look like news to `_fallback_format`.
- `_fallback_format(fmt="news", fallback=True)` answers `"evergreen"`, so the chain runs again.
  Each block marks only its own story failed (`too_many_failures` needs 2), so nothing bounds
  the chain except the 90-minute CI kill. A kill mid-chain costs the day; a kill in the
  post-upload zone is the double-publish window.

## Locked decisions

| # | Decision | Value |
|---|----------|-------|
| 1 | The cap | **At most 3 script attempts per day in one chain** (`MAX_DAY_ATTEMPTS = 3`), the longest chain observed. 09-28, 09-29 and 09-30 all publish exactly as they did. |
| 2 | How it is counted | `run()` takes `attempt` (1 for the cron or a dispatch). `_fall_back` re-runs with `attempt + 1` and returns `None` once `attempt` has reached the cap, printing `🛑 3 attempts today — publishing nothing.` |
| 3 | What does not change | `_fallback_format`'s truth table, the owner-forced rule (no fallback), and `build_script`'s own evergreen → news fall-through. The cap bounds the chain; it does not reorder it. |

## Done when

1. A test drives `_fall_back` through the 09-29 shape (tool → news → news) and shows attempt 3
   blocked returns `None` without calling `run` again.
2. Attempts 1 and 2 still recurse with `attempt` 2 and 3.
3. The full suite passes.
