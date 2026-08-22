# AI Pulse — phase board

One phase per session. A phase that isn't pushed doesn't exist.

| Phase | Scope | Status | Branch / notes |
|-------|-------|--------|----------------|
| v2 Foundation → live channel | pipeline, gates, CI publishing | ✅ done | on `main`, publishing daily |
| **v3-A: utility pivot core** | tool signals (GitHub/HF/PH), tool format behind `tool_format` flag, viral threshold 8, 900-word cap + cut-don't-pad, blocked-day fallback, caption force-align | ✅ done 2026-08-22 (26/26 tests, pushed) | `v3-phase-a` → PR pending merge; spec: docs/spec/ai-pulse-v3.md |
| v3-B: original-visuals engine | Playwright screen-recording provider (PoC proven in A), Pygments code cards, screenshot thumbnails, CI chromium step, flip `tool_format: true` | ⏳ next session | needs: publish.yml edit + factverse_engine visual seam |
| v3-C: income + packaging | 1-page PDF deliverable on GitHub Pages, affiliate slot, README/CONTENT_PLAYBOOK rewrite for v3, STATUS refresh | ⏳ queued | works from view #1, no YPP gate |
| v3-D: learning loop v1 | feed runs.jsonl + analytics.jsonl into topic/packaging choices (AVD ≥2:00 is the target metric) | ⏳ queued | needs ~2 weeks of v3 data first |

## Now
- Owner: open + merge the PR for `v3-phase-a` (https://github.com/Dev-Shivam-05/AI-PULSE/pull/new/v3-phase-a).
  test.yml runs the 26-test suite on the PR automatically.

## Next 3
1. v3-B — screen-recording visual engine (PoC proven; see docs/HANDOFF.md) → flip `tool_format: true`.
2. v3-C — PDF deliverable on GitHub Pages + affiliate slot + docs rewrite.
3. v3-D — learning loop v1 once ~2 weeks of v3 analytics exist (target: AVD ≥ 2:00).
