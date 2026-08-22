# HANDOFF — AI Pulse — Phase v3-A (utility pivot core) — 2026-08-22

## Done
- Diagnosed why the channel doesn't earn: 90-day data = 1,582 views, 5 subs, **0:38 avg view
  duration** on 6-9 min videos → YPP decades away at current rate. Root causes verified in code
  and on-screen: word FLOORS forced padding (repeated claims in 5 of 17 scenes of the last video),
  Pexels stock = AI-slop signature, 8 of last 20 runs died at gates with nothing published,
  whisper typos burned into captions ("Hoppogja's").
- v3 spec locked and approved (`go`): docs/spec/ai-pulse-v3.md. Pivot = "about AI" news →
  "AI you can USE today" tool videos with a concrete deliverable.
- Tool signals LIVE-VERIFIED: github_trending (15 items, top 16.9k★), huggingface_trending (12),
  product_hunt feed (20). kind="tool", recency-floored in ranker.
- Pipeline core: `script_tool` format + required `deliverable` field (behind `tool_format:false`
  flag until visuals land); viral news bar 7→8; MIN floors 850-1000 → 600-620 sanity only;
  NEW `enforce_max_length` cap 900; critique pass now cuts repetition instead of guarding length;
  FACTCHECK/ADVICE/POLICY block on auto runs → falls back to forced evergreen (day never wasted);
  `captions.correct_words` force-aligns caption text to the script (fixes proper-noun typos).
- **26/26 tests pass** in the CI-mirror venv (17 old + 9 new).
- Phase-B PoC PROVEN in scratchpad: Playwright headless Chromium recorded a real trending repo
  (dark GitHub, README scroll, 1920×1080 webm) + page screenshot for thumbnails. Zero stock.
- Branch `v3-phase-a` pushed. PR: https://github.com/Dev-Shivam-05/AI-PULSE/pull/new/v3-phase-a
- Capability note: Claude CAN watch published videos (yt-dlp 480p + ffmpeg contact sheets); used
  it to tear down nXQT0BOL1Wo frame by frame.

## Files changed
- docs/spec/ai-pulse-v3.md — the locked v3 contract (10 decisions, acceptance criteria, phasing)
- docs/spec/GLOSSARY.md — fixed meanings: tool format, deliverable, MAX_WORDS, blocked-day fallback
- docs/PHASES.md — new phase board (v3-A done, B/C/D queued)
- factverse/intelligence/sources.py — github_trending / huggingface_trending / product_hunt fetchers
- factverse/intelligence/signal_engine.py — tool kind weight + recency floor 0.5 for tool items
- factverse/ai_pipeline.py — script_tool, deliverable contract+description block, threshold 8,
  MIN/MAX words, enforce_max_length, cut-don't-pad critique, 3× gate fallbacks, correct_words call,
  tool playlist, CLI "tool" arg, confidence tweak (words≥550, scenes≥8)
- factverse/captions.py — correct_words (difflib 1:1 force-align, timings untouched)
- config.json + config.example.json — "tool_format": false
- tests/test_pipeline_logic.py — 9 new tests
- README.md — viral bar table 7→8

## Decisions made
- Tool lane ships DARK (flag off) until Phase B visuals exist — a tool video illustrated with
  Pexels stock would be worse than evergreen. Threshold-8 + cap-900 + fallbacks are LIVE at merge.
- Product Hunt via public RSS feed (keyword-gated), not the OAuth API — zero new secrets.
- Higgsfield rejected for visuals: 0 credits, and screen recording is better evidence anyway.
- Keep the existing channel; no reset, no rebrand.

## Known broken / deliberately skipped
- Tool videos have NO visual engine yet — that IS Phase B (PoC in scratchpad/poc_screencap.py).
- PoC recording's first ~2s are blank (page load) — Phase B must trim the head.
- Screenshot thumbnails, PDF deliverable, README v3 rewrite — Phases B/C per docs/PHASES.md.
- Duplicate NVIDIA/HF video + OAuth re-consent + old near-dupe cleanup — still owner actions (v2 backlog).

## Next session starts here
- Phase v3-B: build `factverse/screencap.py` (Playwright provider: record repo/model page,
  trim head, segment per scene), Pygments code cards, screenshot thumbnail path, add
  `playwright install chromium` to publish.yml, then flip `tool_format: true` and force one
  supervised `tool` run.
- First command: `/boot` then read docs/spec/ai-pulse-v3.md + scratchpad PoC pattern (rec via
  browser context record_video_dir, color_scheme="dark").
- Watch out for: publish.yml CI time/size — chromium adds ~130MB download per run unless cached
  (use actions/cache on ~/.cache/ms-playwright); and `fetch_text()` on huggingface.co model pages
  may return thin text (JS-rendered) — script_tool already rejects no-grounding items, but that
  can starve HF picks; consider the HF API's raw README endpoint in B.
