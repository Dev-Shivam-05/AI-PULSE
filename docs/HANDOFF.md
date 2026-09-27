# HANDOFF — ToolDojo — v3-B.1 + v3-H + v3-G.1 + v3-G.3a built — 2026-09-27

Built in one session at the owner's instruction ("implement everything, do not stop"). Four
branches, stacked in this order, all pushed, 255/255 tests passing:
`v3-phase-b1` → `v3-phase-h` → `v3-phase-g` → `v3-phase-g3`.
Merging `v3-phase-g3` brings all four; it has no conflicts with main (v3-D, PR #32, is merged).

## Done

- **v3-B.1: tool-lane unblock.** `VIRAL_THRESHOLD` goes from 8 to 10, and a blocked story now
  falls back to a tool video first (`_fallback_format`).
- **v3-H: AI debate lane**, on Wednesdays. Up to 5 models from different labs (Gemini, GPT-OSS
  120B, Qwen 3.8, Nemotron, Inkling) debate the day's question through their official, free APIs.
  - A quote gate rejects any quote that isn't word-for-word what a model said.
  - The transcript is part of what the fact-check checks against.
  - Quote and scoreboard cards were rendered and read.
  - Groq and OpenRouter answered a live 401, which the lane handles.
- **v3-G.1: storyboard Shorts** (A/B test). One of the two daily Shorts is drawn from its own
  narration, word-timed, at 1080×1920. A full 31 s Short went through the real production path;
  rendering took 76 s. Viewing the frames turned up three defects, all fixed.
- **v3-G.3a: honest Shorts titles.** The prompt that asked for "power words" is replaced, and a
  hype screen with a fallback to the Short's hook runs before upload.
- **No code came from `docs/BROWSER_AI_AGENTS_AND_MCP_GUIDE.md`.** Browser automation of consumer
  AI accounts was declined (DECISIONS 2026-09-26).

## Files changed

- New: `factverse/debate.py`, `factverse/storyboard.py`, `assets/storyboard/storyboard.html`.
- Modified: `factverse/ai_pipeline.py`, `shorts.py`, `learn.py`, `llm.py`, `gates.py`,
  `scripts/factverse_engine.py`, both configs, `publish.yml`, tests.
- Specs: `docs/spec/ai-pulse-v3b1.md`, `v3h.md`, `v3g1.md`, `v3g3a.md`.
- Demo artifacts: `output/demo/debate/`, `output/demo/storyboard/`.

## Decisions made

- The debate uses official free APIs, not browser logins. GitHub Models was retired on
  2026-07-30, which was checked. Paid seats (DeepSeek, xAI, OpenAI, Perplexity, Mistral) are
  already wired and each needs only a secret plus a panel row.
- H and G.3a values were chosen by Claude under the "do not stop" instruction. Each spec says
  they are revisable.

## Known broken / deliberately skipped

- **The debate needs two free secrets:** `GROQ_API_KEY` and `OPENROUTER_API_KEY`. Until they
  exist, Wednesday runs the normal lane.
- **The free model rosters change.** A seat that disappears is skipped, and the log names it.
- **Nothing new has run in CI yet.** The storyboard prompt and the debate first meet a real model
  there. Their log lines are: `🎨 Storyboard: k/n beats kept`, `🎨 Storyboard short rendered in`,
  `🥊 Debate:`, `↷ seat … skipped`, `↻ storyboard short fell back:`.
- **The CI render time is unknown.** It is 76 s locally for 284 frames.
- **B.1 should merge after one supervised `format=tool` dispatch** (Now #4). It has still not
  been done.
- **Self-views.** The owner says 2–5 of the 8–12 long-form viewers are their own IDs. That
  distorts every metric, including G.1's A/B, and breaks YouTube's fake-engagement policy.
- **Two files were left in place.** Local demo intermediates (`output/demo/storyboard/sample/`
  content, voice and frames) are untracked because the delete was not permitted. The
  owner-supplied `docs/BROWSER_AI_AGENTS_AND_MCP_GUIDE.md` is still untracked.

## Next session starts here

- **Phase:** none to build. First read the first CI logs after the merge, then the A/B after 10
  daily pairs (the scoreboard verdict line).
- **First command:** `/boot`
- **Watch out for:** a CSS child with `visibility: visible` shows through a hidden parent. That
  bug leaked chat text into every later storyboard beat and was only found by looking at
  rendered frames. Always inspect the frames.
