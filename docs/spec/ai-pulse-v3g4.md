# Spec — v3-G.4: 1080p long-form

Status: **locked** (owner picked "Build 1080p now", 2026-10-01).

## Why this phase exists

The long-form is delivered at 1280×720 (`scripts/factverse_engine.py` `WIDTH`/`HEIGHT`), with
the comment "YouTube re-encodes everything anyway". But the sources are already sharper than
the delivery: the screen recorder captures at 1920×1080 (`screencap.REC_W/REC_H`), and Pexels
stock is 1080p or better. They are thrown away at the final scale. A 720p upload also gets
YouTube's 720p bitrate ladder, which is where the softness comes from.

## Locked decisions

| # | Decision | Value |
|---|----------|-------|
| 1 | Delivery canvas | **1920×1080**, 30 fps. One constant pair, `fv.VIDEO_W` / `fv.VIDEO_H` in `factverse/config.py`; the engine, the bumper splice and the L2 splice all read it. 1080p is the definition of the term, not a tuning value. |
| 2 | Generated cards | Every generated card (stat, code, receipts, debate, L2, bumpers) **keeps its locked 1280×720 layout**. `step5_build`'s existing `scale=…:force_original_aspect_ratio` filter, and the splices' `nv` filter, scale it to the canvas. Re-laying them out would change spec-locked numbers (e.g. the code card's 22 px) and every measured-text surface. Native 1080 cards are a possible G.4b. |
| 3 | Karaoke captions | `build_ass` keeps **PlayRes 1280×720** (`captions.LAYOUT_W/LAYOUT_H`). libass scales PlayRes coordinates to the video, so captions keep today's size and position and are rasterised at 1080 (sharper). Passing the canvas size would have shrunk them to two thirds. |
| 4 | Citation chips | The `drawtext` chip is in **video pixels**, not PlayRes. Its locked 720p values (font 26, box border 10, right inset 28, top 34) are multiplied by `VIDEO_H / 720`, so the chip keeps its size on the frame. |
| 5 | Encoder settings | **Unchanged**: same presets (`ultrafast` for segments and the join, `fast` for passes after that) and the same CRFs. This phase changes resolution only. |
| 6 | Thumbnails | **Unchanged at 1280×720**, which is YouTube's own thumbnail size. |
| 7 | Music bed, transitions | **Not built.** The music mix already exists: `step5_build` mixes any `.mp3` in `assets/music` at volume 0.07. It needs license-clean tracks from the owner (an owner step, not code). Transitions have no spec values, and they would interact with the per-scene timing that keeps visuals in sync with narration. They stay queued. |

## Risks

- **CI time.** The final passes encode 2.25× the pixels. The job has a 90-minute timeout, and a
  day's chain makes at most 3 attempts (v3-B.3), but only the attempt that passes the gates
  renders. The local measurement below gives the ratio; the real number is the first CI run.
- **G.1 A/B confound.** The crop Short (the control arm) is cropped from the long-form, so its
  source becomes 607×1080 instead of 405×720. The control gets sharper partway through the
  experiment. The note goes in the scoreboard row's context, not in the code.

## Measured 2026-10-01 (local, 20 threads, ffmpeg 8.1.2)

The same input was put through the real `step5_build` → `burn_ass` (with 3 citation chips) →
`add_intro_outro` path: 10 scenes over a 305 s voice track, with 1920×1080 `testsrc2` "stock"
(high-entropy, so a worst case for the encoder), a stat card and a code card. Script:
`scratchpad/g4_render.py` (not committed).

| | 720p | 1080p | × |
|--|--|--|--|
| output | 1280×720, 312.2 s, 58.0 MB | 1920×1080, 312.2 s, 197.5 MB | 3.4 |
| `step5_build` | 182.0 s | 304.6 s | 1.7 |
| captions burn | 29.6 s | 169.3 s | 5.7 |
| bumpers | 38.0 s | 172.7 s | 4.5 |
| **total render** | **249.7 s** | **646.7 s** | **2.6** |

Frames extracted from the 1080p file and inspected:

- The citation chip covers 20.7% of the frame width at both sizes.
- Caption cap height is about 5.1% of the frame height at both sizes.
- The stat card, code card and outro bumper are scaled from 720, unclipped, and readable.

The CI runner has 4 vCPUs, not 20, so the absolute numbers will be larger there. The first
CI run is the real measurement, and the job's 90-minute timeout is the limit to watch.

## Done when

1. `fv.VIDEO_W, fv.VIDEO_H == 1920, 1080`, and the engine, `branding.add_intro_outro` and
   `l2.splice` build their scale filters from them. Pinned by tests that read the built args.
2. `build_ass` is still called with 1280×720, and the citation chip's font size is 39 at 1080.
3. A real render through `step5_build` → `burn_ass` → `add_intro_outro` produces a 1920×1080
   file. Frames are extracted and inspected (captions and a stat card are the right size and
   unclipped), and the encode time is measured against the same input at 720p.
4. The full suite passes.
