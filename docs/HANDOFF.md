# HANDOFF — AI Pulse — Phase v3-C.2 (story-lane hardening) — 2026-08-23

*v3-D is still blocked: `docs/tools/` is empty and 0 of the 66 ledger rows are `format="tool"`,
so there is no v3 data to learn from. C.1 hardened the never-run tool lane; this session gave
the same treatment to the three lanes that actually publish every day — news, evergreen,
roundup — which C.1 explicitly left unaudited. 12 defects, **every one reproduced by a failing
test before it was fixed**, then verified against the live signal engine (real ranking, real
page fetches; the LLM is stubbed because no key exists locally).
Contract: `docs/spec/ai-pulse-v3c2.md`. Branch `v3-phase-c` is pushed (`e624fa4`), still stacked
on `v3-phase-b` — merge PR #23 first.*

## Done
- **A repo can no longer become the news story.** `rank()` returns ONE list and v3-A put the
  GitHub / Hugging Face / Product Hunt trending feeds into it, so the viral judge and the weekly
  countdown were scoring tool signals as news. Verified live today: ranked #1 and #2 are both
  `kind="tool"` and #1 is `guillaumemeyer/watermarks-remover: Strip multi-vendor AI provenance
  marks` — the exact candidate C.1 built `gates.tool_unsuitable` to refuse, a gate that guards
  the tool lane and nothing else. The news lane now tries 3 real stories where it would have
  tried 2 repos and a story.
- **A sourced video is no longer written from an unsourced page.** The floor is
  `gates.FACTCHECK_MIN_CHARS` (200) — the fact-checker's own skip threshold, named rather than
  invented. Below it `verbatim_overlap` scored 0.0, `fact_check` skipped, `verify_synthesis` had
  nothing to compare, and the confidence `facts` component read **1.0**, the same score a fully
  verified script gets. Evergreen is ungrounded by design and is untouched.
- **The roundup's gates read the text the prompt read.** They used to RE-fetch `picked[:3]`: a
  transient failure on the second pass handed the copy gate an empty string, and stories 4 and 5
  were never checked in either pass. Live: 6,004 chars pooled across all five stories.
- **One outlet no longer owns the countdown.** The old rule skipped a repeat only once three
  distinct sources were banked, so it could never fire on a dominant feed — against today's live
  signals it produced five TechCrunch stories out of five, on the one format whose entire policy
  defence is curation. Now three outlets, still five stories.
- **The roundup stops misattributing itself.** `source_url` is story 1's URL, so the caption chip
  and every generated stat card stamped one outlet across all five stories and the
  `"Sources in description"` branch was unreachable dead code. `source_chip()` fixes both, and
  the description now lists all five sources — printed and read: 5/5 credited, byte-identical
  across the two `place_description_blocks` calls `run()` makes.
- **The advice gate reads the whole script.** Its LLM confirmation was armed from
  `script_text[:2000]` of a ~5,500-char narration, so anything prescriptive in the last two
  thirds was never checked. The regex pass always saw everything; only the arming was windowed.
- **A re-worded evergreen topic no longer republishes the same video.** Exact lowercase equality
  was the only dedup.
- **The ledger row cannot raise** (`default=str`, broad `except`) — it is the last statement of
  the publish window C.1 closed. Rows now carry `grounding_chars` for v3-D.
- **The veto window is never claimed on a refusal.** `requests.post` does not raise on 4xx, so
  `_notify_review` printed "veto window active" after an HTTP 404 opened no issue at all.
- A dead roundup falls back to evergreen — Sunday is the only roundup slot there is.
- **93/93 tests** (was 75), plus a live 6-section end-to-end verification of both lanes.

## Files changed
- `factverse/ai_pipeline.py` — `news_candidates()` (new) applied in `viral_pick`, the news loop
  and the roundup pool; the 200-char floor in `script_news` / `script_roundup`; roundup fetches
  once and gates on every story; outlet-diversity pass; `source_chip()` (new, pure) replacing the
  inline domain logic in `run()`; the `🔗 Sources:` block in `place_description_blocks`;
  `EVERGREEN_DUP_OVERLAP` + near-duplicate topic check; roundup→evergreen fallback;
  `record_run` unraisable + `grounding_chars`; `_notify_review` status check.
- `factverse/gates.py` — `FACTCHECK_MIN_CHARS = 200` named and reused; `advice_framing` arms on
  the whole narration.
- `factverse/intelligence/signal_engine.py` — `_is_used` takes an optional `threshold` (headline
  default 0.5 unchanged).
- `tests/test_pipeline_logic.py` — 18 new tests, incl. the live top-6 of 2026-08-23 as a fixture.
- `docs/spec/ai-pulse-v3c2.md` (NEW), `docs/DECISIONS.md`, `docs/PHASES.md`, `CLAUDE.md`.

## Decisions made
- **The story lanes read story signals only.** Filtering by `kind` is not a policy judgment about
  what may be reported — it is the lanes reading the feeds they were given. The trending feeds
  were added in v3-A for the tool lane and leaked.
- **Reuse the fact-checker's own floor instead of inventing one.** "If `fact_check` cannot run,
  the lane does not write" is a rule, not a magic number, and it needs no owner approval.
- **`EVERGREEN_DUP_OVERLAP = 0.7`.** Chosen, not asked: the engine's 0.5 headline default blocks
  this lane's own title template. Measured — `How Transformers Actually Work` scores 0.67 against
  `How Diffusion Models Actually Work` (different videos, blocked at 0.5); the true re-word
  scores 1.0 and is still caught at 0.7.
- **A roundup points at its description, never at one domain.** Curation and attribution are the
  format's whole survival argument.
- Full list with reasons: `docs/spec/ai-pulse-v3c2.md` and `docs/DECISIONS.md`.

## Known broken / deliberately skipped
- **A forced `format=news` day where every story is paywalled now publishes nothing.** That is
  the grounding floor working, but it is a real behaviour change. Measured 2026-08-23: 11 of 11
  live news candidates grounded at 2,464–4,000 chars, so it should be rare. `grounding_chars` in
  the ledger is how you will know if it fires more than expected.
- **Expect more `ADVICE_BLOCKED` rows.** The wider arming window means more LLM confirmations and
  therefore some false positives. Unforced, a false positive costs one rewrite pass and falls
  back to evergreen; it does not cost the day.
- **`EVERGREEN_DUP_OVERLAP` is tuned on eight sample titles, not a corpus.** If two genuinely
  duplicate evergreen topics ship, lower it before adding machinery.
- **Decision 1 trusts `kind`.** An item the sources layer leaves without a `kind` defaults to a
  story and stays in the news pool.
- The roundup description carries story 1 twice (`_validate_script`'s manufactured `Source:` line
  plus entry 1 of the sources block). Cosmetic; suppressing it means touching `_validate_script`,
  which every lane and the whole tool-lane test set depends on.
- **The render surfaces are still unaudited** — `shorts`, `captions`, `branding`, `thumbnail`,
  `l2`. C.1 + C.2 together cover every lane's *selection and scripting* path; everything
  downstream of the finished script has never been searched.
- Unchanged from C.1: **GitHub Pages is still off** (every 📄 link 404s), `UNSUITABLE_TOOL` is
  still an unreviewed keyword list, the first `format=tool` dispatch has still never run,
  `promo_block` is still empty, and the v2 backlog (duplicate NVIDIA/HF video, OAuth re-consent)
  is untouched.

## Next session starts here
- **Phase v3-D is still gated on data, not code** — it needs ~2 weeks of v3 analytics, and the
  first tool video has not published yet. Until it does, the next session is either the render
  -surface audit (v3-C.3, needs nothing from you) or a review of the first live tool run.
- First command: `/boot`
- Watch out for: **judging v3 before the data exists.** The verdict metric is average view
  duration ≥ 2:00 across the first 10 tool videos (v2 baseline 0:38). If AVD is still under 1:00
  after 10 videos the topic choice is wrong, not the packaging — reopen the spec instead of
  adding machinery. Second trap, now in `CLAUDE.md`: `rank()` is ONE mixed list — anything
  treating it as stories must go through `news_candidates()` first.
