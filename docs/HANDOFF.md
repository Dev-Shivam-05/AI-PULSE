# HANDOFF — ToolDojo — Phase v3-B.2 — 2026-10-01

## Done
- **The fact-checker now sees the tool facts the writer was handed.** `run()` calls
  `gates.fact_check` with `gates.fact_sources(script)`, which puts a `VERIFIED FACTS (official
  API)` block (stars, license, last_update, open_issues; or HF downloads/likes) ahead of the
  README.
  - Before the fix, all 4 tool scripts since #33 (09-27..09-30) were blocked on their own true
    star or like count.
  - Verified live against the real 09-30 candidate (`zai-org/ZCode`): its README has no star
    count, and the new source text leads with `- stars: 7,274`.
- **A model can no longer plant `verified_facts`.** `_validate_script` pops it on every pass,
  and `_carry_over` hands the fetched value back.
- 258/258 tests pass. Branch `v3-phase-b2` is pushed (2 commits plus this handoff).
- **Post-merge reading of #33, from the ledger:**
  - B.1 works: the tool lane was reached on 4 of 4 days.
  - G.1 works: 3 storyboard Shorts shipped (09-27, 09-28, 09-30); 09-29 shipped crop+crop.
  - H did not run: 09-30 was a Wednesday with no debate row, because the 2 secrets are still
    missing.

## Files changed
- `factverse/gates.py`: new `facts_lines` (one renderer) and `fact_sources` (the checker's
  source text).
- `factverse/ai_pipeline.py`: the writer's facts block uses `facts_lines`, `_validate_script`
  pops `verified_facts`, and the fact_check call uses `fact_sources`.
- `tests/test_pipeline_logic.py`: 3 tests. One reproduces the 09-30 block and shows it passing
  after the fix. One shows that grounding is unchanged when there are no facts. One shows a
  planted value being dropped while the real value survives a rewrite pass.
- `docs/spec/ai-pulse-v3b2.md`: the new spec, with the ledger evidence.
- `docs/PHASES.md`: B.2 row, Now #1/#4 notes, and a new Next 3.
- `docs/DECISIONS.md`: B.2 entry.
- `CLAUDE.md`: 2 traps (the checker must read the writer's inputs, and the "evergreen" fallback
  can publish news).

## Decisions made
- **Facts go before the grounding** so `fact_check`'s `[:12000]` cut can never drop them.
- **No facts means the grounding is passed through unchanged**, so the non-tool lanes behave
  exactly as before.
- `verify_synthesis` and `replication_test` still read the grounding only. That is out of scope.

## Known broken / deliberately skipped
- **09-27's `7 Secs` claim stays blocked** if the README does not say it. That is correct
  behaviour, not this bug.
- **"Fallback to evergreen" published news on 09-29.** `build_script("evergreen")` falls through
  to news when `pick_evergreen_topic` returns no topic. It was not investigated why there was no
  topic; the CI logs are 403 without admin rights.
- **The tool README can be Chinese** (ZCode's is). It is not known whether the writer and
  checker handle that well; it was not looked at.
- **Untracked files are still untracked:** `output/demo/storyboard/sample/*` and
  `docs/BROWSER_AI_AGENTS_AND_MCP_GUIDE.md`, as before.
- **Self-views (Now #0) still distort every metric**, including G.1's A/B.

## Next session starts here
- **Phase:** none to build. After the owner merges `v3-phase-b2`, read the next tool rows in
  `state/runs.jsonl` on main (`git fetch` then `git show origin/main:state/runs.jsonl | tail`).
  Expect a `PUBLISHED` `format=tool` row; then `curl -I` the page and the PDF (Now #2).
- **First command:** `/boot`
- **Watch out for:** a new input that a prompt hands the writer must also go into
  `gates.fact_sources` and be popped in `_validate_script`. Otherwise the checker blocks the
  writer for obeying, or the model plants it.
