# Spec — v3-G.4b: production basics (music bed, mix fix, transitions, outro line)

Status: **locked** (owner: `go`, 2026-10-10). Builds on v3-G.4 (`docs/spec/ai-pulse-v3g4.md`).

## Why this phase exists

G.4 left two production gaps open: no music bed (the code mixed "any `.mp3` in
`assets/music`", the folder was empty) and hard cuts at every scene. Research on main
(937c4b2) found two more defects in the code that already existed:

- **The mix halved the voice whenever a bed existed.** `amix` defaults to `normalize=1`,
  which divides every input by the input count. Measured: voice -19.8 LUFS alone,
  -25.7 LUFS in the old mix. With `normalize=0` it stays at -19.7.
- **The bed glob shared a folder with the bumper stings.** `branding._audio` reads
  `assets/music/intro.mp3` / `outro.mp3`; the bed pick globbed `assets/music/*.mp3`, so a
  dropped sting could become a 5-minute bed. The pick was also `random.choice`.

## Locked decisions

| # | Decision | Value |
|---|----------|-------|
| 1 | Bed license | **CC0 only** for committed tracks (the repo is public). The phase commits **no audio**. `assets/music/bed/SOURCES.txt` holds the rule: title, artist, source URL, license and measured LUFS per track; MP3 128 kbps CBR, 44.1 kHz stereo; folder total ≤ 10 MB; sources = Free Music Archive / OpenGameArt with the CC0 filter |
| 2 | Track pick | `assets/music/bed/*.mp3`, non-recursive. It replaces both the top-level glob and the `bg_music.mp3` lookup. `sorted(tracks)[day_of_year % n]`, as radar `pick_track`. Empty folder → no bed, as before, with a log line |
| 3 | Mix | Bed volume **0.07**; `amix=inputs=2:duration=first:normalize=0`; no ducking; one track per video, looped with `aloop` as before; `afade` in **1.0 s** from 0 and out **2.0 s** ending at the narration's end. Kill switch `"music_bed": true` |
| 4 | Transitions | `xfade=transition=fade`, **0.5 s** (15 frames at the engine's `FPS` 30). The dissolve **ends** on the narration boundary: offset = boundary − 0.5, the incoming segment head-padded with `tpad=start_mode=clone:start_duration=0.5`, so the length is unchanged and every scene starts on its own clean first frame. Offsets from cumulative **probed** segment durations. Per-input prep `setpts=PTS-STARTPTS,fps=30,format=yuv420p,settb=AVTB`. Encoder unchanged (ultrafast, crf 23) |
| 5 | Where | Scene → scene only. **Hard cuts** at boundary 0→1 (cold-open sting), boundary n−2→n−1 (L2 insight splice), between a scene's own clips, and at any join next to a scene that produced no segment. Dissolves into and out of stat/code cards are allowed |
| 6 | Fail soft | If the dissolve join fails or `_join_ok` is false → today's concat-demuxer join. Log line `transitions: N applied` or `transitions: fallback (hard cuts)` (`off` with the switch off, `0 applied` with no eligible boundary). Kill switch `"transitions": true` |
| 7 | Outro line | "for daily AI news" → **"for AI you can use"** in `branding.make_outro` and `shorts._make_voutro` (one constant, `branding.OUTRO_LINE`). Measured, not counted (see below) |

## Implementation

All ffmpeg args are built by pure functions in `scripts/factverse_engine.py` and pinned
by `tests/test_g4b_production.py` (23 tests):

- `bed_tracks()`, `pick_bed(tracks, day_of_year)`: the bed folder and the day pick.
- `mux_args(joined, audio, adur, final, bgm=None)`: the final mux. With no bed it is
  byte-for-byte today's voice-only arg list.
- `dissolve_plan(seg_scenes, n_scenes)`: one bool per join. `step5_build` now records
  which scene each segment came from (`seg_scenes`).
- `xfade_graph(seg_durs, plan)` → `xfade_join_args(...)`: the dissolve join. It refuses
  (returns `None`) on a duration ≤ 0.5 s or a failed probe, which sends the caller to the
  fallback.
- `concat_join_args(...)`: today's join, unchanged.
- `join_scenes(...)`: runs the dissolve join, checks it with `_join_ok`, and falls back to
  the concat join on any failure (including an exception). Returns `(ok, status)`.

**Found while verifying, fixed in the graph:** ffmpeg 8.1.2's `xfade` emits **one frame
more** than `offset + incoming length`: the incoming scene's first frame is shown twice.
A following `xfade` cuts at its own offset, so the extra frame never reaches the next
dissolve. But a hard `concat` after a dissolve carried it: the n−2 boundary (where the L2
insight is spliced) landed **one frame late** and the join was 9,151 frames instead of
9,150. The graph now trims the chain to its probed length (`trim=end_frame=N`) before a
hard cut and at the end. After the fix the join is 9,150 frames and the n−2 cut is on frame
7,965 exactly. The duplicated first frame is kept: it extends a 15-frame still by a 16th.

## Measured 2026-10-10 (local, ffmpeg 8.1.2, 20 threads)

The same input as G.4, through the real `step5_build` → `burn_ass` (3 citation chips) →
`add_intro_outro` path: 10 scenes over a 305.04 s voice track (the storyboard sample
voice looped 10×), 1920×1080 `testsrc2` "stock" with a distinct hue and box position per
scene, a stat card rendered to its exact slot (14.0 s, scene 3 with one stock clip), and a
code card (scene 6). Scene shape 9.0/31.5/28.0/35.2/30.1/33.7/29.4/36.0/32.6/39.5 s.
The bed was one of the owner's Audio Library tracks, copied to a scratch `bed/` folder as
**test input only** (not committed; `eng.MUSIC` pointed at the scratch dir). Scripts:
`scratchpad/g4b/render.py`, `measure.py` (not committed).

### Loudness (ffmpeg `ebur128`, integrated)

| | LUFS |
|--|--|
| content, transitions **off**, no bed (voice only) | **-19.8** |
| content, transitions **on**, bed | **-19.7** (+0.1 LU; limit ±0.5) |
| the bed alone, through the exact `mux_args` music chain | **-32.0** (12.2 LU under the voice; limit ≥ 12) |
| the raw test track | -8.8 |
| old mix (`normalize=1` default), same voice + track | -25.7 |

The test track is a loud master (-8.8 LUFS), so it only just clears the ≥ 12 LU line. At
0.07 (−23.1 dB) a track's raw loudness must be about **−8.7 LUFS or quieter** for the bed
to sit ≥ 12 LU under a −19.8 LUFS voice. That is why `SOURCES.txt` asks for the measured
LUFS of every track.

### Duration and join time

| | transitions off | transitions on |
|--|--|--|
| joined (frames) | 305.000 s (9,150) | 305.000 s (9,150) after the trim fix; 305.033 s (9,151) before it |
| content after the mux | 305.000 s | 305.000 s (difference 0 frames) |
| final after bumpers | — | 312.133 s (+2.6 s intro, +4.5 s outro) |
| join step, inside the render | 32.2 s (concat) | 44.8 s (xfade); 79.6 s in the first run |
| join step, back to back on the same segments | 49.0 s, 24.8 s | 39.7 s, 148.6 s |

The local join times are **noisy**: other agents were rendering on the same laptop during
these runs. The quieter prototype measurement (same 10 segments, `-threads 4` like the
CI runner) is the better ratio: **concat 14.3 s, xfade 61.0 s**. So expect roughly +1 min
per long-form in CI. The full-render total (`step5_build` 249.0 s, captions 109.4 s,
bumpers 85.9 s) is in line with G.4's.

### Frames read (`scratchpad/g4b/r/frames/`)

Boundaries are the cumulative probed segment durations; in the final file every boundary
after the cold open is shifted by the 2.6 s intro.

- **Dissolve into the stat card** (boundary 1, 40.5 s): −0.60 s outgoing stock only;
  −0.30 s and −0.25 s a blend (card "0 stars" over the stock, card stronger at −0.25);
  0.00 s the clean card on its first count-up frame.
- **Stock → stock** (boundary 3, 103.7 s): −0.60 s outgoing only; −0.30 s and −0.25 s
  both boxes visible (blend); 0.00 s the clean incoming scene. Per-frame check: the last
  blend frame is the one before the boundary (93%), and the boundary frame is clean.
- **Into the code card** (boundary 4, 133.8 s) and **out of it** (boundary 5, 167.5 s): the
  same outgoing / blend / clean pattern.
- Note: −0.30 s is already 40% into the dissolve, so it is a blend, not a pure outgoing
  frame. −0.60 s is the pure outgoing frame.
- **Sting boundary** (0, 9.0 s): −0.25 s and −0.05 s scene 1, then the intro sting, then
  scene 2 clean. Hard cut.
- **Final-scene boundary** (8, 265.5 s): −0.25 s and −0.05 s scene 9, 0.00 s scene 10.
  Hard cut, on the boundary frame (it was one frame late before the trim fix).
- **Stat card count-up**: 1.0 s into its slot it reads "6,689 stars"; 0.1 s before its
  14.0 s slot ends it reads the final "21,102 stars".
- **Outro** (long-form, last 0.5 s of the final file) and **vertical outro**
  (`assets/outro_v.mp4` at 2.3 s): "for AI you can use" is unclipped under the SUBSCRIBE
  pill on both.

### Outro text measured

`br._font` (Segoe UI Bold locally): "for AI you can use" is 339 px at size 40 on the
1280 px outro (was 316 px) and 405 px at size 48 on the 1080 px vertical outro (was
378 px). Both are well inside the frame and narrower than the SUBSCRIBE pill above them,
so `fit_font` is not needed. A test pins width < half the frame. `assets/outro.mp4` and
`assets/outro_v.mp4` were re-rendered and committed (the brand stamp is unchanged, so CI
uses the committed files and never re-renders them). `intro.mp4` was not touched.

## Known limits

- **The bed is cut by the sting.** `add_intro_outro` splits the content at the end of the
  hook scene, so the bed plays under the hook, stops for the 2.6 s sting (which has its own
  audio), and resumes mid-phrase after it. This was already so; not addressed here.
- **Content ID risk on CC0 tracks.** A CC0 track can still be registered by someone in
  Content ID. Check YouTube Studio for claims after the first video that has a bed.
- **The owner must supply CC0 tracks.** Until a track is committed to `assets/music/bed/`,
  CI logs `music: no bed (assets/music/bed has no .mp3)` and the video has no bed. Only
  the mix fix and the transitions change the published video until then.
- **`shorts.ensure_vertical_bumpers` is not called anywhere** on main (Shorts have no
  outro by design). The vertical outro was updated anyway, as specified.
- **Each dissolved-into scene holds its first frame for one extra frame** (16 frames
  of still instead of 15) and loses its last frame to the next dissolve's offset: 33 ms,
  not visible.

## Post-merge check (first CI publish run)

1. The run finishes in **< 90 min** (the job timeout). Record its duration.
2. Read the log for `transitions: N applied` (expect 7 on a 10-scene video) or
   `transitions: fallback (hard cuts)`, and for the `music:` line.
3. Watch the published video at two scene boundaries for the dissolve.

## Done when

1. `tests/test_g4b_production.py` passes and the full suite is green.
2. A real render has the dissolves where the plan says, hard cuts at boundaries 0 and n−2,
   and the same duration as the transitions-off render.
3. Voice loudness with the bed is within 0.5 LU of the voice alone, with the bed ≥ 12 LU under.
4. Both outros show "for AI you can use", read on a frame.
