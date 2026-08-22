# AI Pulse — Project Status Report

*Updated: 2026-08-22 · v3-A merged (PR #22) · v3-B in PR #23 · v3-C on `v3-phase-c`*

## Overall Project Status
- **Live and pivoting.** The channel has published autonomously via GitHub Actions since
  2026-07-19. The 90-day numbers (1,582 views · 5 subscribers · **0:38 average view duration**
  on 6–9-minute videos) showed the machine works but the product was wrong, so v3 pivots from
  "about AI" news essays to **"AI you can use today" tool videos** with a deliverable.
- v3 phases: **A** (signals, tool format, 900-word cap, gate fallback, caption force-align) is
  on `main`; **B** (screen-recorded visuals, code cards, tool thumbnails, `tool_format: true`)
  is in PR #23 with tests green; **C** (cheat-sheet PDF on GitHub Pages, affiliate slot, docs)
  is this branch. **D** (learning loop) waits for ~2 weeks of v3 data.
- Success metric for v3: average view duration ≥ 2:00 after 10 tool videos.

## What the pipeline does today
- **Intelligence**: GitHub trending + Hugging Face trending + Product Hunt (`kind=tool`) alongside
  HN / arXiv / lab blogs / RSS; deterministic ranking with tool recency floor; URL + fuzzy +
  token-overlap dedup; failed-topic quarantine.
- **Lanes**: Sunday roundup > news (viral judge ≥ 8/10, two voices) > **tool** (default when a
  tool signal exists) > evergreen. A gate block on an automatic run re-runs the day as evergreen.
- **Script engine**: retention prompts, critique pass that CUTS repetition, 600–620 word sanity
  floor, **900-word cap**, required `deliverable` for tool videos, one honest-limitation scene,
  HF raw-README grounding fallback; every rewrite pass carries the same `_CARRY` key set.
- **Visuals**: tool videos = headless-Chromium screen recording of the tool's page
  (`screencap.py`, measured head trim, sequential per-scene chunks, fail-soft to stock) +
  Pygments code card of the deliverable; news/evergreen = relevance-ranked Pexels + stat-cards.
- **Production**: Kokoro-82M voice (multi-voice), whisper word alignment force-aligned to the
  script's spelling, karaoke captions, source chips, cold-open branding, L2 human insight block.
- **Packaging**: tool thumbnail = real page screenshot + 2–4 words (Inter Black on #DC2626);
  person-cutout thumbnails for news; auto-chapters; description with the deliverable block
  above the fold; **1-page cheat-sheet PDF** per tool video (`docs/tools/`, GitHub Pages);
  `promo_block` affiliate slot.
- **Distribution**: long-form at the 16:45 UTC slot; Short #1 ~2 h later, Short #2 on the next
  07/12/17/21 IST grid slot (≥4 h spacing, hard-validated); watch-next chain links; one
  playlist per lane.
- **Safety/ops**: originality, advice-framing, fact-check and confidence gates; publish-once-per-
  day guard; union state merge; dual retry cron; failure → GitHub issue; cron keepalive;
  nightly analytics snapshot; **63 unit tests** run on every PR (`test.yml`).

## In Progress
- **First supervised tool run** — owner dispatches `publish.yml` with `format = tool` (before
  5:53 PM IST) and watches for "Screen-recorded visuals" + the cheat-sheet line.
- **GitHub Pages** — not enabled yet (github.io URL returns 404). One click: Settings → Pages →
  Deploy from branch → `main` / `docs`. Until then the PDFs open via the GitHub blob viewer.
  **Verify after the first tool run:** `curl -I <the 📄 link in the description>`. Pushes made
  with `GITHUB_TOKEN` (the state-save step) may not trigger the Pages build; if the PDF 404s
  while the file is visible in `docs/tools/` on main, that is the cause — any manual commit or
  a Pages re-deploy from Settings republishes it.

## Owner actions (open)
1. Merge PR #23 (v3-B), then the v3-C PR.
2. Enable GitHub Pages (above).
3. Dispatch the supervised `tool` run and review the first tool video.
4. v2 backlog: set one of the duplicate NVIDIA/HF videos to Private; one-time OAuth re-consent
   (`force-ssl` scope) + `YT_TOKEN_B64` update to activate comment chains.
5. Fill `promo_block` in `config.json` when there is an affiliate to promote.

## Known Issues / Limits
- Product Hunt post pages ground thinly → `script_tool` rejects them → next candidate (3 tries).
- Recording is capped at 300 s; 900-word scripts (~375 s) loop the last chunks once.
- One publish run/day by YouTube quota design (~5.1k of 10k units at 2 Shorts/day).
- GitHub cron fires late (up to ~2 h); mitigated by dual crons + the guard.
- English only; YouTube only (Instagram manual).

## Risks
- **Platform policy** (#1): YPP review of an AI-heavy channel — mitigated by original screen-
  recorded visuals, grounded scripts, curation value, honest limitation scenes.
- Free-tier changes (Gemini, Pexels, YouTube quota), OAuth token invalidation (10-min fix,
  alerts fire), single-owner bus factor.
- Pages link 404s until enabled — the description already carries it.

## Next Priorities
1. Watch the first 10 tool videos' average view duration (the v3 verdict).
2. v3-D learning loop: feed `state/runs.jsonl` + `state/analytics.jsonl` into topic and
   packaging choices.
3. Capture hardening only if CI logs show it (PH/HF page quirks, chromium sandbox).

## Overall Health
- **Green.** Live, self-publishing, self-reporting, self-protecting, ₹0. The product has been
  redefined around a measurable payoff (deliverable + cheat sheet) and original visuals; the
  next two weeks of data decide the tuning, not more machinery.
