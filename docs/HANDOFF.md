# HANDOFF — ToolDojo — Phase v3-R.2 Recovery cohort launch — 2026-11-12

## Done
- **v3-R.1 diagnosis (no code).** Fresh YouTube Studio data was read from the owner's logged-in profile without changing anything. Frames from 4 real videos were read off YouTube's public storyboards. A 2-round ChatGPT Pro review followed, and the owner locked table D1-D14 with "Go for all".
- **The 11-04 changes never reached a viewer.**
  - Tool videos: 0/7 published.
  - Native Shorts: 0/6 published.
  - Non-tool long-forms: median 2-7 views.
  - Shorts: about 13% stayed to watch, and the Shorts feed collapsed on 2026-10-25, before any change.
  - Returning viewers: 18 in 28 days.
  - Comments: 0 ever answered.
- **v3-R.2 is built on branch `v3-phase-r2`. With `recovery_cohort` on:**
  - Scheduled runs publish nothing before 2026-11-16 and on Tue/Thu/Sat/Sun. They exit 0 and write a `COHORT_REST_DAY` row.
  - On Mon/Wed/Fri the tool lane runs, and the six queue topics come first (gpu-unlock first).
  - A forced news/evergreen/roundup/debate run is refused with `COHORT_LANE_PAUSED`.
  - A day with no qualified candidate publishes nothing. The evergreen fallback is gone, and a gate block re-runs the tool lane.
  - A tool with no demo evidence takes the documentation route, labelled "From the docs — not tested by ToolDojo":
    - as a chip from 0:00 until scene 2 (7 s at most);
    - as a description line;
    - with testing claims caught as over-claims.
  - Openings: no logo bumper, no human cold open, no stat-card counter. The writer gets an answer-first "Before You Install" brief plus a cohort title/thumbnail contract.
  - Shorts: one native Short the day after the long-form at 18:45 UTC; no crop or storyboard Shorts. Style failures warn after one repair. Truth, render and readability failures still block.
  - Markdown asterisks are stripped from titles, thumb text, hooks and native labels.
- **Fixed a latent P.1 hole.** A non-pilot tool video would have been uploaded with no thumbnail and no Shorts.
- **Verification:**
  - Tests: 837/837, 50 of them new.
  - The docs-label chip frame was rendered through the real drawtext chain and read: the em dash renders, 39 px at 1080p.
  - The assembled writer prompt and the description were printed and read.
- **Commits:** 5 on `v3-phase-r2`. `git merge-tree` against origin/main is clean.

## Files changed
- `factverse/ai_pipeline.py`:
  - cohort helpers (`cohort_on`, `cohort_day`, `cohort_short_slot`, `cohort_queue_items`, `cohort_label_chip`);
  - `decide_format`, the start of `run()`, `_fallback_format`, the tool lane, `script_tool` (docs route, brief), `_output_contract(cohort=)`;
  - render: no cards and no sting; chip; extras fix; Shorts slot.
- `factverse/evidence.py`: the `docs` source, `COHORT_LABELS` (cohort-scoped D4 wording), `docs_record`/`docs_brief`/`screen_label`, docs over-claims and its description line.
- `factverse/native_short.py`: D8 style-versus-blocking classification, a lenient last attempt in the cohort, `last_warnings`, asterisk strip.
- `factverse/shorts.py`: hook asterisk strip.
- `config.json`, `config.example.json`: `recovery_cohort: true`, `cohort_start: 2026-11-16`, and `cohort_queue` (6 topics with parent video, family, URL and question).
- `tests/test_r2_cohort.py` (new, 50 tests).
- `tests/conftest.py`: `RECOVERY_COHORT=0` suite-wide.
- `docs/spec/ai-pulse-v3r.md` (new, the locked table and the frozen baseline).
- `docs/PHASES.md`: R.1-R.4 rows, Next 3 item 0.
- `docs/DECISIONS.md`: the 2026-11-12 entry.
- `CLAUDE.md`: 3 traps.

## Decisions made
- **D4 labels are cohort-scoped.** The P.1 labels stay outside the cohort, so Live Trials and the K.1 site keep their contract.
- **Before `cohort_start`, scheduled runs publish nothing**, so all six measured uploads fall inside the 14-day window.
- **A forced `tool` dispatch on a rest day is allowed.** It is the owner's own supervised call.
- **Queue items are matched as "served" by the PUBLISHED ledger `source_url`.** They are not matched by parent, because gpu-unlock and nv-uefi-unlocker share one parent.
- **OpenBot's identity comes from the original video's source line** (CopilotKit/OpenBot). nv-uefi-unlocker is `physicsdolphin/nv-uefi-unlocker`, which GitHub search shows as the repo searchers mean.

## Known broken / deliberately skipped
- **A1/A2 were not done.** The permission classifier refused the Studio browser automation, so the owner pastes these in Studio:
  - A1, reply to the RTX 50 comment on gpu-unlock: "No — the original gpu-unlock project currently lists RTX 50-series (Blackwell) as unsupported. Our video should have made that clear, and the title overstated what we could verify. We haven't tested it on hardware. Source: the project's Supported GPUs table and FAQ on GitHub."
  - A2, gpu-unlock title: "gpu-unlock for GeForce RTX 30/40 on Linux: What It Claims and How to Install".
  - A2, description: prepend "Correction (Nov 2026): gpu-unlock is Linux-only. Per the project, RTX 30 is stable, RTX 40 is experimental and RTX 50 (Blackwell) is not supported. A separate third-party Windows port exists; ToolDojo has not tested it or the tool. The speed figures in this video are the author's claims, not our measurements." Then delete the first paragraph's "secretly running at half speed / up to double" sentences.
- **Not run for real yet.** The first real cohort run is CI on Monday 2026-11-16, 12:23 UTC. A local render was not possible: there are no API keys locally.
- **The writer sees only the README's first 5,000 chars.** gpu-unlock's FAQ (Windows port, at char 5,860) is outside it, so the video can say "Linux only, RTX 50 unsupported" but not describe the Windows port. Consider this in R.3.
- **R.3 and R.4 are not built:**
  - R.3: D11 replies, the D6 title gate, D9 visuals, the D7 reserve, the cross-week Short family cooldown, the empty-diagram stock filter.
  - R.4: R0 is not measured. W0 = 13 min is frozen.
- **Leftovers on this machine:**
  - The Studio browser profile is still in the old scratchpad (`…/01a5917a-…/scratchpad/yt-studio-profile`), and a Chrome may still be open on port 9240.
  - The round folder `docs/debate/2026-11-12-tooldojo-deep-diagnosis/` is untracked in the main checkout on purpose, because it holds Studio data and `docs/` is public.
  - The main checkout is still on the stale `v3-gemini-fallback`.

## Next session starts here
- **Phase v3-R.3:** build the comment-reply module, the D6 title gate and the D9 visual rules, after confirming the PR is merged and reading Monday's first cohort run.
- **First command:** `/boot` from `E:\YOUTUBE\AI-PULSE-r2` (or from main, once `v3-phase-r2` is merged).
- **Watch out for:** if the PR is not merged before Monday 2026-11-16, the old daily lanes keep publishing filler. Check `git log origin/main` for `v3-phase-r2` first.
