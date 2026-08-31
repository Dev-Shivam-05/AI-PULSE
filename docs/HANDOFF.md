# HANDOFF — ToolDojo — Phase v3-F.1 (the site) — 2026-08-31

*One phase, done end to end: spec locked (13 decisions), built, rendered and inspected in
the browser at two widths, then a two-lens adversarial review over the diff — 9 reproduced
defects, every one fixed and pinned by a regression test. 161/161 tests. Branch
`v3-phase-f` pushed, stacked on `v3-phase-c` — merge PR #23 (`v3-phase-b`) first, then
`v3-phase-c`, then this.*

## Done

- **`factverse/site.py`**: `docs/` is now a real website. One HTML page per tool video
  (`docs/tools/<date>-<slug>.html`, the same stem as its PDF), a regenerated
  `docs/index.html` and `docs/sitemap.xml`. Dark theme matching the code cards, the
  command in a copy-button box, what/uses/skip_if, a `youtube-nocookie` embed, the PDF as
  a download, OG/Twitter card pointing at the YouTube thumbnail (which is what F.2/F.3
  will render). No Jekyll, no build step, no CDN, no fonts, no analytics — `docs/.nojekyll`
  is committed, so Pages serves the directory verbatim.
- **The catalog is the source of truth.** `state/tools_index.json` holds one entry per
  tool video; every HTML file is 100% derived from it. CI therefore *regenerates* the site
  after `state_merge` (`python -m factverse.site`) rather than stashing it — the PDFs still
  stash to `/tmp`, because an LLM wrote them once and they cannot be reproduced.
- **The 📄 line now links the PAGE, not the PDF** (spec #5, supersedes v3-C decision 8), in
  both the description and the pinned comment. A PDF opened from mobile YouTube is a bad
  experience, and the page is the URL every later platform will share.
- **`deliverable.sheet_for()`**: one LLM extraction feeds both the PDF and the page. A
  *raising* extraction now falls back instead of losing the sheet — the module docstring
  already promised that and only the `return None` path honoured it.
- **Live-verified**: 3 realistic pages rendered and screenshotted at 1280px and 390px
  (index, page with video, page without). Zero horizontal overflow on all six; the Copy
  button really swaps to "Copied" and back after 1.5s under playwright. The first
  inspection caught 2 shipping defects (the index `<h1>` was not the two-tone wordmark; the
  last row's border doubled against the footer rule). Artifacts in `output/demo/site/`.
- **`docs/index.html` + `docs/sitemap.xml` are committed in their empty state**, so the site
  root is a real page the moment Pages is switched on rather than a 404 until the first run.

## Files changed

- `factverse/site.py` — NEW: catalog, render, rebuild, publish_page; every seam fail-soft
- `factverse/ai_pipeline.py` — run() wiring (sheet → PDF → page), the 📄 line and pinned
  comment point at the page, `_validate_script` pops planted `receipts`/`cheat_sheet`
- `factverse/deliverable.py` — `sheet_for()`, `safe_name()`, `sheet=` param
- `factverse/state_merge.py` — `_merge_index` + `state/tools_index.json` in `FILES`
- `.github/workflows/publish.yml` — catalog in the stash loop; rebuild between
  `state_merge` and `git add`; `git add docs/index.html docs/sitemap.xml`
- `tests/test_pipeline_logic.py` — +24 tests (137 → 161)
- `config.json` / `config.example.json` — `site_pages: true` (the kill-switch)
- `docs/spec/ai-pulse-v3f1.md` — the contract: 13 locked decisions + the review addendum
- `docs/PHASES.md` (F.1 done, F.2–F.4 queued), `docs/DECISIONS.md`, `docs/spec/GLOSSARY.md`,
  `CLAUDE.md` (3 new traps)

## Decisions made (full table in the spec)

- The catalog is state; the HTML is a build artifact. Only the source of truth needs the
  both-halves treatment (stash list AND `state_merge.FILES` AND merge semantics).
- `_merge_index` is a union keyed by `page`, not the generic list union — that one dedups
  on exact equality, so a retry with a new `video_url` would print the tool twice.
- The description links the page. Same `<date>-<slug>` stem as the PDF, so the name is
  still decided before the upload.
- Scope: v3-F.1 is the site only. Telegram / X / Reels are now board rows F.2 / F.3 / F.4,
  each needing its own secret and spec — the original F row was four phases of work.

## The review found the first fix was in the wrong place

Worth reading before touching this code. `script.pop("cheat_sheet")` in `run()` only
covered the FIRST validation — `critique_pass`, `enforce_length` and `enforce_max_length`
each validate again afterwards, and `_carry_over` restores only a key it finds in the
source. A name planted in a *later* rewrite answer therefore survived and shipped on the
live video as `.../tools/` with no file name. **The pop belongs inside `_validate_script`**,
which every pass runs before `_carry_over` hands the legitimate value back — and that also
closes the identical, still-open hole for `receipts`. The other 8 defects (an unchecked
`javascript:` href on our own origin, a download button for a PDF that was never written,
a single bad file freezing the index forever, a kill-switch that could not be flipped from
Actions) are in the spec's review addendum with their root causes.

## Known broken / deliberately skipped

- **Nothing is live until Pages is enabled** (owner click, below). Every page and PDF link
  404s until then — the same state the PDF has been in since v3-C, not a new failure.
- `GITHUB_TOKEN` pushes may not trigger a Pages rebuild (`docs/DECISIONS.md:115`). If the
  page is stale after the first tool run, Pages needs the Actions-based deploy instead of
  branch-deploy — a small F.1b row, not a redesign.
- No pages exist for past videos; the catalog fills from the next tool run forward.
- `docs/` also serves `HANDOFF.md`, `STRATEGY.md` and `docs/spec/` verbatim. The repo is
  public, so this exposes nothing github.com does not already serve, and the sitemap does
  not list them. If the repo ever goes private, add `docs/robots.txt`.
- `output/demo/hostile/` is untracked scratch a review agent left in the working tree —
  delete it whenever you like; I did not, because discarding files is your call.
- Everything in the previous handoff's owner list is still outstanding.

## Next session starts here

- **v3-F.2 (Telegram)** if building — the page's OG card is what it will render, so the
  hard part is already done; it needs a bot token in Actions secrets.
- The real next milestone is still the owner's click list: merge PR #23 → merge
  `v3-phase-c` → merge `v3-phase-f` → Studio rename to ToolDojo → **enable Pages**
  (Settings → Pages → Deploy from branch → `main` / `docs`) → supervised `format=tool`
  dispatch.
- First command: `/boot`
- Watch out for, on the first live tool run: the log line `🌐 Page: <url>` (worked) or
  `⚠️ site page failed — …` (fail-soft; the video still ships). Then `curl -I` both the
  page and the PDF — they share a stem, so if one 200s and the other 404s the naming
  drifted. And the standing trap pair: a `_CARRY` key run() computes itself must be popped
  inside `_validate_script`, and `pathlib .name` is platform-dependent — split on both
  separators.
