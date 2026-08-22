# AI Pulse — phase board

One phase per session. A phase that isn't pushed doesn't exist.

| Phase | Scope | Status | Branch / notes |
|-------|-------|--------|----------------|
| v2 Foundation → live channel | pipeline, gates, CI publishing | ✅ done | on `main`, publishing daily |
| **v3-A: utility pivot core** | tool signals (GitHub/HF/PH), tool format behind `tool_format` flag, viral threshold 8, 900-word cap + cut-don't-pad, blocked-day fallback, caption force-align | ✅ done 2026-08-22 (26/26 tests, pushed) | `v3-phase-a` → PR pending merge; spec: docs/spec/ai-pulse-v3.md |
| **v3-B: original-visuals engine** | `screencap.py` (record → measured head trim → per-scene chunks, fail-soft), Pygments code cards, screenshot tool thumbnails, HF raw-README grounding, `_CARRY` rewrite fix, CI chromium + cache + `format` dispatch input, `tool_format: true` | ✅ done 2026-08-22 (47/47 tests; live E2E 10/10 real-UI frames; pushed) | `v3-phase-b` → PR pending merge; first tool video = supervised CI dispatch |
| **v3-C: income + packaging** | cheat-sheet PDF per tool video (`deliverable.py`, GitHub Pages), description rebuilt around the transaction (🔧 + 📄 + `promo_block` above the fold), README/PLAYBOOK/STATUS rewritten for v3 | ✅ done 2026-08-22 (63/63 tests; PDFs rendered + read; pushed) | `v3-phase-c` (stacked on `v3-phase-b`) → PR pending; needs Pages enabled once |
| v3-D: learning loop v1 | feed runs.jsonl + analytics.jsonl into topic/packaging choices (AVD ≥2:00 is the target metric) | ⏳ queued | needs ~2 weeks of v3 data first |

## Now (owner, in this order)
1. Merge PR #23 (`v3-phase-b`), then open + merge `v3-phase-c`
   (https://github.com/Dev-Shivam-05/AI-PULSE/pull/new/v3-phase-c). test.yml runs the 63-test
   suite on each PR automatically.
2. Enable GitHub Pages: Settings → Pages → Deploy from branch → `main` / `docs`. Until this is
   done every cheat-sheet link 404s.
3. Supervised first tool run — Actions tab → "AI Pulse — Auto Publish" → Run workflow →
   format = `tool`, BEFORE 12:23 UTC (5:53 PM IST) so the day's cron no-ops afterwards. Watch the
   log for "Screen-recorded visuals", "Tool thumbnail", "Cheat sheet:"; then check the YouTube
   description (🔧 and 📄 blocks under paragraph 1) and `curl -I` the PDF link.

## Next 3
1. v3-D — learning loop v1 once ~2 weeks of v3 analytics exist (target: AVD ≥ 2:00).
2. v3-B.1 (only if the first CI tool runs show it) — capture hardening from real logs: PH/HF page
   quirks, CI chromium sandbox, recording length vs 900-word scripts.
3. Fill `promo_block` in config.json when there is an affiliate/product to sell.
