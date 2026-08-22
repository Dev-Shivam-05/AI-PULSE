# HANDOFF — AI Pulse — Phase v3-C (income + packaging) — 2026-08-22

*Two phases shipped this session. `v3-phase-b` (original visuals) is PR #23; `v3-phase-c` is
stacked on top of it — merge #23 first. v3-B's own detail lives in docs/DECISIONS.md.*

## Done
- A tool video now writes **one A4 cheat-sheet PDF** to `docs/tools/<date>-<slug>.pdf`: red
  header, title, WHAT IT IS, GET IT RUNNING (the exact command in a dark terminal box), MAKE
  THESE 3 THINGS, SKIP IT IF, footer with source + video links. Verified by rendering two real
  PDFs (LLM path and LLM-failure fallback) and reading them: one page, selectable text.
- A tool video's **description opens with the transaction**: hook paragraph, then
  `🔧 Try it yourself` + command + source, then `📄 Free 1-page cheat sheet: <url>`, then the
  `promo_block` affiliate slot, then the rest. Running the placement twice changes nothing, and
  a rewrite pass that mangles the block gets it repaired rather than trusted.
- Tool videos are illustrated by **the tool itself** (v3-B): headless Chromium records its real
  page, trimmed by measured load latency and cut into per-scene clips, plus a Pygments code card
  of the command and a thumbnail built from the page screenshot. Live E2E: 10 of 10 sampled
  frames were real UI (spec needs ≥7). Falls back to stock if capture fails.
- `tool_format` is **true** — the tool lane is live at merge.
- **63/63 tests** pass locally and on each PR (`test.yml`).

## Files changed
- `factverse/deliverable.py` (NEW) — cheat-sheet PDF: naming, public URL, LLM extraction with
  fallback, one-page renderer.
- `factverse/screencap.py` (NEW, v3-B) — screen-recording visual provider + code cards.
- `factverse/ai_pipeline.py` — description blocks, `_has_cheat_sheet`, `_CARRY` (+`cheat_sheet`),
  `make_cheat_sheet` after upload, capture/code-card/thumbnail seams, `_hf_readme_url`,
  `filter_segment` fix.
- `factverse/thumbnail.py` — `make_tool_thumb` (page screenshot + overlay).
- `config.json` / `config.example.json` — `tool_format: true`, `deliverable_base_url`, `promo_block`.
- `.github/workflows/publish.yml` — chromium cache + soft install, `format` dispatch input,
  state-save commits `docs/tools` via a separate `git add`.
- `.github/workflows/test.yml`, `requirements-ci.txt`, `requirements.txt` — pygments, reportlab,
  playwright pinned exactly.
- `tests/test_pipeline_logic.py` — 38 new tests across B and C.
- `docs/spec/ai-pulse-v3c.md` (NEW), `docs/spec/GLOSSARY.md`, `docs/DECISIONS.md`,
  `docs/PHASES.md`, `docs/STATUS.md`, `docs/CONTENT_PLAYBOOK.md`, `README.md`, `CLAUDE.md` (NEW).

## Decisions made
- The cheat sheet always ships: LLM extraction failure falls back to the deliverable, never to
  "no PDF". The PDF name is decided before upload, the file written after (it carries the video URL).
- Links go above the fold, under the hook paragraph — v3-A appended the deliverable at the end
  of the description, where nobody scrolls.
- The description block is compared exactly and repaired, because matching the `🔧` marker alone
  could publish a link to a file that was never written.
- The affiliate slot (`promo_block`) is wired and empty: adding an affiliate is a config edit.
- Hosting is GitHub Pages from `main` `/docs` (₹0), not a paid host or a new service.
- Tool videos get 100% original visuals when capture succeeds; stock is the failure path only.
- Full list, with reasons: `docs/DECISIONS.md` (Phase B and Phase C sections).

## Known broken / deliberately skipped
- **GitHub Pages is not enabled** — `https://dev-shivam-05.github.io/AI-PULSE/` 404s today, so
  every `📄` link 404s until the owner clicks it on. Needs repo admin; no `gh` CLI here.
- `GITHUB_TOKEN` pushes may not trigger the Pages build — if a PDF 404s while the file is visible
  in `docs/tools/` on main, that is why; any manual commit republishes it.
- `promo_block` is empty — because there is no affiliate or product yet.
- No PDF for news / evergreen / roundup — because they have no deliverable (spec).
- Product Hunt pages ground thinly, so `script_tool` often rejects them — the 3-candidate retry
  covers it; not worth fixing before real logs exist.
- `REC_MAX` is 300 s, so a 900-word script loops its last recording chunks once — acceptable.
- v2 backlog untouched: the duplicate NVIDIA/HF video, and the OAuth re-consent that would
  activate comment chains.

## Next session starts here
- Phase v3-D: feed `state/runs.jsonl` + `state/analytics.jsonl` back into topic and packaging
  choices — but only once ~2 weeks of v3 data exist, so the next session is probably a review of
  the first tool videos, not a build.
- First command: `/boot`
- Watch out for: **judging v3 before the data exists.** The verdict metric is average view
  duration ≥ 2:00 across the first 10 tool videos (v2 baseline 0:38). If AVD is still under 1:00
  after 10 videos, the topic choice is wrong, not the packaging — reopen the spec instead of
  adding machinery. Second trap: any new top-level script key must be added to `_CARRY` or the
  rewrite passes silently drop it (see `CLAUDE.md`).
