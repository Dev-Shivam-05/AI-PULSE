# SPEC LOCK — AI Pulse v3-C.3: render-surface hardening

Status: built 2026-08-24 on `v3-phase-c`. 112/112 tests (was 93).

Why this exists: C.1 audited the tool lane and C.2 the three story lanes, so every lane's
*selection and scripting* path has now been searched. Everything **downstream of the
finished script** never had been — the surfaces that turn a validated script into the
thing a viewer actually sees: `shorts`, `captions`, `branding`, `thumbnail`,
`infographics`, `l2`, and `step5_build`.

10 defects, each reproduced by a failing test before its fix. Four of them are visible in
video already published: the caption overlap was measured across the 24 archived
`captions.ass` files in `state/assets/`, and the stat-card and hook-wrap defects are
deterministic consequences of code that has run every day.

Method: six parallel finders (one per surface plus one for the seams between them)
produced 27 candidates; every candidate was then handed to an independent skeptic told to
refute it. 15 were refuted and dropped — including three of this session's own early
hypotheses. The refutations are as much a part of the result as the fixes and are listed
under REFUTED below so the next session does not re-find them.

This file records the decisions; the pure bug fixes are in `docs/DECISIONS.md`.

## Locked decisions

| # | Decision | Value | Why |
|---|----------|-------|-----|
| 1 | A stat card is rendered to the slot it will actually occupy | `inject_cards` moves to after `scene_durations` in `run()` and takes `scene_durs`; `make_card_clip` is called with `dur = scene_dur / (len(clips) + 1)`, the share `step5_build` will really give it | The card was always rendered at a fixed 4.0s and then handed to a time split it knew nothing about. On the common path (a ~20s scene, 2 stock clips + the card) the card's share is ~6.7s, so `-stream_loop` **replays it**: the number counts up, snaps back to zero and counts again mid-scene. On a short scene the opposite happens — the clip is cut before the count-up finishes and the card's last frame shows a **number that is not the one the script says**. Measured: a 1.0s share of the 4.0s card displays `43%` for a true `54%`. `inject_cards` sat before the voice step for no reason; nothing between it and `step5_build` touches `scene_clips` |
| 2 | The card's final frame is the stat, verbatim | `_count_seq` returns `stat` unchanged once the ease reaches 1.0, instead of re-rendering it through a format spec | The count-up formatter is not an identity function at its own end point. `120.5 billion` renders as `120 billion`, `154.7%` as `155%`, `1500x` as `1,500x` — the frame held longest on screen contradicts the narration on a channel whose whole defence is that its numbers are checked. The stat string is ground truth; only the intermediate frames need synthesising |
| 3 | Two caption phrases are never on screen at once | `build_ass` clamps each event's end to the next event's start: `end = min(last_word_end + 0.10, next_start)` | The +0.10s hold was added with no clamp, and phrases are flushed on `len(cur) >= max_words` far more often than on a real pause — so the break usually lands mid-speech, where the next word starts exactly when the last one ended. Measured over the 24 archived, actually-burned `state/assets/*/captions.ass`: **5,626 of 6,515 consecutive boundaries overlap (86.4%)**, 5,624 of them by exactly 0.10s. libass stacks overlapping events, so at ~86% of phrase changes in every video shipped so far the outgoing phrase and the incoming one are on screen together |
| 4 | A Short's hook is fitted by measurement, not by a character count | `_wrap_hook(hook, font_for)` (new, pure) wraps to <=2 lines by **measured pixel width** against the 1080px frame, keeps the existing 64 -> 50 size step, and ellipsises what still will not fit | The old wrap used a 16-character budget and, on hitting 2 lines, `break`-ed with the pending word still in `cur` — which was then dropped. The in-spec 6-word hook `Anthropic benchmark methodology quietly changed again` was published as `Anthropic` / `benchmark`. 16 chars at 64px is ~590px of 1080, so the loss was to an invented budget, not to the frame. It also silently broke the fact-check contract: `gates.fact_check` verifies the FULL `hook_text`, so truncation can strip the qualifier off a checked claim (`beats every open source rival` -> `beats every open`) |
| 5 | `find_best_moments` output is coerced before it is indexed | `shorts.normalize_moments(raw, num_scenes)` (new, pure) returns a list of well-typed `{scene_num:int, hook_text:str}`, dropping what cannot be coerced and falling back to `[]` | `eng.find_best_moments` ends in `return d["moments"]` on raw Gemini JSON, and `make_shorts` indexes and slices it directly. `"scene_num": "4"` raises `TypeError` inside `min()`; `"hook_text": null` raises `AttributeError` on `.split()`; a dict-shaped `moments` raises on the slice. The raise unwinds past the finished video, the thumbnail and **every `record_run` call** — the render is discarded with no ledger row of any status. This is the same class as the `tags` comma-string of C.1 and gets the same treatment `normalize_shorts_meta` already gives the sibling call |
| 6 | Text is measured against the frame it is drawn on | `branding.fit_font(font_for, lines, start, budget_px, floor=1, step=6)` (new, pure) — the one shrink loop, extracted from `make_tool_thumb`, the only surface that already measured. `thumbnail._headline_font` keeps the 150/118/92 ladder as the STARTING size and then measures, at the same step 6 / floor 72; `compose`, `_text_block` and `make_tool_thumb` all go through it | Both composers picked a size from a fixed 3-step ladder keyed on **character count** and drew it at x=54/56 with no measurement. `OPENAI QUIETLY SHIPPED A NEW REASONING MODEL` measures 1,296px at the ladder's own floor of 92px and runs 72px off a 1,280px frame. `make_tool_thumb` — written later, for v3 — already does this correctly; the two older composers never got it |
| 7 | An empty `thumb_text` falls back to the title | `compose` / `compose_creator` / `make_tool_thumb` take `thumb_text or title`, the shape `run()` already uses for the tool thumb | `script["thumb_text"]` is optional (`_validate_script` does not require it) and `run()` passes `script.get("thumb_text", "")` to `thumbnail.make`. `_wrap_two("")` returns `[]`, both composers skip the headline block and still **save and return** the image, so the run publishes a graded photo with no text on it — and the confidence router's `packaging` term scores the missing `thumb_text` at 0.7 without ever learning the thumbnail came out blank |
| 8 | `splice` reports whether it spliced | `l2.splice` returns `None` on failure instead of the untouched input path, and `inject` marks a clip used / records it only on a real splice | `splice` returned the same `video` string on success and on failure, so `inject` could not tell them apart: a failed splice still consumed the clip **permanently** (every clip is usable at most once) and still wrote it into the run record as evidence of human insight. It also satisfies the `require_insight_block` O1 gate — the one gate whose entire job is to refuse to publish without a human take. Latent today only because the store is exhausted (see RISKS) |
| 9 | `state/l2_usage.json` and `state/stock_ledger.json` survive the CI state-save | both added to the stash list in `publish.yml` and to `state_merge.FILES` | The state-save stashes six files, then `git checkout -B main origin/main` throws away the run's branch. Both of these are tracked, written by the run, and in neither the stash list nor `state_merge.FILES` — so **every CI run silently reverts them**. For `l2_usage` that means the "used at most once" invariant is unenforceable in CI: the same human cold open would be injected into every video. For `stock_ledger` it means the 30-day stock-clip repeat guard never remembers anything |
| 10 | A scene keeps its full duration when one of its clips fails | `step5_build` re-times the survivors to `sdur / len(subs)` when a sub-clip fails to encode | The multi-clip branch discarded `safe_run`'s return value and appended only the subs that landed, then concatenated whatever survived. One failed clip left the scene short by its whole share — and because the audio is the master track and every later scene simply follows, **the rest of the video slid earlier against the narration**. Multi-clip scenes are the default (`dl_clips(count=2)`) |
| 11 | A stat is bounded on a word boundary and drawn inside the card | `infographics._cap_stat` (new, pure) caps at `_STAT_MAX = 24` without cutting mid-word, and `make_card_clip` fits the stat and the label with `branding.fit_font` | Found while rendering decision 2's fix. `plan_cards` capped with an inline `stat[:12]`, so `120.5 billion` reached the screen as `120.5 billio` and `2,400 percent` as `2,400 percen` — and even capped, that measures 1,304px on a 1,280px card and was clipped at both edges. Same family as decision 2: the card contradicting the number the narration speaks |

## OUT OF SCOPE
- The 15 refuted candidates, grouped in the REFUTED table below.
- `stat_card_share` (`ai_pipeline.py:1393`) counts a card scene's WHOLE duration, not the
  card's slice. It is written to the ledger and read by nothing, and decision 1 changes
  the slice it should measure; left for v3-D to define when it actually consumes the column.
- `_citation_filters` truncates to 48 chars AFTER escaping, so a `\:` cut in half would
  leave a dangling backslash and kill the whole caption burn. Not reachable: `source_chip`
  only ever yields a bare domain or `Sources in description`. Noted, not fixed.
- `burn_ass`'s 100,000-byte success floor is mis-sized for the l2 caller — measured, a 3s
  human clip encodes to 96,072 bytes and would be judged a failure. The store's clips are
  15-90s; the l2 duration floor (`d < 3`) and this floor disagree only in a 0.4s window.
- The bumpers are mono and `step5_build` emits stereo. Verified by running the real
  `add_intro_outro` on a stereo 44.1kHz content video: ffmpeg auto-negotiates, both
  branches succeed. No change.
- `MAX_SHORT`, `shorts_per_day`, the confidence weights, and every gate threshold.

## ACCEPTANCE CRITERIA (binary)
- [x] A stat card is rendered at the duration `step5_build` will give it, for both a
      long scene (no loop) and a short one (no truncated count-up)
- [x] `_count_seq(stat, 1.0) == stat` for every stat the regex can match
- [x] No two `build_ass` Dialogue events overlap, for word timings that abut exactly
- [x] Re-running the clamp over all 24 archived caption files leaves 0 overlaps
- [x] A 6-word hook wraps to 2 lines that both measure inside 1080px, with no word dropped
- [x] `normalize_moments` survives a string `scene_num`, a null `hook_text`, a bare-string
      entry and a dict-shaped `moments`, and `make_shorts` returns `[]` instead of raising
- [x] A 44-character headline is drawn inside the frame in `compose` and `_text_block`
- [x] An empty or whitespace `thumb_text` still produces a thumbnail with text on it
- [x] `l2.splice` returns `None` on failure and the clip stays unused and unrecorded
- [x] `state/l2_usage.json` and `state/stock_ledger.json` are in both the CI stash list
      and `state_merge.FILES`
- [x] A scene whose second clip fails to encode still fills its full duration
- [x] `_cap_stat` never cuts a stat mid-word, and the card's stat measures inside the frame
- [x] The full suite is green, and the artifacts were produced and inspected

## REFUTED — do not re-find these
Each was raised by a finder and then killed by an independent skeptic reading the code.

| Claim | Why it is not a defect |
|---|---|
| The re-hook tripwire is a no-op | Locked decision, spec v3-C.1 #5, with a test named for it |
| `shorts` / `branding` / `l2` `subprocess` timeouts raise unguarded | Textually true, but no traced path reaches the timeout, and `burn_ass` — a longer re-encode on the same file — is the one that is wrapped. Left alone deliberately |
| Two Shorts of one run can be near-identical | `shorts_per_day` is 2 and the two moments come from different prompt buckets |
| `_clean_word` strips currency symbols | Captions come from faster-whisper, not the script glyphs — `tts_provider` is kokoro, so `edge_words` is `None` |
| `add_intro_outro` fails without printing | The premise triggers are refuted: the bumpers are git-tracked, and running the real function on a stereo content video succeeds on both branches |
| A real `assets/music/intro.mp3` would break the sting | `assets/music/` is empty and untracked |
| The cold-open threshold excludes real hooks | Scene 1 is a 50-85 word block — ~18-35s, an order of magnitude above the 2.5s threshold |
| YuNet download failure is retried per frame | Reachable, but the cost is bounded and the Haar fallback carries it |
| L2 clips are burned before the abort gates | The store is exhausted; and see decision 8, which fixes the real half of this |
| `stat_card_share` is inflated | True, but it has no consumer — see OUT OF SCOPE |

## RISKS
- **Decision 1 moves a call in `run()`.** `inject_cards` now runs after the voice step, so
  a card render failure surfaces later; it already fails soft per card and the run
  continues on stock. The move is safe because nothing between the old and new positions
  reads or writes `scene_clips` — but it is the one structural change in this phase.
- **Decisions 8 and 9 are latent today.** `state/l2_usage.json` lists all 8 clips in the
  store as used, so `l2.inject` is a no-op on every current run. They fire the day the
  owner records the next weekly batch — which `l2.py` and `docs/PROCESS.md` actively ask
  for, and which decision 9 is a precondition for. This is the same "harden the path
  before it runs" posture as C.1's tool lane.
- **Decision 3 changes the timing of every caption line in every future video.** The
  shortening is at most 0.10s and only where an overlap existed; it cannot lengthen a line.
- **Decision 4 can still ellipsise.** A hook long enough not to fit 1080px twice at 50px is
  cut — but at a measured boundary with a visible `…`, not silently mid-phrase.
- **Decision 10 costs one extra encode pass per clip on a scene that had a failure.** Rare
  by construction; the alternative is the whole rest of the video sliding against narration.
