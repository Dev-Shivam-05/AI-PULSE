# HANDOFF — ToolDojo — Growth programme (P.1, P.2, S.1, M.1, K.1, N.1; T.1 in progress) — 2026-11-04

## Done
- **One branch carries everything: `v3-growth-1104`.** It contains `v3-integration-1101` (B.5, L.6), which was never merged, so the owner opens ONE PR from it and the 11-01 PR is superseded.
  - Suite: **736 passed** on the merged tree.
  - A read-only `git merge-tree` against `origin/main` is clean, `state/*` included.
  - Each phase branch is also pushed on its own: `v3-phase-{p1,p2,s1,m1,k1,n1}`.
- **What happened this session:**
  - A read-only YouTube Studio extraction covering 311 videos.
  - A 4-round ChatGPT growth review with `prompts/yt-02-11.xml`, with Claude playing the owner. It produced 18 points, and the owner answered "go for all".
  - Five build phases, each in its own worktree, then integration.
  - A 3-round ChatGPT live-stream concept round.
  - The owner then supplied a dedicated PC for live work, which became N.1 and T.1.
- **v3-P.1 (rows 3, 4, 17): a tool video now shows real evidence of the tool working.**
  - Hosted demos: a Hugging Face Gradio demo is driven headless with its own example, with a 120 s deadline and an independent visible-result check.
  - Author demos: a GIF/MP4 committed in the repo under MIT/Apache-2.0, with a rights record and an attribution line in the description.
  - The evidence leads scene 1, with a "Hosted test" / "Author demo" label and five statuses with verbatim wording.
  - A candidate without admissible evidence is skipped.
  - Unobserved outcome claims in a title or thumbnail become "Claimed …" or are dropped.
  - Live on 11-04: 3 of 27 trending candidates had admissible evidence.
- **v3-P.2 (rows 5, 6, 13): opening contract, Pilot A, query-map packaging.**
  - The opening contract is checked on the ENCODED file:
    - result at 0.00 s covering ≥ 40% of the frame;
    - speech by 0.5 s;
    - first sentence ≤ 16 words, finished by 6.5 s;
    - limitation by 0:15;
    - first step by 0:25;
    - no sting and no L2 cold open;
    - duration 150-210 s.

    One repair is attempted, then the lane falls back.
  - A context-first arm exists for comparison.
  - Pilot A: 6 pre-assigned pairs, with retention read via `audienceWatchRatio`. The frozen AVD baseline is **72.0 s**.
  - Packaging: query-map titles, a first description sentence of tool + task + evidence status, and descriptive chapters.
  - Frames read: 0:00 shows the hosted result with "Hosted test · 2026-11-04"; 0:15 shows the starting-step card.
- **v3-S.1 (rows 7, 8, 15): native concept Short and Pilot B.**
  - A native concept Short replaces the storyboard Short. Rendered and frames read: 24.5 s, speech at 0.18 s, answer at 3.6 s, 61 words, 60 px text, the full diagram at frame 0.
  - Pilot B: native vs crop, 6 day-pairs, slots 18:45 / 01:30 alternated. Stayed-to-watch is in no public API, so the readout reads a Studio CSV export.
  - Reels carry the native Short only.
- **v3-M.1 (rows 9, 10, 16, 18): memory, north star, shadow queue.**
  - A per-video memory record; the writer now outputs `question_answered` / `questions_open`.
  - Per-video search terms. A follow-up candidate fires at ≥ 50 search views in 28 days, with a 14-day cooldown.
  - North-star ladder (12.11 h → 1,211 h) and search capture by age band.
  - A 14-day shadow queue for a second daily slot.
  - learn's long-form comparison now starts 2026-08-28.
- **v3-K.1 (rows 11, 12, 14, 15): task catalogue and distribution.**
  - `task_family` on every tool entry and ledger row.
  - A hub page per family, only when ≥ 2 hosted tests share an identical input (max 1 hub).
  - "Follow this task" alerts, only on a material change.
  - Useful tool pages, X off by default, Search Console meta-tag support, and the Challenger spec (K.2, queued).
  - The first family by evidence supply is speech-to-text: ≥ 3 comparable CPU Spaces.
- **v3-N.1: the dedicated live PC ("node").**
  - A ZIP plus `install.ps1` creates a hidden user and a startup task that runs in session 0, so no window ever appears.
  - `supervisor.py` runs the job table: power-cut resume, hang kill, backoff, disk guard, self-update with rollback, and a Telegram alert.
  - The preflight picks the stream profile.
  - Verified only by a 130 s supervisor run with fake jobs and an installer `-DryRun`. NOT run on the real node.
- **Docs:**
  - Board rows: P.1, P.2, S.1, M.1, K.1, K.2 (queued), N.1, and T.1 (in progress).
  - X fixed in Now #1.4.
  - Decisions for the growth review, the live round and N.1.
  - 12 new traps in CLAUDE.md.
- **ChatGPT round folders (local only, never committed, because they hold Studio analytics and the repo is public):**
  - `docs/debate/2026-11-04-tooldojo-channel-growth/`
  - `docs/debate/2026-11-04-tooldojo-live-stream-ideas/`, which picked **Live Trials**.

## Files changed
- **New factverse modules:** `evidence.py` (P.1); `opening.py`, `pilot.py`, `querymap.py` (P.2); `native_short.py`, `pilot_b.py` (S.1); `memory.py`, `northstar.py`, `shadow.py` (M.1); `tasks.py` (K.1).
- **New node files (N.1):** `node/` (supervisor, preflight, install/uninstall/status ps1, requirements-node.txt, README) and `scripts/build_node_bundle.py`.
- **`factverse/ai_pipeline.py`:**
  - evidence in `script_tool`;
  - `_CARRY` and the pop list;
  - the render block extracted to `_render_longform` / `_make_extras`;
  - the opening gate;
  - one merged experiment dict in `record_run`;
  - memory fields and `task_family`.
- **Other edits:**
  - `factverse/gates.py`: substantiation.
  - `site.py`: catalog evidence and hubs.
  - `notify.py`: task alerts, X off by default.
  - `shorts.py`, `storyboard.py`, `scheduling.py`, `reels.py`, `analytics.py`, `learn.py`, `l2.py`, `state_merge.py`.
  - `scripts/radar_live.py`: small and env-gated.
  - `.github/workflows/publish.yml` and `notify.yml`: stash lists.
  - Both config files.
- **New tracked state:** `state/pilot_a.json`, `pilot_b.json`, `first_seen.json`, `shadow_queue.jsonl`, `notified_tasks.json`. All are in `state_merge.FILES` (18 entries) and in the stash lists.
- **Tests:**
  - New: `tests/test_{p1_evidence,p2_opening,s1_native,m1_memory,k1_catalogue,n1_node}.py`.
  - `tests/conftest.py` pins every new default-on switch OFF.
  - Small edits in `test_pipeline_logic.py`.
- **Specs:** `docs/spec/ai-pulse-v3-growth.md` (the programme and the shared evidence interface), plus `ai-pulse-v3p1/p2/s1/m1/k1/n1.md`.
- **Docs:** `docs/PHASES.md`, `docs/DECISIONS.md`, `CLAUDE.md`, this file.

## Decisions made
- **Every value the debate did not fix was delegated.** Each is recorded in its phase spec as "delegated — default chosen: X, because Y". Counts: P.1 26, P.2 32, S.1 21, M.1 20, N.1 25, and several in K.1. The owner has not confirmed them.
- **Evidence beats coverage.** A tool day without evidence falls back to another lane, and most days will until supply grows.
- **Source (b), running candidate code, is not built anywhere.** Its containment gates cannot be met on GitHub runners or on Windows Home. That is also why T.1 tests HOSTED demos rather than local CPU runs, which changes the ChatGPT round's plan and is pending the owner's confirmation.
- **When both pilots run on the same day,** Pilot A owns the long-form row's experiment fields.
- **X is off by default** because it is now pay-per-use ($0.20 per post with a URL).
- **The node runs as a hidden standard user in session 0,** not as SYSTEM and not with S4U.
- **One integration branch,** so the owner opens one PR.

## Known broken / deliberately skipped
- **v3-T.1 Live Trials is NOT finished.**
  - At session end the agent had 5 commits on `v3-phase-t1`: `d5ee39c` trials, `8a3e680` trials_live, `7a33d1a` pipeline hooks, `3313c3d` tests, `25998d5` 720p/heartbeat.
  - It was running its local 12-minute RTMP verification.
  - Its spec, push and merge may be incomplete. It is not in `v3-growth-1104`.
- **Never exercised live:**
  - the LLM writer on the new prompts (no keys locally);
  - all 5 new Analytics API queries;
  - the opening repair against the real model;
  - Kokoro timings (word budgets assume about 2.5 words/s);
  - the node on real hardware.
- **Not built:**
  - the "before you install" verdict (the row 17 exception);
  - the source (b) sandbox;
  - Radar Challenger (K.2);
  - the second upload slot (only its shadow queue exists);
  - "documented requirement changed" alerts (there is no requirements field).
- **Evidence supply is thin:** 3 of 27 candidates, so the tool lane will mostly fall back.
- **Studio CSV column names for Pilot B are unverified** until the first export on D+8.
- **The Studio login profile, which holds cookies, is still in the scratchpad:** `C:\Users\shiva\AppData\Local\Temp\claude\e--YOUTUBE-AI-PULSE\01a5917a-a008-4b2c-b488-d75f3ce6ed07\scratchpad\yt-studio-profile`. Delete it if it is not needed.
- **Leftover worktrees:** `E:/YOUTUBE/AI-PULSE-{gw,p1,p2,s1,m1,k1,n1,t1}` from this session, plus the older `-{b4,b5,g3,g4b,gf,int,int1101,l3,l6,live,wt-main}`. Remove them after the merge with `git worktree remove <path>`, never `--force`.
- **The main checkout `E:\YOUTUBE\AI-PULSE` is still on the stale `v3-gemini-fallback`.** Its untracked `docs/debate/`, `prompts/`, `assets/music/` and `output/*` were left alone.

## Next session starts here
- **Phase:** finish v3-T.1 and merge it into `v3-growth-1104`.
  1. Read the T.1 worktree's log and status, and `docs/spec/ai-pulse-v3t1.md` if present.
  2. Complete one real hosted episode, streamed for 12 min to a LOCAL RTMP receiver. Read its frames and measure loudness.
  3. Push it.
  4. Merge it with the node job row disabled, and run the suite in the background.
  5. Push, and give the owner the single PR link: https://github.com/Dev-Shivam-05/AI-PULSE/compare/main...v3-growth-1104?expand=1
- **First command:** `/boot`, then `git -C E:/YOUTUBE/AI-PULSE-t1 status --short; git -C E:/YOUTUBE/AI-PULSE-t1 log --oneline origin/v3-growth-1104..HEAD`
- **Watch out for:** T.1 must honour N.1's job contract.
  - Exit 0 = done.
  - Heartbeat to `logs/trials_live.log` at least every 300 s.
  - Read `TOOLDOJO_STREAM_PROFILE` and scale to 720×1280 on 720p.
  - Never stream to YouTube, and never install the node on the laptop.
