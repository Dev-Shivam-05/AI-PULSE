# HANDOFF — ToolDojo — v3-D built + channel audit + v3-B.1 / v3-G.1 specs locked — 2026-09-26

## Done

- **v3-D learning loop v1: built and pushed** on `v3-phase-d` (228/228 tests). Details are in
  `docs/spec/ai-pulse-v3d.md` and the v3-D board row. The PR is not merged yet:
  https://github.com/Dev-Shivam-05/AI-PULSE/pull/new/v3-phase-d
- **Channel audit** (the owner's Studio screenshot plus `state/`):
  - 3,920 views in 28 days, about 9 in 10 of them Shorts.
  - Long-forms get ~4 views each; 10 subscribers (+3 in 28 days); 36 likes.
  - Against the STRATEGY milestones: ~120× short on Tier-1 watch hours, ~270× on the Shorts path,
    ~12 years to 500 subscribers at this pace.
  - The figures are recorded in `docs/DECISIONS.md` (2026-09-26 entry).
- **Root causes found and verified in code/ledger:**
  1. `viral_pick` returns the max of 8 LLM scores and it cleared `VIRAL_THRESHOLD` 8 on every
     weekday (22/22 first attempts since 09-01 were news), and the three blocked-day fallbacks are
     hard-coded to evergreen, so **0 of 64 published videos were tool**.
  2. The only visual instruction per scene is a 2-4 word stock-search term, so the narrated
     example can never be on screen.
  3. Shorts are a 405×720 crop of the 720p long-form, scaled up 2.67×.
  4. There is no music at all (`assets/music` is empty and untracked).
- **The browser-agent guide** (`docs/BROWSER_AI_AGENTS_AND_MCP_GUIDE.md`, from the owner's Shivam
  Brain project) was read in full and **not adopted**. The reasons are in DECISIONS.
- **Two specs locked with `go`:**
  - `docs/spec/ai-pulse-v3b1.md`: tool-lane unblock.
  - `docs/spec/ai-pulse-v3g1.md`: storyboard Shorts, with an A/B test.

  The glossary gained 7 G.1 terms, plus forward notes on the two lines B.1 will change.

## Files changed

- On `v3-phase-d` (the v3-D phase): `factverse/learn.py` (new), `factverse/analytics.py`,
  `factverse/gates.py`, `factverse/ai_pipeline.py`, tests, the v3-D spec, `CLAUDE.md` (2 traps),
  `.gitignore`, `output/demo/learn/scoreboard_approx.txt`.
- On `v3-phase-b1` (this commit, docs only):
  - `docs/spec/ai-pulse-v3b1.md` (new)
  - `docs/spec/ai-pulse-v3g1.md` (new)
  - `docs/spec/GLOSSARY.md`
  - `docs/DECISIONS.md`
  - `docs/PHASES.md`: B.1 and G.1 rows, G.2–G.4 queued, Now #4 now gates B.1, new Now #7,
    Next 3.
  - `docs/HANDOFF.md`

## Decisions made

- **Browser automation of consumer AI sites is declined for this pipeline.**
  - It saves ₹0: the LLM is already on the Gemini free tier.
  - It cannot run unattended in CI.
  - It violates OpenAI's Terms and would put the owner's main Pro account at risk.
  - It breaks on every site redesign.
  - The guide's own P11 advises against extending it.
- **B.1:** `VIRAL_THRESHOLD` 8 → 10. Blocked-day fallback goes to tool first, then evergreen,
  one level only; owner-forced runs keep no fallback. The merge waits for one supervised
  `format=tool` dispatch.
- **G.1:** one of the 2 daily Shorts is drawn from its own narration and A/B-tested against
  today's crop Short. Verdict after 10 pairs.
- **Order: B.1, then G.1, each in its own session.**

## Known broken / deliberately skipped

- **The CI job logs cannot be read** without admin rights (`GET /actions/jobs/{id}/logs` → 403).
  The tool-lane diagnosis rests on `state/runs.jsonl`, which CI commits back.
- **The supervised `format=tool` dispatch has never been run.** The last 100 Actions runs are all
  `schedule`. The tool lane has never executed in CI.
- **v3-D's new analytics query is unverified live** (no YouTube token locally). The first CI
  analytics line `… N ledger videos)` is the check.
- **G.1's derived details.** The spec writes down two things the approved table left implicit,
  and the owner can object:
  - the `STOP_WORDS` list for the grounding gate;
  - x 120 as the visual area's left edge (a mirror of the approved x 960).

  Every other layout number in G.1 is traced to an existing repo constant.
- **An untracked file was left alone.** `docs/BROWSER_AI_AGENTS_AND_MCP_GUIDE.md` (owner-supplied)
  is still untracked and was not committed. Note that `docs/` is served verbatim by Pages, so a
  `.md` there would be published as raw text.

## Next session starts here

- **Phase v3-B.1:** build `docs/spec/ai-pulse-v3b1.md` on `v3-phase-b1`, which is already checked
  out and stacked on `v3-phase-d`.
- **First command:** `/boot`
- **Watch out for:** `run()` recursion semantics.
  - An owner-forced run (`force_format` from a dispatch, `fallback=False`) must still return
    `None` on a block. That is the supervised-run contract.
  - Only runs with `fallback=True` may chain tool → evergreen.
  - Put the decision in the pure `_fallback_format` helper and test its whole truth table.
  - Stub `ap.run` as the consumer sees it to prove the recursion arguments, rather than letting a
    real run recurse.
