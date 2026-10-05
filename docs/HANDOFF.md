# HANDOFF — ToolDojo — Phase v3-L.3 — 2026-10-05

## Done
- **Radar Live is live-tested on YouTube twice (private).** Both sessions were 10 minutes. Both
  had health Excellent and ended by themselves ("Stream Finished" in Studio).
  - The stream key went from Studio straight into `.env` by script. It was never printed.
- **v3-L.3 built, tested and pushed** on `v3-phase-l3`:
  - The stream connects only after 3 segments are ready (pre-roll). Result: **0 standby** in
    both L.3 sessions. The L.2 code had 3 standbys in its first minute.
  - Narration asks `gemini-3.5-flash-lite` first and is 100-160 words. 12/12 and 12/13
    spotlights were LLM-written; segments run 42-46 s (were ~30 s).
  - A music bed at 0.07 plays under every segment. The local session had 0 silent seconds.
  - The facts row drops its last chip until it fits, so nothing is clipped. Verified with a
    forced 7-chip overflow.
- **ToolDojo channel banner generated:** `E:\YOUTUBE\AI-PULSE\output\brand\banner_tooldojo_2560x1440.png`
  (read as an image). The owner has not uploaded it yet.
- **Tests:** full suite 332/332.

## Files changed
- `scripts/radar_live.py` — pre-roll (`preroll()`), the music bed (`pick_track`, `segment_args`
  with `music`/`music_at`, `Producer._encode` keeps the bed's running time), `MUSIC_DIR`.
- `factverse/radar.py` — narration 100-160 words (gate 70-200), a 1,400-char cap, and
  `NARRATION_MODEL` asked first.
- `assets/radar/radar.html` — the facts row is fitted by measuring, plus `window.__facts()`.
- `tests/test_radar.py` — 9 L.3 tests; `GOOD` lengthened to the new word bounds.
- `.gitignore` — `assets/music/radar/*.mp3` (the owner's ~40 MB of tracks stay local).
- `docs/spec/ai-pulse-v3l3.md` — the locked spec, plus §6 with all the session evidence.
- `docs/PHASES.md` — L.3 row (done), L.4 and L.5 rows queued, Next 3 rewritten.
- `docs/DECISIONS.md` — the L.3 entry.
- `CLAUDE.md` — 2 environment facts (`.env` per checkout, how the stream key was captured).

## Decisions made
- The owner approved the spec-lock table with `go`. The values are in the spec and in
  DECISIONS.
- **Declined: driving the ChatGPT or Gemini web apps from a browser to write scripts.**
  - Both providers' terms forbid it.
  - The Google account is the channel's own account.
  - An unattended stream cannot solve a captcha.
  - The standby problem was start-up timing, not script quality.
- **Dual stream stays OFF until L.4.** YouTube's auto-crop cuts the card in half.
- **The shared `llm._FALLBACK_MODELS` was not touched.** It belongs to the daily pipeline and
  to the unmerged `v3-gemini-fallback` branch.

## Known broken / deliberately skipped
- **Input lags at segment seams (0.3-1.6 s, 37 in 10 min)** — not fixed, because it predates
  L.3: the L.2 code showed the same lines on YouTube. Health stayed Excellent.
  - Unverified hypothesis: the main thread's `remux()` of the next segment starves the writer.
  - Measure it before changing anything (spec v3l3 §6).
- **Fewer facts chips per card** — on purpose. The 700 px card column flex-shrinks the facts
  box to one row, and the locked layout was kept.
- **The schedule is not installed, and the stream is not Public** — that is the owner's decision.
- **L.4 (vertical) and L.5 (Telegram live link)** — queued, not built.
- **Still untracked in `E:\YOUTUBE\AI-PULSE`:** `output/demo/storyboard/sample/*` and
  `docs/BROWSER_AI_AGENTS_AND_MCP_GUIDE.md`. Not touched.

## Owner update (2026-10-05, after this session)
- `v3-phase-l3` is **merged** (PR #38, verified on `origin/main`).
- The owner reports the live stream's Studio visibility is **Public**. Claude did not verify it.
- **Still left:** upload the banner, install the daily schedule. Neither is done.

## Next session starts here
- **Phase:** finish the L.3 rollout, then build v3-L.5.
  1. Banner: the file is `E:\YOUTUBE\AI-PULSE\outputrandanner_tooldojo_2560x1440.png`.
     Owner path: Studio → Customization → Branding → Banner image.
  2. Schedule: `powershell -File scripts/radar_schedule.ps1 -Install`, run from a checkout
     that is on **updated main**. Read the script first to see which path the task launches.
  3. v3-L.5: post `youtube.com/@tooldojo/live` to the Telegram group 60 s after the stream
     connects. Needs a spec-lock first.
- **First command:** `/boot`
- **Watch out for:** `E:\YOUTUBE\AI-PULSE` is checked out on `v3-gemini-fallback`, which does
  NOT have the L.3 code. A schedule launched from there streams the L.2 code, publicly, every
  day (3 standbys at the start, no music, short narration). Put that checkout on updated
  main, or point the task at one that is, before installing.
  - It must keep its `.env` and `assets/music/radar/`: both are gitignored and already there.
  - Its uncommitted and untracked files belong to another session. Do not discard them;
    commit first if switching branches.
