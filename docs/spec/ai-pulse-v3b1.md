# Spec — v3-B.1: tool-lane unblock

Status: **locked** (3 decisions, approved with `go` on 2026-09-26). **Not built yet.**
Supersedes the v3 "threshold 8" row (`docs/spec/ai-pulse-v3.md:50`) and, once merged, the
glossary's "utility lane" and "blocked-day fallback" lines.

## Why this phase exists

The ToolDojo pivot has never run: **0 of the 64 PUBLISHED ledger rows are `format=tool`.**
Measured on 2026-09-26 from `state/runs.jsonl`. The CI job logs are not readable without admin
rights (`GET /actions/jobs/{id}/logs` answers HTTP 403 "Must have admin rights to Repository"),
so the ledger CI commits back is the evidence.

- `tool_format` was `false` on main until the 2026-09-01 merge of PR #26 (`fcc1731`).
- Since 2026-09-01 the **first** attempt of every non-Sunday day was news: 22 of 22.
- `decide_format` runs news when the viral judge's score is `>= VIRAL_THRESHOLD`
  (8.0, `factverse/ai_pipeline.py:454`, `:1210`). `viral_pick` (`:457-487`) returns the
  **highest** of up to 8 LLM scores, and that maximum cleared 8 every day: the news published
  since 09-01 scored 9 ×11, 8 ×3, 10 ×1. A threshold the maximum always clears is not a gate,
  so the tool check at `:1212` was never reached.
- The three blocked-day fallbacks all force `evergreen`: policy (`:1488-1490`), advice
  (`:1513-1515`), fact-check (`:1528-1530`). On the 10 blocked days since 09-01 the tool lane
  was never tried.
- The same viral judge scores "emotional charge (awe / fear / outrage / wonder)" and a
  "stop scrolling" framing (`:463-468`) — the source of titles like "AI MELTDOWN!" and
  "Meta Muse AI EXPOSED". That rubric is v3-G.3's (packaging), not this phase's.

## Locked decisions

| # | Decision | Value |
|---|----------|-------|
| 1 | When news runs | `VIRAL_THRESHOLD` 8.0 → **10.0**. On the 09-01 → 09-25 data news would have run once in 22 weekdays; every other weekday goes to the utility lane — tool when a tool signal exists and `tool_format` is on, else evergreen. `decide_format`'s own logic is unchanged. |
| 2 | After a blocked story | An **automatic** run (no `force_format`) whose script is blocked by the policy, advice or fact-check gate re-runs as **`tool`** when `fv.flag("tool_format")` is on (else `evergreen`, as today). A **fallback** run that is blocked again re-runs as `evergreen` if it was not evergreen already — **one level only**. A blocked evergreen fallback publishes nothing (as today). An **owner-forced** run (`force_format` from the CLI or a `workflow_dispatch`) still has **no** fallback. Update the glossary. |
| 3 | Merge condition | The PR merges only after **one supervised `workflow_dispatch` with `format=tool` has published** (owner: Actions → "AI Pulse — Auto Publish" → Run workflow → format `tool`, on a weekday before 12:23 UTC / 17:53 IST, so that day's cron then skips). The tool lane has never run in CI. |

## How — mechanics, no new numbers

- `run(publish=False, force_format=None, fallback=False)`. `fallback` is `True` only on the
  recursive calls the gates make.
- One pure helper, used at all three gate sites instead of the inline condition:

  ```python
  def _fallback_format(fmt: str, force_format: str | None, fallback: bool,
                       tool_on: bool) -> str | None:
  ```

  | Case | Returns |
  |---|---|
  | `force_format` set and `fallback` is False (owner-forced) | `None` |
  | automatic first run, `fmt` not in (`tool`, `evergreen`), `tool_on` | `"tool"` |
  | automatic first run, `fmt` not in (`tool`, `evergreen`), not `tool_on` | `"evergreen"` |
  | automatic first run, `fmt == "tool"` (the utility lane chose tool and it was blocked) | `"evergreen"` |
  | any run with `fmt == "evergreen"` | `None` |
  | `fallback` is True and `fmt != "evergreen"` | `"evergreen"` |

  Each site then does
  `nxt = _fallback_format(...); if nxt: return run(publish=publish, force_format=nxt, fallback=True)`
  and prints `↪️  Falling back to a tool video — …` or the existing evergreen line.
- `fmt` is already re-bound from the returned script (`ai_pipeline.py:1453`). A `tool` request
  that `build_script` turned into an evergreen script (`:1270-1271`) is therefore treated as
  evergreen by the helper: no second evergreen attempt.
- The docstring at `ai_pipeline.py:9` ("v3: 8/10") and the comment at `:454` are updated to 10.

## Files

- `factverse/ai_pipeline.py`: the threshold, the docstring, the `run()` signature, the helper
  and the three call sites.
- `tests/test_pipeline_logic.py`: see the acceptance criteria.
- `docs/spec/GLOSSARY.md`: the "utility lane" and "blocked-day fallback" lines.
- `docs/PHASES.md`, `docs/DECISIONS.md`, `docs/HANDOFF.md`.

## Acceptance criteria

- [ ] `VIRAL_THRESHOLD == 10.0`. A test pins `decide_format` choosing `tool` for a best viral
      score of 9.0 when a tool signal exists and the flag is on, and `news` for 10.0.
- [ ] The helper's truth table (every row above) is tested.
- [ ] A test proves a blocked automatic news run calls
      `run(force_format="tool", fallback=True)`, and a blocked fallback tool run calls
      `run(force_format="evergreen", fallback=True)` (stub `ap.run`'s recursion and the gates,
      as the consumer sees them).
- [ ] An owner-forced `format=tool` run that is blocked still returns `None` without recursing
      (the supervised-run semantics in `docs/PHASES.md` → Now #4).
- [ ] The full suite is green (run it in the background — it takes ~2.5 min) and the branch is
      pushed. The owner opens the PR only after decision 3.

## Out of scope

- Rewriting the viral judge's rubric, and titles/hooks in general (v3-G.3).
- Sunday roundup scheduling.
- Anything visual (v3-G.1).

## Risks

- **The tool lane has never run in CI.** Decision 3 gates the merge on one supervised run;
  until then, B.1 changes nothing live.
- More tool days means more `gates.tool_unsuitable` refusals and grounding-floor retries. Each
  falls back to evergreen inside `build_script`, so a day is not lost.
- News becomes rare (about 1 day in 22 on the measured data). That is the v3 intent: the comment
  at `:454` already says "the utility lane is the default".
