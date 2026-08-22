# HANDOFF — AI Pulse — Phase v3-C (income + packaging) — 2026-08-22

*Two phases shipped this session: v3-B (screen-recording visuals, PR #23) and v3-C (this).
`v3-phase-c` is stacked on `v3-phase-b`, so merge #23 first. The v3-B detail is in that PR's
commits and in docs/DECISIONS.md.*

## Done
- **Spec locked first** (docs/spec/ai-pulse-v3c.md, 11 decisions + binary acceptance criteria),
  then built. Nothing in the code introduces a value that is not in that table.
- **`factverse/deliverable.py`** — the free 1-page cheat sheet. A4 portrait, exactly one page:
  red header bar, title (Inter Black), WHAT IT IS / GET IT RUNNING (deliverable in a dark
  terminal box, JetBrains Mono) / MAKE THESE 3 THINGS / SKIP IT IF, footer with source + video
  links. Sections come from one `llm.generate_json` call; on failure the sheet still ships with
  the deliverable (`fallback_sheet`). File name `docs/tools/<date>-<slug>.pdf` is decided BEFORE
  upload (so the description can link it) and written AFTER upload (so it carries the video URL).
- **Description rebuilt around the transaction** (`place_description_blocks`): hook paragraph,
  then `🔧 Try it yourself` + command + source, then `📄 Free 1-page cheat sheet: <url>`, then the
  `promo_block` affiliate slot, then the rest. Previously the deliverable was appended at the
  very END of the description — below the fold, where nobody clicks.
- **`promo_block`** config key (default `""`) — the affiliate slot, inserted verbatim under the
  cheat-sheet line (tool) or after paragraph 1 (other lanes). Empty = never appears.
- **CI/state:** `reportlab` in requirements-ci.txt + test.yml + requirements.txt; the state-save
  step commits `docs/tools` (as a SEPARATE `git add` — an unmatched pathspec fails the whole
  command, and losing topic state causes duplicate videos); `docs/.nojekyll` for Pages.
- **Docs rewritten for v3:** README (tool lane as default, screencap in the pipeline diagram, new
  config keys, correct venv commands), CONTENT_PLAYBOOK (tool-video anatomy, description
  template, real Shorts hook angles/timings), STATUS (dated 2026-08-22, v3 A+B+C truth, owner
  actions). GLOSSARY + PHASES updated.
- **63/63 tests** (17 new this phase). Real reportlab renders in tests, not mocks.
- **Verified for real:** rendered two cheat sheets (full + LLM-failure fallback) and READ them —
  one page, correct sections, selectable text, links intact. Printed the assembled description
  for a real tool script and confirmed block order and idempotency.

## Review (36 agents; the account hit its weekly limit mid-run)
10 findings were skeptic-verified and 19 verifiers never ran. **I reproduced the four sharpest
unverified ones myself instead of assuming they were noise — all four were real bugs:**
1. LLM returning `steps` as a *string* made the sheet `['p','i','p','i','n']` (iterating a
   string yields characters) → `_as_list` coercion.
2. A long unbreakable command (`git+https://…`) ran off the code box → hard character wrap.
3. A description starting with a blank line put the block ABOVE the hook → `_insert_after_hook`
   strips leading newlines.
4. A non-tool script carrying a deliverable advertised a PDF that is never written →
   `_has_cheat_sheet` now mirrors `make_cheat_sheet`'s exact condition.
Plus the confirmed ones: the advice-gate rewrite can echo back a *partially mangled* block, and
trusting the `🔧` marker alone would ship a link to a file we never wrote → the block is now
compared exactly and repaired; `_insert_after_hook` no longer splits on the `\n\nSource:` tail
that `_validate_script` manufactures (that pushed the links below the whole body); README told
you to run a `playwright` that `setup.ps1` never installed; six doc facts were wrong (Shorts hook
angles are `cliffhanger`/`single_fact`, hook window 3.5 s / CTA 6 s, Short #1 lands ~2 h after the
long-form not on the grid, comments are posted but cannot be pinned, quota ~5.1k not ~6.8k).

## Files changed (v3-C)
- factverse/deliverable.py (NEW) · factverse/ai_pipeline.py (blocks, `_has_cheat_sheet`,
  `cheat_sheet` in `_CARRY`, `make_cheat_sheet` after upload, `cheat_sheet` in the run ledger)
- config.json + config.example.json (`deliverable_base_url`, `promo_block`)
- .github/workflows/publish.yml (state-save) · test.yml + requirements-ci.txt + requirements.txt
- docs/spec/ai-pulse-v3c.md (NEW) · docs/spec/GLOSSARY.md · docs/PHASES.md · docs/HANDOFF.md
- README.md · docs/CONTENT_PLAYBOOK.md · docs/STATUS.md · docs/.nojekyll · docs/tools/.gitkeep
- tests/test_pipeline_logic.py (17 new)

## Known broken / deliberately skipped
- **GitHub Pages is not enabled** — `https://dev-shivam-05.github.io/AI-PULSE/` returns 404
  today, so the `📄` link 404s until the owner enables it (one click, below).
- Pushes made with `GITHUB_TOKEN` may not trigger the Pages build. If a PDF 404s while the file
  IS visible in `docs/tools/` on main, that is the cause — any manual commit or a Pages
  re-deploy republishes it. Verify with `curl -I <the 📄 link>` after the first tool run.
- `promo_block` is empty: there is no affiliate yet. The slot is wired and tested.
- No PDF for news/evergreen/roundup (no deliverable there) — per spec.
- `latin-1` stripping only bites if no Unicode body font is found; publish.yml installs DejaVu.
- v3-B leftovers still open: Product Hunt pages ground thinly (3-candidate retry covers it);
  `REC_MAX` 300 s means a 900-word script loops its last chunks once.
- v2 owner backlog unchanged: duplicate NVIDIA/HF video, OAuth re-consent for comment chains.

## Next session starts here
1. **Owner:** merge PR #23 (`v3-phase-b`), then open + merge `v3-phase-c`
   (https://github.com/Dev-Shivam-05/AI-PULSE/pull/new/v3-phase-c).
2. **Owner:** enable Pages — Settings → Pages → Deploy from branch → `main` / `docs`.
3. **Owner:** supervised first tool run — Actions → "AI Pulse — Auto Publish" → Run workflow →
   format `tool`, before 12:23 UTC (5:53 PM IST). Watch for "Screen-recorded visuals",
   "Tool thumbnail", "Cheat sheet:". Then check the video description has the 🔧 and 📄 blocks
   directly under the first paragraph, and `curl -I` the PDF link.
4. **Then Phase v3-D** (learning loop v1) — but only after ~2 weeks of v3 analytics exist.
   The metric that decides everything: average view duration ≥ 2:00 over the first 10 tool
   videos (v2 baseline 0:38). If AVD is still under 1:00 after 10, the problem is the topic
   choice, not the packaging — reopen the spec, do not add machinery.
- Local dev: `py -3 -m pytest tests/ -q` (63 tests). System Python 3.11.9 has playwright +
  chromium + pygments + reportlab.
