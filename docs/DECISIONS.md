
## 2026-08-23 — story-lane hardening (Phase C.2)
The same treatment C.1 gave the tool lane, applied to news / evergreen / roundup — the lanes
that publish every day and had never been searched for defects of their own. 12 defects, each
reproduced before its fix, verified against the live signal engine. Contract:
`docs/spec/ai-pulse-v3c2.md`.
- **The story lanes now read story signals only** (`news_candidates`). v3-A put the GitHub / HF /
  Product Hunt trending feeds into the same `rank()` list, so the viral judge and the weekly
  countdown were scoring repos as news. Live 2026-08-23: ranked #1 and #2 were both `kind="tool"`
  and #1 was the AI-provenance stripper — which `gates.tool_unsuitable` refuses to *teach* and
  guards nowhere else. The news lane could still have written it up.
- **If the fact-checker cannot run, the lane does not write.** `gates.FACTCHECK_MIN_CHARS` (200,
  already inside `fact_check`) is now the news/roundup grounding floor. Below it every accuracy
  gate passed for free and the confidence `facts` component read 1.0 — the same score a fully
  verified script gets. Evergreen is ungrounded by design and is untouched.
- **The roundup's gates read the text the prompt read.** They used to re-fetch `picked[:3]`: a
  transient failure handed `verbatim_overlap` an empty string (a free pass on the copy gate) and
  stories 4-5 were never checked in either pass. Live pooled grounding is now 6,004 chars.
- **One outlet may not own the countdown.** The old dedup only skipped a repeat once three
  distinct sources were banked, so it never fired on a dominant feed: live today it produced five
  TechCrunch stories out of five, on the one format whose defence is curation. Now three outlets.
- **The roundup stops misattributing itself.** `source_chip()` — the caption chip and every stat
  card used to carry story 1's domain across all five stories, and the "Sources in description"
  branch was unreachable. The description now actually lists all five sources.
- **The advice gate reads the whole script.** Its LLM confirmation was armed from the first 2,000
  chars of a ~5,500-char narration.
- **Evergreen dedup is near-duplicate, at 0.7** (`EVERGREEN_DUP_OVERLAP`). Exact string equality
  was the only guard; the engine's 0.5 headline default over-blocks this lane's own
  "how does X actually work" template (measured: 0.67 for two different subjects, 1.0 for the
  true re-word).
- A dead roundup falls back to evergreen — Sunday is the only roundup slot there is.
- `record_run` can no longer raise (`default=str`, broad except): it is the last statement of the
  publish window C.1 closed. Rows now carry `grounding_chars` for v3-D.
- `_notify_review` no longer announces a veto window on an HTTP 404 — `requests.post` does not
  raise on 4xx, so the log claimed a review issue that did not exist.

## 2026-08-23 — tool-lane pre-flight hardening (Phase C.1)
Six-surface adversarial audit of the never-executed `format=tool` path, run because the next
step is a live supervised dispatch. 34 candidate defects → 8 confirmed after refutation, plus
2 found by hand. Every one reproduced before its fix. Full contract: `docs/spec/ai-pulse-v3c1.md`.
- **A tool video is an endorsement, so the tool lane now REJECTS, not just penalises.**
  `gates.tool_unsuitable` screens title and README for circumvention / safety-defeat / piracy.
  Verified live: the day's #1 tool candidate was `watermarks-remover: Strip multi-vendor AI
  provenance marks`, with two `Qwen3.8-27B-Uncensored` forks behind it. Without this the first
  tool video the channel ever published would have been a guide to defeating AI provenance.
- **Grounding floor 1200 chars** for the tool lane (owner-approved). Product Hunt's ~640 chars
  of nav chrome cleared both `fetch_text`'s 400 floor and `gates.fact_check`'s 200 skip, so
  claims were fact-checked against "Overview Reviews 1 Team More" and blocked the day. This
  corrects the Phase-C handoff's claim that PH pages "ground thinly, so script_tool often
  rejects them" — it accepted them.
- **Hugging Face grounds on the raw model card only**, never the page. The page's readable text
  is inlined `chat_template` JSON, so the old empty-page repair branch could never fire.
- **Nothing may raise between `yt_upload` and `record_run`.** A raise there left a video live
  with no `PUBLISHED` row, so `already_published_today()` said no and the retry cron published a
  second video into the same slot. The re-hook tripwire now fires before the upload instead.
- **`fmt` is re-bound from the returned script**, so a `tool → evergreen` fallback stops being
  logged as a tool video — that ledger is what v3-D is supposed to learn from.
- The cheat sheet renders the whole command; the wrap used to be sliced to two rows, shipping a
  command cut mid-flag that still looked copy-pasteable.
- State-save survives a dispatch from a feature branch by committing the run's tracked writes
  onto the throwaway branch — **not** by forcing the checkout, which would discard them.

## 2026-08-22 — v3 utility pivot (Phase A)
- **Pivot locked:** "about AI" news essays → "AI you can use today" tool videos. Driver: 90-day
  data (0:38 AVD, 5 subs); reference model = HyperAutomation Labs transcript (video as a
  transaction: viewer leaves with repo link + command + shortlist).
- News viral bar 7→8/10; word floors are sanity-only (600-620); **cap 900** is the new law.
- Blocked gate on an auto run falls back to forced evergreen — a blocked story never costs the day.
- Captions display script spelling force-aligned onto whisper timings (1:1 blocks only).
- Tool lane gated behind `tool_format:false` until the Phase-B screen-recording engine exists.
- Income path pre-YPP = description deliverables (PDF in Phase C), NOT ads.

## 2026-08-22 — v3 original-visuals engine (Phase B)
- **Tool videos are illustrated by the tool itself.** `factverse/screencap.py` records the tool's
  real page with headless Chromium (1920×1080, dark) and cuts it into sequential per-scene clips;
  Pexels is used for tool videos ONLY when capture fails (soft fallback), not as a ≤30% mix.
- Recording length is sized from the script's word count (60–300 s) because the script exists
  before visuals are fetched; scenes keep `step5_build`'s loop/cut fitting, so no exact cuts.
- Blank page-load head is trimmed by MEASURED `goto` latency (floor 2.5 s), not a constant.
- Code card = the deliverable rendered as a terminal card (Pygments bash, JetBrains Mono 22px);
  it leads the final scene and the first post-hook install/run scene, and REPLACES a stat card
  there rather than stacking (a scene's time is shared equally between its clips).
- Tool thumbnail = page screenshot + 2–4 word overlay (Inter Black, white on #DC2626, red
  baseline). Person-cutout retired for tool videos; fonts are bundled (OFL) in assets/fonts.
- Every LLM rewrite pass carries the same `_CARRY` key set — the advice-gate rewrite had carried
  only 4 keys and silently dropped `deliverable`. The deliverable description block is idempotent
  and re-appended before render for the same reason.
- CI: playwright pinned exactly (the browser cache key hashes requirements-ci.txt); the chromium
  install step is `continue-on-error` — a missing browser degrades to stock, never a lost day.
- `tool_format: true` at merge. The supervised first tool run happens in CI (no API keys exist
  locally): `workflow_dispatch` with `format=tool`, before the day's 12:23 UTC cron.
- HF model pages are JS-thin: `script_tool` grounds from `/raw/main/README.md` as a fallback.

## 2026-08-22 — v3 income + packaging (Phase C)
- **Every tool video ships a free 1-page cheat sheet** (`factverse/deliverable.py`, reportlab,
  A4, exactly one page). Sections come from one LLM extraction; on failure the sheet still ships
  with the deliverable. There is never "no PDF" — the transaction is the product.
- The PDF **name is decided before upload** (so the description can link it) and the **file is
  written after upload** (so it carries the video URL). The name rides on the script as
  `cheat_sheet` and is in `_CARRY`.
- **Links go above the fold**: `place_description_blocks` inserts 🔧 deliverable + 📄 cheat sheet
  + `promo_block` directly under the hook paragraph. v3-A appended the deliverable at the END of
  the description, which is below the fold and effectively invisible.
- Paragraph 1 is computed on the LLM's own text: `_validate_script` manufactures a
  `\n\nSource: …` tail, and splitting on that put the links below the whole body.
- **The description block is verified, not trusted.** An LLM rewrite pass can echo the block back
  mangled; matching on the 🔧 marker alone could ship a public link to a file we never wrote, so
  the exact expected block is compared and a stale fragment is cut and re-inserted.
- The cheat-sheet link is only added when a PDF will actually be written (`_has_cheat_sheet`
  mirrors `make_cheat_sheet`'s condition exactly: `format == "tool"` and a deliverable).
- **Affiliate slot** = config `promo_block`, empty by default, inserted verbatim. Income ladder
  is wired before there is anything to sell, so adding an affiliate is a config edit, not a code
  change. Still no ads, no email capture, no paid product (spec decision 9 stands).
- Hosting = GitHub Pages from `main` `/docs` (₹0), `deliverable_base_url` in config. Pages needs
  one owner click; `GITHUB_TOKEN` pushes may not trigger the Pages build, so the link is verified
  with `curl -I` after the first tool run rather than assumed.
- LLM list fields are coerced (`_as_list`): a bare string was being iterated into characters.
  Any future LLM-shaped list field must go through it.
