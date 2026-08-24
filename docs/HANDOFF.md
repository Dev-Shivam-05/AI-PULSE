# HANDOFF — ToolDojo — Phase v3-E.2 (receipts.py) — 2026-08-24

*One phase, done end to end: spec locked (12 decisions), built, live-verified, then a
70-agent adversarial review over the diff (6 lenses → 32 raw findings → 20 confirmed
collapsing to 9 root causes + 5 upheld splits, 7 refuted) — every confirmed defect fixed
and pinned by a regression test. 137/137 tests. Branch `v3-phase-c` pushed (`8f7c377`),
still stacked on `v3-phase-b` — merge PR #23 first.*

## Done
- **`factverse/receipts.py`**: the "we checked this" claim is now true. `check_plan` (pure)
  turns the README-verbatim deliverable into a download-ONLY check — pip pinned to wheels
  (`--only-binary :all: --no-deps --no-cache-dir`; sdists execute setup.py, wheels execute
  nothing), `git clone --depth 1`, or a requests fetch with a real 60s WALL-CLOCK deadline
  + 2 GB cap and a sanitized filename. Segments with `|`, `&&`, `;`, `$(`, backticks,
  docker, npx or `<(` are refused; so are `pip install .`/`-e .`/`-r file` (a local dir
  makes pip execute the build backend). Candidate code is never executed, ever.
- **The beat**: `run_check` measures the real download (seconds, MB, output lines, PyPI
  version/date) and `add_beat` appends "Checked by ToolDojo on August 24: the download
  finished in 8 seconds at 1.7 megabytes." to the install scene — the same scene
  `inject_code_card` targets, positioned after every reject-gate and BEFORE
  `packaging_payoff`, so a thumb number spoken only in the beat is a kept promise (tested).
- **The footage**: `make_terminal_clip` renders the check's real output as a terminal clip
  (code-card palette, sequential reveal to 70%, then `OK: 1.7 MB in 8s — checked by
  ToolDojo 2026-08-24` holds in green), rendered to exactly its slot share (frame count
  CEILS — a floor made step5_build loop a 1-frame flashback). `inject_receipt_clip`
  replaces the still code card on the install scene; the final scene keeps the card.
- **Live-verified twice**: real cold check of openai 3.3.1; the FIRST frame inspection
  caught 3 shipping defects (tofu ✔ → the word OK, pip `[notice]` nags, the machine's
  own path in the Saved line); the second inspection is clean. Artifacts in
  `output/demo/receipts_live/`.
- Ledger rows now carry `receipts={kind, seconds, mb}` for v3-D.

## Files changed
- `factverse/receipts.py` — NEW: plan/check/beat/clip, all seams fail-soft `None`
- `factverse/ai_pipeline.py` — run() wiring (check → beat → rejoin narration → payoff;
  clip injection after inject_code_card), `receipts` in `_CARRY`, `script.pop("receipts")`
  after the format re-bind, isinstance-guarded ledger read
- `tests/test_pipeline_logic.py` — +8 tests (129→137), incl. an endless-stream fetch and
  both-separator path rules
- `config.json` / `config.example.json` — `receipts_check: true` (the kill-switch)
- `docs/spec/ai-pulse-v3e2.md` — the contract: 12 locked decisions + live-inspection
  amendments + the full review addendum
- `docs/PHASES.md`, `docs/DECISIONS.md` — board + decisions

## Decisions made (full table in the spec)
- Download-only is the security line; refusal is conservative (a refused segment costs the
  beat, never the day; flag `receipts_check` default true).
- The beat lands after fact_check deliberately — its numbers are OUR measurement, not
  source claims to be checked against grounding.
- Only `add_beat` may set `script["receipts"]`: `_validate_script` mutates the LLM dict in
  place, so a model-planted top-level key SURVIVES — it could fabricate the receipts
  footage, and a non-dict raised in the post-upload zone (double-publish). run() pops it.

## Known broken / deliberately skipped
- The fetch kind measures only direct-artifact URLs; `curl … | sh` style installers are
  refused rather than half-measured (stamping a 10KB stub as "the download" is a lie).
- Clone seconds include git's negotiation; honest but not pure transfer time.
- No run()-level integration test (the suite has none); the wiring adds no raise path and
  the supervised `format=tool` dispatch is the final proof.
- Everything in the previous handoff's owner list is still outstanding (see board `## Now`).

## Next session starts here
- **v3-F (distribution engine)** if building — but it needs Pages enabled first, so the
  real next milestone is the owner's click list: merge PR #23 → merge `v3-phase-c` →
  Studio rename to ToolDojo → enable Pages → supervised `format=tool` dispatch.
- First command: `/boot`
- Watch out for: **the receipts beat on the first live run.** Expect one of three log
  lines — `🧾 Receipts: pip 1.7 MB in 8s` (worked), `↻ deliverable is not
  download-checkable` (correct refusal, e.g. ollama's `curl | sh`), or `⚠️ receipts check
  failed — shipping without the beat` (fail-soft). All three ship a video; only a repeat
  pattern of the third across days means a threshold is wrong. And the standing trap pair:
  requests' `timeout` is per-read (never trust it as a deadline), and `pathlib .name` is
  platform-dependent (split on both separators for anything burned into an artifact).
