# HANDOFF — AI Pulse — Phase v3-C.1 (tool-lane pre-flight hardening) — 2026-08-23

*v3-D is still blocked: `docs/tools/` is empty, all 66 runs in the ledger are v2 news/roundup,
so there is no v3 data to learn from. This session hardened the one thing on the critical path
that needed nothing from you — the `format=tool` code path, which had never executed end to end
and was about to do so live. Six-surface adversarial audit: 34 candidate defects → 8 confirmed
after refutation, plus 2 found by hand. **Every one was reproduced before it was fixed.**
Contract: `docs/spec/ai-pulse-v3c1.md`. Branch `v3-phase-c` is pushed (`21c81e1`), still stacked
on `v3-phase-b` — merge PR #23 first.*

## Done
- **The channel will no longer write a tutorial for a tool it should not teach.**
  `gates.tool_unsuitable` screens title and README; `build_script` skips the candidate and
  `script_tool` rejects again on the grounding. Verified against the live signal engine today:
  it blocks `guillaumemeyer/watermarks-remover: Strip multi-vendor AI provenance marks` (which
  was the **#1 tool candidate**, fit 70.5) and both `Qwen3.8-27B-Uncensored` forks, and passes
  `Qwen3.8-27B`, the GGUF quant and Claude Academy. Without this, the first tool video this
  channel ever published was a step-by-step guide to defeating AI provenance.
- **A tool video can no longer be written from navigation chrome.** Grounding floor 1200 chars
  (you approved it). Product Hunt returns ~640 chars of "Overview Reviews 1 Team More", which
  cleared `fetch_text`'s 400 floor *and* `gates.fact_check`'s 200 skip — so claims were
  fact-checked against nav text, came back unsupported, and blocked the day.
- **Hugging Face videos are grounded in the real model card.** Verified live against
  `deepseek-ai/DeepSeek-V3`: before, the prompt's SOURCE EXCERPT opened with
  `"lstrip":false,"normalized":true`; after, with *"We present DeepSeek-V3, a strong
  Mixture-of-Experts…"*. A gated model now returns `None` rather than grounding on the JS shell.
- **Today can no longer publish twice.** A raise between `yt_upload` and `record_run` left a
  video live with no `PUBLISHED` row, so `already_published_today()` said no and the 14:53 cron
  published a second video into the same slot. The re-hook tripwire now fires before the upload;
  post-upload bookkeeping cannot abort the ledger row.
- **The cheat sheet ships the whole command.** The wrap was sliced to two rows, so a 152-char
  `docker run … && docker exec …` rendered as `… ollama/ollama serve && docker` — still
  copy-pasteable, no longer valid. One page still holds for a 300-char deliverable and a 5-step
  overflow.
- **CI can actually save state from a dispatch.** `git checkout -B main origin/main` was
  aborting (reproduced, EXIT=1) because a dispatch runs from `v3-phase-c` where tracked state
  differs from `origin/main`; under `bash -e` the step died before `state_merge`, before
  `git add docs/tools`, before the commit. Also fixed: the retry loop deleted the cheat-sheet
  PDF it had just committed.
- **The review veto window works.** `GH_TOKEN` now reaches the publish step, so a NOTIFY-routed
  video opens a review issue instead of printing it to a log nobody reads.
- `_validate_script` survives `tags` as str / None / dict / int (all four raised before).
- The ledger stops stamping a `tool → evergreen` fallback as `format="tool"` — that ledger is
  exactly what v3-D is meant to learn from.
- **75/75 tests** (was 63), plus a 20-check end-to-end smoke of the description → PDF chain.

## Files changed
- `factverse/ai_pipeline.py` — suitability screen + 1200 floor + HF card-only grounding in
  `script_tool`; `normalize_shorts_meta` (new, pure) and the tripwire moved before upload;
  post-upload bookkeeping made non-fatal; `fmt` re-bound from the returned script; `tags`
  coercion in `_validate_script`; mangle-repair now excises every stale block fragment.
- `factverse/gates.py` — `UNSUITABLE_TOOL` + `tool_unsuitable()`, the only gate that refuses a
  topic outright rather than penalising it.
- `factverse/deliverable.py` — render the full command wrap; cap the box at 8 rows and name the
  cut instead of hiding it.
- `.github/workflows/publish.yml` — stash/restore `docs/tools/*.pdf` across the state-save retry;
  commit tracked writes before `checkout -B` (no `--force`); `GH_TOKEN` on the publish step.
- `tests/test_pipeline_logic.py` — 12 new tests, incl. one that composes the whole tool lane
  end to end rather than link by link.
- `docs/spec/ai-pulse-v3c1.md` (NEW), `docs/DECISIONS.md`, `docs/PHASES.md`, `CLAUDE.md`.

## Decisions made
- **1200-char grounding floor** for the tool lane (you chose it from a 3-option table). Smallest
  value clearing the observed 640-char chrome with margin while a real README (~5000) passes.
- **The tool lane rejects, it does not penalise.** A tool video teaches its subject, which is an
  endorsement that reporting on it is not. `sensitive_topic_risk` only ever applied a confidence
  multiplier, and its list is finance/health/legal/politics — nothing for circumvention.
- **Commit-then-checkout, never `--force`,** in the CI state-save. Forcing would have discarded
  the run's tracked writes; committing them onto the throwaway branch discards nothing.
- **Nothing may raise between the upload and the ledger row.** A missed bookkeeping write is
  recoverable; a duplicate publish on an inauthentic-content-policy-sensitive channel is not.
- Full list with reasons: `docs/spec/ai-pulse-v3c1.md` and `docs/DECISIONS.md`.

## Known broken / deliberately skipped
- **GitHub Pages is still not enabled** — every `📄` link 404s until you click it on. Needs repo
  admin; no `gh` CLI on this machine.
- **A forced `format=tool` run has no evergreen fallback.** `force_format` is not `None`, so all
  three gates skip the "a blocked story must not cost the day" path. Deliberate for a supervised
  run — you want to see the failure — but a blocked tool day publishes nothing.
- **`UNSUITABLE_TOOL` is a keyword list**, so it will both miss things and over-block. It is
  meant to be edited; that is now step 3 of the owner list in `docs/PHASES.md`.
- **Only the tool lane was audited.** The shared fixes (`_validate_script`, publish window) do
  protect news/evergreen/roundup, but those lanes were never searched for defects of their own.
- The first audit run lost 5 of 6 surfaces to API/network errors; it was re-run and the second
  pass completed 40/40. The findings above are from the complete pass.
- `promo_block` still empty; no PDF for non-tool formats; v2 backlog (duplicate NVIDIA/HF video,
  OAuth re-consent) untouched.

## Next session starts here
- Phase v3-D: feed `state/runs.jsonl` + `state/analytics.jsonl` back into topic and packaging
  choices — but still only once ~2 weeks of v3 data exist. Until the first tool video publishes,
  the next session is a review, not a build.
- First command: `/boot`
- Watch out for: **judging v3 before the data exists.** The verdict metric is average view
  duration ≥ 2:00 across the first 10 tool videos (v2 baseline 0:38). If AVD is still under 1:00
  after 10 videos, the topic choice is wrong, not the packaging — reopen the spec instead of
  adding machinery. Second trap: any new top-level script key must be added to `_CARRY`, and
  nothing new may raise between `yt_upload` and `record_run` (see `CLAUDE.md`).
