# AI Pulse — phase board

One phase per session. A phase that isn't pushed doesn't exist.

| Phase | Scope | Status | Branch / notes |
|-------|-------|--------|----------------|
| v2 Foundation → live channel | pipeline, gates, CI publishing | ✅ done | on `main`, publishing daily |
| **v3-A: utility pivot core** | tool signals (GitHub/HF/PH), tool format behind `tool_format` flag, viral threshold 8, 900-word cap + cut-don't-pad, blocked-day fallback, caption force-align |  ✅ done 2026-08-22 (26/26 tests) | merged to main (PR #22); spec: docs/spec/ai-pulse-v3.md |
| **v3-B: original-visuals engine** | `screencap.py` (record → measured head trim → per-scene chunks, fail-soft), Pygments code cards, screenshot tool thumbnails, HF raw-README grounding, `_CARRY` rewrite fix, CI chromium + cache + `format` dispatch input, `tool_format: true` | ✅ done 2026-08-22 (47/47 tests; live E2E 10/10 real-UI frames; pushed) | `v3-phase-b` → PR pending merge; first tool video = supervised CI dispatch |
| **v3-C: income + packaging** | cheat-sheet PDF per tool video (`deliverable.py`, GitHub Pages), description rebuilt around the transaction (🔧 + 📄 + `promo_block` above the fold), README/PLAYBOOK/STATUS rewritten for v3 | ✅ done 2026-08-22 (63/63 tests; PDFs rendered + read; pushed) | `v3-phase-c` (stacked on `v3-phase-b`) → PR pending; needs Pages enabled once |
| **v3-C.1: tool-lane pre-flight hardening** | adversarial audit of the never-run `format=tool` path: suitability screen (`gates.tool_unsuitable`), 1200-char grounding floor, HF model-card grounding, double-publish window closed, `tags` coercion, full command on the cheat sheet, CI state-save on a feature branch, `GH_TOKEN` for the veto window | ✅ done 2026-08-23 (75/75; 10 defects, each reproduced then fixed) | `v3-phase-c`; spec: docs/spec/ai-pulse-v3c1.md |
| **v3-C.2: story-lane hardening** | the C.1 treatment applied to news / evergreen / roundup: story lanes stop drawing from tool signals, grounding floor = the fact-checker's own 200-char skip, roundup gates read the fetched text and span every story, outlet diversity, `source_chip`, full source list in the description, whole-script advice gate, near-duplicate evergreen topics at 0.7, unraisable `record_run`, honest veto window | ✅ done 2026-08-23 (93/93; 12 defects, each reproduced then fixed; verified against live signals) | `v3-phase-c`; spec: docs/spec/ai-pulse-v3c2.md |
| **v3-C.3: render-surface hardening** | the C.1/C.2 treatment applied to everything DOWNSTREAM of the script: stat cards rendered to their real slot and never rewriting their own number, caption phrases that stop overlapping, Shorts hooks fitted by measurement, `normalize_moments`, thumbnail text measured against the frame, `l2.splice` reporting failure, `l2_usage`/`stock_ledger` surviving the CI state-save, a scene keeping its duration when a clip fails | ✅ done 2026-08-24 (112/112; 10 defects, each reproduced then fixed; 27 candidates found, 15 refuted; artifacts rendered and inspected) | `v3-phase-c`; spec: docs/spec/ai-pulse-v3c3.md |
| **v3-C.4: tool suitability screen precision** | the never-reviewed `UNSUITABLE_TOOL` list measured against live feeds, 28 flagship tools and 11 defensive tools: prose words (`bypass`/`crack`) screen the title only, subject terms exempt a defensive reading, repo punctuation normalises, GitHub grounds on the raw README while the screen still reads the page | ✅ done 2026-08-24 (117/117; 5 defects, each reproduced then fixed; verified against live network) | `v3-phase-c`; spec: docs/spec/ai-pulse-v3c4.md |
| **v3-E: receipts + packaging precision** | the 12-rank gap audit vs Hyperautomation Labs, code side: `verified_facts` (stars/size/license fetched per candidate, fed to writer + cards + thumb), command-containment gate (deliverable.text must be a substring of the README), packaging-payoff gate (every number in title/thumb must be spoken in narration), limitation scene grounded in the repo's top GitHub issues, `receipts.py` (safe CI checks: pip download timing/size, registry lookups → 'Checked by <channel> on <date>' beat + real terminal footage), declarative numeric thumb contract, deterministic tool chapters, per-lane pinned comment (command + PDF link), PDF upgraded to HAL-style field guide (per-item stars/license/'Honest:' line), post-rename brand asset regen ('AI YOU CAN USE'), ElevenLabs seam behind a flag for the 10-video verdict window (~$11 once, Creator first-month; fail-soft to kokoro) | ✅ part 1 done 2026-08-24 (129/129; 11 review findings fixed; artifacts inspected: PDF receipts line, ToolDojo bumpers, live API fetches) | `v3-phase-c`; spec: docs/spec/ai-pulse-v3e.md |
| **v3-E.2: receipts.py** | safe CI check-execution (download-only: wheels via `--only-binary :all:` `--no-cache-dir`, shallow clone, wall-clock+size-capped fetch — candidate code never executes), 'Checked by ToolDojo on <date>' narration beat on the install scene (before `packaging_payoff`, so its numbers support the thumb), real terminal footage rendered to its exact slot share, `receipts` ledger column | ✅ done 2026-08-24 (137/137; live cold check openai 3.3.1 + frames inspected twice — 1st inspection caught 3 defects incl. the tofu ✔; 70-agent adversarial review: 9 root-cause defects + 5 upheld splits, all fixed & test-pinned, incl. an unbounded fetch that could hang both cron firings and an LLM-plantable `script["receipts"]` in the double-publish zone) | `v3-phase-c`; spec: docs/spec/ai-pulse-v3e2.md |
| **v3-F.1: the site** | `factverse/site.py`: one HTML page per tool video + regenerated index + sitemap, rendered from `state/tools_index.json` (in `state_merge.FILES` with its own union-by-`page` semantics AND the publish.yml stash list); the description's 📄 line now links the PAGE, not the PDF; `deliverable.sheet_for` feeds both from one extraction | ✅ done 2026-08-31 (161/161; site rendered and screenshotted at 1280/390 — 2 defects found by inspection and fixed; then a 2-lens adversarial review found 9 reproduced defects, all fixed and test-pinned, incl. a planted `cheat_sheet` that survived the LATER rewrite passes and shipped in the published description, an unchecked `javascript:` href on our own Pages origin, and one bad file freezing the index forever) | `v3-phase-f` (stacked on `v3-phase-c`); spec: docs/spec/ai-pulse-v3f1.md; needs the Pages click to go live |
| v3-F.2: Telegram channel bot | the day's video + command + page link pushed to a Telegram channel (bot token in Actions secrets), fail-soft | ⏳ queued | needs a bot token; the page's OG card is what it will render |
| v3-F.3: X free tier | one post per video off the same catalog row | ⏳ queued | free tier is ~500 posts/mo — enough for 1/day |
| v3-F.4: IG/FB Reels | the existing Shorts re-used as-is via the Graph API | ⏳ queued | platform order per audit wf_5c0e184c |
| v3-D: learning loop v1 | feed runs.jsonl + analytics.jsonl into topic/packaging choices (AVD ≥2:00 is the target metric) | ⏳ queued | needs ~2 weeks of v3 data first — **counted only from 2026-08-24**: owner disclosed pre-that analytics are ~94-98% self-generated views (different accounts/IPs), so every earlier row (incl. the 0:38 AVD baseline) is directionally useful but numerically invalid |

## Now (owner, in this order)
0. **Stop the self-views today — permanently.** Artificial traffic (own views via different
   accounts/IPs) violates YouTube's fake-engagement policy; the penalty ladder ends at channel
   termination, which ends the whole 1-2yr hands-off plan. It also poisons the exact metric
   (AVD) every v3 decision is keyed on. No purge needed — just stop; from today the analytics
   start meaning something. Real organic baseline ≈ 2-6% of 2,220/28d ≈ 45-130 views — that is
   a NORMAL day-30 channel, not a failure.
0.5. **Rename the channel to "ToolDojo" BEFORE the first format=tool dispatch** (approved
   2026-08-24; owner delegated the pick). Verified 2026-08-24: @tooldojo free on YouTube,
   GitHub and X; Google SERP for "ToolDojo" has NO product, channel or company (only the
   retired word-order-reversed "Dojo Toolkit" JS library); no live site on
   tooldojo.com/.ai/.co/.in. The 11-agent audit killed all five dictionary compounds
   (ToolProof/ProofStack/RunProof/ToolTested/StackProof — each has live exact-name
   incumbents). Steps: Studio → rename channel + claim @tooldojo; then config.json
   `channel_name` + `youtube_channel_name` = "ToolDojo"; brand asset regen is a v3-E row.
   Grab tooldojo.in (~Rs 300/yr) whenever convenient — not a blocker.
1. Merge the branch stack IN ORDER — each is stacked on the one before it:
   PR #23 (`v3-phase-b`) → `v3-phase-c`
   (https://github.com/Dev-Shivam-05/AI-PULSE/pull/new/v3-phase-c) → `v3-phase-f`
   (https://github.com/Dev-Shivam-05/AI-PULSE/pull/new/v3-phase-f). test.yml runs the
   161-test suite on each PR automatically.
2. Enable GitHub Pages: Settings → Pages → Deploy from branch → `main` / `docs`. Until this is
   done every cheat-sheet link AND every tool page 404s. After the first tool run, `curl -I`
   BOTH the page and the PDF: they share a stem, so one 200 + one 404 means the naming drifted.
   If the page is stale after a run, `GITHUB_TOKEN` pushes did not trigger the Pages build and
   it needs the Actions-based deploy instead of branch-deploy (a small F.1b row).
3. **`gates.UNSUITABLE_TOOL` has now been measured and fixed** (v3-C.4) — it was refusing
   ComfyUI, unsloth, transformers, the official C2PA SDK/CLI, two deepfake detectors, two NSFW
   classifiers and NeMo-Guardrails, while the day's live provenance stripper passed its title
   screen. One editorial row is left for you: decision 6 makes `voice clon` match READMEs, so a
   legitimate open TTS project that calls itself voice cloning (F5-TTS, RVC, XTTS) is now
   refused. That is the existing policy without its spelling hole, not a new policy — say the
   word and it is one tuple edit. `captcha solver` / `anti-detect browser` were measured as
   passing and deliberately NOT added (C.1 fenced widening as out of scope).
4. Supervised first tool run — Actions tab → "AI Pulse — Auto Publish" → Run workflow →
   format = `tool`, BEFORE 12:23 UTC (5:53 PM IST) so the day's cron no-ops afterwards. Watch the
   log for "Screen-recorded visuals", "Tool thumbnail", "Cheat sheet:"; then check the YouTube
   description (🔧 and 📄 blocks under paragraph 1) and `curl -I` the PDF link.
   Also expect, and read, any of: `⛔ Skipping tool candidate`, `↻ grounding too thin`,
   `↻ tool is not something this channel teaches`. Those are the new screens working, not errors.
   A forced `tool` run has **no evergreen fallback** — if a gate blocks it, the day publishes
   nothing. That is deliberate for a supervised run.
5. On the FIRST unattended day after the merge, watch the log for the v3-C.3 lines that mean the
   new screens are working, not erroring: `↻ Scene N: k clip(s) failed — re-timing …` (a scene
   keeping its slot) and `⚠️ No usable Shorts moments returned` (a malformed LLM answer that used
   to kill the whole render). Then read the new ledger column `grounding_chars` and watch for two
   v3-C.2 side effects: `↻ grounding too thin — trying the next story` (the story
   lanes now refuse a page the fact-checker cannot check) and any `ADVICE_BLOCKED` row (the
   advice gate now reads the whole script, so expect more LLM confirmations). Both are the new
   screens working; only a repeat pattern means the thresholds are wrong.

6. **Record the next weekly L2 batch** (`l2_store/cold_opens/`, `l2_store/insight_blocks/`).
   All 8 clips in the store are marked used, so `l2.inject` is currently a no-op and every video
   ships with no human take. v3-C.3 fixed the two defects that were waiting on the other side of
   that — a failed splice used to burn a clip and fake the originality record, and CI reverted
   `l2_usage.json` on every run — so the store can now be refilled safely.

## Next 3
1. **v3-F.2 — Telegram channel bot.** The natural next build: the tool page already emits the
   OG card Telegram renders, so the remaining work is a bot token in Actions secrets, a
   fail-soft `notify.py` seam, and one post per published video (title + command + page link).
   Needs no Pages click to develop — only to look right when clicked.
2. v3-D — learning loop v1 once ~2 weeks of post-2026-08-24 analytics exist (target: AVD ≥ 2:00);
   the ledger now carries `packaging`, `grounding_chars`, `receipts` and `tool_page` columns.
3. v3-B.1 (only if the first CI tool runs show it) — capture hardening from real logs: PH/HF page
   quirks, CI chromium sandbox, recording length vs 900-word scripts. On the first live tool run,
   also read the receipts log line (🧾 worked / ↻ not checkable / ⚠️ failed — all three still
   ship a video; only a repeating ⚠️ across days means a threshold is wrong) and the site line
   (🌐 Page: <url> worked / ⚠️ site page failed — the video still ships either way).
