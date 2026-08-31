# Spec — v3-F.1: GitHub Pages becomes a real site

Status: **locked 2026-08-31** (owner approved the table below with `go`, no changes).
Branch: `v3-phase-f` (stacked on `v3-phase-c`). Predecessor spec: `docs/spec/ai-pulse-v3c.md`
(the cheat-sheet PDF), `docs/spec/ai-pulse-v3e2.md` (receipts).

## Why this phase exists

`docs/tools/*.pdf` has been the channel's only owned surface, and a PDF is a dead end: it
does not open well on a phone, it cannot be linked to from Telegram or X with a preview
card, and it cannot grow. v3-F.1 turns the already-committed `docs/` directory into an
actual website — one HTML page per tool video plus a regenerated index — so that every
later distribution surface (F.2 Telegram, F.3 X, F.4 Reels) has a URL worth sharing.

Everything here is static: **`docs/.nojekyll` is committed, so GitHub Pages serves the
directory verbatim.** There is no Jekyll, no plugin allowlist, no build step, no
dependency. Markdown would serve as raw text; therefore the generator emits HTML.

## Locked decisions

| # | Ambiguity | Locked value | Why this default |
|---|---|---|---|
| 1 | What "a real site" is | `factverse/site.py` writes three artifact kinds: `docs/tools/<date>-<slug>.html` (one per tool video), `docs/index.html` (regenerated), `docs/sitemap.xml`. No Jekyll, no build step, no dependencies | `docs/.nojekyll` is already committed — Jekyll is off, so markdown would serve as raw text. Plain HTML has zero moving parts in an unattended run |
| 2 | Where page data lives | `state/tools_index.json` — a **list** of entries `{page, pdf, title, slug, date, tool, command, source_url, video_url, video_id, what, uses[3], skip_if}`. HTML is 100% derived from it and regenerated every run | The catalog is state (mergeable); HTML is a build artifact. A list gets `_merge_list` semantics for free, but see #3 |
| 3 | Merge semantics for the catalog | New `_merge_index` in `state_merge`: union keyed by `page`, **later `date` + `video_url` wins**; `state/tools_index.json` added to `FILES`. Basename is unique across `FILES` | The default list-union would duplicate an entry whose `video_url` changed on a retry, printing the same tool twice on the index |
| 4 | HTML survives `checkout -B main origin/main`? | **Not stashed to /tmp.** CI runs `python -m factverse.site` *after* `state_merge`, before `git add`; `git add docs/index.html docs/sitemap.xml docs/tools` as a separate, unmatched-pathspec-safe add | PDFs are stashed because an LLM wrote them once and they cannot be reproduced. HTML is pure output of the merged catalog — regenerating is strictly safer than copying |
| 5 | What the description links (📄 line) | **The page**, not the PDF: `📄 Free 1-page cheat sheet: <base>/tools/<date>-<slug>.html`. The page carries the copy-button command, the embedded video, and a "Download the 1-page PDF" button | A PDF opened from mobile YouTube is a bad experience; the page is the only thing that can grow (Telegram/X later share this URL). This supersedes v3-C decision 8's PDF link |
| 6 | Page name | `deliverable.pdf_name()`'s stem + `.html` — the same `<date>-<slug>` — decided pre-upload alongside `cheat_sheet` | The description must link it before the upload; one slug for both files means no second naming rule to drift |
| 7 | Page sections, in order | ToolDojo wordmark → `<h1>` title → the command in a code box with a Copy button → "What it is" (≤40 words) → 3 uses → "Skip it if" → 16:9 `youtube-nocookie` embed → Download PDF button → Source link → footer (channel + date) | Exactly the cheat-sheet fields already extracted by `deliverable.extract_sheet()`; no second LLM call, no new prompt |
| 8 | Visual design | Single dark theme, committed: bg `#0D1117`, text `#E6EDF3`, muted `#8B949E`, accent `#DC2626`, code box `#161B22` with `#30363D` border, system font stack, `max-width: 720px`, 16px base / 15px mobile. All CSS inlined in a `<style>` per page | `#0D1117`/`#DC2626` are already `INK`/`RED` in `deliverable.py`; matches the code cards on screen |
| 9 | JavaScript | One inline `<script>`, ~12 lines: Copy button → `navigator.clipboard.writeText`, label swaps to `Copied` for 1.5s; on failure it selects the text instead. Nothing else — no analytics, no fonts, no CDN | The command is the product. Everything else degrades to plain HTML with JS off |
| 10 | Sharing metadata | `<title>`, `<meta name=description>` (= the "what" line, ≤160 chars), canonical, and OG/Twitter tags with `og:image = https://i.ytimg.com/vi/<video_id>/maxresdefault.jpg` | The video ID is already in `yt_url`, so a share card costs zero uploads — and Telegram/X (F.2/F.3) render exactly these tags |
| 11 | Index page | Newest-first list of every catalog entry: date, title, one-line "what", `→` to the page. Header = channel name + one-line pitch + YouTube link. No pagination | At one video a day it is ~365 rows in a year; a flat list is faster than pagination and fully greppable |
| 12 | Failure behaviour | Every seam returns `None`/no-op on exception; the site write happens **after** `make_cheat_sheet` in the post-upload zone, wrapped so nothing can raise before `record_run`. Log lines: `🌐 Page: <url>` / `⚠️ site page failed — …` | The standing repo rule: a raise past `yt_upload` costs a duplicate publish |
| 13 | Kill switch | `config.json` `"site_pages": true` | Matches `receipts_check`; lets the owner turn the site off without a revert |

### Implementation notes (decided during the build, inside the locked table)

- **The pinned comment follows decision 5 too.** `pinned_comment()` carries the same
  "📄 Free cheat sheet:" promise as the description; pointing one at the page and the
  other at the PDF would be two different answers to the same question. Both link the page.
- `script["cheat_sheet"]` keeps holding the **PDF** file name (that is what
  `deliverable.make_cheat_sheet` writes); the page name is derived from it by
  `site.page_name()`. There is exactly one slug.
- Regeneration is capped at the newest **500** entries (risk note below) — older pages stay
  on disk and keep working, they are just not rewritten or listed.
- `_esc()` HTML-escapes every interpolated value, including inside the `<script>` (the
  command is placed in the DOM as text, never as a JS string literal).

## Out of scope (deliberately not built)

- **Telegram bot, X posting, IG/FB Reels, newsletter** — board rows v3-F.2 / F.3 / F.4;
  each needs its own secret and its own spec.
- A custom domain (`tooldojo.in`), site search, tags/categories, RSS, comments, or any
  analytics/tracking script.
- Retrofitting pages for past videos — the catalog starts empty and fills from the next
  tool run forward.
- Enabling Pages (an owner click) and verifying a live 200 — verification here is local
  rendering plus screenshots.

## Acceptance criteria

- [ ] `py -3 -m pytest tests/ -q` passes with ≥8 new tests (137 → ≥145)
- [ ] `python -m factverse.site` on a 3-entry catalog writes `docs/index.html`,
      `docs/sitemap.xml` and 3 `docs/tools/*.html`; re-running produces byte-identical files
- [ ] A rendered page and the index are screenshotted at 1280px and 390px and read —
      command box, embed, PDF button, all three uses visible, no horizontal scroll
- [ ] `state_merge.merge_file("state/tools_index.json", ours, theirs)` with the same `page`
      on both sides returns exactly one entry, the later `date`/`video_url` winning
- [ ] `state/tools_index.json` is in **both** `state_merge.FILES` and the `publish.yml`
      stash loop; `docs/index.html`, `docs/sitemap.xml`, `docs/tools` are all `git add`ed
- [ ] The description's 📄 line resolves to `<base>/tools/<date>-<slug>.html` and that exact
      file name is what `site.write_page` produces (one test asserts both from one script dict)
- [ ] A simulated exception inside every `site.*` public function returns `None`, prints a
      `⚠️`, and `run()` still reaches `record_run`

## Risks

- **Decision 5 supersedes a v3-C contract line.** If Pages stays off the page 404s exactly
  as the PDF does today — no new failure mode. Cheapest check: enable Pages, `curl -I` both.
- `GITHUB_TOKEN` pushes may not trigger a Pages rebuild (`docs/DECISIONS.md:115`). Cheapest
  check: after the first tool run, `curl -I` the page; if stale, Pages needs the
  Actions-based deploy instead of branch-deploy — a small F.1b row, not a redesign.
- The catalog grows unbounded and every run rewrites every page (~4 KB each). 365 pages is
  ~1.5 MB and sub-second; the 500-entry regeneration cap keeps it that way.

## Review addendum (2026-08-31, two adversarial lenses over the diff)

Two agents reviewed `v3-phase-c..HEAD` — one on correctness and the unattended run, one on
the published surface and the CI state-save. Both reproduced every finding before reporting
it. **9 defects confirmed and fixed, each pinned by a regression test.** Two independent
findings were the same root cause (the pop placement) and are counted once.

| # | Defect | Root cause | Fix |
|---|---|---|---|
| 1 | A `cheat_sheet` planted in a LATER rewrite pass shipped on the live video — `.../tools/` with no file name when `safe_name` reduced it to `""` | `run()` popped it once, but `critique_pass` / `enforce_length` / `enforce_max_length` all run after that, and `_carry_over` only restores a key it finds in the source | Pop `receipts` and `cheat_sheet` inside `_validate_script`, which every pass runs *before* `_carry_over` restores the legitimate value. This also closes the identical, still-open hole for `receipts` |
| 2 | The PDF download button pointed where no PDF was written | `entry_for` sanitized `page` but stored `pdf` raw, so they diverged the moment `safe_name` changed anything | `"pdf": deliverable.safe_name(...)` |
| 3 | A long name lost its extension | `safe_name`'s `[:120]` truncated after the dot | Truncate the stem, keep the extension |
| 4 | The page offered a download on the day the PDF seam failed | `make_cheat_sheet` returns `None` fail-soft; `run()` had that answer and discarded it | `publish_page(..., pdf=cheat_sheet)`; no `pdf` field → no button |
| 5 | `javascript:` / `data:` URL clickable on our own Pages origin | `deliverable.url` is written by a model grounded in a third-party README and was never scheme-checked; `html.escape` cannot help — a scheme is not a metacharacter. `screencap.py` already refuses this exact field | `site.safe_link()`: `http://`/`https://` only |
| 6 | One unreadable page file froze `index.html` and `sitemap.xml` **forever**, invisibly | The `try` wrapped the whole loop, so a raise skipped the index/sitemap writes below it — while `publish_page` still returned a URL and the ledger still said `tool_page=True` | Per-entry `try/except: continue`; only a failure outside the loop returns `-1` |
| 7 | The canonical, index href and sitemap `<loc>` could advertise a URL the generator had refused to write | `rebuild()` sanitized only the file name; three other surfaces used the raw `page` — and the catalog is merged state read back off `origin/main` | `entry_name()` is the single answer for file, canonical, href and `<loc>` |
| 8 | `render_sitemap` raised on a non-dict row | The `isinstance` guard filtered `sorted()`'s *output*, so the non-dict reached `.get()` first | Filter before sorting; `max()` reads the filtered rows |
| 9 | `site_pages` could not be flipped from the environment | `fv.setting` returns an env var as a string and `bool("false")` is `True`; `receipts_check` uses `fv.flag` for exactly this reason | `fv.flag("site_pages", True)` |
| 10 | `_merge_index` raised `TypeError` on a scalar JSON body, in the one CI step with no `|| true` | `list(a or [])` | `isinstance(a, list)` guard |

### Verified correct (reproduced, no defect)

- **The CI state-save, including retries.** Replayed end-to-end against a real bare origin
  with iteration 1's push forced to fail and a competing push landing on `origin/main` in
  between: iteration 2's `checkout -B` deletes the tracked HTML and PDF, the PDF returns
  from `/tmp/tools_incoming` and the HTML is correctly *regenerated* from the merged
  catalog. Final `origin/main` had both artifacts, the merged catalog, a correct index row
  and sitemap, and the concurrent run's `used_topics.json` un-clobbered.
- **The copy-button JS.** `_JS` is a constant with zero interpolation; a command containing
  `</script><script>alert(document.domain)</script>`, quotes, backslashes and newlines
  renders escaped inside `<code>` with no breakout, and `navigator.clipboard` being
  undefined falls through to the select-text path.
- **Byte-identical regeneration** (acceptance #2), **relative links** in both directions,
  and **`publish_page` fail-soft** under an injected `RuntimeError` in all nine seams.

### Known and accepted

- `docs/` is now a sitemapped site and still contains `HANDOFF.md`, `STRATEGY.md`,
  `ENGINEERING_AUDIT.md` and `docs/spec/`. With `.nojekyll` those serve verbatim. **The
  repository is public, so this exposes nothing that github.com does not already serve** —
  but the sitemap lists only the index and the tool pages, so crawlers are not pointed at
  them. If that changes (a private repo, or a custom domain), add a `docs/robots.txt`.
- `safe_name` maps `"..."`, `"___"` and `"//"` to `""`. Every consumer now falls back to a
  name derived from the title, so an empty result costs nothing — but a future consumer
  must handle `""` rather than assume a name.
