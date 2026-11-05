# HANDOFF — ToolDojo — Phase v3-T.1 Live Trials — 2026-11-05

## Done
- **`v3-growth-1104` now carries everything, T.1 included.** The owner opens ONE PR from it: https://github.com/Dev-Shivam-05/AI-PULSE/compare/main...v3-growth-1104?expand=1
  - It contains `v3-integration-1101` (B.5, L.6), P.1, P.2, S.1, M.1, K.1, N.1 and T.1, so the 11-01 PR is superseded.
  - Suite: **787 passed** on the T.1 tree.
  - A read-only `git merge-tree` against `origin/main` is clean.
- **Live Trials runs a real 12-minute episode, end to end, against a local RTMP listener.** Nothing reached YouTube.
  - Airtime 720 s exactly: 13/13 windows, 0 holds, 0 restarts, exit 0, 0 decode errors at 1080×1920.
  - Whole show −23.5 LUFS, peak −3.9 dBFS.
  - It hit a real TIMEOUT on test 3 and aired the correct branch: "6/8 CHECKS PASSED; ONE TIMED OUT".
  - The results sheet reads correctly at 390 px, with no sideways scroll.
- **All four result branches render through the real segment path,** and their frames were read. PARTIAL/FAIL and INCONCLUSIVE were rendered, not aired.
- **Six defects were found by reading frames, then fixed and test-pinned.** All six are listed in `docs/spec/ai-pulse-v3t1.md` § Verification. The two viewers would notice most:
  - results were on screen before the replay that "revealed" them;
  - a 10 s hold card aired at 1:30 in every episode.
- **The show is shipped switched off:** `trials_live: false`, and the node row `enabled: false`.

## Files changed
- `assets/trials/trials.html` — check values and the running score stay hidden until their moment; fonts load before the first fit; fit measures every state while visible.
- `scripts/trials_live.py` — `frame_times` draws only the moments the page can change (this removed the hold); `pending` row text; `top_score_at`; `verdict_cls`.
- `scripts/radar_live.py` — `Renderer.frames` accepts a caller's `spec["times"]`; Radar's own behaviour is unchanged.
- `factverse/trials.py` — sheet wording: reason capitalised, and no upload-to-result time on a run with no result.
- `tests/test_t1_trials.py` — 7 new tests.
- `config.json`, `config.example.json` — merge conflict resolved: N.1's node block wins, plus T.1's `trials_live` and the `live_trials` pulse file.
- `docs/spec/ai-pulse-v3t1.md` — Verification filled in, the T.1b proposal, new known limits.
- `docs/PHASES.md`, `docs/DECISIONS.md`, `CLAUDE.md`, this file.

## Decisions made
- **The grid stays as the owner locked it.** The still-time fix has new values, so it became a proposal (v3-T.1b), not part of this phase.
- **`repeat_choice` keeps R3's wording:** it repeats the first PARTIAL/FAIL, else the control. Repeating a timed-out clip is an owner question.
- **WER threshold stays at the 0.15 default** until the owner gives a word.

## Known broken / deliberately skipped
- **The show is stable but mostly still (v3-T.1b, needs the owner's word).** Measured on the PASS narration: 182 s of voice in 720 s (25%), and 401 s in stretches of 15 s+ where nothing on screen changes. Each run window ends on 49-60 s of one static frame, and the viewer never hears a clip. This is likely to hurt the L11 retention target. Do it before `trials_live` goes on.
- **Never run:** a YouTube stream, the real node (i3 render headroom is unmeasured; only the 720×1280 encode was checked), the LLM narration, the published-sheet path (Contents API), and the test-incomplete ending on air.
- **561 kbps received bitrate** on these static pages. Whether YouTube warns about it is unknown until the private rehearsal.
- **Two fixture sets = two episodes.** The third show is refused until a new set is committed. Every completed test so far has passed, so the fixtures may be too easy.
- **Carried over, still true:**
  - Never exercised live: the LLM writer on the new prompts, all 5 new Analytics API queries, the opening repair against the real model, Kokoro timings, the node on real hardware.
  - Not built: the "before you install" verdict, the source (b) sandbox, Radar Challenger (K.2), the second upload slot, "documented requirement changed" alerts.
  - Evidence supply is thin (3 of 27 candidates), so the tool lane will mostly fall back.
  - Studio CSV column names for Pilot B are unverified until the first export on D+8.
  - The 2026-11-04 delegated values in the phase specs are unconfirmed by the owner.
- **The Studio login profile, which holds cookies, is still in a scratchpad:** `C:\Users\shiva\AppData\Local\Temp\claude\e--YOUTUBE-AI-PULSE\01a5917a-a008-4b2c-b488-d75f3ce6ed07\scratchpad\yt-studio-profile`. Delete it if it is not needed.
- **Disk: E: has 2.5 GB free (96% used).** This session left 98 MB in `AI-PULSE-t1/output/trials/verify` and 611 MB in `AI-PULSE-t1/temp/trials`. Both are gitignored and were not deleted.
- **Leftover worktrees:** `E:/YOUTUBE/AI-PULSE-{gw,p1,p2,s1,m1,k1,n1,t1,b4,b5,g3,g4b,gf,int,int1101,l3,l6,live,wt-main}`. Remove them after the merge with `git worktree remove <path>`, never `--force`.
- **The main checkout `E:\YOUTUBE\AI-PULSE` is still on the stale `v3-gemini-fallback`,** with 10-01 docs. Its untracked `docs/debate/`, `prompts/`, `assets/music/` and `output/*` were left alone.

## Next session starts here
- Phase v3-T.1b: fill the show's still time, only after the owner approves the table in `docs/spec/ai-pulse-v3t1.md`. Owner steps first: open the ONE PR and answer the one-word list in `docs/PHASES.md` § Next 3 item 1.
- First command: `/boot`, run from `E:\YOUTUBE\AI-PULSE-gw` until the PR is merged.
- Watch out for: `/boot` in the main checkout reads stale docs. It is on an old branch whose handoff is from 10-01, so it reported no phase to build.
