# HANDOFF — ToolDojo — Phases v3-B.4 + v3-G.3 + v3-G.4b + gemini cleanup — 2026-10-10

## Done
- **One branch carries everything: `v3-integration-1010`.** It merges B.4, G.3, G.4b and the
  gemini-fallback cleanup, plus the docs. Suite: **396 passed** on the combined tree, and
  `merge-tree` against main (937c4b2) is clean. The four phase branches are also pushed on
  their own.
- **v3-B.4: the tool lane gets real candidates again.**
  - Since 10-07 the lane failed 3/3 candidates daily and silently fell through to
    news/evergreen. Product Hunt items are now skipped before a writer call.
  - The README is fetched at 20,000 chars, and the first code block past the 5,000-char writer
    window is appended.
  - Live check today: the 3 eligible candidates (embeddinggemma-2, coucou, RemoveMacAI) all
    carry a real install command in their grounding.
- **v3-G.3: packaging.**
  - The viral judge and the critique pass no longer reward fear/outrage, and the contract now
    asks for "what you can DO".
  - A stripped leftover title is replaced by the model's own clean alternate. 8 of 78 published
    titles were leftovers; 6 now get an alternate, and 2 had lost `titles` to the `_CARRY` bug
    this phase fixes.
  - The ledger records `thumb_text`, `title_alt` and `title_terms`.
  - Impressions and CTR are collected from the YouTube Reporting API into `analytics.jsonl` and
    the scoreboard. Not exercised live yet, because there is no token locally.
- **v3-G.4b: production basics.**
  - 0.5 s dissolves between scenes. Total duration is identical, and the dissolve frames were
    read.
  - `amix normalize=0` fix: the voice measured −19.7 LUFS with a bed vs −19.8 without. The old
    mix would have given −25.7.
  - The bed comes from `assets/music/bed/` (CC0 only, currently empty).
  - The outro line is now "for AI you can use". Both outros were re-rendered and read.
- **gemini-fallback:** the shut-down `gemini-2.0-flash` is removed from the chain.
- **Measured from main's state:**
  - Storyboard A/B: 9 pairs, storyboard won 1, so G.2 is not built.
  - The longest CI publish run in 14 days took 37.4 of 90 min, so 1080p is safe.

## Files changed
- `factverse/ai_pipeline.py`:
  - B.4: tool eligibility, the 20,000 fetch with the code-block append, and a log line on the
    writer-failure path.
  - G.3: judge, contract, critique, retention rules, `titles` in `_CARRY`, and the ledger
    fields.
- `factverse/gates.py` — clean alternate in `packaging_payoff`, the long-form hype screen,
  `FEAR_TERMS`/`title_terms`.
- `factverse/analytics.py`, `factverse/learn.py` — Reporting API reach collection, plus the
  impressions/CTR scoreboard block.
- `scripts/factverse_engine.py` — the xfade join with concat fallback, the `bed/` pick, and
  `mux_args` (normalize=0 and fades).
- `factverse/branding.py`, `factverse/shorts.py`, `assets/outro.mp4`, `assets/outro_v.mp4` —
  the outro line.
- `factverse/llm.py` — `gemini-2.0-flash` dropped from the chain.
- `config.json`, `config.example.json` — kill switches `reach_report`, `transitions`,
  `music_bed`.
- `assets/music/bed/SOURCES.txt` — the CC0-only rule. No audio was committed.
- Tests:
  - New modules: `tests/test_b4_tool_supply.py`, `tests/test_g3_packaging.py`,
    `tests/test_g4b_production.py`.
  - `tests/test_llm.py` is updated.
  - `tests/test_pipeline_logic.py`: one URL added to the MarkItDown fixture.
- Specs: `docs/spec/ai-pulse-v3b4.md`, `docs/spec/ai-pulse-v3g3.md`,
  `docs/spec/ai-pulse-v3g4b.md`.
- Docs:
  - `docs/PHASES.md`, `docs/DECISIONS.md` — the board and the decisions.
  - `docs/STRATEGY.md` — the thumbnail line now follows v3-E #5.
  - `CLAUDE.md` — 4 traps.

## Decisions made
- **All values were approved by the owner with one `go`** on a 5-row spec-lock table. They are
  in DECISIONS (2026-10-10).
- **G.2 is not built.** The pre-registered A/B rule is already decided (≤ 5 wins).
- **Live work is excluded:** L.4, L.5, the seam lags and the schedule. The owner assigned it to
  a separate background session, and it shares `radar_live.py`.
- **Music in git must be CC0.** The repo is public and the Reels re-upload the bed, so the
  Audio Library tracks stay local.
- **HELD candidates re-rolling on the retry cron stays as is.**
- **One integration branch, so the owner opens one PR instead of four.**

## Known broken / deliberately skipped
- **Mermaid fences** — the first code block can be a diagram (OpenDots), which would ship as
  "the command". Needs one word: skip `mermaid` fences.
- **The fear-term list catches 13 of 78 titles, not ~21** — "hacked/danger/risks/worries/
  backlash" are missing. A fear-framed alternate can still win the title fallback. Both need an
  owner word before the list changes.
- **Ranking still favours Product Hunt** (`feed_max` is computed before the used filter, and
  Atom `updated` is read before `published`). Eligibility now protects the lane; a ranking
  phase would fix the root cause.
- **The music bed is silent until the owner adds CC0 tracks.** The bed also restarts after the
  sting; that predates this work.
- **Reach and CTR are unverified live** — that needs the Reporting API enabled, and possibly a
  re-minted token.
- **The exact gate behind the 10-07..09 tool failures is inferred** — the CI logs need auth.
- **Leftover worktrees:** `E:/YOUTUBE/AI-PULSE-{b4,g3,g4b,gf,int,wt-main}`. Remove them after
  the merge with `git worktree remove <path>`, never `--force`.
- **Still untracked in `E:\YOUTUBE\AI-PULSE`:** `output/demo/storyboard/sample/*`,
  `docs/BROWSER_AI_AGENTS_AND_MCP_GUIDE.md`, `output/brand/`. That checkout is still on the
  stale `v3-gemini-fallback` branch.

## Next session starts here
- Phase: none to build. The owner merges
  https://github.com/Dev-Shivam-05/AI-PULSE/pull/new/v3-integration-1010, enables the YouTube
  Reporting API in GCP, adds CC0 tracks to `assets/music/bed/`, and answers the mermaid and
  fear-list words.
- First command: `/boot`. Then read the first post-merge run: the ledger `format` (expect a
  `tool` row) and the log lines `⏭️ Skipping tool candidate`, `📎 first code block`,
  `transitions:`, `music:` and `↷ reach report`.
- Watch out for: the first post-merge CI run's duration and the `transitions:` line. If the
  xfade join misbehaves on the 4-vCPU runner, flip `"transitions": false` in config.json. That
  is one flag, not a rewrite.
