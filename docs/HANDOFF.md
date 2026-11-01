# HANDOFF — ToolDojo — Phases v3-B.5 + v3-L.6 — 2026-11-01

## Done
- **One branch carries everything: `v3-integration-1101`.** It merges `v3-phase-b5` and
  `v3-phase-l6` plus the docs. The two phase branches are also pushed on their own.
- **Background.** The morning session ran the ChatGPT review
  (`docs/debate/2026-11-01-radar-live-growth-review/RESULT.md`); the owner answered "go for
  all". It built L.6 itself and B.5 through a subagent, then ended before committing anything:
  no commit, no spec, no board row. This session committed that work unchanged as `wip:`
  commits, then tested, fixed, verified and documented it.
- **v3-B.5: daily lane mix + no-loop recordings.**
  - Automatic runs: Mon/Tue/Thu/Fri tool (else evergreen), Wed debate, Sat evergreen, Sun
    roundup. News only replaces a slot, at most once per ISO week. Kill switch `lane_mix_v2`.
  - Evergreen subject screen: on the real ledger all 8 named LLM/hardware repeats are caught.
  - Recordings browse README → releases → issues → commits, scroll down only, and are recut
    after the narration timings. Real recut on removemacai: 6 pieces at their exact shares,
    **0 loops**, frames read.
  - Fixed: 2 older tests went red because the new screen reads the real ledger.
  - **426/426.**
- **v3-L.6: Radar Live viewer + inventory.**
  - A local 5-min session was received and read: **445 tools** (was ≤ 100), 8 segments,
    0 standby, 316 s, 0 decode errors, **−19.8 LUFS / −4.8 dBTP**.
  - Frames read: two source boards, NEXT cue, subscribe line at 166 s, true end card.
  - 3 defects found and fixed: label wording, subscribe line wording, and two text-overflow
    bugs seen only in rendered frames (the line under SOURCE DELAYED, a benefit line cut
    mid-word).
  - **419/419.**

## Files changed
- B.5: `factverse/screencap.py`, `factverse/ai_pipeline.py`, `config.json`,
  `config.example.json`, `tests/test_b5_daily.py` (new), `tests/test_pipeline_logic.py`,
  `docs/spec/ai-pulse-v3b5.md` (new).
- L.6: `factverse/radar.py`, `scripts/radar_live.py`, `assets/radar/radar.html`,
  `requirements.txt` + `requirements-ci.txt` (edge-tts ≥ 7.3.1; 7.2.8 answered 403),
  `tests/test_l6_radar.py` (new), `tests/test_radar.py`, `docs/spec/ai-pulse-v3l6.md` (new).
- Docs: `docs/PHASES.md` (B.5, L.6 rows; L.7, L.8, L.9 queued; Next 3), `docs/DECISIONS.md`,
  `CLAUDE.md` (1 trap: a picker reading the real ledger).

## Decisions made
- The owner delegated the review's open choices ("whatever you think will be best"). They are
  recorded in DECISIONS (2026-11-01).
- Agreed wording is used verbatim. When it did not fit the slot, the slot changed, not the words.
- A recording holds its last frame rather than loop.
- `UPDATED` is not built: nothing in the data can verify a change, and the review gives no
  threshold.
- One integration branch, so the owner opens one PR.

## Known broken / deliberately skipped
- **A short README is ~69% held frame** in a tool video (68.7 s of recording for 302.5 s of
  slots). It no longer loops, but it is static. The fix needs a decision: more pages, other
  footage, or fewer recording slots.
- **L.7 (CI broadcast + analytics), L.8 (seam lags + ramp) and L.9 (show wheel) are not
  built.** Each is its own phase. L.6 already reads the manifest L.7 will write.
- The end card's pill still says "Subscribe to ToolDojo for practical AI tools". Review point 8
  fixed the wording of the on-stream line only.
- The pre-existing L.3 seam lags are untouched; they are L.8's first job.
- **Leftover worktrees:** `E:/YOUTUBE/AI-PULSE-{b4,b5,g3,g4b,gf,int,int1101,l3,l6,live,wt-main}`.
  Remove them after the merge with `git worktree remove <path>`, never `--force`.
- **`E:\YOUTUBE\AI-PULSE` is still on the stale `v3-gemini-fallback` branch.** Its untracked
  `docs/debate/`, `prompts/`, `assets/music/radar/` and `output/*` files were left alone; the
  review folder is not committed.

## Next session starts here
- **Phase:** v3-L.7, after the owner merges
  https://github.com/Dev-Shivam-05/AI-PULSE/compare/main...v3-integration-1101?expand=1.
- **First command:** `/boot`. Then read the first post-merge run's log for `🧰 Tool day` /
  `🗓️` lines and confirm there is NO `⚠️ recording recut failed`.
- **Watch out for:** L.7 adds a workflow and `state/live_broadcast.json`, so the
  both-halves trap applies: the stash list AND `state_merge.FILES`. Check the granted OAuth
  scope before building the insert/bind calls.
