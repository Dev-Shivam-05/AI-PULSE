# HANDOFF — ToolDojo — Phases v3-B.3 + v3-G.4 — 2026-10-01

## Done
- **v3-B.3: a day's blocked-fallback chain now stops at 3 attempts.** Before, an "evergreen"
  fallback that `build_script` turned into news could re-run without limit. On 09-29 and 09-30
  the chain was tool blocked → news blocked → news published. Those days would still publish
  under the cap; attempt 4 now prints `🛑 3 attempts today — publishing nothing.`
- **v3-G.4: the long-form renders at 1920×1080.**
  - Verified by a real 305 s render through `step5_build` → `burn_ass` → `add_intro_outro`. The
    output was 1920×1080 and 312.2 s long.
  - Frames were read. The citation chip is 20.7% of the frame width and caption cap height is
    5.1% of the frame height, the same as at 720p. The stat card, code card and outro are
    unclipped.
  - The render takes 2.6× as long locally: 646.7 s vs 249.7 s.
- 263/263 tests pass. Both branches are pushed: `v3-phase-b3` (stacked on b2) and
  `v3-phase-g4` (stacked on b3).
- **Read from main's state:**
  - The v3-D ledger query works live: 29-32 `ledger_videos` in every snapshot since 09-29.
  - The scoreboard has evergreen's weighted AVD at 2:31 against news at 1:03. Evergreen is not
    trusted yet (44 views).
  - The A/B has 1 mature pair, and storyboard lost it.
- **Closed by the owner:** voice-cloning TTS projects stay refused (Now #3).

## Files changed
- `factverse/ai_pipeline.py`:
  - `MAX_DAY_ATTEMPTS = 3`, and `run(attempt=…)` / `_fall_back(…, attempt)`.
  - The `build_ass` call now uses `captions.LAYOUT_W/H` instead of the canvas.
- `factverse/config.py`: `VIDEO_W, VIDEO_H = 1920, 1080`, the one canvas constant.
- `scripts/factverse_engine.py`: `WIDTH`/`HEIGHT` read the canvas constant, and the build log
  line prints the real height.
- `factverse/branding.py`, `factverse/l2.py`: the splice `nv` scale filter reads the canvas
  constant. Left at 1280:720, it would have downscaled the finished video.
- `factverse/captions.py`:
  - `LAYOUT_W/H = 1280, 720` is the PlayRes layout space.
  - The citation chip's drawtext values scale by `VIDEO_H/720`.
- `factverse/screencap.py`: a comment only.
- `tests/test_pipeline_logic.py`: 1 B.3 test (the 09-29 chain) and 4 G.4 tests (canvas, both
  splices, caption layout, chip scale). 2 existing tests were updated for `attempt`.
- `docs/spec/ai-pulse-v3b3.md`, `docs/spec/ai-pulse-v3g4.md`: new specs, with the evidence and
  measurements.
- `docs/PHASES.md`: B.3, G.4 and G.4b rows; Now #1 and #3 closed; Next 3 rewritten.
- `docs/DECISIONS.md`: B.3 and G.4 entries.
- `CLAUDE.md`: 2 traps (caption vs drawtext coordinate systems, and fmt re-binding in the
  fallback chain).

## Decisions made
- **Cap the chain at 3 attempts** (owner). The literal B.1 spec would have published nothing on
  09-29 and 09-30.
- **Only the G.4 canvas changes.** Cards keep their locked 1280×720 layouts and are scaled.
  Re-laying them out would change spec-locked numbers and every measured-text surface.
- **Encoder presets, CRFs and thumbnails are unchanged.** G.4 changes resolution only.

## Known broken / deliberately skipped
- **The music bed was not built.** The code already mixes any `.mp3` in `assets/music`; the
  owner has to supply license-clean tracks.
- **Transitions were not built.** There are no spec values, and they interact with the
  per-scene timing. Both are in the G.4b row.
- **The 1080p CI duration is unmeasured.** The runner has 4 vCPUs against 20 locally, and the
  job timeout is 90 min. The first CI run after the merge is the measurement.
- **Why `pick_evergreen_topic` returned no topic on 09-28..09-30 is unknown.** The CI logs
  answer 403. The near-duplicate screen does reject "how LLMs think" and "agents go rogue"
  re-words against the live used list, so that is plausible, but it is not proven.
- **The outro bumper says "for daily AI news"**, which is off-brand for ToolDojo. It was seen in
  the frames and left alone because it was out of scope.
- **The crop Short (the A/B control) gets a sharper source with G.4** while the experiment is
  running.
- **Untracked files are still untracked:** `output/demo/storyboard/sample/*` and
  `docs/BROWSER_AI_AGENTS_AND_MCP_GUIDE.md`.

## Next session starts here
- **Phase:** none to build. The owner merges `v3-phase-g4`, which carries b2 and b3 with it.
  Then read the first run's ledger row and its Actions duration (the first 1080p CI render).
- **First command:** `/boot`
- **Watch out for:** a run that times out at 90 min after the merge. If it does, the 1080p
  passes are the cause (captions burn 5.7×, bumpers 4.5× locally). The quick fix is one
  constant back to 1280×720, not a rewrite.
