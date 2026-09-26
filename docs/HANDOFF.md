# HANDOFF — ToolDojo — Phase v3-D (learning loop v1) — 2026-09-26

*Spec locked (10 decisions, approved with `go`), built, 228/228 tests, branch `v3-phase-d`
pushed (2 commits, merges cleanly into main).*

## Done

- **Every ledger video now gets measured.** `analytics.collect()` makes a third query for the
  ids of every PUBLISHED long-form in `runs.jsonl` since 2026-08-24 (`video==` filter, cap 200)
  and stores `ledger_videos` + `ledger_headers` in the snapshot. The old top-25 report had
  missed 11 of the first 33 v3 long-forms (Shorts crowd it out). The query has its own `try`:
  if it fails, the two existing reports are still written.
- **A scoreboard exists**: `py -3 -m factverse.learn` prints, per format and per hook pattern,
  videos / mature / views / views-weighted AVD / share ≥ 2:00 / trusted. It also prints in the
  CI "Collect channel analytics" step after every snapshot (no workflow change).
- **One guarded lever**: the news hook rotation drops a trusted pattern whose weighted AVD is
  < 0.5× the best trusted one (≥ 2 trusted needed, ≥ 3 always active, worst first). It is
  recomputed every run, and any failure keeps all five. `gates.pick_hook_pattern` now takes
  `active`, with a `len(active) − 1` window. With all five active it behaves exactly as before
  (tested against the old implementation).
- **Verified**: scoreboard read over the real state files (0 ledger videos yet, so nothing
  dropped) and over an approximation of the real numbers built from the 130 existing snapshots
  (`output/demo/learn/scoreboard_approx.txt`): news 124 views / 0:24 weighted AVD, evergreen
  23 / 0:52, no hook arm trusted, **nothing dropped**, as the spec requires.

## Files changed

- `factverse/learn.py` — NEW: pure join, arms, drop rule, scoreboard; every entry fail-soft
- `factverse/analytics.py` — `ledger_query_args` (pure), `collect(yta=None)` test seam, the
  third query in its own `try`, scoreboard after the snapshot
- `factverse/gates.py` — `pick_hook_pattern(recent, active=None)`, window `len(pool) − 1`
- `factverse/ai_pipeline.py` — the news lane passes `learn.active_hook_patterns()`
- `tests/test_pipeline_logic.py` — +11 tests (217 → 228); one stub signature widened
- `docs/spec/ai-pulse-v3d.md` — NEW contract; `docs/spec/GLOSSARY.md` — 6 terms
- `docs/PHASES.md`, `docs/DECISIONS.md`, `CLAUDE.md` (2 traps), `.gitignore` (per-run
  scoreboard), `output/demo/learn/scoreboard_approx.txt`

## Decisions made

- **v1 measures first, because the data cannot carry a decision yet.** A long-form gets a
  median of ~4 views, and integer watch-minutes read as 0 s. The thresholds keep the lever
  inert until arms are trusted.
- **Ask for the ledger's own ids**, not the top-N. **AVD comes from the API's per-video
  seconds**, not from minutes × 60 / views.
- **No new state file.** The rotation is derived on every run, so the stash list and
  `state_merge.FILES` are untouched.
- **Format choice stays out of the loop**, and the tool-lane diagnosis outranks a loop v2.

## Known broken / deliberately skipped

- **The new query has never run against the real API.** There is no YouTube token locally, so
  only its args are asserted. The first CI analytics line is the real check:
  `📈 Analytics snapshot saved (… N ledger videos)`, with N ≈ 33+. `⚠️ ledger query skipped:`
  means the `video==` filter shape is wrong. That costs nothing, but paste the line into the
  next session.
- **The tool lane published 0 of 33 videos since 2026-08-24** even though `"tool_format": true`
  is set. That is out of scope here, and it is the next phase.
- **The self-view stop cannot be seen in the data.** If it did not happen, every threshold is
  tuned on fake traffic.
- **A dropped pattern produces no new videos**, so it returns only if its old numbers move.
  Accepted for v1.
- `docs/BROWSER_AI_AGENTS_AND_MCP_GUIDE.md` appeared untracked at 21:19 from outside this
  session. I did not touch or commit it. Also note that `docs/` is served verbatim, so a `.md`
  file there is published as raw text.
- Observed today, not changed: Telegram is posting (25 in `notified.json`), Pages answers 200,
  and X / IG / FB have posted nothing (their lists are empty).

## Next session starts here

- Phase v3-B.1: find out, from the CI logs, why the tool lane has never published (`🧰`,
  `⛔ Skipping tool candidate`, `↻`, `No tool script — falling back`). The owner has to open
  the "Auto Publish" run logs or dispatch a supervised `format=tool` run first, because `gh`
  is not installed here.
- First command: `/boot`
- Watch out for: **`tests/test_pipeline_logic.py` is one module, so a helper name is global.**
  A second `def _row` silently broke 16 unrelated notify tests this session. Grep `^def <name>`
  before adding any helper.
