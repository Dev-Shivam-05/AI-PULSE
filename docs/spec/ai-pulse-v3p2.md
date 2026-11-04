# Spec — v3-P.2: proof-first opening contract, Pilot A, query-map packaging

Status: **locked**. The owner approved the 2026-11-04 review ("go for all … do not stop until
everything is done"). This phase implements rows 5, 6 and 13 of
`docs/debate/2026-11-04-tooldojo-channel-growth/RESULT.md`, built on v3-P.1's evidence engine
(`docs/spec/ai-pulse-v3p1.md`) and the shared interface in `docs/spec/ai-pulse-v3-growth.md`.
Values marked *locked* come from review round 3 (`03_chatgpt.md` §2-§4) as amended in round 4
(`04_claude.md` A1-A3, accepted with corrections in `04_chatgpt.md` §1; query map from §3 Rank 2).
Every other value is a **delegated decision** with its default and reason.

## Why this phase exists

1. **The usable part came late.** Retention on every tool video falls from 95% to 55-60% by
   0:07; gpu-unlock's "Get The Commands" started at 4:42 with 12% of viewers left. P.1 made the
   evidence exist; P.2 decides what the first 25 seconds show and checks it on the encoded file.
2. **Nobody knows whether proof-first beats context-first** at this channel's volume. Pilot A
   answers it with 6 pre-assigned pairs, read at the same publication age.
3. **Search is 82% of long-form views**, mostly exact tool names. Titles, the first description
   sentence and the chapters now match the query (entity / entity + task).

## Locked decisions

| # | Decision | Value |
|---|----------|-------|
| 1 | Frame 0 | Proof-first: the captured or author-demonstrated result at 0.00 s, full opacity, no fade, no blank frame. |
| 2 | Result size | The result region covers **≥ 40%** of the frame for the first **2 s** (crop / enlarge). |
| 3 | First speech | Starts by **0.50 s**. First sentence **≤ 16 words**, ends by **6.50 s**, states the observed result or "The author's demo shows …". |
| 4 | Source label | From frame 0 and throughout third-party footage, **≥ 32 px** (P.1's 40 px pill). |
| 5 | Limitation | A prerequisite or limitation is stated by **0:15**. |
| 6 | First step | The first safe command or hosted-demo action appears by **0:25**, readable **≥ 5 s**. A hosted tool's step is the demo action, never an install command. |
| 7 | Branding | **No brand-only sting** anywhere in a pilot video; the L2 cold open never displaces frame 0. |
| 8 | Text | Essential explanation and command text **≥ 48 px** at 1920×1080. |
| 9 | Duration | **150-210 s**; the two videos of a pair differ by **≤ 15%**; no padding. |
| 10 | Script architecture | Per source, round 3 §3: hosted (a) "here is what happened with our input", author (c) "what the author shows, and what remains unknown". Sandbox (b) not built. |
| 11 | Gate | On the ENCODED file (frames + audio word timings, renderer metadata), one automatic repair, then skip the way the lane falls back today. |
| 12 | Context-first arm | Same evidence, standards, band, voice, music, step deadline. 0:00-0:15 task context + suitability; first displayed result at **0:15-0:16**; first sentence states the task in ≤ 16 words; frame 0 complete and informative. |
| 13 | Pilot A | **6 pre-assigned pairs** (A1), matched on evidence source × intent type (A3: install-and-run / use-a-hosted-demo / decide-before-installing); task family, publication date, duration, traffic-source mix recorded as covariates. Random arm within each pair and random publish order, recorded before any performance. |
| 14 | Readout | Per-video retention near **0:07** (primary), 0:30, 1:00, storing the ACTUAL sampled time; both videos at the SAME publication age; read day 7, then 14, then 28; first common usable checkpoint by availability; recheck all at day 28. |
| 15 | Promising | ≥ **5 of 6** pairs favour proof-first, median paired advantage ≥ **8 pts** at ~0:07, treatment medians **65 / 45 / 38%**. |
| 16 | Unresolved | < 6 evaluable pairs; missing pairs are reported, never replaced. |
| 17 | Readout shows | Individual pairs, median, exposure-weighted aggregate, the result without the largest winner, "outlier-dependent" when that flips it. |
| 18 | AVD guardrail (A2) | Frozen unweighted median of eligible pre-pilot tool videos' first-7-day AVD, from per-video snapshots, never lifetime; treatment median (all 6 treatment videos) below it = "revise". |
| 19 | Query map | Hosted: `RepoName — <Task>: Hosted Demo and Limits`; author: `RepoName Demo Explained: Requirements and Limits`. One canonical name plus a genuinely used alias; no separate spellings. |
| 20 | Description | First sentence = tool + task + evidence status; the command and cheat-sheet block directly below it. |
| 21 | Chapters | Descriptive ("Observed result", "Requirements", "Starting step", "Limitations") only where the section exists; 00:00 first, ≥ 3 timestamps, each ≥ 10 s. |
| 22 | Ledger | Three timestamps: first detected signal, first admissible evidence, publication. Experiment fields `experiment`/`pair_id`/`arm`/`slot` (growth spec). Companion Shorts unchanged. |

## Delegated decisions ("default chosen: X, because Y")

| # | Decision | Default chosen | Because |
|---|----------|----------------|---------|
| D1 | Scene architecture | Fixed roles by index. Proof: S1 result (≤ 20 words), S2 fit + limitation (≤ 16; S1+S2 ≤ **36** words), S3 first step, S4 input→action→output sequence, S5-6 details incl. what the evidence does not establish (filter), final decision. Context: S1 task + suitability (**28-42** words), S2 result (≤ 14), S1+S2 ≤ **56**, then the same S3+. 7-9 scenes. | The renderer and the gate must know where each rule lives; the word budgets put the limitation by ~14 s and the step by ~22 s at 2.5 words/s. |
| D2 | Pilot word band | **400-500** words (writer), lint tolerance ±30; the encoded duration decides. | 150-210 s at 150 wpm (the pipeline's long-standing rate) is 375-525; the band keeps ~10 s margin each side. |
| D3 | Writer first sentence | Asked for **≤ 13** words (rule: ≤ 16). | 13 words end ~5.4 s at 2.5 w/s, leaving margin under 6.5 s. |
| D4 | Pilot passes | Critique / expand / tighten passes are **skipped** for pilot scripts; a deterministic lint (`opening.lint`) plus **one** writer fix pass replace them. Content issues (scene count, first sentence > 16 or not stating the result, no limitation) block before render; timing issues go to the encoded gate. | Those passes restructure scenes freely and would move the result, the limitation and the step out of their slots. |
| D5 | Limitation detection | A sentence in the arm's limitation scenes matching `requires / needs / prerequisite / only works|runs|supports|for|on / does not / can't / won't / not for / without / limit* / must have / you need / GPU / VRAM / CUDA / API key / account / sign in / log in`; "not independently tested" is removed first (it is the evidence's status, not the tool's limit). | Deterministic and checkable; the round asks for "a prerequisite or limitation". |
| D6 | Result frame | The frame of the evidence master clip, among 6 samples in its last quarter, that differs MOST from its first frame (ties: later). | A GIF that loops back ends on its start, not its result. |
| D7 | Result region | Pixels changed (> **24/255** at 192×108) between the result frame and a baseline, kept only in 12×12 blocks where ≥ **25%** changed (dense change); padded 3%; aspect clamped to **[0.75, 4.0]** around the change's centroid; enlarged ≤ **4×**; centred on the dark canvas, label top-left. Baseline = frame 0 or the frame at 1.0 s, whichever gives the SMALLER region that is still ≥ **4%** of the frame. | Measured on gradio/image_mod: frame 0 is the page still laying out, and button hovers / selection borders are sparse edits — both stretched the region to the whole page (100%). With the rule: input + output panes, 67%; Mika 74%; AnyModelBot 74%. The clamp guarantees ≥ 40% whenever the region fits. |
| D8 | Opening visuals | Built as absolute events, then cut at scene bounds. Proof: result still 0 → end of S1; S2 keeps its own visuals; step card from S3's start for max(S3, **5.5 s**); then the master clip slot-fitted with the label. Context: task card (first sentence 84→48 px, tool + alias, source label) 0 → R; result still R → max(S3 start, R + **3 s**); then step, then sequence. R = S1's end when it falls in 15.0-16.0 s, else **15.0**. The final scene also leads with the step card. One clip per owned scene, rendered to its exact share (C.3). | step5_build splits a scene equally between its clips, so mixed pieces must be one clip; +0.5 s covers the incoming dissolve; the 3 s floor was added after a real render whose scenes 1+2 ended before 0:15 (the first timeline refused it). |
| D9 | Step card | Header "STARTING STEP"; hosted: "Open the hosted demo:" + the Space host + "Pick <example>" + "Run it and compare the output"; author: "Run the documented command:" + the grounded deliverable (JetBrains Mono 64→48 px) + "From the README — not run by ToolDojo". A command that cannot fit 4 lines at 48 px keeps 3 lines plus a visible "… full command in the description". | Round 3: "never invent an installation command" for a hosted tool; CLAUDE.md: measured text, never silently truncated. |
| D10 | Receipts / code card | Not used in pilot videos (the step card replaces the 33 px code card; the receipts beat rewrites narration after the gates and changes the timing architecture). | Text ≥ 48 px; same standards in both arms. |
| D11 | Brand + L2 | Pilot videos skip `add_intro_outro` (intro AND outro are brand bumpers) and call `l2.inject(cold_open=False)`; the unused cold open stays for the next ordinary video; the insight block is unchanged. | Round 3: no brand-only sting anywhere; the cold open must not displace frame 0. |
| D12 | First speech | A voice whose first word starts after 0.35 s is trimmed to start 0.15 s before it (`_trim_lead`). | TTS lead-in silence varies by engine; trimming is lossless for the content. |
| D13 | Frame matching | Encoded frames sampled at **8 fps** for the first **32 s**, 480×270, compared to the rendered references above the caption band (top 78%) and outside the citation chip; match = mean abs diff ≤ **14/255**; frame 0 also needs stdev ≥ **8**. | Measures the encoded file itself (0.125 s resolution) without being fooled by burned captions. |
| D14 | Speech timings | Whisper on the ENCODED file when `faster_whisper` is installed (CI); else the narration's own word timings (`timing_source` says which), valid because pilot videos add nothing before the narration (verified: |encoded − audio| ≤ 1 s, `no_sting`). Script tokens aligned to timed words with difflib. | No whisper locally; CI has it. |
| D15 | Pair duration | Difference relative to the SHORTER video ≤ 15%. | The stricter reading. |
| D16 | Repair | Failures that need words (first sentence, limitation, step late, duration) → one writer fix of scenes/task only, re-checked by the overclaim, overlap, advice and fact-check gates, then re-voice and re-render; visual failures → one re-render. Still failing → `OPENING_BLOCKED` + `_fall_back`. | "One automatic repair attempt; persistent failure means skip." A repair must never be a way around a gate. |
| D17 | Intent type | Hosted → use-a-hosted-demo; author with a heavy prerequisite in the grounding (GPU / CUDA / VRAM / NVIDIA / RTX / Docker / API key / large RAM / A100 / H100) → decide-before-installing; else install-and-run. | Deterministic, from text the pipeline already has. |
| D18 | Pair formation | Pairs `B1P1`-`B1P6` with a pre-drawn `first_arm` each (= publish order and arm of member 1). A pilot-eligible video closes the first OPEN pair of its stratum, else opens the next unused pair. A member is a PUBLISHED ledger row (or a `members` record); a blocked render never takes a slot. | "Pre-assigned" without knowing tomorrow's supply; arrival order only, never performance. |
| D19 | The draw | `random.SystemRandom` seed **1015367535**, frozen 2026-11-04 in `state/pilot_a.json`: B1P1-B1P5 context-first first, B1P6 proof-first first. Not redrawn. | A 5:1 split is a legitimate draw; redrawing would be choosing an assignment. |
| D20 | Readout windows | Window `[publish date, publish date + age]` (7/14/28), queried once it is **2 days** old (YouTube: processing 1-2 days), retried for 14 days while the curve is empty. Usable curve = **≥ 10** points. | Same-age comparison; empty curves mean "not enough information". |
| D21 | Sampled time | A point's time = `elapsedVideoTimeRatio × duration` (the ratio is the exclusive END of its interval, per the docs); the nearest point to 7 / 30 / 60 s. | The docs define the ratio that way. |
| D22 | Stop rule for 6 pairs | Round 3's "all 3 pairs favour context-first and median disadvantage ≥ 5 pts" → **all 6** pairs favour context-first and median ≤ −5 pts. | The literal adaptation of "all pairs". |
| D23 | Flat | Batch 1: median advantage ≤ 0 (and not "stop") → "flat: one more 6-pair batch". Batch ≥ 2: median ≤ 0 with ≤ 2 positive pairs → "stop" (round 3's stopping rule). Precedence: unresolved, stop, promising, revise delivery, flat, revise hypothesis. | Round 3 gives the after-batch-2 rule but no number for "flat". |
| D24 | Revise delivery | ≥ 5/6 wins and median ≥ 8 but a 0:30 / 1:00 target missed, or the AVD guardrail breached. | Round 3 §4 + A2. |
| D25 | Exposure weighting | Weight = the pair's total views in the checkpoint window. | "Exposure-weighted" names no weight. |
| D26 | Outlier-dependent | Removing the largest-advantage pair flips the median's sign, or drops a "promising" median below 8 pts. | Round 3's "reverses the apparent advantage". |
| D27 | AVD baseline eligibility | PUBLISHED tool long-forms published before the freeze, with a snapshot collected on publication day + 7 listing them, views > 0 and AVD > 0 (the last snapshot that day). | `ledger_videos` is cumulative from DATA_FLOOR, so at age 7 it IS the first 7 days. |
| D28 | Query-map task | The writer's new `task` field (2-5 words, no numbers), coerced: ≤ 5 words, ≤ 40 chars, no `N×`/`N%`; a hosted title without a usable task is `RepoName: Hosted Demo and Limits`. Alias = `owner/repo`, used in the first sentence and the tags. | The pattern needs a task; a claim is not a task. |
| D29 | Query-map scope | Title + first sentence: every tool video with admissible evidence (pilot or not). Descriptive chapters: pilot videos; other tool videos keep `tool_chapters`. | Only the pilot architecture guarantees the sections exist. |
| D30 | First-seen store | `state/first_seen.json` url → {signal, evidence}, earliest wins, capped at 3,000 urls; signal = any ranked tool candidate, evidence = the first admissible gather. | No store recorded either before; the ledger reads them. |
| D31 | Chapter format | `00:00` mm:ss, a "Chapters:" header, sections < 10 s merged into the previous one; < 3 left → no chapters. | Round 4: start at 00:00, ≥ 3, ≥ 10 s. |
| D32 | Test defaults | `tests/conftest.py` pins `PILOT_A`, `QUERY_MAP`, `PILOT_RETENTION` off. | Same reason as P.1 D25. |

## Interface

- `script["pilot"]` = `{"experiment": "pilot_a", "pair_id", "arm": "proof"|"context", "slot": 1|2,
  "stratum", "intent", "source", "partner_seconds"}` — set by `script_tool`, popped by
  `_validate_script`, carried by `_CARRY` (with `query_map` and `task`).
- Ledger (one dict, `_p2_ledger`, computed before the upload): `experiment`, `pair_id`, `arm`,
  `slot`, `pilot_stratum`, `pilot_intent`, `opening` (the gate's result), `duration_s`,
  `pilot_task`, `t_signal`, `t_evidence`, `t_publication`.
- `state/pilot_a.json`: frozen design + `avd_baseline` + `members` (appended after an upload).
  `state_merge`: main's design wins, members union by (pair_id, arm), first wins.
- `state/analytics.jsonl` snapshots gain `pilot_reads`: `[{video, age, start, end, read_on,
  curve: [[ratio, audienceWatchRatio, relativeRetentionPerformance]], totals: [views, minutes,
  avd], traffic: [[source, views]]}]`.
- `python -m factverse.pilot readout` prints the readout (also printed after every analytics run).

## Files changed

- `factverse/opening.py` (new): writer contract, lint, fix prompt, timeline, result region,
  result still / context card / step card, `place_opening`, the encoded-file gate `measure`,
  `repair_kind`, `ledger_view`, `chapter_candidates`.
- `factverse/pilot.py` (new): design, intent, assignment, members, AVD baseline, Analytics
  query args, reads, readout, decision rules, CLI.
- `factverse/querymap.py` (new): name/alias, task, titles, first sentence, chapters, first-seen.
- `factverse/ai_pipeline.py`: pilot slot + architecture prompt in `script_tool`; `run()`'s render
  block extracted to `_render_longform` (unchanged for non-pilot videos), the opening gate loop
  with one repair, query-map title/description/chapters, `_p2_ledger`, member record.
- `factverse/l2.py`: `inject(..., cold_open=True)`.
- `factverse/analytics.py`: `pilot_reads` (own try, `pilot_retention`) and the readout print.
- `factverse/state_merge.py`, `.github/workflows/publish.yml`: both new state files.
- `config.json`, `config.example.json`: `pilot_a`, `query_map`, `pilot_retention` (all `true`).
- `state/pilot_a.json` (new, frozen), `tests/test_p2_opening.py` (new), `tests/conftest.py`
  (three env names added), `tests/test_pipeline_logic.py` and `tests/test_b5_daily.py` (two
  source-pinning tests follow the moved code).

## Verification

**Suite: 557 passed** (2026-11-04, full `py -3 -m pytest tests/ -q` on the branch, 136 s). The
first full run had 2 failures, both source-pinning tests: the `_fall_back` count is now 8 (the
three opening-contract exits), and the B.5 recut-order test now reads `_render_longform`, where
run()'s render block moved unchanged. `tests/test_p2_opening.py`: 44 tests.

**Real renders through `run()`** (fixture scripts — no LLM keys locally — on the real P.1 hosted
capture of `gradio/image_mod`, real screencap of github.com/gradio-app/gradio, edge-tts voice,
real step5_build / captions / L2 / opening gate; only the LLM gates, Shorts, cheat sheet, site
and ledger writers stubbed). Measured by the gate on the ENCODED files:

| | proof-first | context-first (pair partner) |
|---|---|---|
| duration (150-210) | 170.86 s | 174.98 s — pair diff **2.4%** |
| frame 0 vs reference | diff 0.95/255, stdev 105 | diff 1.12/255 (task card), stdev 42 |
| result | 0.00 → 7.125 s, 67% of frame | first shown **15.00 s** (window 15.0-16.0) |
| first speech | 0.10 s | 0.10 s |
| first sentence | 12 words, ends 4.57 s | 11 words, ends 3.60 s |
| limitation ends | 11.83 s | 11.50 s |
| step card | 11.375 s → 22.125 s (10.75 s) | 18.00 s → 26.25 s (8.25 s) |
| label / text / captions | 40 / 52 / 75 px | 40 / 52 / 75 px |
| sting | none (encoded = audio ± 1 s) | none |
| dissolves | 6 applied | 6 applied |
| gate | **PASS** attempt 1 | FAIL `limitation_late` (15.27 s) → script repair → **PASS** attempt 2 |

The context-first run exercised the whole repair loop: the first render's limitation ended at
15.27 s; the repair (a stand-in for the writer's one fix, returning a shorter scene 1) was
re-voiced, re-rendered and re-measured. That second render first exposed a real bug — the
first timeline refused an opening whose scenes 1+2 end before 0:15 (`placement`) — fixed by D8's
3 s result floor and re-rendered. Frames read (0.00 / 2 / 7 / 15 / 25 s, plus 14.8 / 15.5 for
context): result still with the label from frame 0; task card complete at frame 0; result at
15.5; step card at 15 (proof) and 25 (context); captions below every essential text.

Earlier render, kept as evidence the gate measures: a 396-word fixture came out at **126 s** with
edge-tts and the gate failed it on `duration` (no repair available → fallback).

**Result regions on all three real P.1 clips** (D7): image_mod 67% (input + output panes), Mika
74%, AnyModelBot 74%; stills read.

**Description, as assembled** (proof render):
```
gradio (gradio-app/gradio) for rotate images, shown in our hosted-demo run of 2026-11-04: passed this specific test.

🔧 Try it yourself:
pip install gradio
https://github.com/gradio-app/gradio
📄 Free 1-page cheat sheet: https://dev-shivam-05.github.io/AI-PULSE/tools/2026-11-04-gradio-rotate-images-hosted-demo-and-lim.html

See what the Gradio image_mod demo does with one fixed input.
…
Chapters:
00:00 Observed result
00:11 Starting step
00:22 Input to output
01:08 Limitations
02:32 Decision and next step
```
Title: `gradio — Rotate Images: Hosted Demo and Limits`. Ledger row: experiment `pilot_a`,
arm, slot, stratum `hosted|use-a-hosted-demo`, `duration_s`, `pilot_task`, `t_signal`,
`t_evidence`, `opening` (the measurements above).

**Pilot A freeze** (`state/pilot_a.json`): seed 1015367535; B1P1-B1P5 context-first first, B1P6
proof-first first. Applied to a stream of 13 candidates (P.1's three real admissible ones, then
hypothetical arrivals) it fills all 6 pairs by stratum and refuses the 11th arrival whose stratum
has no open pair. Readout over fixture retention reads (6 pairs): per-pair advantages, median
9.5 pts, exposure-weighted 8.22, 5/6 proof wins, treatment ~0:07 median 63.9 < 65 → "revise
delivery"; the actual sampled times (7.0-7.4 s for "0:07") are printed per point.

**AVD baseline, frozen: 72.0 s** (n = 7: 72, 90, 43, 50, 65, 171, 81 s), from origin/main's
`state/analytics.jsonl` (207 snapshots, last 2026-11-03) and `state/runs.jsonl`. Excluded:
FHfd45OkoRE (3 views, AVD 0 at age 7 — watch time not processed), and the three tool videos
published 10-30, 11-01, 11-03 (no age-7 snapshot yet).

**Retention API shape** (verified on the official docs,
https://developers.google.com/youtube/analytics/channel_reports — "Audience retention", and
https://developers.google.com/youtube/analytics/dimensions — `elapsedVideoTimeRatio`): required
dimension `elapsedVideoTimeRatio`, metrics `audienceWatchRatio` / `relativeRetentionPerformance`,
required filter `video==` with ONE id (a comma list is not supported), optional `audienceType`,
`subscribedStatus`, `youtubeProduct`; 100 points, ratio 0.01-1.0, each the exclusive end of its
interval. Not run live (no token locally) — the args are tested.

## Known limits

- **Word budgets are voice-dependent.** D1/D2 assume ~2.5 words/s (Kokoro on CI); edge-tts
  measured **3.1-3.3 words/s** locally (396 words → 126 s). The gate judges the encoded file, so a
  mismatch costs a repair or a day, never a wrong video. The first CI pilot day will show the
  Kokoro rate; tune D1/D2 from it.
- **The writer repair was not run live** (no LLM keys locally). The loop around it was: the repair
  input was a deterministic stand-in returning the shorter scene a writer would.
- **Only the hosted source was rendered end to end.** The author path's opening pieces were
  checked on the real Mika and AnyModelBot clips (result regions, stills), not through `run()`.
- **Context-first lag.** When scene 1 ends before 0:15 the task card holds while the result
  sentence is already being spoken (≤ 3.5 s in the verified render); the 0:15 rule wins. The
  writer budget aims scene 1 at ~15 s to keep it small.
- **Speech timings locally are the narration's own** (`timing_source: narration_words`): no
  faster-whisper on this machine. CI has it and transcribes the encoded file.
- **Lexical checks are lexical.** "States the observed result" = starts "The author's demo shows"
  / contains "hosted"; the limitation is a keyword sentence. A writer can satisfy both without
  saying anything useful — that is still a reviewer's job.
- **The first-7-day AVD baseline used same-day snapshots**: data for the last day of the window
  may have been partly processed. Treatment reads wait 2 days, so the baseline may be slightly
  conservative.
- **The draw is lopsided (5:1 context-first first)** — a legitimate random draw, kept.
- **Supply decides the pace.** P.1 measured 3 admissible of 27 candidates on one day; 12 pilot
  videos at that rate is weeks, and one stratum (decide-before-installing) may never pair.
- **"first detected signal" starts today.** No earlier sightings were stored, so a candidate seen
  before 2026-11-04 has its first CI sighting as its signal time.
- Dissolves: an untagged clip next to a bt470bg recording piece in one scene breaks the xfade join
  (frames dropped → hard-cut fallback). Opening clips are now tagged; the code card / stat card
  of ordinary tool videos are not (see Traps).

## Traps found (for the integration step to copy into CLAUDE.md)

- **Colour tags must match inside a scene.** The concat of an untagged generated still and a
  `bt470bg` screen-recording piece made ffmpeg reconfigure its filter graph mid-join, drop 270
  frames (9 s) and fall back from dissolves to hard cuts — silently, because `fv.LOGS` did not
  exist in the worktree so `safe_run` could not even write `ffmpeg_error.log`. Tag every
  generated clip `-colorspace bt470bg -color_range tv` (what swscale produced from RGB anyway).
  Ordinary tool videos mix the code card with recording pieces in the final scene: the same bug
  may already cost them their dissolves.
- **A hosted clip's frame 0 is not a settled page.** The recording starts 1 s before the example
  click, while Gradio is still laying out; "what changed" against frame 0 was the whole page.
  Pick the baseline that gives the smallest dense change.
- **A layout rule tied to scene boundaries breaks on the first short scene.** The context arm's
  result was placed per scene and refused a real render whose scenes 1+2 ended at 12.4 s. Place
  contract times as absolute events, then cut at scene bounds.
- **Word-count budgets are a property of the VOICE**, not of the script (edge 3.1 w/s vs Kokoro
  ~2.5). Any timing rule must be checked on the encoded file.
- **Source-pinning tests move with code.** `inspect.getsource(ap.run)` and the `_fall_back`
  count broke when the render block moved to `_render_longform`; update them with the move.

## Owner steps

- None required to ship: all three switches are on in `config.json`. To pause the pilot, set
  `pilot_a: false` (tool videos then take P.1's path); `query_map: false` restores the model's
  titles and the old chapters; `pilot_retention: false` stops the Analytics reads.
- After batch 1, if the readout says **flat**, freeze batch 2 by hand:
  `python -m factverse.pilot freeze` refuses while `state/pilot_a.json` exists, on purpose —
  move the batch-1 file aside in a reviewed commit first.

## Done when

- [x] The suite is green with the new tests.
- [x] Both arms rendered through `run()`, frames read, the gate measured the encoded files.
- [x] Assembled description, chapters, the 6-pair assignment and a fixture readout printed.
- [x] AVD baseline frozen from per-video snapshots (72.0 s, n = 7).
- [ ] The first CI pilot day logs `🧪 Pilot A: pair …` and `📏 Opening gate … PASS|FAIL`, and the
      ledger row carries `experiment: pilot_a`.
