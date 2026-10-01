# Spec — v3-B.2: the fact-checker reads the facts the writer was handed

Status: **locked** (owner `go`, 2026-10-01). A defect fix; it adds no number, threshold or field.

## Why this phase exists

After PR #33 merged on 2026-09-27, the tool lane was finally reached on 4 of 4 days.
**All 4 tool scripts were `FACTCHECK_BLOCKED`, and every critical failure was a number the
pipeline itself had handed to the writer.** Measured from `state/runs.jsonl` on origin/main:

| Date | Tool | Critical failures |
|------|------|-------------------|
| 09-27 | Jev Ultrafast | `7 Secs` ×2, the title (soft: `over 20,000 stars`, `MIT license`) |
| 09-28 | Jev Ultrafast | `21,102 stars on GitHub` ×2 (soft: `163 open issues`, the push date) |
| 09-29 | Laya (HF) | `4,478 likes on Hugging Face` ×2, `officially reports 0 downloads` |
| 09-30 | ZCode | `7,243 stars on GitHub` ×2 (soft: `11 open issues`, `last update on 2026-09-29`, `Apache-2.0 license`) |

The mechanism (`factverse/ai_pipeline.py`):

- `script_tool` fetches `_verified_facts(url)` (stars, license, last_update, open_issues; or
  HF downloads, likes) and tells the writer: *"use these numbers verbatim; they are the ONLY
  numbers you may state about the tool itself"*. The hook rule asks for "the most surprising
  concrete detail (stars, …)".
- It then stores `s["grounding"] = grounding`, the README only. The facts go into
  `s["verified_facts"]`.
- `run()` calls `gates.fact_check(script, …, script.get("grounding", ""))`. The fact-checker
  never sees the facts, so the number the writer was ordered to use is "unsupported". Because
  it is in the title or thumbnail, it is a critical failure, and the video is blocked.
- `gates.packaging_payoff` already counts `verified_facts` as support. `fact_check` was the one
  consumer left out.

The supervised `format=tool` dispatch (PHASES Now #4) would have been blocked the same way.

## Locked decisions

| # | Decision | Value |
|---|----------|-------|
| 1 | What fact_check reads | `gates.fact_sources(script)`: a `VERIFIED FACTS (official API)` block with the same `- key: value` lines the writer saw, placed **before** the grounding so `fact_check`'s `[:12000]` cut can never drop it. When there are no facts, it returns the grounding unchanged, so every non-tool lane behaves exactly as today. |
| 2 | One renderer | The writer's block and the fact-checker's block both come from `gates.facts_lines(facts)`. A formatting change cannot make the two disagree (e.g. `21,102` vs `21102`). |
| 3 | Planted facts | `_validate_script` pops `verified_facts`, as it already does `receipts` / `cheat_sheet` / `debate`. Without this, a model could invent `"verified_facts": {"stars": 99999}` and license its own number past the fact-check (and past `packaging_payoff`, which is the case today). `_carry_over` returns the legitimate value after every rewrite pass. |

## Out of scope

- `7 Secs` (09-27) is a speed claim, not an API fact. If the README does not say it, the block
  is **correct**, and this phase leaves it blocked.
- `verify_synthesis` / `replication_test` keep reading the grounding only.
- B.1's fallback order and the viral threshold are not changed.

## Done when

1. A tool script whose title says `21,102 stars` and whose `verified_facts` has
   `stars: 21102` reaches `fact_check` with `21,102` in the source text. Pinned by a test that
   stubs `ap.llm.generate_json` and reads the prompt.
2. A planted `verified_facts` in any LLM answer does not survive `_validate_script`. The real
   value survives a rewrite pass.
3. The full suite passes.
4. Live evidence is the next tool day in the ledger: a `PUBLISHED` `format=tool` row, or a
   block whose critical failures are not API facts.
