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
| **v3-F.2: Telegram channel bot** | `factverse/notify.py` + `.github/workflows/notify.yml` (16:55 UTC, after the 16:45 publish slot — the upload is PRIVATE until then): the newest `PUBLISHED` ledger row is posted to a Telegram channel; tool rows carry the command in a tap-to-copy `<code>` block + the F.1 page link, story rows title + video. `state/notified.json` (both-halves treatment) makes it idempotent; `_redact` keeps the token out of a public log | ✅ done 2026-08-31 (180/180; both message bodies rendered and read, live `api.telegram.org` 401 path verified with an invalid token; self-review found + fixed the 4096-char shed order and the `&#x27;` escaping) | `v3-phase-f`; spec: docs/spec/ai-pulse-v3f2.md; **needs 2 Actions secrets + a bot** (5 owner steps in the spec) before it can post |
| **v3-F.3: X (Twitter) free tier** | a second surface inside `factverse/notify.py` off the same ledger row + catalog join, on the same 16:55 UTC workflow: OAuth 1.0a signed on the stdlib (nothing to install, nothing that expires), `weighted_len` for X's 280 *weighted* chars (a URL is 23, an emoji is 2), shed-by-value then a last-resort title cut, `state/notified_x.json` as its OWN both-halves state so Telegram taking a video cannot silently retire it for X | ✅ done 2026-09-01 (196/196; OAuth pinned to RFC 5849 §3.4.1.1 + Twitter's published HMAC vector; three post bodies rendered and read; live `api.x.com` 401 path verified with invalid credentials; the "every seam raises" test found a real fail-soft hole — `enabled()`/`_x_secrets()` sat outside the try and would have failed the workflow) | `v3-phase-f`; spec: docs/spec/ai-pulse-v3f3.md; **needs an X app + 4 Actions secrets** (6 owner steps in the spec) before it can post |
| **v3-F.4: IG / FB Reels** | `factverse/reels.py` + a step in `publish.yml` (NOT notify.yml — `output/shorts/` dies with the runner, so a surface that re-uploads a FILE lives where the file is): the day's first Short becomes one Instagram Reel and one Facebook Page Reel through the official Graph API. Local-binary resumable upload (no public host needed), one long-lived Page token for both, a caption with no YouTube link (so the still-private long-form costs nothing), `state/notified_ig.json` + `state/notified_fb.json` as their own both-halves state | ✅ done 2026-09-01 (217/217; both captions rendered to `output/demo/reels/` and read; live 400 verified on BOTH `graph.facebook.com` and `rupload.facebook.com`, handled, no token in the log; self-review found the token in a GET query string and an unchecked server-supplied `upload_url`, both fixed and test-pinned) | `v3-phase-f`; spec: docs/spec/ai-pulse-v3f4.md; **needs a Meta app + FB Page + Business IG + 3 Actions secrets** (8 owner steps in the spec) before it can post |
| **v3-D: learning loop v1** | measure first, then one guarded lever: a third analytics query for EVERY ledger video (the top-25 report was crowded out by Shorts — 11 of the first 33 v3 long-forms were never measured), `factverse/learn.py` scoreboard per format / hook pattern (views-weighted AVD from the API's per-video seconds, mature at 7 d, trusted at ≥5 videos AND ≥100 views), and a drop rule on the news hook rotation (< 0.5× the best trusted pattern, never below 3 active) with `pick_hook_pattern` re-windowed to `len(active) − 1` | ✅ done 2026-09-26 (228/228; scoreboard read over the real state files AND over an approximation of the real numbers — drops nothing, as designed: long-forms get a median ~4 views) | `v3-phase-d`; spec: docs/spec/ai-pulse-v3d.md; data **counted only from 2026-08-24** (self-view cutoff). The new query is only verified live by the first CI analytics line `… N ledger videos)` |
| **v3-B.1: tool-lane unblock** | diagnosed 2026-09-26 from the ledger (the CI job logs answer 403 without admin rights): the viral judge returns the MAX of 8 scores and it cleared `VIRAL_THRESHOLD` 8 on every weekday (22/22 first attempts since 09-01 were news), and all three blocked-day fallbacks were hard-coded to evergreen — so 0 of 64 published videos were tool. Fix: threshold **8 → 10**, fallbacks try **tool first**, then evergreen, one level only; owner-forced runs keep no fallback | ✅ built 2026-09-26 (231/231; `_fallback_format` truth table + recursion + wiring pinned) — **merge waits for Now #4** | branch `v3-phase-b1`; spec: docs/spec/ai-pulse-v3b1.md; **merges only after one supervised `format=tool` dispatch has published** (Now #4) |
| **v3-G.1: storyboard Shorts** | one of the 2 daily Shorts gets a picture drawn from its own narration: a Gemini storyboard (3-8 beats, 7 templates), a grounding gate (every on-screen number spoken, every element shares a narration word), word-timed reveals, native 1080×1920 rendered by headless Chromium; the other Short stays on today's 405×720 crop as the control; ledger `shorts: [{url, engine}]` + scoreboard A/B pairs | 🔒 spec locked 2026-09-26 — build after B.1 | branch `v3-phase-g` (stacked on B.1); spec: docs/spec/ai-pulse-v3g1.md; verdict after 10 daily pairs: storyboard wins ≥ 8 → G.2 |
| **v3-H: AI debate lane** | Wednesdays: up to 5 models from different labs debate one yes/no question built from the day's story, through their OFFICIAL APIs (free Sep 2026: Gemini + GPT-OSS 120B & Qwen 3.8 on Groq + Nemotron & Inkling on OpenRouter; paid seats pre-wired). Two rounds, verbatim-quote gate, the transcript is the fact-checker's grounding, quote + scoreboard cards, a panel block in the description. Browser automation of consumer AI accounts was evaluated and declined | ✅ built 2026-09-26 (242/242; cards rendered and read in `output/demo/debate/`; live 401 from BOTH Groq and OpenRouter handled as a clean skip) | branch `v3-phase-h` (stacked on B.1); spec: docs/spec/ai-pulse-v3h.md; **needs 2 free secrets** (`GROQ_API_KEY`, `OPENROUTER_API_KEY`) — until then Wednesday runs the normal lane |
| v3-G.2: storyboard long-form | the same engine for long-form scenes (stock only as fallback) + zoomed/highlighted tool-UI callouts | ⏳ conditional | only if G.1's A/B says build |
| v3-G.3: packaging | titles and hooks that sell the ToolDojo promise instead of the viral judge's "fear / outrage" rubric; impressions + CTR data (not in the Analytics API we use) | ⏳ queued | needs its own spec |
| v3-G.4: production basics | 1080p long-form (today 1280×720 x264 ultrafast), a license-clean music bed (`assets/music` is empty and untracked, so CI mixes none), transitions | ⏳ queued | needs its own spec |

## Now (owner, in this order)
0. **Stop the self-views today — permanently.** Artificial traffic (own views via different
   accounts/IPs) violates YouTube's fake-engagement policy; the penalty ladder ends at channel
   termination, which ends the whole 1-2yr hands-off plan. It also poisons the exact metric
   (AVD) every v3 decision is keyed on. No purge needed — just stop; from today the analytics
   start meaning something. Real organic baseline ≈ 2-6% of 2,220/28d ≈ 45-130 views — that is
   a NORMAL day-30 channel, not a failure.
   *2026-09-26: the −47% watch time in Studio is consistent with this having happened.*
0.5. ✅ *Studio shows the channel as "ToolDojo" (screenshot, 2026-09-26); whether the @tooldojo
   handle is claimed was not visible.* **Rename the channel to "ToolDojo" BEFORE the first format=tool dispatch** (approved
   2026-08-24; owner delegated the pick). Verified 2026-08-24: @tooldojo free on YouTube,
   GitHub and X; Google SERP for "ToolDojo" has NO product, channel or company (only the
   retired word-order-reversed "Dojo Toolkit" JS library); no live site on
   tooldojo.com/.ai/.co/.in. The 11-agent audit killed all five dictionary compounds
   (ToolProof/ProofStack/RunProof/ToolTested/StackProof — each has live exact-name
   incumbents). Steps: Studio → rename channel + claim @tooldojo; then config.json
   `channel_name` + `youtube_channel_name` = "ToolDojo"; brand asset regen is a v3-E row.
   Grab tooldojo.in (~Rs 300/yr) whenever convenient — not a blocker.
1. **Merge `v3-phase-d` into main** (v3-D, 2 commits). `v3-phase-f` is ALREADY merged —
   verified 2026-09-26: `origin/v3-phase-f` is an ancestor of `origin/main`. For v3-phase-d,
   `git merge-tree --write-tree origin/main origin/v3-phase-d` exits 0 and main had 0 commits
   the branch lacks on 2026-09-26 — re-run that read-only check before merging, because each
   day's cron adds a state commit. PR: https://github.com/Dev-Shivam-05/AI-PULSE/pull/new/v3-phase-d
   test.yml runs the suite on the PR. After the next cron, read the analytics step: it should
   say `📈 Analytics snapshot saved (… N ledger videos)` with N ≈ 33+ and print the scoreboard.
   `⚠️ ledger query skipped: …` means the `video==` filter shape is wrong — costs nothing, but
   paste that line into the next session.
1.4. **Create the X app and add its 4 Actions secrets** (v3-F.3). Free tier, ~500
   posts/month against our ~31. The order matters: set **App permissions = Read and
   write** BEFORE generating the access token, or the token stays read-only and posting
   returns 403 `oauth1-permissions`. Then repo Settings → Secrets and variables →
   Actions → New repository secret, four times: `X_API_KEY`, `X_API_SECRET`,
   `X_ACCESS_TOKEN`, `X_ACCESS_SECRET` (full walkthrough in
   docs/spec/ai-pulse-v3f3.md). Until then the 16:55 workflow logs
   `↷ X not configured — skipping` and costs nothing.
1.5. ✅ **Telegram is posting from CI** — observed 2026-09-26: `state/notified.json` holds 25
   posted videos, so both secrets are set and the 16:55 UTC workflow works.
   Two notes still open: the chat id is a **private supergroup**, not a broadcast channel — for
   distribution create the public channel `@tooldojo`, make the bot an admin, and change that
   one secret (no code change). And the token has been shared in plain text; rotating it in
   @BotFather (`/revoke`) once CI is wired is cheap hygiene, and only means updating the same
   two places.
1.6. **Create the Meta app and add its 3 Actions secrets** (v3-F.4) — 8 steps in
   docs/spec/ai-pulse-v3f4.md. Order matters and step 4 is the one that decides whether this
   phase is usable at all: the Instagram account must be **Business** (not Creator), it must
   be linked to a Facebook Page, and before anything else you should post ONE Reel by hand
   from Graph API Explorer. If Meta demands App Review for `instagram_content_publish` on
   your own account, stop and say so — the code is ready either way, but the account is not.
   Then Settings → Secrets and variables → Actions → New repository secret, three times:
   `META_PAGE_TOKEN` (the long-lived **Page** token, which does not expire — not the User
   token, which lasts 60 days), `META_PAGE_ID`, `META_IG_USER_ID`. Until they exist the
   publish workflow logs `↷ Instagram not configured — skipping` and costs nothing.

2. ✅ GitHub Pages is on — observed 2026-09-26: https://dev-shivam-05.github.io/AI-PULSE/
   answers 200. No tool page exists yet because no tool video has shipped. After the first tool run, `curl -I`
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
4. **Supervised first tool run — this now gates v3-B.1's merge.** Never done: the last 100
   Actions runs are all `schedule`, none `workflow_dispatch` (checked 2026-09-26). On a
   **weekday** (a Sunday dispatch would cost that week's roundup): Actions tab → "AI Pulse — Auto Publish" → Run workflow →
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

7. **Optional, helps v3-G.3:** one screenshot of Studio → Analytics → Content → Reach
   (impressions + impressions click-through rate, last 28 days). The Analytics API we use does not
   return these, so today we have no CTR baseline at all.

## Next 3
1. **Build v3-B.1** (spec locked: docs/spec/ai-pulse-v3b1.md) on `v3-phase-b1` — small: the
   threshold, a pure `_fallback_format` helper at the three gate sites, tests. Its PR waits for
   Now #4 (the supervised tool dispatch).
2. **Build v3-G.1** (spec locked: docs/spec/ai-pulse-v3g1.md) on `v3-phase-g`, in its own
   session — the storyboard Shorts engine and its A/B. Read the whole spec first: every layout
   number is already traced to a constant in the repo; anything else is a new spec row.
3. **Read the A/B after 10 daily pairs** (the scoreboard prints `A/B pairs: N · storyboard wins:
   W`): ≥ 8 → spec v3-G.2 (long-form); ≤ 5 → stop and rethink; 6-7 → 10 more. Meanwhile merge
   `v3-phase-d` and read the first real v3-D scoreboard (Now #1); X (1.4) and Meta (1.6) are still
   owner clicks.
