# HANDOFF — AI Pulse — Phase v3-C.4 (tool suitability screen precision) — 2026-08-24

*The phase board carried an owner action since C.1: "Read `gates.UNSUITABLE_TOOL` and edit it.
It will both miss things and over-block." This session did not read it — it **ran** it, over the
live tool feeds, over 28 flagship AI tools and over 11 defensive tools, and read the verdicts.
It was refusing the tools the utility lane exists to teach, and the day's real provenance
stripper walked past its title screen. 5 defects, every one reproduced by a failing test before
it was fixed, then re-verified against the live network rather than a stub.
Contract: `docs/spec/ai-pulse-v3c4.md`. Branch `v3-phase-c` is pushed, still stacked on
`v3-phase-b` — merge PR #23 first.*

## Done
- **The gate earns its place — that was checked first.** Of 47 live tool candidates,
  `ShadowAqueduct/watermark-remover: Purge multi-vendor AI watermarks` was ranking on the day,
  along with five `Qwen3.8-27B-Uncensored` forks. Nothing here loosens the policy.
- **…but the live stripper PASSED the title screen.** The list held `watermark remov` (space)
  and `watermarks-remover` (plural); the repo is `watermark-remover`. It reached `script_tool`
  and was refused only because its README happens to quote the *other* repo's name in ASCII
  art. `_norm_terms` now maps `-`, `_` and `/` to spaces before matching, which closes the
  whole class in one line.
- **Prose words stopped refusing real tools.** Measured over 28 flagship AI tools: `bypass`
  refused **unsloth** — whose own Windows install line is
  `set-executionpolicy -scope process -executionpolicy bypass`, the exact text a cheat sheet
  copies — plus **ComfyUI** (`ctrl+b` = "bypass selected nodes") and **yt-dlp**; `crack`
  refused **transformers** ("a sassy, wise-cracking robot" in an example prompt).
  `UNSUITABLE_NAME_ONLY` now screens the title only, where `GPTBypass` is still caught.
- **A tool that DETECTS the thing is no longer treated as the tool that DOES it.** 6 of 11
  defensive tools were refused by their own subject: the **official C2PA SDK and CLI** (the
  term `c2pa` was added to block provenance STRIPPERS and it blocked the STANDARD), two
  deepfake **detectors**, two **NSFW safety classifiers**. `UNSUITABLE_SUBJECT` exempts a
  document that reads as defensive within `DETECTOR_WINDOW = 120`, unless an evasion claim
  ("undetectable", "anti-detection") sits in the same window. The window is measured: 5–69
  chars in the six defensive tools, **1,049** in the stripper.
- **A GitHub tool video is grounded in the raw README.** `fetch_text` on a github.com page
  returns a mean **1,637 chars of chrome** first ("You signed in with another tab or window",
  the file listing) — so only ~3,360 chars of README were ever read, **and that chrome was
  handed to the LLM as "SOURCE EXCERPT (ground every claim in this)" and to `gates.fact_check`**.
  Same 28 tools, two windows: 1/28 blocked on the page vs 4/28 on the full README — the verdict
  depended on where a word fell in a document. HF got this in C.1 #2; GitHub never did.
- **Grounding and screening were split.** The rendered page carries the repo's topic tags, the
  one intent signal the raw README lacks — `facefusion` is declared only by its topics
  (`deep-fake deepfake face-swap faceswap`), so the fix above would have let it through.
  The writer now gets the clean README; `tool_unsuitable` reads both. Verified: facefusion
  still refused.
- **Names added inside the locked scope**, all measured as *passing* beforehand: `abliterated`,
  `obliterated` (`OBLITERATUS/Qwen3.8-27B-OBLITERATED` ranked live and passed the title screen —
  it was caught only because its card also said "uncensored"), `nudify`, `deepnude`,
  `unwatermark`, `remove any watermark`, `humanizer`, `voice clon`, `clone voice`.
- **117/117 tests** (was 112), plus `verify_c4.py` re-run against the live network: 8 abuse
  cases refused, 5 former false positives passing, 7 defensive tools passing, 2 controls
  (the stripper's README, facefusion) still refused. All checks passed.

## Files changed
- `factverse/gates.py` — `UNSUITABLE_TOOL` rewritten; `UNSUITABLE_NAME_ONLY`,
  `UNSUITABLE_SUBJECT`, `DETECTOR_WINDOW`, `_DEFENSIVE`, `_EVASION`, `_norm_terms()`,
  `_reads_as_defensive()` (all new, pure); `tool_unsuitable` screens three lists.
- `factverse/ai_pipeline.py` — `_gh_readme_url()` (new, pure); `script_tool` grounds on the raw
  README, keeps the page fallback, and screens `grounding + page`.
- `tests/test_pipeline_logic.py` — 5 new tests; `test_non_hf_tool_grounds_on_the_page_only`
  rewritten as `test_github_tool_grounds_on_the_raw_readme_but_screens_the_page_too` (the C.1
  behaviour it asserted is what decision 4 supersedes).
- `docs/spec/ai-pulse-v3c4.md` (NEW), `docs/DECISIONS.md`, `docs/PHASES.md`, `CLAUDE.md`.

## Decisions made
- **Measure a policy list before trusting it.** Every defect here was found by running the gate
  over live feeds and real READMEs. Reading the tuple would have found none of them — the
  failures are all about what real documents actually say.
- **A term list needs a surface.** The same word is an identity in a 90-char repo name and noise
  in 5,000 chars of prose. Three lists, three surfaces.
- **Narrowing what the writer reads must not narrow what the gate reads.** Hence the
  grounding/screening split; it costs one extra HTTP GET per GitHub candidate (≤3/day).
- **No widening.** `captcha solver`, `anti-detect browser`, `residential proxy` and
  `account generator` were measured as passing and deliberately not added — C.1 fenced that as
  a policy call, and it still is.
- Full list with reasons: `docs/spec/ai-pulse-v3c4.md` and `docs/DECISIONS.md`.

## Known broken / deliberately skipped
- **`voice clon` now matches READMEs, so legitimate open TTS is refused.** F5-TTS, RVC and XTTS
  pass today only because the old term (`voice clone`) could not match "voice cloning". This is
  the existing policy applied without its spelling hole, not a new policy — but it is the row
  most likely to want loosening, and it is one tuple edit. **This is the one editorial call left
  for the owner.**
- **`ondyari/FaceForensics` is still refused, and that is correct.** It was on this session's
  defensive list until its README was read: it ships "the two stage FaceShifter face swapping
  method … able to generate high fidelity identity preserving face swap results". Recorded
  because the first instinct was to force it green.
- **"Clone any voice from 3s" still passes** — `clone voice` is not a substring of "clone any
  voice". Left rather than adding a regex for one phrasing.
- **`piracy` would refuse an *anti*-piracy tool.** Not measured against a real candidate.
- **A repo whose README is `.rst` or lowercase falls back to the page**, exactly as today. Unlike
  the hub (C.1 #2) the GitHub fallback is safe: its text is chrome-padded, not fiction.
- Unchanged from C.1/C.2/C.3: **GitHub Pages is still off** (every 📄 link 404s), the first
  `format=tool` dispatch has still never run, `promo_block` is still empty, all 8 L2 clips are
  still marked used, and the v2 backlog is untouched.

## Next session starts here
- **Phase v3-D is still gated on data, not code.** It needs ~2 weeks of v3 analytics and the
  first tool video has not published yet. C.1 (tool lane), C.2 (story lanes), C.3 (render
  surfaces) and now C.4 (the one list nobody had measured) have searched the whole path from
  signal to uploaded file. There is no auditing left to queue.
- First command: `/boot`
- Watch out for: **judging v3 before the data exists.** The verdict metric is average view
  duration ≥ 2:00 across the first 10 tool videos (v2 baseline 0:38). If AVD is still under
  1:00 after 10 videos the topic choice is wrong, not the packaging — reopen the spec instead of
  adding machinery. Second trap, now in `CLAUDE.md`: a keyword screen means different things on
  a name and in a document, and narrowing what the writer reads must not narrow what the gate
  reads.
