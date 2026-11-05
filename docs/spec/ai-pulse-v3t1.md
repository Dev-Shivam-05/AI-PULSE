# Spec — v3-T.1: ToolDojo Live Trials (12-minute vertical live test show)

Status: **locked** for the values marked *locked*; every other value is a **delegated decision**
listed with its default and the reason, for the owner's one word. The owner chose this show on
2026-11-04 after the ChatGPT round `docs/debate/2026-11-04-tooldojo-live-stream-ideas/`
(RESULT.md rows 1-16, `02_chatgpt.md` §2, `03_chatgpt.md` §2-§5) and said go.

## Why this phase exists

1. Tool videos are 53.6% of long-form views and search is 82% of long-form traffic. An archive
   titled with the exact tool name keeps earning from search (RESULT row 1).
2. No ToolDojo video has ever shown a tool **tested** on fixed inputs with checks a viewer can
   repeat. The tool lane records README pages (P.1 "why").
3. The node (v3-N.1) can run one unattended command in a schedule window. This phase is that
   command: `scripts/trials_live.py`.

## The integrator's decision (owner to confirm)

The round preferred **local CPU execution** for the first episodes (row 15). The channel's
2026-11-04 growth contract (row 4, source (b)) forbids running untrusted package code without
containment: a gVisor-class sandbox, zero network, 2 CPU / 2 GiB / 120 s run, 300 s job. The
node is a Windows Home PC on the owner's home network, so that containment cannot be met there
today. **Therefore T.1 runs every trial against the tool's own HOSTED demo (a Hugging Face Gradio
Space), driven headlessly the way P.1's evidence engine drives one. No candidate code ever
executes on the node.** The on-screen source label is **"Hosted test"** (P.1 `evidence.LABELS`).
The first task family is **speech to text** (K.1: the only family with ≥ 3 comparable CPU Spaces).

Local execution stays **off and unbuilt**. Its admission gates are below (§ Later phase).

## Locked decisions (from the round)

| # | Decision | Value | Source |
|---|----------|-------|--------|
| L1 | Show | One named tool per episode, fixed inputs, real execution, deterministic checks, scorecard, honest verdict. **12 minutes.** | row 1 |
| L2 | Slot | **Saturday 18:45-18:57 UTC.** The live replaces the 18:45 Short. | row 14 |
| L3 | Format | **Vertical** 1080×1920, **Stacked** layout, text **64 / 80 / 96 px** (essential / heading / principal score), measured after the final transform. | row 6 |
| L4 | Narration | Prepared in advance in **4 branches**: pass / partial-fail / timeout / inconclusive, chosen only after the result is known. Persistent disclosure **"Prepared narration • Tool execution and scores live"**. | row 5 |
| L5 | Scoring | Counts ("7/8 checks passed; one timed out"), never percentages. A broken checker never defaults to PASS. Vocabulary PASS · PARTIAL/FAIL · TIMEOUT · INCONCLUSIVE. | row 16, R3 §2 |
| L6 | Variation | Every episode changes its question, inputs, checks, findings and limitations. Swapping the tool name over the same narration is forbidden. | row 16 |
| L7 | Viewers | Native reactions only, never presented as votes. No poll. | row 7 |
| L8 | Tool selection | Hard gates: ₹0, deterministic checks, no clicks, all 4 branches rehearsed. Then rank: exact-name search movement → a real release in the last 30 days → 7-day star growth. GPU-only or OS-level tools are not live (an edited explainer instead). | row 13, R3 §5 |
| L9 | Episode B | "Same task, two tools" is an episode type inside Trials, only when the comparison is honest (same inputs). | row 2 |
| L10 | Live day | The news Short is dropped (3 notifications / 24 h). No recap upload in the archive's first 72 h. | rows 8, 9 |
| L11 | 14-day test | Two episodes. Better than baseline: archive AVD > 1:02; stretch 2:00. Stop: both < 0:45 with ≥ 25 views each. Concurrency and subscribers are signals only. | row 12 |
| L12 | Run of show | R3 §2's fixed grid (below); repeat the first failed test, else the declared control; keep both results. Two consecutive execution failures → the prepared "test incomplete" ending. | R3 §2, R2 §2 |

### The grid (`trials_live.GRID`, 720 s, every segment an even length for the 2 s GOPs)

| Window | Time | Shows |
|---|---|---|
| `open` | 00:00-00:30 | Clip 1 and our **preflight result**, labelled "PREFLIGHT RESULT · hh:mm:ss UTC · BEFORE THE STREAM"; "LIVE RERUN STARTING". Narration says it is not today's result. |
| `rules` | 00:30-01:00 | The question, the test (4 clips, known transcripts, 2 checks each, 60 s per run) and the configuration (its own HF demo, hardware, "not a laptop test"). |
| `result1` | 01:00-01:30 | The fresh baseline rerun: replay, marked transcript, checks ticking, branch. |
| `run2..4` | 01:30, 03:30, 05:30 (90 s) | The clip, why it matters, the replay of the run recorded during this stream, the transcript, the checks ticking. |
| `result2..4` | 03:00, 05:00, 07:00 (30 s) | The test's branch and the running count. |
| `repeat` | 07:30-09:00 | The repeat (first failed test, else clip 1), both results on screen. |
| `verdict` | 09:00-10:00 | Scorecard per test, verdict branch, "N/8 CHECKS". |
| `files` | 10:00-11:00 | The results-sheet link — only when it really published. |
| `limits` | 11:00-12:00 | Limitations and the takeaway; the stream ends. |

## Delegated decisions ("default chosen: X, because Y")

| # | Decision | Default chosen | Because |
|---|----------|----------------|---------|
| D1 | **WER pass threshold** (owner word needed) | **0.15**: a clip passes "word errors" when errors ≤ floor(0.15 × reference words) — 1 error for 12-13 words, 2 for 14. Shown as a count ("ERRORS 1 · MAX 1"), never a percentage. | No spec has it (K.1 left it open). 0.15 lets one slip in a 13-word sentence but not two; the key-word check catches the slip that matters. Measured: 16 real runs, every clean clip 0 errors, the noisy clip 1 error on VibeVoice ("trip" → "trick"). |
| D2 | Checks per clip | Exactly 2: **key words heard** (2 per clip, all must appear) and **word errors within the allowance** → 8 declared checks per episode. | Two independent, deterministic checks; the key word is the one error a reader cannot afford ("room four" → "room for", "cache" → "cash"). |
| D3 | Normalisation | Lower case; apostrophes and punctuation dropped; digits read as words (`9:15` → nine fifteen, `4` → four, `4th` → fourth, `2,450` → two thousand four hundred fifty); `%` → percent. Word-level Levenshtein; ties keep a right word right. | Printed on the results sheet so a viewer can repeat the count by hand. |
| D4 | Run deadline | **60 s** per run, page load to result (`RUN_SECONDS`). Past it after submit = TIMEOUT; before submit = INCONCLUSIVE. | Measured 2.6-6.4 s from upload to text on both Spaces; 60 s covers a cold Space without stalling the grid. P.1's 120 s is a capture deadline, not a test window. |
| D5 | When runs execute | During the broadcast, each no earlier than **120 s** before the window that first shows it (`RUN_LEAD_SECONDS`); the replay is labelled with its own run time ("RUN RECORDED 18:47:05 UTC · THIS STREAM"). | A segment must be rendered before it airs; the round's "live" is "executed during the event", and the label makes the lead visible. |
| D6 | Status order | unavailable / quota / sleeping → INCONCLUSIVE; deadline after submit → TIMEOUT; tool error → PARTIAL/FAIL; output unreadable or a checker raised → INCONCLUSIVE; all checks true → PASS; else PARTIAL/FAIL. | Execution failures are never scored; a checker failure is never a pass (L5). |
| D7 | Verdict | All 4 PASS → PASS; any PARTIAL/FAIL → PARTIAL/FAIL; else any TIMEOUT → TIMEOUT; else INCONCLUSIVE. The repeat is shown beside, never substituted. | R3's vocabulary applied to the episode; "preserve both results". |
| D8 | Incomplete ending | After two consecutive TIMEOUT/INCONCLUSIVE runs, testing stops; the remaining run/result windows and the repeat are dropped and the show goes to verdict → files → limits, so it ends **before** 12:00. | R2: "the prepared 'test incomplete' ending rather than prolonged filler". |
| D9 | "Materially varied" gate | Refused when the question or the fixture set repeats an earlier episode, or when the **investigation** narration (open, rules, run2-4, limits — not the fixed branch vocabulary) overlaps an earlier episode's by more than **0.5** (word 4-gram Jaccard). | Measured on the two sets: different set 0.33-0.37, name swap over the same set 0.88. R3: "standardize the evidence standards; vary the investigation". |
| D10 | Fixtures | 2 sets × 4 clips (`voice-notes`, `dev-commands`), roles control / ordinary / complication / boundary, self-generated with Edge TTS voices (en-US, en-GB +35%, en-AU +35%, en-IN / en-IE under ffmpeg pink/brown noise at 5 dB SNR, one at -18 dB), 16 kHz mono WAV, 4.0-5.3 s, sha256 in `sets.json` and checked before every show. | Licence-clean (no third-party recording), under the 30 s cap of the tightest Space, known transcripts. Two sets = the two pilot episodes; a third needs a new set (the gate refuses a reused one). |
| D11 | Tool registry | The 3 K.1 Spaces (`microsoft/vibevoice-asr-bitnet-demo`, `k2-fsa/automatic-speech-recognition` pinned to "English", `istupakov/onnx-asr`) plus tool-lane feed items whose task family is speech-to-text and whose README links a Space. Demand signals read from: YouTube exact-name search terms (analytics `search_terms`, two windows), the GitHub latest release, GitHub stargazer timestamps (7 d vs the 7 d before). Missing data ranks after any measured value, never as zero. | Row 13's order. Today no search data exists, so the choice is labelled "exploratory: unvalidated demand" (R3 §5). |
| D12 | Hardware gate | `cpu-basic` or `cpu-upgrade` only. | ₹0 to us and no ZeroGPU quota (K.1: anonymous ZeroGPU is ~2 GPU-min/day per IP). |
| D13 | Layout (1080×1920) | brand + score y36-92 (40 px); disclosure y104-152 (36 px, one line, floor 30); tool name y196-292 (80 px, floor 64); question y296-444 (64 px: the full question, else the episode's short form); evidence card y456-930 (replay box 720×405 at x180 y512); output card y946-1342 (transcript at 64 px, 4 lines); score y1354-1534 (two 64 px check rows, or 96 px label + 64 px count); captions y1540-1692 (64 px, 5-word phrases). Labels (brand, disclosure, card headers, badge) are the 30-40 px source-label tier. | R2's zones are "approximately"; the transcript needed four 64 px lines. The label tier follows P.1 D12 (≥ 32 px source label). |
| D14 | Delivered size | Rendered at 1080×1920 always; `TOOLDOJO_STREAM_PROFILE=720p30` (the node's i3 choice) scales the encode to 720×1280 at 8000 kbps. Only libx264 (`TOOLDOJO_ENCODER` other values are logged and ignored). | The px floors are measured on the 1080 page; a 720 scale keeps proportions (64 px → 43 px at 720 wide, ~21 px at a 360 px phone either way). |
| D15 | Live-day Short | On a Saturday with `trials_live` on, the Short slotted at **18:45 UTC** is not uploaded; the 01:30 Short stays whatever its lane. | Saturday is the evergreen lane (B.5), so its Shorts are non-news unless a hot story took the day. Shorts are excerpts of the day's long-form, so "make the retained Short non-news" (R3 §4) cannot be done by topic allocation; owner may say otherwise. |
| D16 | No recap in 72 h | No recap uploader exists. Implemented where a recap could appear: the tool lane skips a candidate whose URL or name is a Live Trials tool within `recap_not_before` (start + 72 h), read from `state/trials_episodes.json`. | The only path that could publish a near-duplicate of the episode. |
| D17 | Results sheet | `docs/trials/<date>-<tool>-<set>.html`, HTML only, every value escaped, every href through `site.safe_link`; committed by the node through the GitHub Contents API with `TRIALS_GITHUB_TOKEN` (contents:write on this repo). The node never edits its own checkout. The `files` window shows the link only when the commit succeeded; otherwise its prepared "did not publish" branch. | Pages serves docs/ verbatim; a link that does not exist must never be shown. |
| D18 | State | Node-local `output/trials/episodes.json` (gitignored) is the planner's history; `state/trials_episodes.json` is the published copy (no narration, no local paths) that CI reads for D16. CI never writes it, so it needs no stash/`state_merge` entry. | Both-halves trap: only a file the CI run WRITES needs the treatment. |
| D19 | Stream key | `YT_TRIALS_STREAM_URL` / `YT_TRIALS_STREAM_KEY` in the node's `.env`, rtmps://*.youtube.com only (radar_live `valid_ingest`), redacted in every log line. | A vertical stream is its own YouTube stream. |
| D20 | Start | The node job passes no arguments; the script connects at **18:45 UTC** (`--start-at` default) after preparing (measured ~80 s: plan, preflight, 40 voiced lines in parallel, first renders). Ready later than 18:50 → skipped, exit 0. | The node's `lead_seconds` is 300. |
| D21 | Kill switches | `trials_live` (config, default **false**) gates the show AND the Short drop; the node row `live_trials` ships `enabled: false`. | No key exists yet; dropping a Short with no live would lose a publication. |
| D22 | Narration | `factverse.llm` rewrites the template line by line when a key exists; each line must pass `text_ok` (word budget per window, no hype, no hosted overclaim, no number outside the grounding) or keeps the template. With no key the template runs (the verified path). | The show must run with no LLM at all. |
| D23 | Music | radar_live's bed: the day's shuffled playlist normalised to -36.8 LUFS under -19.8 LUFS speech (L6 row 10). | Same measured mix as Radar Live. |

## Node contract (v3-N.1)

Job row (in `config.json` and `config.example.json`, shipped disabled):
`{"name":"live_trials","enabled":false,"stream":true,"cmd":["{python}","scripts/trials_live.py"],"days":["sat"],"start_utc":"18:45","lead_seconds":300,"slot_minutes":12,"min_minutes":12,"max_minutes":30,"hang_seconds":300,"pulse_file":"logs/trials_live.log","attempts_per_day":2,"remaining_arg":"","radar_profile":false,"env":{}}`

- Exit 0 = done for the slot (aired, skipped, switched off, not a Saturday). Non-zero = a failure
  worth a retry; a retry after 18:50 skips itself (D20).
- Heartbeat: `logs/trials_live.log` gets a line at least every 60 s (`heartbeat`).
- Headless: Playwright headless; `CREATE_NO_WINDOW` on every ffmpeg child the script starts.
- No new dependencies (playwright, edge-tts, requests, Pillow are already required).

## Later phase: local execution (NOT built) — admission gates

Local CPU execution may be built only when **all** of P.1's (b) gates hold
(`docs/spec/ai-pulse-v3p1.md` § (b)): a separate disposable runner plus a gVisor-class sandbox;
non-root, read-only base, restricted scratch; pinned, hash-checked, binary-only acquisition with
no candidate code during acquisition; **zero network** during install and run; CPU-only offline
quickstarts from constrained templates; **2 CPU, 2 GiB RAM**, 128 processes, 512 MiB scratch,
250 MiB dependencies; acquisition 120 s, install + run **120 s**, whole job **300 s**; 1 MiB log
and 50 MiB artifacts handled as untrusted; success = exit 0 **and** an independent output check.
Additionally for Trials: the runner must not be the home node (a Windows Home PC on the owner's
LAN cannot isolate a candidate from the LAN), and the on-screen label becomes "Sandbox test".

## Episode B ("Same task, two tools") — admission rule built, run-of-show not built

`trials.comparison_honest(a, b)`: the same fixture set (same inputs and checks), two different
tools, both on free CPU hosting. R2's B grid (alternating order, equal budgets) is a later phase;
when a comparison cannot fit honestly, B does not run (R3 §2).

## Files changed

- `factverse/trials.py` (new): checks (`normalize`, `align`, `checks_for`, `test_status`,
  `verdict`, `tally`, `repeat_choice`, `incomplete`), fixtures (`load_sets`, `fixture_ok`,
  `make_fixtures`), planning (`space_facts`, `upload_plan`, `gate`, `rank_key`,
  `search_movement`, `release_days`, `star_growth`, `feed_candidates`, `plan_episodes`,
  `comparison_honest`), hosted runs (`drive_upload`, `run_test`, `capture_cut`,
  `evidence_record`), narration (`template_narration`, `llm_narration`, `text_ok`,
  `materially_varied`, `investigation_text`), record + sheet (`render_sheet`, `public_record`,
  `publish_files`), pipeline hooks (`skip_short_slot`, `recap_blocked`, `recap_not_before`),
  `fourteen_day_readout`.
- `scripts/trials_live.py` (new): the producer process, window specs, encoder args with the
  capture overlay and output profile, the sender (radar_live's `Streamer`, `remux`, `preroll`,
  `redact`, `valid_ingest` imported), `--dry-run` rehearsal, heartbeat.
- `assets/trials/trials.html` (new), `assets/trials/fixtures/speech-to-text/` (new: `sets.json`
  + 8 WAVs).
- `scripts/radar_live.py`: `Renderer(page, size)` and `extra_times` in `frames()` (5 lines).
- `factverse/ai_pipeline.py`: `_trials_skip_short` in the Shorts upload loop and
  `_trials_recap_blocked` in the tool-candidate loop (lazy import, never raise).
- `config.json`, `config.example.json`: `trials_live: false`, `node_jobs` row.
- `.gitignore`: `output/trials/`.
- `tests/test_t1_trials.py` (new).

## Verification

Measured 2026-11-05 on the laptop, against a local RTMP listener (ffmpeg). Nothing reached YouTube.

**Run 1 (before the fixes below):** 730 s, 13 windows, 1 hold, 0 restarts, exit 0. Its frames found
the defects listed under "Found by reading the frames".

**Run 2 (`1a8c85a`, the verification run):**

| Check | Result |
|---|---|
| Airtime | 720 s exactly: 13/13 windows, **0 holds, 0 restarts**, exit 0 |
| Received stream | 1080×1920, 21,600 frames, decode 0 errors |
| Timestamps | 1 anomaly: a 56 ms video step at 599.99 s (the verdict → files seam), keyframe gaps 1,977 / 2,000 / 2,023 ms |
| Bitrate | 561 kbps (static pages); the profile's ceiling is 14,000 kbps |
| Loudness | whole show −23.5 LUFS, peak −3.9 dBFS, LRA 20.2 LU. Most-voiced windows −19.9 to −21.4 LUFS; music alone −36.9 LUFS (run 1's hold) |
| Real runs | 5 on `k2-fsa/automatic-speech-recognition`: 4 PASS, **1 real TIMEOUT** (test 3: no result inside 60 s; the same clip took 2.5 s in run 1) |
| Branch shown, with its reason | TIMEOUT, 6/8: "No check failed, but test(s) 3 did not finish within 60 s." on the sheet; "6/8 CHECKS PASSED; ONE TIMED OUT" on air |
| Results sheet at 390 px | scrollWidth 390, read in full. Not published (local run) |
| Heartbeat | longest gap between log lines 60 s (N.1's hang limit is 300 s) |
| 720p profile | the real encoder with a capture overlay gives 720×1280, frame read. Not timed on the node |

**All four result branches, through the real segment path (no stream):** one mixed episode (PASS,
PARTIAL/FAIL, TIMEOUT, INCONCLUSIVE, repeat of the failed test) rendered through
`Producer.render_window`; frames read; `unfit` empty for all 10 windows. PARTIAL/FAIL and
INCONCLUSIVE have never aired, and the test-incomplete ending is verified by logic only.

**Found by reading the frames, fixed and test-pinned:**

1. A check's value ("KEY WORDS 2/2", "ERRORS 0") and the running score were on screen before the
   replay, so the show announced each result before running it.
2. The first segment rendered was fitted before the fonts had loaded, then drawn in the real font:
   the hold card's disclosure lost its last characters.
3. Fit was measured on `display:none` elements, which measure 0 and always "fit": the repeat's
   sub-line was clipped while reporting no problem.
4. A 10 s hold card aired at 1:30, every episode. 21 of the 38 s a 90 s window took to render were
   per-second screenshots of a page with no moving clock. `frame_times` draws only the moments the
   page can change (107 → 31 shots; 90 s window now ~24 s).
5. A timed-out test's sheet entry said "39.5 s from upload to result", when there was no result.
6. The final count changed colour between the verdict and the files/limits windows.

## Open: the show is mostly still (v3-T.1b, not built, needs the owner's word)

Measured on run 2, PASS narration: **182 s of voice in 720 s (25%)**, and **401 s of the show sit in
stretches of 15 s or more where nothing on screen changes**; the longest is 62 s (`repeat`), and
each run window ends on 49-60 s of one static frame. **The viewer also never hears a clip**: the
input is shown as text only. The show is stable, but this is likely to cost the L11 retention
target (archive AVD > 1:02). Proposed, keeping the locked 12-minute grid:

| # | Change | Value |
|---|---|---|
| 1 | Play the real fixture in every run window, after its narration | the committed WAV at the speech level, −19.8 LUFS (L6 row 10), bed unchanged |
| 2 | Narrate up to the budgets already in `WINDOW_SPEECH` | run 40 s (today 17-20 s), repeat intro 26 s (today 10 s) |
| 3 | Reveal the transcript word by word beside the reference, each word marked as it lands | one word every 0.5 s |

Target: voice ≥ 50% of the show, no unchanged stretch over 15 s.

## Known limits

- **Two fixture sets = two episodes.** The third show is refused until a new set is committed.
- Every completed test so far PASSES on both drivable Spaces (the only non-pass in the verification
  runs was a timeout): the fixtures may be too easy to separate tools. Harder fixtures must still
  be fair; that is an editorial call for the owner.
- `repeat_choice` repeats the first PARTIAL/FAIL, else the control, per R3's wording. So a TIMEOUT is
  not repeated; run 2 re-ran the control instead of the clip that timed out.
- The render headroom is measured on the laptop only. On the node's i3 a window may land late, and
  a hold card then airs; more than 120 s of holds ends the show.
- 561 kbps is far below the profile's ceiling. Whether YouTube warns about it is unknown until the
  private rehearsal.
- `istupakov/onnx-asr` is listed but not drivable: its simple tab returns a dataframe (headless
  Chromium crashed on it in the prototype) and the generic plan picks its VAD tab, whose button
  is hidden behind a tab. Its preflight fails (INCONCLUSIVE in 49 s) and the next candidate runs.
- No exact-name search data exists yet, so every pick is "exploratory: unvalidated demand".
- The replay is of a run executed up to 120 s earlier in the same stream, not a real-time
  screen; the label says when it ran.
- Hosted runs measure the Space, not the tool on the viewer's machine (`site.NOT_ESTABLISHED`).
- Whether a SCHEDULED vertical stream appears in the vertical live feed once live is unknown
  (13822251 wording; RESULT "Points still open").
- The 14-day readout needs the archive AVD/views typed in or read from analytics; no collector
  is wired to it yet.
- The phone rehearsal of the Stacked layout (row 6 "verify on a real phone") is the owner's.

## Done when

- [x] Suite green with the new tests.
- [x] One real episode streamed for 12 minutes to a local RTMP listener; frames read; loudness
      measured; branch shown with its reason.
- [x] Results sheet rendered and read at 390 px.
- [ ] Owner: vertical stream key in the node's `.env`, `TRIALS_GITHUB_TOKEN`, `trials_live: true`,
      the node row enabled, a private rehearsal on YouTube, the phone check.
