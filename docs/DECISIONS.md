
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

## 2026-08-24 — v3-C.3 render-surface hardening
*Everything downstream of the finished script. C.1 covered the tool lane and C.2 the story lanes,
so every lane's selection and scripting path had been searched — the surfaces that turn a
validated script into what a viewer sees never had. 10 defects, each reproduced by a failing test
first. Spec: `docs/spec/ai-pulse-v3c3.md`.*

- **A stat card is rendered to the slot it will actually occupy.** `inject_cards` moved to after
  `scene_durations` and takes `scene_durs`; the card is rendered at `scene_dur/(clips+1)`, the
  share `step5_build` really gives it. At a fixed 4.0s it either looped (replaying the count-up
  mid-scene) or was cut before the count finished — measured, a 1.0s share of the 4.0s card
  displays `43%` for a true `54%`.
- `inject_code_card` must stay AFTER `inject_cards`: `_lead_with` REPLACES a leading stat card so
  a third clip cannot squeeze the command below readable length.
- **The card's final frame is the stat, verbatim.** `_count_seq` re-rendered the number through a
  format spec at its own end point: `120.5 billion` → `120 billion`, `154.7%` → `155%`. It also
  used to be cut mid-word by `stat[:12]` (`120.5 billio`) and to overflow the card
  (`2,400 percent` = 1,304px on 1,280px).
- **`branding.fit_font` is the one shrink loop.** Extracted from `make_tool_thumb`, the only
  surface that already measured its text; now used by the card, `compose`, `_text_block` and
  `make_tool_thumb` itself. A character-count ladder is not a width.
- **Two caption phrases are never on screen at once.** `build_ass` clamps each event's end to the
  next event's start. Measured over the 24 archived `state/assets/*/captions.ass`: 5,626 of 6,515
  boundaries overlapped (86.4%); re-timed, 0 of 6,511. Confirmed on screen — libass stacks
  overlapping events, so the incoming phrase was shoved up over the outgoing one for 0.1s at
  ~86% of phrase changes in every video shipped.
- **A Short's hook is fitted by measurement, not a character count**, using the font drawtext
  actually loads (`short.ttf`), not `br._font`. The old wrap dropped the pending word on reaching
  two lines: `Anthropic benchmark methodology quietly changed again` shipped as
  `Anthropic` / `benchmark`. `gates.fact_check` verifies the FULL hook_text, so that cut also
  broke the fact-check contract.
- **`find_best_moments` output is coerced** (`shorts.normalize_moments`). It ends in
  `return d["moments"]` on raw Gemini JSON; a string `scene_num` or null `hook_text` raised
  past the finished video, the thumbnail and every `record_run` call.
- **An empty `thumb_text` falls back to the title.** Both composers skipped the headline and still
  saved the image — publishing a graded photo with no text. A WHITESPACE value is truthy, so the
  `or` fallbacks already in the callers never fired for it.
- **`l2.splice` returns `None` on failure**, so `inject` consumes and records a clip only when it
  is really in the video. A failed splice used to burn a one-use clip AND satisfy the
  `require_insight_block` O1 gate with a video containing no human take.
- **`state/l2_usage.json` and `state/stock_ledger.json` survive the CI state-save.** Both tracked,
  both written by the run, both absent from the stash list and `state_merge.FILES` — so
  `git checkout -B main origin/main` reverted them every run. They are dicts and the fallback
  merger is a list union, so they needed their own semantics (`_merge_used`, `_merge_seen`)
  before being added, or the state-save step would have raised and lost everything.
- **A scene keeps its full duration when a clip fails to encode.** Measured with real ffmpeg:
  one corrupt clip in a 3-clip 30s scene produced a 50.00s video against 60.00s of narration —
  the tail cut off, and `qa_video` passes it (50 > 60 × 0.75). Now 60.00s, drift 0.00s.

## v3-C.4 — tool suitability screen precision (2026-08-24)
- **The suitability list is screened by SURFACE.** A term does not mean the same thing in a
  90-char repo name as in 5,000 chars of prose. Measured over 28 flagship AI tools, `bypass`
  refused unsloth (its own Windows install line is `-executionpolicy bypass`), ComfyUI
  (`ctrl+b` bypasses a node) and yt-dlp, and `crack` refused transformers ("a sassy,
  wise-cracking robot" in an example prompt). `UNSUITABLE_NAME_ONLY` matches the title only.
- **A tool that DETECTS the thing is not the tool that DOES it.** 6 of 11 defensive tools were
  refused by their own subject — including the official C2PA SDK and CLI, which the term `c2pa`
  was added to protect, plus two deepfake detectors and two NSFW safety classifiers.
  `UNSUITABLE_SUBJECT` exempts a document that reads as defensive within `DETECTOR_WINDOW`,
  unless an evasion claim ("undetectable", "anti-detection") sits in the same window.
- **`DETECTOR_WINDOW = 120`** — measured, the nearest defensive word was 5–69 chars away in the
  six blocked defensive tools and 1,049 in the live stripper. Covers the observed max with
  ~1.7x margin, ~9x below the control.
- **Repo punctuation normalises to spaces before matching.** The live
  `ShadowAqueduct/watermark-remover` PASSED the title screen because the list held
  `watermark remov` (space) and `watermarks-remover` (plural); it was caught only because its
  README quotes the other repo's name in ASCII art. One line closes the whole class.
- **A GitHub tool video is grounded in the raw README, not the rendered page.** Measured mean
  **1,637 chars of GitHub chrome** ("You signed in with another tab or window", the file
  listing) preceded every README, so ~1/3 of the 5,000-char window was UI — text the LLM was
  told to "ground every claim in" and that `gates.fact_check` verified against. Same 28 tools:
  1/28 blocked on the page window vs 4/28 on the full README, i.e. the verdict depended on
  where a word fell in a document.
- **Grounding and screening are different jobs.** The rendered page carries the repo's topic
  tags, the strongest intent signal GitHub exposes and the one thing the raw README lacks —
  `facefusion` is declared only by its topics (`deep-fake deepfake face-swap faceswap`), so
  grounding on the README alone would have let it through. The writer gets the clean README;
  `tool_unsuitable` reads both.
- **`FaceForensics` stays refused and that is correct.** It was on the defensive list until its
  README was read: it ships "the two stage FaceShifter face swapping method ... able to generate
  high fidelity identity preserving face swap results". Recorded because the first instinct was
  to force it green.

## v3-E — receipts + packaging precision, part 1 (2026-08-24)
- **The writer only states numbers it was HANDED.** `_verified_facts` fetches stars/license/
  last-update from the official APIs per candidate (GH_TOKEN when present, fail-soft {}),
  goes into the prompt as a VERIFIED FACTS block, rides `_CARRY`, feeds the stat cards and
  the PDF receipts line ("179,325 stars · MIT · checked 2026-08-24" — rendered and read).
- **The copy-paste contract is enforced, not requested.** A deliverable not verbatim in the
  source is replaced by the source's own first fenced block, else the candidate is rejected.
  This required `fetch_text` to stop collapsing newlines — the review proved the repair was
  dead code against real grounding, and the test had fabricated the only shape it could pass on.
- **A number promised on the packaging must exist in the video.** `gates.packaging_payoff`,
  token-exact, suffix-aware, mutating deterministically; the tool-lane title template never
  leaks to other lanes; a mangled thumb blanks so the title fallback fires.
- **The honest-limitation scene cites the tool's own bug tracker** (top-commented open
  issues, PRs filtered) instead of inventing humility from a vendor README.
- **Brand surfaces follow config.** Wordmark, tagline, banner and PDF header all render from
  `channel_name`/`tagline`; `assets/.brand` stamps what the bumpers were rendered for and
  mismatches force a regen — the ToolDojo rename applied itself and was frame-inspected
  (TOOL gradient + DOJO white, "AI YOU CAN USE").
- **The paid voice is a flag, not a dependency.** ElevenLabs runs first only when flag+key+
  voice id all exist, skips dialogue scripts, drops punctuation-only words, and any failure
  lands in kokoro→edge unchanged. publish.yml hands the secret through; unset = inert.
- **Verification is mutation-tested where it matters.** The PDF receipts test spies the
  canvas draw seam because the review deleted the render block and the suite stayed green.

## 2026-08-24 — v3-E.2 receipts.py
- **The check downloads, it never executes — absolute.** pip pinned to wheels
  (`--only-binary :all:`, an sdist download runs setup.py), `--no-cache-dir` (a cached
  wheel is a 0.1s "download" — a lie), shallow clone, wall-clocked+capped fetch. Refusal
  is the default for anything shell-shaped (`|`, `&&`, `;`, `$(`, backticks, docker, npx,
  `<(`, `pip install .`/`-e`/`-r`): a refused segment costs the beat, never the day, and
  never stamps a 10KB installer stub as "the download".
- **The beat's numbers are our own measurement, not source claims** — inserted AFTER
  fact_check on purpose, and BEFORE packaging_payoff so a thumb number spoken only in the
  beat counts as kept.
- **Only `add_beat` may set `script["receipts"]`.** `_validate_script` mutates the LLM's
  dict in place, so any top-level key the model invents survives into the script; run()
  pops `receipts` after the format re-bind and the post-upload ledger read is
  isinstance-guarded (a planted non-dict raised in the double-publish zone).
- **requests' `timeout` is never a deadline.** It bounds the gap between socket reads; a
  slow-drip URL held the run until the CI job kill on both cron firings. Every streamed
  fetch carries its own `time.monotonic` wall clock and byte cap.
- **Anything burned into an artifact splits paths on BOTH separators.** `pathlib .name`
  is platform-native — the Saved-line test was green on the Windows dev box and red on
  ubuntu CI, and git's `Cloning into '<abs path>'` line re-shipped the same leak.
- **Glyph width probes cannot detect tofu** (tofu has width). A glyph that must render
  becomes a word (`OK:`), not a probed fallback — second occurrence of this bug class
  after the thumbnail star.
- **Animated clip frame counts CEIL to their slot share** — `int()` flooring left the
  clip 1/30s short, step5_build looped it, and animation frame 0 flashed at the cut.


## 2026-08-31 — v3-F.1 the site (spec: docs/spec/ai-pulse-v3f1.md)
- **`docs/.nojekyll` is committed, so Pages serves the directory verbatim.** There is no
  Jekyll, no plugin allowlist and no build step — markdown would be served as raw text.
  Anything published under `docs/` must therefore be written as HTML. (This closes the
  jekyll-readme-index / jekyll-relative-links question: those plugins are irrelevant here.)
- **The catalog is the source of truth, the HTML is a build artifact.**
  `state/tools_index.json` is state (stashed + union-merged); `docs/*.html` is regenerated
  from it after `state_merge` on every CI run. The PDFs still stash to /tmp because an LLM
  wrote them once and they cannot be reproduced — HTML can, so regenerating beats copying.
- **A derived artifact needs no stash, but its SOURCE needs both halves of the trap.**
  `state/tools_index.json` is in `state_merge.FILES` *and* the publish.yml stash list, with
  its own merge semantics (union keyed by `page`) — the generic list union dedups on exact
  equality, so a retry with a new `video_url` would have printed the same tool twice.
- **The description's 📄 line links the PAGE, not the PDF** (supersedes v3-C decision 8).
  A PDF opened from mobile YouTube is a bad experience; the page carries the copy-button
  command, the embed and the PDF as a download, and it is the URL F.2/F.3 will share. The
  pinned comment carries the same promise, so it links the same place. One `<date>-<slug>`
  stem serves both files, so the name is still decided before the upload.
- **One extraction, two consumers** (`deliverable.sheet_for`): the PDF and the page render
  the same sheet. A second `extract_sheet` call would pay for it twice and could disagree
  with itself. A *raising* extraction now falls back instead of losing the sheet — the
  module's own docstring already promised that, and only the `return None` path honoured it.
- **`cheat_sheet` was the `_CARRY` trap in a new place, and it was already live.**
  `_validate_script` mutates the LLM dict in place, so a model-planted `cheat_sheet` key
  survived: it was stamped into the PUBLISHED description and joined onto `TOOLS_DIR`,
  where `../../../x.pdf` wrote outside `docs/` while the writer reported success. run()
  now pops it beside the `receipts` pop (run() computes the name itself), and
  `deliverable.safe_name()` basenames on BOTH separators and filters the charset.
  Any future artifact name derived from model output goes through `safe_name`.
- The first cut of `safe_name` split on `/` only — green on Windows, red on the ubuntu
  runner. That is the **third** time this exact trap has been hit in this repo.

### v3-F.1 review pass — what the 9 defects taught (2026-08-31)

- **Popping a plantable `_CARRY` key ONCE in `run()` is not a fix.** `critique_pass`,
  `enforce_length` and `enforce_max_length` each validate again afterwards, and
  `_carry_over` restores only a key it finds in the source — so a value planted in a
  *later* rewrite answer survives. The pop belongs inside `_validate_script`, which every
  pass runs before `_carry_over` hands the legitimate value back. This is why v3-E.2's
  `receipts` fix was incomplete too: both keys are now popped in one place.
- **`html.escape` is not URL validation.** A scheme is not a metacharacter, so an escaped
  `javascript:` href is still script execution — on our own Pages origin, from a URL a
  model wrote while grounded in a third-party README. `screencap.py` had guarded this exact
  field with `startswith("http")` since v3-B; the site did not inherit it. When a field is
  already treated as untrusted somewhere in the repo, find that guard before writing a new
  consumer.
- **A whole-loop `try` around artifact writes is a silent freeze.** One unreadable page
  file aborted `rebuild`'s loop, skipping the index and sitemap writes below it — the site
  froze at its last good state on every future run, while `publish_page` still returned a
  URL and the ledger still recorded `tool_page=True`. Per-item `try/except: continue`.
- **Sanitising the write path is not enough if other surfaces publish the raw value.**
  `rebuild` cleaned the file name; the canonical, the index href and the sitemap `<loc>`
  used the raw one, so they could advertise a URL the generator had refused to create. One
  function (`entry_name`) now answers for all four.
- **A guard placed after `sorted()` never runs.** `render_sitemap`'s `isinstance` filter
  ran on the sorted output, so the non-dict it was written for reached `.get()` first.
  Filter, then sort.
- **A boolean config key must use `fv.flag`, never `fv.setting`.** `setting` returns an env
  var as a string and `bool("false")` is `True`, so `site_pages` could not be turned off
  from Actions. Every new kill-switch goes through `flag`.
- **Truncating a file name must not eat its extension.** `safe_name`'s `[:120]` cut after
  the dot, leaving the PDF writer and the page linker looking for different files.
- **When a fail-soft seam returns `None`, the consumer must be told.** `make_cheat_sheet`
  returning `None` still produced a page advertising the download; `run()` had the answer
  and discarded it. Pass the result, do not re-derive the assumption.
