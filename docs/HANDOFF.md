# HANDOFF — AI Pulse — Phase v3-C.3 (render-surface hardening) — 2026-08-24

*C.1 audited the tool lane and C.2 the three story lanes, so every lane's **selection and
scripting** path had been searched. This session did the surfaces that turn a validated script
into what a viewer actually sees — `shorts`, `captions`, `branding`, `thumbnail`,
`infographics`, `l2`, `step5_build` — which had never been searched at all.
10 defects, **every one reproduced by a failing test before it was fixed**, and every fix
verified against a rendered artifact, not just a green test. 27 candidates were found and 15
were refuted and dropped, including three of this session's own early hypotheses; the
refutations are recorded in the spec so they are not re-found.
Contract: `docs/spec/ai-pulse-v3c3.md`. Branch `v3-phase-c` is pushed (`cc9383f`), still stacked
on `v3-phase-b` — merge PR #23 first.*

## Done
- **Two caption phrases no longer share the screen.** `build_ass` held each finished phrase for
  0.10s with no clamp against the next one's start, and phrases flush on `max_words` far more
  often than on a real pause — so the break lands mid-speech, where whisper reports word N+1
  starting exactly when word N ends. Measured across the 24 archived, actually-burned
  `state/assets/*/captions.ass`: **5,626 of 6,515 boundaries overlapped (86.4%)**, 5,624 by
  exactly 0.10s. Re-timed through the clamp: **0 of 6,511**. Confirmed on screen — burning the
  2026-07-22 file at t=2.15s shows `hacked asterisk an entire` shoved up above
  `Open AI's AI Asterisk`, a two-row jump at ~86% of phrase changes in every video shipped.
- **A stat card is rendered to the slot it will actually get.** `step5_build` splits a scene's
  time equally between its clips, so a card stacked onto a 2-clip scene gets `sdur/3` — but it
  was always rendered at a fixed 4.0s. On the common path it **looped**, replaying the count-up
  mid-scene; on a short scene it was cut before the count finished and the last frame showed a
  number the script never said (measured: `43%` for a true `54%`). `inject_cards` moved to after
  `scene_durations` and renders each card at `scene_dur/(clips+1)`.
- **The card stops rewriting its own number** three separate ways: `_count_seq` re-rendered the
  stat through a format spec at its own end point (`120.5 billion` → `120 billion`, `154.7%` →
  `155%`); `plan_cards` cut it mid-word with `stat[:12]` (`120.5 billio`); and the proportional
  size overflowed the card (`2,400 percent` = 1,304px on 1,280px, clipped both edges).
- **A Short's hook keeps its words.** The wrap used a 16-character budget and, on reaching two
  lines, broke with the pending word still in `cur` — which was dropped. The in-spec 6-word hook
  `Anthropic benchmark methodology quietly changed again` was burned as `Anthropic` /
  `benchmark`: 19 of 53 characters. Rendered both ways through real drawtext to confirm. It also
  broke the fact-check contract — `gates.fact_check` verifies the FULL hook_text.
- **A malformed LLM `moments` answer no longer kills the day.** `find_best_moments` ends in
  `return d["moments"]` on raw Gemini JSON; a string `scene_num` raised inside `min()`, a null
  `hook_text` on `.split()`. The raise unwound past the finished video, the thumbnail and
  **every `record_run` call** — the render died with no ledger row of any status.
- **A thumbnail is never published blank or clipped.** Both older composers sized text off a
  character-count ladder and drew it unmeasured (`OPENAI QUIETLY SHIPPED A NEW REASONING MODEL`
  runs 72px off the frame), and an empty `thumb_text` made them skip the headline and still save
  the image. `branding.fit_font` is now the one shrink loop, shared with `make_tool_thumb`.
- **A failed L2 splice no longer burns a clip or fakes the record.** `splice` returned its input
  on success AND failure, so `inject` consumed a one-use clip permanently and recorded it as
  human insight — which also satisfies the `require_insight_block` O1 gate with a video
  containing no human take.
- **`state/l2_usage.json` and `state/stock_ledger.json` survive CI.** Both tracked, both written
  by the run, both in neither the stash list nor `state_merge.FILES` — so
  `git checkout -B main origin/main` reverted them on **every run**. Both are dicts and the
  fallback merger is a list union, so adding them alone would have raised inside the state-save
  step under `bash -e` and lost *every* state file; they got their own semantics first.
- **A scene keeps its duration when a clip fails to encode.** Measured with real ffmpeg — one
  corrupt clip in a 3-clip 30s scene: **before 50.00s video vs 60.00s narration** (the tail cut
  off, and `qa_video` passes it), **after 60.00s, drift 0.00s**.
- **112/112 tests** (was 93), plus a full render-seam run: cards → `step5_build` → caption burn →
  branding, frames inspected at three points across the card's real slot (12% → 47% → 54%, held).

## Files changed
- `factverse/infographics.py` — `CARD_DUR`, `card_slot_dur()` (new, pure), `_cap_stat()` (new,
  pure), `_count_seq` returns the stat verbatim at t>=1, `make_card_clip` fits stat + label,
  `inject_cards` takes `scene_durs`.
- `factverse/captions.py` — `build_ass` clamps each event's end to the next event's start.
- `factverse/shorts.py` — `_overlay_font()`, `_wrap_hook()` and `normalize_moments()` (all new,
  pure); `make_shorts` uses them and returns `[]` instead of raising.
- `factverse/thumbnail.py` — `X_EDGE`, `_headline()`, `_headline_font()` (new, pure); `compose`,
  `compose_creator` and `make` take `title=`; `make_tool_thumb` shares the one shrink loop.
- `factverse/branding.py` — `fit_font()` (new, pure), the shared measured-shrink helper.
- `factverse/l2.py` — `splice` returns `None` on failure; `inject` acts only on a real splice.
- `factverse/state_merge.py` — `_merge_used`, `_merge_seen`, and the two files in `FILES`.
- `.github/workflows/publish.yml` — the same two files added to the pre-checkout stash list.
- `scripts/factverse_engine.py` — `sub_durations()` (new, pure); `step5_build` re-times a scene's
  surviving clips.
- `factverse/ai_pipeline.py` — `inject_cards` / `inject_code_card` moved below the timings;
  `thumbnail.make(..., title=)`.
- `tests/test_pipeline_logic.py` — 19 new tests. `docs/spec/ai-pulse-v3c3.md` (NEW),
  `docs/DECISIONS.md`, `docs/PHASES.md`, `CLAUDE.md`.

## Decisions made
- **Measure, never count characters.** Four surfaces independently sized burned text by character
  count and all four shipped clipped or truncated text. `branding.fit_font` is the single loop,
  and it must be given the font that will really be drawn — Shorts render with `short.ttf`
  (Arial Bold), not `br._font` (Segoe UI Bold), and measuring with the wrong face still overflows.
- **A generated clip must be rendered to the share `step5_build` will give it.** The alternative —
  making the animation loop-safe — hides the problem instead of fixing it, and the durations were
  already available a few lines later in `run()`.
- **Fail soft means return `None`.** Returning something indistinguishable from success is worse
  than raising: `l2.splice` looked like it worked and the caller acted on that.
- **No new numbers.** Every fix reuses a value already in the file (0.10s, 64/50, 150/118/92,
  step 6 / floor 72, the 0.58 text band) or derives from the frame. `_STAT_MAX = 24` replaces an
  inline 12 and is a sentence guard, not a layout number — width is now measured.
- Full list with reasons: `docs/spec/ai-pulse-v3c3.md` and `docs/DECISIONS.md`.

## Known broken / deliberately skipped
- **Decisions 8 and 9 (L2) are latent, not live.** `state/l2_usage.json` lists all 8 clips in the
  store as used, so `l2.inject` is a no-op on every current run. They fire the day the owner
  records the next weekly batch — which `l2.py` and the docs actively ask for, and which the CI
  fix is a precondition for. This is the same "harden it before it runs" posture as C.1's tool lane.
- **Decision 3 changes the timing of every caption line in every future video.** The shortening is
  at most 0.10s and only where an overlap existed; it can never lengthen a line.
- **Decision 4 can still ellipsise.** A hook too long for two measured lines is cut — but at a
  measured boundary with a visible `…`, not silently mid-phrase.
- **`stat_card_share` (`ai_pipeline.py`) counts a card scene's WHOLE duration, not the card's
  slice.** It is written to the ledger and read by nothing, and decision 1 changes the slice it
  should measure. Left for v3-D to define when it actually consumes the column.
- **`_citation_filters` truncates to 48 chars AFTER escaping**, so a `\:` cut in half would leave
  a dangling backslash and kill the whole caption burn. Not reachable — `source_chip` only ever
  yields a bare domain or `Sources in description`. Noted, not fixed.
- **`burn_ass`'s 100,000-byte success floor is mis-sized for the l2 caller** — measured, a 3s human
  clip encodes to 96,072 bytes and would be judged a failure. The store's clips are 15-90s and
  l2's own floor is 3s, so the two thresholds disagree only in a ~0.4s window.
- **The bumpers are mono and `step5_build` emits stereo.** Investigated and dismissed: running the
  real `add_intro_outro` on a stereo 44.1kHz content video succeeds on both branches — ffmpeg
  auto-negotiates. No change made.
- 15 candidates were refuted outright and are tabled in the spec under REFUTED so the next
  session does not spend the day re-finding them.
- Unchanged from C.1/C.2: **GitHub Pages is still off** (every 📄 link 404s), `UNSUITABLE_TOOL` is
  still an unreviewed keyword list, the first `format=tool` dispatch has still never run,
  `promo_block` is still empty, and the v2 backlog is untouched.

## Next session starts here
- **Phase v3-D is still gated on data, not code.** It needs ~2 weeks of v3 analytics and the first
  tool video has not published yet. With C.1 + C.2 + C.3 the whole path from signal to uploaded
  file has now been searched — there is no auditing left to queue. The next session is the review
  of the first live tool run, or v3-D once the data exists.
- First command: `/boot`
- Watch out for: **judging v3 before the data exists.** The verdict metric is average view
  duration ≥ 2:00 across the first 10 tool videos (v2 baseline 0:38). If AVD is still under 1:00
  after 10 videos the topic choice is wrong, not the packaging — reopen the spec instead of adding
  machinery. Second trap, now in `CLAUDE.md`: a tracked state file the run writes must be in BOTH
  `publish.yml`'s stash list AND `state_merge.FILES`, with merge semantics for its shape added
  first — the fallback merger raises on a dict, which under `bash -e` loses every state file.
