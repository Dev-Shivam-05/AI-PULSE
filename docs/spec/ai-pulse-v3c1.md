# SPEC LOCK — AI Pulse v3-C.1: tool-lane pre-flight hardening

Status: built 2026-08-23 on `v3-phase-c`. 75/75 tests.

Why this exists: the `format=tool` path had never executed end to end, and the first
supervised `workflow_dispatch` was about to be the first time. A six-surface adversarial
audit of that path found 8 defects that survived refutation, plus 2 found by hand. Each was
reproduced before its fix. This file records only the decisions that add a number, a list,
or a contract — the rest are bug fixes, listed in `docs/DECISIONS.md`.

## Locked decisions

| # | Decision | Value | Why |
|---|----------|-------|-----|
| 1 | Tool-lane grounding floor | `ai_pipeline.TOOL_GROUNDING_MIN = 1200` chars. Below it `script_tool` returns `None` and `build_script` moves to the next of `tools[:3]` | Product Hunt's server HTML is ~640 chars of pure nav chrome ("Overview Reviews 1 Team More"). It cleared `fetch_text`'s 400-char floor **and** `gates.fact_check`'s 200-char skip, so claims were verified against navigation text, came back unsupported, and blocked the day. 1200 clears the observed 640 with ~2× margin while a real README or model card (~5000) passes untouched. Owner-approved 2026-08-23 |
| 2 | Hugging Face grounding | For a URL matching `_hf_readme_url`, fetch the raw model card **only**. Never fall back to the HTML page | The hub page is a JS shell whose readable text is inlined `tokenizer_config` / `chat_template` JSON — 5000 chars of it, so the old "repair only if the page came back empty" branch could never fire. For a gated or README-less model the fallback grounds the whole video in a Jinja template that reads as real |
| 3 | Tool suitability screen | `gates.tool_unsuitable(title, text) -> (blocked, term)`, list `gates.UNSUITABLE_TOOL`. Applied twice: in `build_script`'s tool loop (title) and in `script_tool` after grounding (README). A hit **rejects**; the next candidate is tried | A tool video teaches the tool, which is an endorsement that reporting on it is not. `sensitive_topic_risk` covers only finance/health/legal/politics and only applies a confidence penalty. Verified live 2026-08-23: the #1 tool candidate (fit 70.5) was `watermarks-remover: Strip multi-vendor AI provenance marks`, with two `Qwen3.8-27B-Uncensored` forks at #5/#6 |
| 4 | Ledger format | `run()` re-binds `fmt = script.get("format", fmt)` immediately after `build_script` | `build_script` falls back `tool → evergreen → news`, but `fmt` was the request, not the result. Every `record_run` row — including the terminal `PUBLISHED` one — stamped a fallback video with a format nobody made, which is the ledger v3-D learns from |
| 5 | Publish-window invariant | Between a successful `yt_upload` and `record_run`, nothing may raise. `normalize_shorts_meta()` runs before the upload; `validate_shorts_batch` is tripped there; post-upload bookkeeping is wrapped | A raise in that window left a video live with no `PUBLISHED` row, so `already_published_today()` answered False and the 14:53 retry cron published a **second** video into the same slot. A missed bookkeeping write is recoverable; a duplicate publish is not |
| 6 | Cheat-sheet command integrity | `build_pdf` renders the full wrap of every step; the box caps at 8 rows and names the cut (`... full command in the video description`) | The wrap was sliced `[:2]`, so a 152-char `docker run … && docker exec …` shipped as `… ollama/ollama serve && docker` — still copy-pasteable, no longer valid, on a sheet whose own prompt says "Commands must be copied EXACTLY". A deliverable may be 300 chars, so this was the normal case |
| 7 | Review veto window | `publish.yml`'s publish step passes `GH_TOKEN: ${{ github.token }}` | Actions does not put `GITHUB_TOKEN` in a step's process environment, so `_notify_review` found no token, printed the review to the log, and a NOTIFY-routed video published unattended with nobody able to veto it |
| 8 | State-save on a feature branch | Commit the run's tracked writes onto the throwaway branch before `git checkout -B main origin/main`. No `--force` | A dispatch runs from `v3-phase-c` (the only ref with the tool code), where those writes differ from `origin/main`, so the checkout refuses and `bash -e` kills the step before `state_merge`, before `git add docs/tools`, before the commit. Committing first discards nothing; forcing would |
| 9 | Cheat sheets across state-save retries | PDFs stash to `/tmp/tools_incoming` before the checkout and are restored after, exactly as state files do | On retry pass 2 the PDF is no longer untracked but committed to the local `main` that `checkout -B` discards, so the checkout deleted it and the second `git add docs/tools` had nothing to add — while the published description already linked it |
| 10 | `tags` type | `_validate_script` coerces `tags` (str → split on `,`/newline; any other non-list → `[]`) | `setdefault` fills a missing key but never coerces a wrong type. All four of str/None/dict/int raised, and every tool-lane call site is bare, so the unattended run died with a traceback |

## OUT OF SCOPE
- Widening `UNSUITABLE_TOOL` beyond circumvention / safety-defeat / piracy — it is deliberately narrow
- A grounding *quality* check beyond length (a chrome detector, an LLM relevance judge)
- Retrying a blocked tool day as evergreen when the format was forced (see RISKS)
- v3-D learning loop — still needs ~2 weeks of v3 data

## ACCEPTANCE CRITERIA (binary)
- [x] A chrome-only page (400 < len < 1200) yields no tool script
- [x] A gated HF model fetches the card only, never the JS shell, and returns `None`
- [x] `tool_unsuitable` blocks the live provenance stripper and both `Uncensored` forks, and passes `Qwen3.8-27B`, the GGUF quant and Claude Academy
- [x] `_validate_script` survives `tags` as str / None / dict / int and still emits the brand tags
- [x] `normalize_shorts_meta` makes `validate_shorts_batch` unraisable for None / short / string-list / empty-title input
- [x] A 152-char command appears complete in the rendered PDF, and the sheet is still 1 page for a short command, a 152-char line, a 300-char deliverable and a 5-step overflow
- [x] `git checkout -B main origin/main` exits 0 from a diverged feature branch, and `origin/main` receives both the merged state file and the PDF bytes
- [x] The cheat-sheet PDF survives a failed-push retry of the state-save loop
- [x] 75/75 tests green

## RISKS
- **A forced `format=tool` run has no fallback.** `force_format` is not `None`, so the
  "a blocked story must not cost the day" evergreen fallback is skipped at all three gates.
  Correct for a supervised run — you want to see the failure — but it means a blocked tool
  day publishes nothing. Left as is; revisit if it bites on an unattended forced run.
- `UNSUITABLE_TOOL` is a keyword list, so it will both miss things and over-block. It is
  meant to be edited as real candidates appear.
- The audit covered 6 surfaces of the tool lane only. Decisions 5 and 10 land in shared code
  (`run()`, `_validate_script`) and so already protect news / evergreen / roundup too — but
  those lanes, `l2.inject` and `captions` were never searched for defects of their own.
