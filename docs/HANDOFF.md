# HANDOFF — AI Pulse — Phase v3-B (original-visuals engine) — 2026-08-22

## Done
- v3-A was merged to main (PR #22) at session start; v3-B built on `v3-phase-b` off merged main.
- **`factverse/screencap.py`** — the tool-video visual engine. Headless Chromium records the tool's
  real page (1920×1080, dark, slow human-style scroll; length sized from the script's words,
  60–300 s), trims the MEASURED page-load blank head (floor 2.5 s), cuts sequential per-scene
  chunks (shape = `step3_download`'s `list[list[path]]`, so `step5_build` is untouched) and
  returns the page screenshot. Fails SOFT (None) → Pexels fallback; the 14:53 UTC cron is the retry.
- **Code card** — the deliverable as a terminal card (Pygments bash, JetBrains Mono 22px, monokai,
  red baseline) → silent mp4; leads the final scene + the first post-hook install/run scene;
  replaces a stat card there instead of stacking (scene time is split equally between clips).
- **`thumbnail.make_tool_thumb`** — page screenshot + 2–4 word overlay, Inter Black ~130px, white
  on #DC2626, red baseline (spec decision 6). Fonts bundled in `assets/fonts/` (both SIL OFL).
- **Wiring** in `ai_pipeline.run()`: capture at the visual seam for `format=="tool"`, code card
  after stat cards, tool thumb ahead of the person/engine chain.
- **Bugs found by the adversarial review and fixed:** `filter_segment` was ALWAYS False (computed
  after `_validate_script` had already stripped the per-scene `filter` key) — now read first; the
  advice-gate rewrite carried only 4 keys and silently dropped `deliverable` → all four rewrite
  passes share `_CARRY` + `_carry_over`; the "🔧 Try it yourself" description block is idempotent
  and re-appended before render.
- HF grounding: `script_tool` falls back to `huggingface.co/<id>/raw/main/README.md` (JS pages are thin).
- **CI:** `requirements-ci.txt` pins `playwright==1.60.0` (browser cache key hashes the file) +
  pygments; `publish.yml` caches `~/.cache/ms-playwright`, installs chromium with
  `continue-on-error` (missing browser → stock, never a lost day), and gained a
  `workflow_dispatch` input `format` (news|evergreen|roundup|tool) for supervised runs; `test.yml`
  installs pygments.
- **`tool_format: true`** in config.json + config.example.json — the tool lane is LIVE at merge.
- **47/47 tests** (26 old + 21 new) on system Python 3.11.9 (no venv needed locally).
- **Verified for real (not just tests):** live capture of github.com/microsoft/markitdown →
  6 chunks → `step5_build` → 150 s 720p mp4 with music bed; 10 sampled frames = **10/10 real
  UI/code** (spec needs ≥7/10); code card and thumbnail inspected as images.
- Review: 4 dimension reviewers + 2 skeptics per finding (36 agents); 11 findings confirmed and
  all actioned; 5 refuted (404 recording, constant-head arithmetic, non-body scroll containers,
  non-dict deliverable, k<n untested — the last one got a test anyway).

## Files changed
- factverse/screencap.py (NEW) — recorder, trim/segment planners, capture(), code cards, injection
- factverse/thumbnail.py — `make_tool_thumb`, `TOOL_RED`, `_tool_font`
- factverse/ai_pipeline.py — screencap import; `_CARRY`/`_carry_over`/`_append_deliverable`;
  `_hf_readme_url`; filter_segment fix; visual + code-card + thumbnail seams in run()
- .github/workflows/publish.yml — chromium cache + soft install step; `format` dispatch input
- .github/workflows/test.yml — + pygments
- requirements-ci.txt — playwright==1.60.0, pygments
- assets/fonts/Inter-Black.ttf, assets/fonts/JetBrainsMono-Regular.ttf (NEW, OFL)
- config.json + config.example.json — tool_format true
- tests/test_pipeline_logic.py — 21 new tests (v3-B section)
- docs/DECISIONS.md, docs/PHASES.md, docs/spec/GLOSSARY.md, docs/HANDOFF.md

## Decisions made
- 100% original visuals for tool videos when capture succeeds (no ≤30% Pexels mix); stock only as
  the failure fallback. Spec's ≥70% is satisfied with margin.
- Recording is duration-agnostic on purpose: visuals are fetched BEFORE audio/durations exist.
- No local supervised publish run: there are no API keys on this machine (Actions secrets only).
  The first real tool video is a CI dispatch the owner watches (see Next).
- FORCE_PUBLISH is NOT exposed as a dispatch input — it also bypasses the confidence HOLD router.

## Known broken / deliberately skipped
- Product Hunt post URLs record fine (real UI) but `fetch_text` grounding on PH is often thin →
  `script_tool` rejects → next candidate. 3-candidate retry covers it; not fixed.
- `REC_MAX` 300 s vs a 900-word script (~375 s): the last scenes loop their chunk once. Acceptable.
- Scroll-bottom detection uses `document.body.scrollHeight` — verified on GitHub/HF/PH; an
  inner-scroll-container site would record a static page (still real UI, not broken).
- `enforce_length`/`critique_pass` prompts still don't SEND deliverable to the LLM (they only carry
  it) — fine, the deliverable is data, not prose.
- v2 owner backlog unchanged: duplicate NVIDIA/HF video, OAuth re-consent, old near-dupe cleanup.

## Next session starts here
- Owner first: merge PR `v3-phase-b`
  (https://github.com/Dev-Shivam-05/AI-PULSE/pull/new/v3-phase-b), then Actions tab → "AI Pulse —
  Auto Publish" → Run workflow → format `tool`, BEFORE 12:23 UTC (5:53 PM IST) so the day's cron
  no-ops. Forced runs have NO blocked-day fallback (by design) — a gate block shows as a failed run.
- In that log look for: "Screen-recorded visuals: N scenes, zero stock", "Tool thumbnail: real page
  screenshot + overlay", and the `Cache Playwright Chromium` step (first run is a miss: +~2 min).
  If it says "Screen capture failed — stock visuals", paste the traceback into the next session.
- Then Phase v3-C: 1-page PDF deliverable on GitHub Pages, affiliate slot, README/CONTENT_PLAYBOOK
  rewrite for v3, STATUS refresh. First command: `/boot`, read docs/spec/ai-pulse-v3.md.
- Local dev note: system `py -3` (3.11.9) already has playwright+chromium+pygments; run
  `py -3 -m pytest tests/ -q`. The old "CI-mirror venv" lives in a temp dir and may vanish.
