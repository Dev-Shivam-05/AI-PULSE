# Spec — v3-L.6: Radar Live viewer + inventory

Status: **locked**. The owner approved the 2026-11-01 review with "go for all" (2026-11-01).
This phase builds review points 3, 4, 5, 7, 8 and 14
(`docs/debate/2026-11-01-radar-live-growth-review/RESULT.md`). The session that built it ended
before writing this file; the rows below are the ones its code cites as "L6 row N", checked
against that code and the review on 2026-11-01.

## Why this phase exists

- **Inventory was our own cap.** The radar read 50 GitHub + 50 Hugging Face results. Measured
  2026-11-01: 160 repos matched the old query, 1,083 at 30 days / >50 stars; HF has 200 trending
  models and 200 Spaces. A 5-6 h session needs far more distinct tools than 100.
- **The ranking mixed two scales.** `radar.py:90` was lifetime stars/day and the board
  interleaved GitHub stars with HF likes as one "momentum" list.
- **A spotlight read name → stars → README.** A viewer who joins mid-stream did not learn what
  the tool is FOR.
- **The screen had no NEXT cue, no subscribe line, no honest end card, and no stale warning.**
- **Live audio was never measured in LUFS.**

## Locked decisions

| Row | Review point | Decision | Value |
|---|---|---|---|
| 1 | #3 | Wider GitHub inventory | One `created:` search per window `GITHUB_WINDOWS = (0-7, 7-14, 14-30 days ago)`, `>= 50` stars, `100` items each, newest first; de-duplicated by id. A failed window is skipped; `None` only when every window failed. |
| 1 | #3 | Wider HF inventory | `100` trending models AND `100` trending Spaces. `None` only when both failed. |
| 2 | #3 | Space description | A Space's card text is the author's own `short_description`, quoted as theirs. |
| 3 | #4 | Two boards | GitHub and Hugging Face are ranked separately, each by its own measure (GitHub ★/day, HF trending). `SECTION_SIZE = 4` per source on a spotlight, `BIG_SECTION_SIZE = 7` on the full board. Narration never ranks across sources. |
| 4 | #4 | Labels | `SPOTTED THIS SESSION` (never spotlighted before), `BACK ON RADAR` (spotlighted before and past the 3-day cooldown; the card states the change since last time), `SOURCE DELAYED` (no good refresh for more than `STALE_MINUTES = 30`). |
| 5 | #5 | Benefit first | Prompt order: the problem it solves → what it does → one concrete piece of evidence → limitation ("limitations are not documented yet" when none is grounded; never invented) → next step. 100-160 words. The card's `USE IT TO:` line is `2-9` words with its own gate: readable, no hype terms, no number absent from the grounding. A failing line is dropped; the narration survives. |
| 6 | #8 | NEXT cue | The top bar shows `NEXT ▸ <tool>` only for the tool the next spotlight has reserved, and that spotlight shows it. |
| 7 | #1 (prep) | Session length | `--minutes` wins, then today's CI manifest (`state/live_broadcast.json` on main, status `ready`, today's IST date, `30-360` min), then config, then `120`. Always clamped to `1-360`. No manifest = the config length exactly as before. |
| 8 | #8 | Subscribe line | First at `165` s, then at most every `900` s, `5` s each, `2` s into a segment, never on a segment too short to hold it. It takes the NEXT cue's place, never the captions'. Text, verbatim from the review: "If these discoveries help you choose AI tools, subscribe to ToolDojo for practical updates." While it shows it also takes the as-of slot (see Verification). |
| 9 | #8 | End card | Asked for `WRAP_LEAD = 150` s before the target; hard stop `OVERRUN = 600` s after it. A voiced card states the true reason ("Every fresh tool on the radar has now been covered" / "That is the end of today's session") and the tool count. "Back every day at 8 PM" is said only when the daily task really exists. |
| 10 | #14 | Audio | Speech `-19.8 LUFS` (the long-form's measured voice), music `17 LU` under it = `MUSIC_TARGET_LUFS = -36.8`, each track `loudnorm`ed to it (TP `-2`). `VOICE_GAIN_DB = 0.0` because edge-tts measured -19.8 LUFS. Every track plays in a per-day shuffled order before any repeats. |
| — | #7 | Own videos | The radar plays no video of ours; 0 reruns holds by construction. |

Also in this phase: `edge-tts >= 7.3.1` in both requirements files. 7.2.8 answered **403** on
2026-11-01 (expired `Sec-MS-GEC` version), so every live voice line would have failed.

## Files changed

- `factverse/radar.py`: wide GitHub/HF fetches, Spaces, `board_sections`, `section_rank`,
  `status_label`, `is_stale`, the benefit-first prompt + `use_it_ok`, `sections_narration`,
  `end_narration`.
- `scripts/radar_live.py`: playlist + `normalize_args`, `cta_window`, `session_minutes`,
  `manifest_for_today` / `fetch_manifest`, wrap/end card, NEXT reservation.
- `assets/radar/radar.html`: two source boards, benefit line, labels, NEXT cue, subscribe line,
  stale warning, end card.
- `requirements.txt`, `requirements-ci.txt`: edge-tts.
- `tests/test_l6_radar.py` (new, 23 tests); `tests/test_radar.py`: 3 lines.

## Verification

**Suite: 419 passed** (2026-11-01, full run on the branch after the fixes below).

**Local 5-minute session, received file read** (`radar_live.py --minutes 5 --out <file>.flv`,
real GitHub/HF/edge-tts/LLM calls, 2026-11-01 11:12-11:21 UTC):

- Inventory: **445 tools** after the screen (40 screened out), both sources OK; 439 fresh.
  The old fetch had at most 100.
- `session end: ok · 8 segments · 0 standby · 0 restarts`. Pre-roll 3 segments.
- Received file: **316.05 s**, 1920×1080, 30 fps, **0 decode errors**.
- Loudness (ffmpeg `ebur128=peak=true`, whole file, voice + bed): **−19.8 LUFS integrated**,
  true peak **−4.8 dBTP** (target −19.8 ±1, limit −1.5). Music normalised to −36.8 LUFS (5 tracks,
  16.6 min, per-day order).
- Frames read at 10, 60, 110, 150, 166, 172, 230 and 310 s:
  - spotlight cards with SPOTTED THIS SESSION, the per-source rank chip, two source boards
    (GitHub "ranked by stars per day since created", HF "ranked by HF trending score");
  - NEXT ▸ names the tool the next spotlight shows (Mistral-Large-4-1T-A52B, then anatomy);
  - the full board at 150 s, 7 + 7, never ranked across sources;
  - **the subscribe line at 166 s**, the verbatim text at 28 px across the bar; at 172 s NEXT
    and the as-of text are back;
  - the end card at 310 s: "That's the end of today's session. 6 tools covered today", with no
    "back every day" because the schedule is not installed (correct).

**Defects found by looking, fixed and re-rendered:**

1. The built labels were "NEW / BACK ON THE RADAR" and the subscribe line was shorter wording;
   both now match the review verbatim (`status_label`, `CTA_TEXT`, tests updated).
2. The verbatim subscribe line in the 900 px centre slot shrank to the 18 px floor and ran
   under "SOURCE DELAYED · data as of …". For its 5 s it now takes the as-of slot too
   (`#top.cta`) and fits at 28 px.
3. Live: the Mistral card showed "USE IT TO: RUN MULTILINGUAL MULTIMODAL REASONING AND AGENTIC
   WORKLOAI", cut mid-word at the 24 px floor (log: `text did not fit at the floor: ['use']`).
   A line that cannot fit is now dropped like a gate failure (row 5) and the description takes
   the full height. Re-rendered with that exact line: dropped, nothing clipped.

Not verified here: a YouTube ingest (owner's private test), a session longer than 5 min, and the
CI manifest path (nothing writes it until L.7).

## Known limits

- **`UPDATED` is not built.** The review defines it as "a verified meaningful change, with
  source and time". The radar fetches no release or changelog data, so there is nothing to
  verify a change against, and a threshold would be invented. It needs a release fetch and a
  spec row (L.7 or later).
- The manifest is read but nothing writes it yet: CI broadcast creation is L.7.
- `BACK ON RADAR` is given to any re-spotlit tool past its cooldown. The review asked for "a
  material new change"; the card shows the star/like change since last time, but no minimum
  is enforced (no value is written down).
- 5-6 h inventory with the cooldown applied is still unmeasured over 7 real days (review open
  point 2).
- The seam lags (v3l3 §6) are untouched; they belong to L.8.
