# HANDOFF — ToolDojo — Phases v3-R.2, R.3, R.4 (recovery cohort) — 2026-11-12

## Done
- **R.1 diagnosis.** Fresh Studio data, the frames of 4 real videos and a 2-round ChatGPT Pro review. The owner locked D1-D14 ("Go for all"). The round folder is untracked in the main checkout.
- **R.2 cohort launch.** With `recovery_cohort` on:
  - Long-forms go public on Mon/Wed/Fri only, from 2026-11-16. The check uses the publish day, not the run day.
  - Every other lane is paused, including through fallbacks. A day with no qualified candidate publishes nothing.
  - The six queue topics run first, gpu-unlock first.
  - A tool with no demo takes the documentation route: an on-screen chip from 0:00 plus a description line.
  - No sting, no cold open and no stat-card counter.
  - One native Short goes out the next day at 18:45 UTC, with no crop Shorts. Its style failures warn after one repair.
- **R.3 answers and visuals:**
  - `factverse/replies.py` answers every genuine viewer question within 24 h, from the video's own sources. The first CI run answers the RTX 50 comment (A1).
  - `answer_line` is description line 1 and leads the channel comment.
  - Packaging: the title names the tool and the thumbnail carries the answer. The critique pass is skipped and the packaging restored after the length passes.
  - Footage is phone-readable stills: 1920x1080 frames with 48 px text and no scroll. With no readable visuals the video is not published.
  - A 168 h Short family cooldown.
  - Abstract stock queries are replaced with concrete ones.
  - The README sections that answer the queue question are appended to the grounding.
- **R.4 read.** `factverse/cohort.py` collects first-7-day retention curves (cohort plus the 11 baseline videos), and `python -m factverse.cohort` writes the day-14 / day-21 report with the D14 verdict. W0 = 13 min, recomputed from real data.
- **Verification:**
  - Tests: 915/915.
  - A real readable-stills capture of gpu-unlock produced 26 stills, 81 s, 1920x1080 @ 30 fps; the frames were read.
  - On the real gpu-unlock README, exactly the Windows and RTX 50 FAQ entries are picked.
  - The docs chip frame was rendered and read.
  - The assembled prompt and description were read.
  - An independent review found 9 issues; all were fixed and test-pinned, or recorded below.
- **Commits:** 17 on `v3-phase-r2` (including this handoff fix). **Not pushed:** the Claude OS guard hook blocked `git push`, so the owner pushes.

## Files changed
- `factverse/ai_pipeline.py` — cohort schedule, lanes, queue, docs route, prompt contract, rewrite-pass handling, render, Shorts slot and cooldown, answer line, packaging fixer, README sections, concrete queries.
- `factverse/evidence.py` — `docs` source, cohort-scoped D4 labels, docs brief, chip label, over-claims, description line.
- `factverse/native_short.py` — D8 style warnings on the lenient last attempt, asterisk strip.
- `factverse/shorts.py` — hook asterisk strip.
- `factverse/screencap.py` — readable stills mode (`_shoot_pages`, `stills_list`, `first_page_url`).
- `factverse/replies.py` (new) — D11 replies.
- `factverse/cohort.py` (new) — R.4 reads and report.
- `factverse/analytics.py` — `cohort_reads` hook.
- `factverse/state_merge.py` — `state/replied.json`.
- `.github/workflows/publish.yml` — replies step and stash entry.
- `state/replied.json` (new, `{}`).
- `config.json`, `config.example.json` — `recovery_cohort`, `cohort_start`, `cohort_queue`, `comment_replies`, `cohort_reads`.
- `.gitignore` — `output/cohort/`.
- Tests: `tests/test_r2_cohort.py`, `tests/test_r3_answers.py`, `tests/test_r4_read.py`, `tests/conftest.py`.
- Docs: `docs/spec/ai-pulse-v3r.md`, `docs/PHASES.md`, `docs/DECISIONS.md`, `CLAUDE.md`.

## Decisions made
- **The R.2 claim of a "latent P.1 hole" was wrong.** It is corrected in DECISIONS and in a CLAUDE.md trap.
- **The cohort skips `critique_pass` and the query-map retitle.** Both rewrite the answer-first packaging.
- **Within the cohort, no readable visuals means nothing is published** (D8: readable evidence is render integrity). There is no fallback to a scroll or to stock.
- **The docs route blocks first-person testing claims only.** Attributed claims are allowed.
- **Replies need literal `true` booleans**, and links, domains, handles and bait are refused.
- **Implementation values** (chip 7 s, 1,500 README chars, stills, replies limits, read window) are in the spec's "Implementation values" table.

## Known broken / deliberately skipped
- **D7 reserve of 3 pre-rendered videos is NOT built.** CI keeps nothing between runs, so reserves would have to live on the channel as private uploads. That is an owner decision. Its no-filler half is built.
- **A2 is the owner's to do.** Both the browser and API routes were refused by the permission classifier. Paste this in Studio on video 4MTEDi4MdnQ:
  - **Title:** "gpu-unlock for GeForce RTX 20/30/40 on Linux: What It Claims and How to Install".
  - **Description first paragraph** (replaces the current one): "Correction (Nov 2026): gpu-unlock is Linux-only. Per the project, RTX 30 is stable, RTX 20 and RTX 40 are experimental, and RTX 50 (Blackwell) is not supported. A separate third-party Windows port exists; ToolDojo has not tested it or the tool. This video walks through the project's own install steps; the speed figures are the author's claims, not our measurements."
- **A1:** D11 answers the RTX 50 comment automatically on the first CI run after the merge (`comment_replies: false` turns that off). The owner may also answer it by hand first.
- **Not observed in production yet:**
  - the first cohort run (Mon 2026-11-16);
  - the first live reply;
  - the first `cohort_reads` collection: whether the Analytics API still returns the baseline's October 7-day curves is unverified until it runs.
- **Shorts stayed-to-watch is Studio-only.** The day-21 Shorts read needs the owner's CSV (`video,feed_impressions,stayed_pct`).
- **Leftovers:** the Studio browser profile in the old scratchpad, the untracked round folder, the stale main checkout and old worktrees (`git worktree remove <path>`, never `--force`).

## Next session starts here
- **Phase:** none to build. Owner: push `v3-phase-r2`, open and merge the PR before Monday 2026-11-16, do A2, and decide on D7. Then read Monday's CI log for:
  - `📘 No demo evidence` / `📖 Readable stills` / `🧩 Native Short`;
  - the `COHORT_*` ledger rows;
  - `💬 replies`.
- **First command:** `/boot` from `E:\YOUTUBE\AI-PULSE-r2` (or from main after the merge).
- **Watch out for:** a `VISUALS_BLOCKED` row means the readable-stills browser failed in CI. The 14:53 cron retries, but two in a row means the CI browser needs a look, not a fallback to stock.
