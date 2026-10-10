# Spec — v3-B.4: tool-lane supply fix

Status: **locked** (owner approved the values below with "go", 2026-10-10).

## Why this phase exists

Since 10-07 the tool lane has failed all 3 of its candidates every day. `build_script`'s
tool → evergreen → news fall-through writes no ledger row for a candidate that fails, so the
ledger shows only the fallback.

A read-only diagnosis on 2026-10-10 replayed `script_tool`'s path before the LLM call on all
9 failed candidates (10-07..10-09) with the repo's own functions:

- All 9 passed the 1,200-char floor (`TOOL_GROUNDING_MIN`), `gates.tool_unsuitable` and the facts
  fetch.
- None had a fenced code block or an install command inside the 5,000-char grounding window.
  So the v3-E containment check ("↻ deliverable not found in the source — rejected.") almost
  certainly rejected each one.
- **6 of 9 were Product Hunt pages.** Their text is stripped HTML with no ``` fences, so they
  could never pass that check. Each one still cost a writer call and one of the 3 slots.
- **2 were real candidates whose first fence sat just past the cut.** The google/embeddinggemma-2
  card's first fence is at char 5,190 (`pip install -U sentence-transformers transformers`). The
  CopilotKit/OpenDots README's first fence is at char 7,227. The live run shows that fence is a
  ```` ```mermaid ```` diagram; its `git clone` block is at 8,491 (see Known limits).

## Locked decisions

| # | Decision | Value |
|---|----------|-------|
| 1 | Eligibility | Only a **GitHub repo** (`_gh_repo`) or a **Hugging Face model** (`_hf_readme_url`) goes to `script_tool`. `ai_pipeline.tool_source_eligible(url)` checks this. Anything else (e.g. producthunt.com) is skipped before a writer call, with the log line `⏭️ Skipping tool candidate (not a GitHub repo or HF model): <title>`. |
| 2 | Slot counting | The filter runs in the same loop as the title screen, **before** `tools[:3]`. "3 candidates tried" now means 3 *eligible* candidates. A skipped Product Hunt page does not use up a slot. |
| 3 | Fetch size | The raw README / HF card is fetched with `TOOL_README_FETCH = 20000` chars. |
| 4 | Writer window | Unchanged: `grounding = full[:5000]`. `fetch_text` applies its 400-char floor to the whole text before it slices, so this window is byte-identical to the old `limit=5000` fetch. |
| 5 | Fence append | If `_first_fenced(grounding)` is empty but `full` has a fenced block, that first raw block (with its ``` fences) is appended to `grounding` after a blank line. If the block *starts* inside the window (it was cut by it), the cut copy is dropped first. Otherwise its dangling opening fence would pair with the appended one, and `_first_fenced` would return a truncated command. Log line: `📎 first code block was past the excerpt — appended (<n> chars).` |
| 6 | Consistency | The writer prompt, `command_grounded`, `_first_fenced`, `s["grounding"]` (and so `gates.fact_sources`, `verbatim_overlap`, `verify_synthesis`, `replication_test`, `grounding_chars`) all read the same appended text. The 1,200 floor is measured before the append, as before. `gates.tool_unsuitable` still reads README + page. Its screen is built **after** the append, so it reads at least what the writer reads. |
| 7 | GitHub page fallback | Unchanged. A repo with no raw README is grounded on its rendered page, and nothing is appended from it (the page has no fences). |
| 8 | Visible rejection | The silent `return s` where `_validate_script` returned nothing now prints `↻ writer returned no valid tool script — rejected.` and returns `None`. |
| 9 | Fail soft | A fetch that answers `""` or `None` still costs only the candidate (`or ""` on each fetch). |

## Files changed

- `factverse/ai_pipeline.py`: `TOOL_README_FETCH`, `tool_source_eligible`, `_fenced_block_raw`;
  the `script_tool` grounding block and writer-rejection log; the `build_script` tool loop.
- `tests/test_b4_tool_supply.py` (new, 12 tests, helpers prefixed `_b4_`).
- `tests/test_pipeline_logic.py`: one existing test candidate
  (`test_unsuitable_tools_are_skipped_before_a_tutorial_is_written`) gained a GitHub `url`. It
  had none, so the eligibility rule correctly skipped it.

## Verification (live, read-only, 2026-10-10, no LLM)

`signal_engine.rank(limit=20)` with the real feeds, filtered by `too_many_failures` as `run()`
does. Then the worktree's eligibility filter, then the real `script_tool` with the writer call
stubbed to capture the prompt:

```
ranked=19  tool signals=7
  eligible         huggingface/trending   https://huggingface.co/google/embeddinggemma-2
  eligible         github/trending        https://github.com/Louis-CFM/coucou
  SKIP not GH/HF   producthunt            https://www.producthunt.com/products/reso
  SKIP not GH/HF   producthunt            https://www.producthunt.com/products/agentdock
  SKIP not GH/HF   producthunt            https://www.producthunt.com/products/kernelai
  SKIP not GH/HF   producthunt            https://www.producthunt.com/products/maildun-for-mac
  eligible         github/trending        https://github.com/omlahore/RemoveMacAI

== first 3 of 3 eligible, through script_tool (LLM stubbed) ==
--- https://huggingface.co/google/embeddinggemma-2
     📎 first code block was past the excerpt — appended (61 chars).
     ↻ writer returned no valid tool script — rejected.
    grounding chars=5063  fenced block in grounding=True
    _first_fenced -> 'pip install -U sentence-transformers transformers'
--- https://github.com/Louis-CFM/coucou
     📎 first code block was past the excerpt — appended (149 chars).
     ↻ writer returned no valid tool script — rejected.
    grounding chars=5151  fenced block in grounding=True
    _first_fenced -> 'brew install xcodegen • git clone https://github.com/Louis-CFM/coucou.git • cd coucou/NotchBuddy • xcodegen • open NotchBuddy.xcodeproj # then ⌘R'
--- https://github.com/omlahore/RemoveMacAI
     ↻ writer returned no valid tool script — rejected.
    grounding chars=5000  fenced block in grounding=True
    _first_fenced -> 'curl -fsSL https://raw.githubusercontent.com/omlahore/RemoveMacAI/main/install.sh | bash -s app'

== the two diagnosis candidates whose fence sat past the 5,000-char cut ==
--- https://github.com/CopilotKit/OpenDots
     📎 first code block was past the excerpt — appended (662 chars).
     ↻ writer returned no valid tool script — rejected.
    grounding chars=5664  fenced block in grounding=True
    _first_fenced -> 'flowchart TB • Web["Web app: pages, Spaces, Dots, chat"] -->|AG-UI| Runtime[CopilotKit runtime] • Slack[Slack] Managed[Managed channel connection] • Managed Cha'
--- https://huggingface.co/google/embeddinggemma-2
     📎 first code block was past the excerpt — appended (61 chars).
     ↻ writer returned no valid tool script — rejected.
    grounding chars=5063  fenced block in grounding=True
    _first_fenced -> 'pip install -U sentence-transformers transformers'
```

The "writer returned no valid tool script" lines come from the stub (it answers `None`). They
also show that decision 8's log line fires. Before B.4, today's first 3 candidates would have
been embeddinggemma-2, coucou and Product Hunt `reso`. Two of those had no fence in grounding,
and `reso` could never have one. Now all 3 eligible candidates carry a real command.

## Known limits

- **The first fence is not always a command (OpenDots).** Decision 5 appends the *first* block,
  as approved. In OpenDots that block is a ```` ```mermaid ```` flowchart. If the writer's command
  is not verbatim in the source, the v3-E repair puts `_first_fenced`'s output on the code card,
  in the description and in the PDF. Here that output is diagram text. Before B.4 this candidate
  was rejected. OpenDots itself is now excluded by `too_many_failures` (it failed 10-08 and 10-09),
  but the class is real. The same hazard already existed for any README whose first fence inside
  5,000 chars is a diagram. **Proposed follow-up (needs one word):** skip fences whose info
  string is `mermaid`, both in `_first_fenced` and in the appended block.
- **Product Hunt still uses ranking slots.** The skip happens in `build_script`. 4 of today's 7
  tool signals were Product Hunt items that can never become a tool video. Ranking was out of
  scope: `signal_engine.rank`'s per-feed cap (`feed_max`), and whether an Atom entry's `updated`
  or `published` date drives recency, are left as they are.
- **Hugging Face Spaces are not eligible.** No feed produces them, and `_hf_readme_url` does not
  match the 3-segment `huggingface.co/spaces/<owner>/<name>` URL. Eligibility therefore covers
  GitHub repos and HF models only.
- **The appended block has no size cap.** It is at most what fits inside the 20,000-char fetch,
  but a long first code listing would lengthen the writer prompt and every gate's source text by
  that much. No cap was approved.
- **The failing gate is inferred, not read.** The CI logs that would show the exact rejection
  line need authentication (they answer 403). The containment gate is the only remaining
  rejection consistent with the replay. The first tool day after merge will confirm it through
  the new log lines.

## Done when

1. `build_script("tool")` never calls `script_tool` for a non-GitHub/HF URL, and skipped
   candidates do not use up the 3 slots.
2. A card whose only fence starts at char 5,190 reaches the writer prompt and passes containment.
3. A README with a fence inside 5,000 chars yields byte-identical grounding.
4. Full suite green; live run above.
