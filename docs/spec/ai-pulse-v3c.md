# SPEC LOCK — AI Pulse v3-C: income + packaging

*Locked 2026-08-22. Owner approved with `go`. Builds on docs/spec/ai-pulse-v3.md (decision 9:
"one free 1-page PDF per tool video on GitHub Pages, ₹0, + affiliate-ready description slot").
A session with no memory of the conversation must be able to build the identical thing from this file.*

## Locked decisions

| # | Ambiguity | Locked value | Why this default |
|---|-----------|--------------|------------------|
| 1 | PDF library | `reportlab>=4.0` (in requirements-ci.txt and test.yml) | Standard, pure-Python, selectable text. Pillow's PDF is image-only |
| 2 | PDF format | A4 portrait, exactly 1 page. Top bar #DC2626 with "AI Pulse · free cheat sheet"; title (Inter Black 26pt); **What it is** (≤40 words); **Get it running** (deliverable in JetBrains Mono 11pt on a #0D1117 box); **Make these 3 things** (3 bullets); **Skip it if** (1 line); footer: source URL · YouTube link · @aipulse · date | Reuses the two bundled fonts and the tool-thumbnail red; body = DejaVu Sans (CI) → Helvetica fallback |
| 3 | Where PDF content comes from | One `llm.generate_json` call over the script → `{what, steps[2-5], uses[3], skip_if}`. LLM failure → fallback PDF with title + deliverable + source + video link. **Never no PDF** | Scenes aren't labeled; extraction is cheap; fallback keeps the transaction |
| 4 | File name | `docs/tools/<YYYY-MM-DD>-<slug>.pdf`, slug = title lowercased, non-alnum→`-`, ≤40 chars | Deterministic before upload, so the description link is known in advance |
| 5 | Public URL | GitHub Pages from `main` `/docs`: `<deliverable_base_url>/tools/<file>`; config key `deliverable_base_url` = `https://dev-shivam-05.github.io/AI-PULSE`. **Owner one-time click:** Settings → Pages → Deploy from branch → `main` / `docs` | Spec decision 9 (₹0). Until enabled the same file opens at the GitHub blob URL |
| 6 | When generated / how published | After YouTube upload (carries the video link), before state-save. `publish.yml` state-save stages `docs/tools` with the state files. Non-publish runs write it too (footer without video link) | The PDF needs the video URL; state-save already commits run outputs to main |
| 7 | Description layout (tool) | Paragraph 1 of the LLM description (hook + keyword) → `🔧 Try it yourself:` + command + source → `📄 Free 1-page cheat sheet: <url>` → promo block → remaining paragraphs → chapters → watch-next. Paragraph 1 = text before the first blank line; no blank line → first line; single line → end | "Top block" was the Phase A intent but it appended at the end; links above the fold |
| 8 | Affiliate slot | Config `promo_block` (string, multi-line OK), default `""`. Inserted verbatim after the cheat-sheet line (tool) or after paragraph 1 (other formats). Empty → nothing inserted | Income ladder on every video; owner fills the text when an affiliate exists |
| 9 | Docs rewrite | README (v3 as default lane, pipeline with screencap, config keys, commands); CONTENT_PLAYBOOK (tool-video anatomy, description template, PDF, news bar 8/10); STATUS dated 2026-08-22 with v3 A+B+C truth + open owner actions | STATUS still said "17 tests, 2026-07-20" |
| 10 | Tests | Real reportlab render into tmp_path (1 page, >5 KB), fallback path, slug, placement order, promo empty/non-empty, idempotency | Same conventions as the v3-B test section |
| 11 | Description cap | LLM description clamped to 4000 chars before the blocks are placed | YouTube's 5000-char limit; the blocks add ~250 chars |

## OUT OF SCOPE
- Enabling Pages by API (no `gh`, needs admin token) — owner click
- PDFs for news / evergreen / roundup (no deliverable there)
- Paid products, email capture, Gumroad, Instagram
- Any second PDF template

## ACCEPTANCE CRITERIA (binary)
- [ ] A tool run writes exactly one `docs/tools/<date>-<slug>.pdf`; page count == 1; size > 5 KB
- [ ] With `generate_json` → None, the PDF still renders and contains the deliverable text
- [ ] Tool description contains, in order: paragraph 1, `🔧 Try it yourself`, `📄 Free 1-page cheat sheet: …/tools/<file>.pdf`, promo block (when set), remaining text; placing twice yields one block
- [ ] `promo_block = ""` → the string never appears in any format's description
- [ ] `publish.yml` state-save stages `docs/tools/*.pdf`
- [ ] README / PLAYBOOK / STATUS no longer describe Pexels as the tool-video visual; STATUS header date = 2026-08-22
- [ ] All tests green locally and on PR CI

## RISKS
- Pages link 404s until the owner enables it — check: `curl` the URL after the first merge
- reportlab TTF registration on Linux — covered by rendering the real PDF in a CI test
- YouTube's 5000-char description cap — decision 11
