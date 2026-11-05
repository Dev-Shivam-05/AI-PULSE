# Spec — v3-S.1: native concept Short, Pilot B, Reels source

Status: **locked** for rows 7, 8 and 15 (Reels part) of the 2026-11-04 growth review. The owner
approved the programme with *"go for all … do not stop until everything is done"* (2026-11-04).
Built 2026-11-04 on `v3-phase-s1` (from `v3-growth-1104`).

Source of the numbers: `docs/debate/2026-11-04-tooldojo-channel-growth/` (kept local, like every
review folder): round 3 `03_chatgpt.md` §2 "Native concept Short" + "Crop control" and §4
"Pilot B"; `03_claude.md` "Change 2" (the baseline table); `04_chatgpt.md` Rank 4 (Reels).
The values used are copied below so this repo stays self-contained. A value nobody wrote down is
listed under **Delegated decisions** as "default chosen: X, because Y".

## Why this phase exists

- Winning Shorts are self-contained concept answers (30.3% / 32.9% stayed to watch). Storyboard
  Shorts got 6.4% / 3.8%.
- Directly verified G.1-era baselines (Shorts with ≥ 100 feed impressions):

  | Engine | Shorts | Median stayed | IQR | Median feed impressions |
  |---|---|---|---|---|
  | Crop | 18 | 16.9% | 12.5–24.2% | 216 |
  | Storyboard | 12 | 10.1% | 6.7–14.1% | 193 |

- So the storyboard slot is replaced by a **native concept Short**, compared against the best
  current arm (the crop excerpt) in Pilot B.

## Locked decisions

### Native concept Short (round 3, verbatim values)

| # | Element | Rule | Where enforced |
|---|---|---|---|
| 1 | Frame 0 | Complete explanatory diagram or comparison at 0.00 s; everything needed to identify the subject is present | one beat, every element `t = -10`; renderer probe `__shown(0)` must be N/N |
| 2 | Headline | ≤ 8 words; no progressive reveal of the headline or diagram labels in the first 2 s | `validate`; probe `__shown(2.0)` = N/N; no highlight before 2.0 s |
| 3 | First speech | Starts by 0.30 s; first sentence ≤ 14 words, completed by 5.00 s | gate on the ENCODED file |
| 4 | Answer | Core answer spoken and visually represented by 0:07 | answer sentence (1 or 2) ends ≤ 7.0 s; the diagram is complete from frame 0 |
| 5 | Length | 20–28 s; ≤ 65 spoken words; no sentence cut to meet the cap | `plan_length`, gate; over the cap = repair, never a cut |
| 6 | Explanation | At least one visible causal step or comparison, not text restating narration | diagram template `compare` (titles + ≥ 1 item) or `steps` (3–5) |
| 7 | Qualification | Before the final 2 s | its sentence ends ≤ duration − 2 s |
| 8 | Ending | Complete takeaway by duration − 2 s; hold the final visual | last sentence ends ≤ duration − 2 s; the one beat holds to the end |
| 9 | Branding/CTA | No brand sting, no CTA | no bumpers, no hook overlay, no CTA drawtext; CTA phrases in the narration fail `validate` |
| 10 | Text size | Essential text ≥ 60 px on 1080×1920 | board `floor: 60`; renderer `__minSize()` ≥ 60; captions 68 px |
| 11 | Validation | Timeline checked against the encoded output; one automatic repair; persistent failure = skip | `native_short.measure` + `gate`; `REPAIRS = 1` |
| 12 | Crop control | Unchanged: the current crop-excerpt process, ~35–36 s; native rules NOT retrofitted | `shorts.make_shorts` untouched apart from `storyboard=` and `last_windows` |
| 13 | Script | Independent script from the day's topic: one model call, validated and coerced | `native_short.prompt` / `validate` |
| 14 | Renderer | The storyboard Chromium renderer and page, reveal disabled at frame 0; own TTS files | `storyboard.render_meta`; `nv_voice.*` |
| 15 | Engine name | `"native"` (growth spec); file marker `_nv_` | `storyboard.engine_of` |

### Pilot B (round 3 §4)

| # | Decision | Value |
|---|---|---|
| 16 | Batch | 6 production-day pairs, 12 Shorts |
| 17 | Slots | 18:45 UTC on production day D and 01:30 UTC on D+1, pinned by `scheduling.pilot_b_slots` (today's grid already gives these two with the 16:45 long-form slot; pinning means a changed `longform_slot_utc` cannot move them) |
| 18 | Assignment | Alternate native/crop daily; the first assignment is a random draw (`random.SystemRandom`), recorded with its time and method in `state/pilot_b.json`; each format gets each slot 3 times |
| 19 | Pairing | The same question where possible; otherwise the same concept family, recorded as the weaker match |
| 20 | Primary measure | Directly reported stayed to watch (Studio: engaged views / Shorts feed impressions) |
| 21 | Floor | ≥ 100 feed impressions for EACH Short in a pair |
| 22 | Observation | 7 days per upload; a 72-hour snapshot is provisional; all assigned videos recorded, none silently removed |
| 23 | Promising: repeat | 6 evaluable pairs; native median ≥ 22%; median paired advantage ≥ 5 pts; native wins ≥ 5 of 6 |
| 24 | Revise | Positive but smaller gains, inconsistent wins, or strong selection followed by weak explanation viewing |
| 25 | Stop this package | Native wins ≤ 1 of 6 and median paired disadvantage ≥ 5 pts; keep crop while redesigning |
| 26 | Unresolved | Fewer than 6 evaluable pairs; low exposure is reported, never turned into a zero |
| 27 | Second batch | After 12 evaluable pairs: median advantage ≤ 0 and ≤ 6 wins → stop scaling this implementation |
| 28 | Watch-time guardrail | Seconds watched per Shorts-feed impression, only where measured; a decline > 10% with a stayed gain = "revise, not scale"; never estimated by multiplying |
| 29 | Report | Individual pairs, median, exposure-weighted aggregate, and the result without the largest winner; "outlier-dependent" if removing it reverses the advantage |
| 30 | Baseline | Crop median 16.9% (n = 18) |

### Reels (row 15) and switches

| # | Decision | Value |
|---|---|---|
| 31 | Reels source | Only the ToolDojo-owned native concept Short. No native that day = no Reel; never a crop excerpt, never author-demo footage. `notified_ig.json` / `notified_fb.json` stay separate |
| 32 | Kill switches | `native_shorts`, `pilot_b`, `pilot_b_batches`, `reels_native_only` in `config.json` and `config.example.json` (all `fv.flag`/`fv.setting`, flippable from Actions env) |

## Delegated decisions (each needs the owner's one word)

| # | Decision | Default chosen, because |
|---|---|---|
| D1 | What a slot gets when the native Short is skipped | **The second crop excerpt** (already rendered as a spare), placed in the native's slot; the control keeps its own slot. Because the channel keeps two Shorts a day and round 3 forbids silently dropping a day. The pair is recorded as **unevaluable** (`evaluable_by_design: false`, reason kept), and the ledger arm is `native_skipped@<slot>` |
| D2 | What "one automatic repair" is | **A second model call** that receives the failure list (measured on the render where one exists). A pre-render failure (validation, or a TTS timeline that cannot pass) uses the same single repair. At most 2 model calls a day for the native Short, because a deterministic fix cannot shorten a sentence without cutting it |
| D3 | Where the first word sits | **0.15 s** (`LEAD_S`): the TTS lead is trimmed by input seek. Because 0.30 s is the limit and a few frames of measurement jitter must not fail a compliant Short |
| D4 | Hold after the last word | **2.5 s** (`HOLD_S`), and the Short is padded to 20 s when shorter. Because the rule is "takeaway by duration − 2 s" and the same jitter argument applies |
| D5 | How first speech / takeaway end are measured | **The later of** whisper's word time and the energy onset/offset of the encoded audio (`silencedetect` at **−45 dB, 0.10 s**). Because whisper clamps the first word to 0.00 s (measured: 0.00 vs a real 0.18 s onset). Without whisper, the planned TTS timings re-anchored on the measured onset (`tts+silencedetect`) |
| D6 | Native layout | Headline in the crop Short's hook band (top y = 192 = 0.10 × 1920, width 960 = 1080 − 2 × `HOOK_MARGIN`, at most 2 lines, as `shorts._wrap_hook`); the diagram fills the stage 60 px below the headline down to the approved y 1150; a native compare **stacks** its two sides. Because at a 60 px floor two side-by-side 390 px columns cannot hold common words ("thousands" overflowed) |
| D7 | Text that does not fit at 60 px | **A repairable failure, never a demotion** (storyboard demotes to a statement; the native has no smaller fallback that keeps the rules) |
| D8 | Watermark | **Kept**: the control's 42 px top-left channel name. It is not essential text (outside the 60 px rule) and round 3's long-form rules allow a non-obstructive watermark; keeping it means the arms differ only in the package |
| D9 | Captions | **Same pass as the control** (68 px, `max_words=3`, `margin_v=620`) — mute viewers, and 68 ≥ 60 |
| D10 | "Pointing" motion | Each diagram label's 240 ms highlight (G.1's) plays when its cue word is spoken, only inside [2.0 s, duration − 2 s − 240 ms]. No reveal, no entrance, no beat change |
| D11 | Numbers in the native script | Every number on screen or spoken must appear in `gates.fact_sources(script)` + the long-form narration (already fact-checked). Diagram labels and the headline must pass G.1's grounding gate against the native narration |
| D12 | "Same question" | `same_question` when every diagram label passes G.1's grounding gate against the **crop control's own excerpt narration** (the writer is handed that excerpt and its hook); otherwise `concept_family` |
| D13 | Native title | Its own script's `title` (≤ 60 chars, hype-screened) + ` #Shorts`; the headline otherwise. `step8_meta` only knows the long-form |
| D14 | Production day D | The UTC date of the long-form publish slot. The pair index counts recorded production days, not calendar days |
| D15 | After 6 assigned days | **The pilot stops assigning** (`pilot_b_batches: 1`). The native Short keeps replacing the storyboard slot, its slot chosen by G.1's day-of-year parity, with no experiment fields. Batch 2 = the owner sets `pilot_b_batches: 2` (a new recorded draw). Because round 3 makes a second batch a decision after reading the first |
| D16 | Pilot slots unavailable | (18:45 not ≥ 20 min ahead, or the long-form date moved) → the normal grid, pair recorded unevaluable "pilot slots unavailable" |
| D17 | Ledger fields | Long-form row (PUBLISHED only): `experiment: "pilot_b"`, `pair_id: "B1-01"…`, `arm: "native@18:45" \| "native@01:30" \| "native_skipped@…"`, `slot`: the native's slot. Shorts rows: `{url, engine, slot}` with `slot` "HH:MM" UTC. **Pilot A owns the long-form row's fields on a day both run** (it is the long-form's own experiment); Pilot B's pairing is always complete in `state/pilot_b.json` and the Shorts rows |
| D18 | Readout input | One Studio CSV per pair, `B<batch>-<nn>.csv`, exported on D+8 or later covering D..D+8 (the 01:30 Short then has 7 full days); optional `B<b>-<nn>_feed.csv` filtered to the Shorts-feed traffic source for the guardrail. Any other CSV in the folder is a fallback, labelled "combined export (window not per pair)" |
| D19 | Exposure-weighted aggregate | Σ(stayed × feed impressions) / Σ feed impressions per arm. The outlier test checks both the median and the weighted advantage |
| D20 | Shorts per day with the native on | Exactly 2 (native + control), whatever `shorts_per_day` says, because the pilot is a pair |
| D21 | Reels switch default | `reels_native_only: true` — the row's rule is the default; off restores "the first Short" |

## API finding: stayed to watch is not in the APIs

Checked 2026-11-04 on the official docs:

- YouTube Analytics API metrics (<https://developers.google.com/youtube/analytics/metrics>):
  `engagedViews` exists ("viewed past the first frame, or the user clicks/taps to play"). There is
  **no** "stayed to watch", "shown in feed", feed-impression or swiped-away metric; `impressions`
  is the deprecated ad-impression metric.
- Dimensions (<https://developers.google.com/youtube/analytics/dimensions>): `creatorContentType
  = SHORTS` and traffic source `SHORTS` ("referred by swiping vertically…") exist; nothing about
  impressions.
- Revision history (<https://developers.google.com/youtube/analytics/revision_history>):
  `engagedViews` added 2025-03 for the old Shorts view method; reach reports gained
  `video_thumbnail_impressions` on 2026-01-15; no Shorts-feed impression or stayed-to-watch entry.
- Reporting API (<https://developers.google.com/youtube/reporting/v1/reports/channel_reports>,
  <https://developers.google.com/youtube/reporting/v1/reports/metrics>): `channel_reach_basic_a1`
  has `video_thumbnail_impressions` ("thumbnail shown for more than 1 second…"); the docs do not
  say it covers the Shorts feed.
- Studio's definition (<https://support.google.com/youtube/answer/12220281>): "Stayed to watch:
  the percentage of times viewers stayed to watch past the initial seconds of a Short", under
  Analytics → Content → Shorts; the expanded report (Advanced mode) can export.

So the numerator is in the API but the denominator is not. **The readout reads CSVs the owner
exports from Studio.** It also accepts a CSV without the stayed column and reconstructs it as
engaged views / shown in feed (Studio's own definition, which round 2 checked exactly on 5 Shorts).

### Owner export steps (per pair, on D+8 or later)

1. Open the pair's two Short ids: `py -3 -m factverse.pilot_b status` lists the recorded days;
   `state/pilot_b.json` holds each pair's `native.url` and `crop.url`.
2. studio.youtube.com → **Analytics** → **Advanced mode** (top right).
3. Date range → **Custom**: D to D+8.
4. Filter **Content type: Shorts** (optional: filter the two videos).
5. Metric columns → add **Shown in feed**, **Stayed to watch (%)** and **Engaged views** (add
   **Watch time (hours)** too).
6. **Export** (download icon) → **Comma-separated values (.csv)** → unzip → take
   `Table data.csv`, rename it `B1-01.csv` (the pair id) and put it in one folder, e.g.
   `output/pilot_b/`.
7. Guardrail (optional): same steps with the filter **Traffic source: Shorts feed** → save as
   `B1-01_feed.csv`.
8. `py -3 -m factverse.pilot_b readout output/pilot_b`

The readout finds columns by name (`Content`, `Shown in feed`, `Stayed to watch`, `Engaged views`,
`Watch time (hours)`), case-insensitive, and skips the `Total` row. **The exact Studio column
names are unverified until the first real export** (there is no Studio session in this phase).

## Files changed

- `factverse/native_short.py` (NEW): prompt, validation/coercion, board, TTS, mux/caption args,
  encoded-file measurement, gate, one repair, `make()`.
- `factverse/pilot_b.py` (NEW): state + merge, assignment, composition, ledger fields, record,
  Studio CSV readout, CLI (`schedule`, `readout`, `status`).
- `factverse/storyboard.py`: `render_meta` (metadata, `demote_unfit=False`), `NATIVE_MARK`,
  `engine_of` → `"native"`.
- `assets/storyboard/storyboard.html`: board `floor`, a headline band, stacked compare,
  `__minSize()`, `__shown(t)`.
- `factverse/shorts.py`: `storyboard=` override, `last_windows`.
- `factverse/scheduling.py`: `pilot_b_slots`, `slot_label`.
- `factverse/ai_pipeline.py`: `_s1_native_day`, `_s1_native_title`, pinned slots, Shorts rows
  `slot`, `pilot_b.record`, `**_s1_ledger` on `record_run`.
- `factverse/reels.py`: native-only pick, `reels_native_only`.
- `factverse/learn.py`: `native` engine collected and shown.
- `factverse/state_merge.py` + `.github/workflows/publish.yml`: `state/pilot_b.json` (both halves).
- `config.json`, `config.example.json`: the four switches.
- `tests/test_s1_native.py` (NEW, 66 tests); `tests/test_pipeline_logic.py`: three older Reels
  tests now state the pre-S.1 rule they test (`reels.native_only` stubbed off).

## Verification

**One native Short rendered end to end** through `native_short.make()` (scratchpad
`s1_render.py`): a hand-written fixture model answer (no LLM key locally), real edge-tts
(`en-US-GuyNeural`), the real Chromium renderer, mux, caption pass, and the encoded-file
measurement with faster-whisper (installed in a scratch venv; CI has it).
Artifacts: `output/demo/s1/final/` (`native_short.mp4`, `report.json`, `f0_00.png`,
`f2_00.png`, `f7_00.png`, `flast.png`).

| measured on the encoded mp4 | value | rule |
|---|---|---|
| duration (ffprobe) | 24.500 s, 1080×1920, 30 fps, h264 + aac | 20–28 s |
| first speech | 0.182 s (energy onset; whisper said 0.00) | ≤ 0.30 s |
| sentence 1 end (13 words) | 3.64 s | ≤ 5.00 s |
| answer (sentence 1) end | 3.64 s | ≤ 7.0 s |
| qualification (sentence 4) end | 16.24 s | ≤ 22.5 s |
| takeaway end | 21.237 s | ≤ 22.5 s |
| words | 61 script / 61 whisper | ≤ 65 |
| smallest text | 60 px (headline 82 px) | ≥ 60 |
| fully drawn at 0.0 s / 2.0 s | 7/7 and 7/7 | all |
| gate | `[]` (pass), attempt 1, match `same_question`, render 30.3 s | |

Frames read: 0.00 s — headline + both cards complete; 2.00 s — identical diagram, caption only;
7.00 s — "cores" highlighted on the two left labels as spoken; last second — the final visual
held, every label pointed at, no caption.

The validator was exercised for real first: the first fixture (75 words) was refused with
"75 spoken words (max 65)" and repaired once; the second (side-by-side compare) was refused with
"text does not fit at 60px". That is what led to D6.

**Pilot B, 6 days through `assign` → `plan_day` → `pilot_b_slots` → `record`**
(`output/demo/s1/pilot/pilot_b_demo.txt`): the draw gave native 18:45 first; B1-01..B1-06
alternate 18:45/01:30 (native 3×/3× per slot); every ledger dict is as in D17. The readout over
Studio-format fixture CSVs prints every pair, flags B1-05 "below 100 feed impressions"
(reported, not zeroed), shows medians 27.9% / 18.0%, +8.4 pts, 4 of 5 wins, weighted
25.8% vs 19.2%, the without-B1-01 line, guardrail "not available", and the verdict
"audience effect unresolved (fewer than 6 evaluable pairs)". Read on 2026-11-12 every pair is
"observation window open (provisional)".

**Suite: 516 passed** (2026-11-04, full `py -3 -m pytest tests/ -q` on the branch, 133 s).
The first full run had 3 failures, all older Reels tests asserting "the first Short is posted"
with crop-named fixtures; they test posting mechanics, so they now stub `reels.native_only`
off (the B.5 precedent), and the native-only rule has its own test.

## Known limits

- **The prompt first meets the real model in CI.** No Gemini key locally: the render used a
  hand-written answer. The first CI logs show `🧩 Native Short:` or `↻ native short attempt`.
- **Layout capacity is tight.** At 60 px, a stacked compare holds a title + 2 short items per
  side only with a one-line headline; a two-line headline leaves room for about title + 1 item.
  The fit check and repair enforce it; the cost is skips, measured in CI.
- **CI uses Kokoro, the local render used edge-tts.** Kokoro's lead differs; D3 trims it. CI
  render time is unmeasured (local: 30.3 s render + whisper).
- **"Represented visually by 0:07" is structural**: the whole diagram is on screen from frame 0.
  Nothing checks semantically that the diagram depicts the answer.
- **Stayed to watch is manual** (API finding). Studio's export column names are unverified.
- **The storyboard engine does not run while `native_shorts` is on**, so G.1's storyboard-vs-crop
  pairs stop accumulating.
- **Fewer Reels**: a day without a native Short posts none (row 15's rule).
- Noticed, not fixed (outside scope): `ai_pipeline.synthesize_voice`'s ElevenLabs branch returns
  a bare path, not `(audio, words)`; the caller unpacks two values. The flag is off.

## Traps found (proposed for CLAUDE.md)

- **Whisper clamps the first word to 0.00 s.** A "speech starts by X" check needs the energy
  onset of the encoded audio (`silencedetect`); take the later of the two.
- **A text-size floor changes the layout, not just the font.** Side-by-side columns that work at
  44 px cannot hold ordinary words at 60 px. The fit check is the authority, and for a format
  with a hard floor an unfit board is a repairable failure, not a silent demotion.
- **Experiment fields reach `record_run` as one dict.** `record_run(..., **_s1_ledger)` plus a
  second `experiment=` keyword is a TypeError inside the double-publish window. Pilot A must
  merge into the same dict.
- **A random draw in tracked state is first-writer-wins.** `pilot_b.merge` keeps origin/main's
  draw; a list union would raise on the dict, and "ours wins" would re-assign days already
  published.
- **Git Bash heredocs eat backslashes even with `<<'EOF'`.** `\\` + newline became a line
  continuation and `"\\n"` a real newline in two patch scripts here. Edit with the Edit tool.

## Done when

- [x] Native Short rendered end to end, frames at 0 / 2 / 7 s / last second read, timings
      measured from the encoded file, gate passes.
- [x] Pilot B schedule for 6 days printed; readout run over fixture CSVs.
- [x] Full suite green; branch pushed.
- [ ] First CI day: the native Short renders (or logs its skip reason) and `state/pilot_b.json`
      lands on main with B1-01.
- [ ] Owner exports the first pair's CSV on D+8 and confirms the column names.
