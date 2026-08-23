# SPEC LOCK — AI Pulse v3-C.2: story-lane hardening (news / evergreen / roundup)

Status: built 2026-08-23 on `v3-phase-c`. 93/93 tests.

Why this exists: C.1 audited the tool lane only. Its shared fixes (`_validate_script`,
the publish window) already protected the other three lanes, but those lanes had never
been searched for defects of their own — and v3-A had changed the ground under them.
`rank()` now returns ONE list containing the GitHub / Hugging Face / Product Hunt
trending feeds that were added to feed the tool lane, and the news judge and the weekly
roundup were still reading all of it.

12 defects, each reproduced by a failing test before its fix. Verified against the live
signal engine on 2026-08-23 (real ranking, real page fetches, LLM stubbed — no key
exists locally). This file records the decisions; the pure bug fixes are in
`docs/DECISIONS.md`.

## Locked decisions

| # | Decision | Value | Why |
|---|----------|-------|-----|
| 1 | Story lanes read story signals | `ai_pipeline.news_candidates(ranked)` drops `kind == "tool"`. Applied in `viral_pick`, in `build_script`'s news loop, and as the roundup's preferred pool | v3-A added the trending feeds to the same ranked list. Live 2026-08-23: ranked #1 and #2 were both `kind="tool"` and #1 was `watermarks-remover: Strip multi-vendor AI provenance marks`. `gates.tool_unsuitable` refuses to *teach* that and guards nothing else, so the news lane could still have written it up as the day's story and the Sunday roundup could have counted it among "the stories that actually mattered" |
| 2 | Story-lane grounding floor | `gates.FACTCHECK_MIN_CHARS = 200` (named, not new — it is the skip threshold already inside `fact_check`). `script_news` returns `None` below it and `build_script` tries the next story; `script_roundup` returns `None` when the pooled excerpts fall below it | A news video CLAIMS a source. With grounding under that floor `verbatim_overlap` scores 0.0, `fact_check` skips, `verify_synthesis` has nothing to compare — and the confidence `facts` component then reads **1.0**, identical to a fully verified script. Reusing the fact-checker's own floor states the rule without inventing a number: if that gate cannot run, the lane does not write. Evergreen is ungrounded **by design** and is untouched |
| 3 | Roundup grounding is the text the prompt read | `script_roundup` keeps the excerpts it fetched and joins them into `script["grounding"]` | It used to RE-fetch `picked[:3]`. A transient failure on the second pass handed `verbatim_overlap` an empty string — a free pass on the copy gate for a script written from real source text — and stories 4 and 5 were never checked at all, in either pass. Live: pooled grounding is now 6,004 chars across all five stories |
| 4 | One outlet may not own the countdown | `script_roundup` takes one story per `source` first, then tops up with repeats to five | The old rule skipped a repeat only once three distinct sources were banked, so it could never fire on a feed where one outlet dominates. Against the live signals of 2026-08-23 it produced five TechCrunch stories out of five — on the one format whose entire policy defence is curation. After the fix: three outlets, still five stories |
| 5 | On-screen attribution | `ai_pipeline.source_chip(script) -> (domain, chip)`. A roundup returns `("", "Sources in description")`; every other format returns its own domain | `_validate_script` sets `source_url` to story 1's URL, so `src_domain` was always truthy for a roundup: the caption chip **and every generated stat card** stamped one outlet across all five stories, and the `"Sources in description"` branch was unreachable dead code |
| 6 | The roundup description lists every source | `place_description_blocks` appends a `🔗 Sources:` block from `roundup_items` (idempotent; `roundup_items` is already in `_CARRY`, so it survives the rewrite passes) | The video burns "Sources in description" on screen for its whole runtime while `_validate_script` credited exactly one URL. Four outlets went uncredited on a channel whose survival argument is curation and attribution |
| 7 | Advice gate window | `gates.advice_framing` arms its LLM confirmation from the **whole** narration, not `script_text[:2000]` | A 900-word script is ~5,500 chars, so a finance / health / legal turn in the last two thirds never armed the check. The screen is a keyword scan over a 20-item tuple — the full text costs nothing. The regex pass always saw the whole text; only the arming was windowed |
| 8 | Evergreen near-duplicate overlap | `ai_pipeline.EVERGREEN_DUP_OVERLAP = 0.7`, passed to `signal_engine._is_used(..., threshold=)` (new optional arg; the headline default stays 0.5) | Exact lowercase equality was the only dedup, and the model re-words a topic every time it is asked. The engine's 0.5 default over-blocks this lane's own title template — the prompt literally asks for "how does X actually work", and measured, `How Transformers Actually Work` scores 0.67 against `How Diffusion Models Actually Work` (different videos). 0.7 still catches the true re-word, which scores 1.0 |
| 9 | A dead roundup must not cost the Sunday | `build_script("roundup")` falls back to evergreen, the shape the tool lane already uses | Sunday is the only roundup slot there is. The fallback labels itself `format="evergreen"`, so run()'s C.1 re-bind keeps the ledger honest |
| 10 | The ledger records how grounded a script was | `record_run(..., grounding_chars=…)` on the terminal row | Decision 2 makes grounding a publish-or-not input; v3-D cannot correlate AVD against it if it is never written down |
| 11 | The ledger row cannot raise | `record_run` serialises with `default=str` and catches `Exception`, not `OSError` | It is the LAST statement of the publish window C.1 closed (spec v3-C.1 #5). A `TypeError` there leaves the video live with no `PUBLISHED` row, `already_published_today()` answers False, and the 14:53 retry cron publishes a second video into the same slot |
| 12 | The veto window is never claimed on a refusal | `_notify_review` checks `status_code in (200, 201)` before printing "veto window active", and prints the HTTP status otherwise | `requests.post` does not raise on 401/403/404. The log announced a review window that no issue backed — worse than none, because the operator stops looking for the issue |

## OUT OF SCOPE
- The `titles` array is dropped by `enforce_length` / `enforce_max_length` (they pass a
  narrower key set than `critique_pass`). Nothing downstream reads it — left alone.
- The roundup description now carries story 1 twice: `_validate_script`'s manufactured
  `Source: …` line plus entry 1 of the `🔗 Sources:` block. Cosmetic; suppressing it means
  touching `_validate_script`, which every lane and the whole tool-lane test set depends on.
- `_MAX_DESC` is a character clamp against a YouTube limit measured in bytes.
- No change to `MIN_WORDS` / `MAX_WORDS` / `VIRAL_THRESHOLD` / the confidence weights.
- The shared render surfaces (`shorts`, `captions`, `branding`, `thumbnail`, `l2`) — the
  lanes were the target, not the renderer.

## ACCEPTANCE CRITERIA (binary)
- [x] No `kind="tool"` candidate reaches `script_news`, `viral_pick`'s listing, or the
      roundup countdown while story signals exist
- [x] A news story whose page yields <200 chars is skipped and the next story is tried,
      without an LLM call
- [x] A roundup whose pages all fail produces no script, and falls back to evergreen
- [x] The roundup's gated grounding contains text from every story it counts down
- [x] `source_chip` returns `("", "Sources in description")` for a roundup and the real
      domain for news
- [x] The roundup description credits every story, and is byte-identical across the two
      `place_description_blocks` calls `run()` makes
- [x] A sensitive term past char 2000 arms the advice gate's LLM confirmation
- [x] `_is_used` at 0.7 separates the re-word from the different subject; at 0.5 it does not
- [x] `_notify_review` on HTTP 404 prints the status and the review body, never
      "veto window active"
- [x] `record_run` writes its row when handed a value `json` cannot serialise
- [x] Live verification against today's real signals: news lane tries 3 stories (was 2 repos
      + 1 story), roundup spans 3 outlets (was 1), pooled grounding 6,004 chars (was a
      re-fetch of 3 of 5)
- [x] 93/93 tests green (was 75)

## RISKS
- **Decision 2 can cost a day that v2 would have published.** A day where every story
  candidate is paywalled or bot-walled now yields no news script. `decide_format` only
  picks news for a viral score ≥ 8, and the unforced gate fallbacks still route to
  evergreen, so the exposed case is a forced `format=news` dispatch. Measured 2026-08-23:
  11 of 11 live news candidates grounded at 2,464–4,000 chars, so this should be rare —
  it is the silent day it catches that matters. `grounding_chars` in the ledger is how
  you will know if it fires more than expected.
- **Decision 7 widens the advice gate's arming, so expect more LLM confirmations and
  some false positives.** A false positive costs one rewrite pass and, unforced, falls
  back to evergreen. Watch for `ADVICE_BLOCKED` rows appearing where they never did.
- **Decision 8's 0.7 is tuned on eight sample titles**, not a corpus. If two genuinely
  duplicate evergreen topics ship, lower it before adding machinery.
- **Decision 1 assumes `kind` is set correctly by the sources layer.** An item with a
  missing `kind` defaults to a story and stays in the news pool.
- The tool lane is unchanged by this phase, and the C.1 risks still stand — the first
  supervised `format=tool` dispatch has still never run.
