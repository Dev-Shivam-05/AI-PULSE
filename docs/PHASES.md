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
| v3-D: learning loop v1 | feed runs.jsonl + analytics.jsonl into topic/packaging choices (AVD ≥2:00 is the target metric) | ⏳ queued | needs ~2 weeks of v3 data first |

## Now (owner, in this order)
1. Merge PR #23 (`v3-phase-b`), then open + merge `v3-phase-c`
   (https://github.com/Dev-Shivam-05/AI-PULSE/pull/new/v3-phase-c). test.yml runs the 75-test
   suite on each PR automatically.
2. Enable GitHub Pages: Settings → Pages → Deploy from branch → `main` / `docs`. Until this is
   done every cheat-sheet link 404s.
3. **Read `gates.UNSUITABLE_TOOL`** (factverse/gates.py) and edit it. It is the list of tools this
   channel refuses to teach. It was added because the day it was written, the top-ranked tool
   candidate was an AI-provenance stripper. It will both miss things and over-block.
4. Supervised first tool run — Actions tab → "AI Pulse — Auto Publish" → Run workflow →
   format = `tool`, BEFORE 12:23 UTC (5:53 PM IST) so the day's cron no-ops afterwards. Watch the
   log for "Screen-recorded visuals", "Tool thumbnail", "Cheat sheet:"; then check the YouTube
   description (🔧 and 📄 blocks under paragraph 1) and `curl -I` the PDF link.
   Also expect, and read, any of: `⛔ Skipping tool candidate`, `↻ grounding too thin`,
   `↻ tool is not something this channel teaches`. Those are the new screens working, not errors.
   A forced `tool` run has **no evergreen fallback** — if a gate blocks it, the day publishes
   nothing. That is deliberate for a supervised run.

## Next 3
1. v3-D — learning loop v1 once ~2 weeks of v3 analytics exist (target: AVD ≥ 2:00).
2. v3-B.1 (only if the first CI tool runs show it) — capture hardening from real logs: PH/HF page
   quirks, CI chromium sandbox, recording length vs 900-word scripts.
3. Audit the shared render surfaces (`shorts`, `captions`, `branding`, `thumbnail`, `l2`). C.1
   covered the tool lane and C.2 the story lanes, so every lane's *selection and scripting* path
   has now been searched — but everything downstream of the script is still unaudited.
