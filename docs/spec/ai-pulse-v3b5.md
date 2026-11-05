# Spec — v3-B.5: daily lane mix, evergreen subject screen, no-loop recordings

Status: **locked**. The owner approved the 2026-11-01 review's point 16 ("go for all", 2026-11-01)
and raised the looping recording in the same message. The values below are the brief that
session locked; this file was written on 2026-11-01 by the session that verified and pushed it.

Source of the decisions: `docs/debate/2026-11-01-radar-live-growth-review/RESULT.md` row 16, and
the owner's message: *"if you are recording any GitHub repository, so in that the same video is
coming in loop… uske liye kuch karna ho toh kar dena"*.

## Why this phase exists

1. **Recordings looped.** `screencap._record_page` scrolled to the bottom, smooth-scrolled back
   to the top and repeated, so a short README produced the same footage over and over.
   `capture()` cut the recording into `k = min(n_scenes, total//4)` equal chunks BEFORE the
   narration existed; `step5_build` then `-stream_loop`ed any clip shorter than its slot, and
   when k < n consecutive scenes reused the same chunk. `REC_MAX = 300` at `WPS = 2.4`
   under-estimated real narration (median script ~761 words).
2. **The daily mix.** Long-forms made 537 views in 30 days against 7,772 for Shorts. The one
   long-form above 100 views was a tool video (RemoveMacAI, 252). News won the viral judge on
   most weekdays.
3. **Evergreen repeated itself.** 8 of the last 13 evergreen titles were two subjects (LLM
   internals, AI hardware).

## Locked decisions

| # | Decision | Value |
|---|----------|-------|
| 1 | Browse plan | GitHub repo: README page → `/releases` → `/issues` → `/commits`. HF model: card → `/tree/main` → `/discussions`. Any other URL: the page only (`screencap.browse_plan`). |
| 2 | Scroll | Down only, at the existing reading rhythm. At the bottom, or when the page's share is spent, go to the next page. Never scroll back up. |
| 3 | Page share | `page_budget = remaining / pages_left`, so a short page hands its unused time on. |
| 4 | Redirected sub-page | Not recorded (`landed_on`): a repo with Issues off redirects `/issues` to the README. A 404 page is skipped. |
| 5 | Page-load blank | Trimmed per page (measured head), as before. |
| 6 | Pages exhausted early | Hold the last frame. Never loop. |
| 7 | Recording length | `WPS = 2.0`, `REC_MIN, REC_MAX = 60, 480` s. |
| 8 | Cut after timings | `capture()` returns the full trimmed recording plus provisional clips. `screencap.recut` runs in `run()` after `inject_cards`, `inject_code_card` and `inject_receipt_clip`, right before `step5_build`. |
| 9 | Piece size | Exactly the share `step5_build` gives that clip: `durs[i] / len(scene_clips[i])`. Pieces are sequential and non-overlapping. |
| 10 | Short recording | Uniform `setpts` stretch, at most `MAX_SLOW = 1.35`; any remaining gap is a held frame (`tpad stop_mode=clone`), `TAIL_PAD = 0.5` s margin. `-stream_loop` therefore never triggers for a recording piece. |
| 11 | Recut failure | All or nothing: the provisional clips stay and the run logs `⚠️ recording recut failed`. Fail soft (`None`), never a raise. |
| 12 | Thumbnail | Still taken from the first page. |
| 13 | Lane mix (automatic runs only) | Sun roundup (unchanged) · Wed debate when `debate_format` and the panel hold, else the tool rule · Sat evergreen · Mon/Tue/Thu/Fri tool when a tool signal exists, else evergreen. |
| 14 | News | No longer a daily contender. A story with `viral >= VIRAL_THRESHOLD` may take any non-Sunday slot at most `NEWS_PER_ISO_WEEK = 1` time, judged from `PUBLISHED` ledger rows with `format == "news"` in the same ISO week (never a log line). The week check runs first, so a week that had its news day spends no viral-judge call. |
| 15 | Kill switch | `"lane_mix_v2": true` in `config.json` and `config.example.json`. Off = the previous behaviour exactly. Owner-forced formats, the fallback chain and `MAX_DAY_ATTEMPTS` are unchanged. |
| 16 | Evergreen subject screen | Lowercase, simple plural stem, drop the `EVERGREEN_STOP` generic words. Families: `llm` = {llm, transformer, large language model, language model}; `hardware` = {cpu, gpu, chip, hardware, npu, tpu}. A candidate sharing **≥ 1** subject term with any evergreen PUBLISHED in the last `EVERGREEN_SUBJECT_DAYS = 30` days is skipped. |
| 17 | Trial length | 4 weeks from the first CI run with `lane_mix_v2` on. |

## Files changed

- `factverse/screencap.py`: `browse_plan`, `landed_on`, `page_budget`, `recut_plan`,
  `stream_loops`, `_join_args`, `_piece_args`, the down-only `_browse`, `_record_pages`, `recut`;
  `WPS`, `REC_MAX`, `MAX_SLOW`, `TAIL_PAD`.
- `factverse/ai_pipeline.py`: `subject_terms`, `recent_evergreen_titles`, `subject_clash` in
  `pick_evergreen_topic`; `news_published_this_week`, `_lane_mix_v2` behind the flag; the
  `screencap.recut` call before `step5_build`.
- `config.json`, `config.example.json`: `lane_mix_v2`.
- `tests/test_b5_daily.py` (new, 30 tests); `tests/test_pipeline_logic.py`: two older evergreen
  tests now stub the ledger read (see Verification).

## Verification

**Suite: 426 passed** (2026-11-01, full `py -3 -m pytest tests/ -q` on the branch).

The first full run had 2 failures: `test_evergreen_topic_rejects_a_reworded_repeat` and
`test_evergreen_dedup_separates_a_reword_from_a_new_subject`. The new subject screen reads the
REAL ledger through `learn.read_runs`, and the real published "The Chip Revolution" and LLM
evergreens blocked those fixtures' "AI Chips" and "Transformers" ideas. The screen was right;
the tests now stub `ap.learn.read_runs` because they test the used-topics re-word check.

**Real capture + recut** on `https://github.com/omlahore/removemacai`, a fake 6-scene script with
scene shares totalling 302.5 s (`output/demo/b5/measure.json`, frames and contact sheet beside it):

| scene | share (s) | source span (s) | slow | probed (s) | loops |
|---|---|---|---|---|---|
| 1 | 40.0 | 0.000 + 9.080 | 1.35 | 40.5 | 0 |
| 2 | 65.0 | 9.080 + 14.755 | 1.35 | 65.5 | 0 |
| 3 (slot 1) | 27.5 | 23.835 + 6.242 | 1.35 | 28.0 | 0 |
| 4 | 70.0 | 30.077 + 15.890 | 1.35 | 70.5 | 0 |
| 5 | 50.0 | 45.967 + 11.350 | 1.35 | 50.5 | 0 |
| 6 | 50.0 | 57.317 + 11.350 | 1.35 | 50.467 | 0 |

The frames were read: README top → install → how it works → star history → releases →
commits, each piece starting where the last ended. No page appears twice and nothing loops.

**Evergreen screen measured on the real ledger** (100 published, 13 evergreens in the last 30):

| date | title | verdict against evergreens published in the 30 days before |
|---|---|---|
| 08-23 | AI Watermarks: Can You Trust Them? | passes |
| 08-24 | How Large Language Models Actually Think | passes |
| 08-27 | LLMs: How AI 'Thinks' Without A Brain | blocked on `llm` |
| 08-30 | Large Language Models: How They REALLY Think | blocked on `llm` |
| 09-01 | AI Creates Art: Your Job Safe? Faster | passes |
| 09-06 | Stable Diffusion: Million Images Trained | passes |
| 09-11 | AI Image Generators: The 5 Billion Image Secret | blocked on `image` |
| 09-13 | AI Agents Gone Rogue: Scenarios | passes |
| 09-14 | AI Agents: Rogue Revolution or Automation's Future? | blocked on `agent` |
| 09-16 | AI's Real Impact: Industries Transformed | passes |
| 09-18 | Open vs Closed AI: Your Guide | passes |
| 09-24 | LLMs: How Billion Parameters Understand You | blocked on `llm` |
| 09-26 | AI Agents Go Autonomous: The Unseen Risks | blocked on `agent` |
| 09-27 | LLMs: How AI Truly Thinks | blocked on `llm` |
| 10-08 | LLM Inner Workings: How Trillion Parameters Learn | blocked on `llm` |
| 10-09 | AI vs. Human Creativity: The Real Winner | passes |
| 10-10 | AI Hardware: Why CPUs Fail at AI | passes |
| 10-13 | AI Agents: Your Digital Butler Gains Autonomy | blocked on `agent` |
| 10-15 | AI Art vs. Human Art: Understand the Creative Engines | passes |
| 10-16 | AI Beyond ChatGPT: Unlock Industry Transformations | blocked on `industry` |
| 10-17 | LLM Explained: Your AI Brain Decoded | blocked on `llm` |
| 10-19 | LLMs Explained: How AI 'Thinks' With Data | blocked on `llm` |
| 10-21 | Beyond CPUs: Specialized AI Hardware Explained | blocked on `hardware` |
| 10-22 | LLM Mechanics: How AI Learns to Think | blocked on `llm` |
| 10-26 | The Chip Revolution: Making AI Think Faster | blocked on `hardware` |
| 10-28 | Voice AI: How Assistants Hear You | passes |
| 10-30 | LLM Thinking: Transformers Explained | blocked on `llm` |

All 8 repeats named in the brief are caught. Creativity, art, voice AI and the first hardware
title still pass. "AI Beyond ChatGPT" is blocked on `industry`; that is a real subject repeat
of "AI's Real Impact: Industries Transformed" 30 days earlier.

## Known limits

- **A short README is mostly a held frame.** The real recording above was 68.7 s across its
  pages for 302.5 s of slots. At the 1.35 cap that is 92.7 s of motion, so about **69% of the
  recording's screen time is a still frame**. It is no longer a loop, but it is static. A fix
  needs a decision this spec does not hold (more pages, other footage, or fewer recording
  slots), so it is a follow-up, not a tweak.
- The lane mix's effect is unmeasured until 4 weeks of CI runs exist (row 17).
- The recording's real duration on CI is unmeasured; the first tool day's log shows it.

## Done when

- [x] The suite is green with the new tests (426).
- [x] A real capture + recut produced pieces at their exact shares with 0 loops, and the frames
      were read.
- [x] The subject screen was measured on the real ledger.
- [ ] The first CI tool day logs a recut and no `⚠️ recording recut failed` line.
- [ ] 4 weeks of the mix, then read the scoreboard per format.
