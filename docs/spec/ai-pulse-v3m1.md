# Spec — v3-M.1: memory record, north-star ladder, second-slot shadow queue

Status: **locked**. The owner approved the 2026-11-04 review's 18-row table with *"go for
all … do not stop until everything is done"* (`docs/spec/ai-pulse-v3-growth.md`). This phase
covers rows **9** (memory), **10** (north star), **16** (second-slot shadow queue), the
**data-correction part of row 18** that touches `learn`, and the open point on **search
longevity**. The values below are copied from the review (round 3 §5-§6, round 4 Rank 2 and
Rank 5). Any value nobody wrote down is listed under *Delegated decisions* as "default chosen:
X, because Y".

## Why this phase exists

1. **Memory.** nv-uefi-unlocker's search variants brought 186 views, and no follow-up was ever
   made. The pipeline did not record which question a video answered, which questions it left
   open, or which search terms found it.
2. **North star.** The target is 100× on-demand long-form watch time per 28 days, from 12.11 h
   to 1,211 h. Neither the scoreboard nor the collector measured it.
3. **Second slot.** A second daily long-form is earned only through a measured backlog. Nothing
   measured whether a second qualified candidate exists, or how much job-time headroom is left.
4. **Search longevity.** No one has measured search capture by video age.

## Locked decisions

| # | Decision | Value |
|---|----------|-------|
| 1 | Per-video record (`memory.build_record`) | Groups from round 3 §5: **identity** (video id, publication UTC, format, lane, topic family, canonical tool, experiment, pair, arm, slot, template version); **viewer need** (question answered, questions left open, parent and follow-up ids); **evidence** (`script["evidence"]` if given, else ledger `evidence_source`/`evidence_status`, else empty); **delivery** (`duration_s`, `first_result_s`, `first_step_s`, `answer_s`, `opening_gate`, read if present); **performance** (72 h / 7 d / 28 d views + watch minutes, cumulative since the self-view cutoff, 28-day traffic-source mix); **demand** (raw search queries with their date window, normalised query families, search bands, follow-up status). The record is BUILT from existing files, never stored. |
| 2 | Writer fields | `question_answered` (one string) and `questions_open` (a list) are requested in `_output_contract` for **every** lane. They are `_CARRY` keys, model-written, so they are carried and never popped. `_validate_script` coerces both (`memory.coerce_question[s]`). Both are stored in the ledger row. |
| 3 | Per-video search terms | YouTube Analytics API traffic-source-detail report: `dimensions=insightTrafficSourceDetail`, `filters=video==ID;insightTrafficSourceType==YT_SEARCH`, a 28-day window, `sort=-views`, `maxResults=25`. Args come from the pure `analytics.search_terms_args`. |
| 4 | Follow-up rule (verbatim) | A canonical query family with **≥ 50** attributed search views in the **last 28 days** (never lifetime), plus a specific question the original left unanswered, plus admissible evidence, becomes **ONE** follow-up candidate. |
| 5 | Cooldown | **14 days** per family, unless the follow-up corrects an error or documents a material change (`exempt` reason `correction` / `material_change`). The clock is the newest PUBLISHED ledger row with that `followup_family`, so no state file is needed. |
| 6 | Normalisation | Case, spaces, hyphens, underscores and dots are folded (`memory.norm_query`): "nv-uefi-unlocker" and "nv uefi unlocker" are one family. The raw queries are kept beside it. |
| 7 | Hand-off | A candidate is not an upload. `build_script`'s tool branch puts it first in its candidate list as an item carrying `followup_question`, `followup_parent` and `followup_family`. It still passes every gate (title screen, source eligibility, `script_tool`, then every run() gate). On success `script["followup"]` is set; it is popped inside `_validate_script` and carried by `_carry_over` (the receipts/cheat_sheet trap). |
| 8 | North star | Rolling 28-day on-demand long-form watch time: `creatorContentType == VIDEO_ON_DEMAND` minutes from `dimensions=creatorContentType`. Baseline **12.11 h** (Oct 7 – Nov 3, long-form only). |
| 9 | Ladder | 2× = 24.22 h by day 30 · 5× = 60.55 h by day 60 · 10× = 121.10 h by day 90 · 25× = 302.75 h · 50× = 605.50 h · 100× = 1,211.00 h. Each stage prints its round-3 §6 leading-evidence line verbatim. |
| 10 | Day 0 | The first publication under the new production contract = the first PUBLISHED ledger row with `experiment == "pilot_a"` (its publish date). Until it exists, every stage prints **"not started"**. |
| 11 | Outlier flag | **"outlier-dependent"** when the largest video's share of the window's on-demand watch time is above **50%**. |
| 12 | Live | Live / archived-live watch time (`LIVE_STREAM`) is a separate counter and never counts toward the north star. |
| 13 | YPP | Qualified hours are read manually from Studio → Earn, and printed as such. |
| 14 | Insufficient observations | "Unresolved", never on track or failed. |
| 15 | Search longevity | Search capture per video by age band **1–7 / 8–14 / 15–28 / 29–56** days, normalised per day, for the videos where data exists. |
| 16 | Shadow queue: what each automatic run records | Whether a SECOND tool candidate passed the pre-writer gates (eligible source, grounding floor, suitability screen, `evidence.probe`, where a missing probe means "unknown"), and the run's wall time. One line per run in the NEW `state/shadow_queue.jsonl`. |
| 17 | Shadow evaluator (verbatim) | 14-day window; ≥ **10** days with a qualified second candidate; p95 job time **< 60 min**; no missed primary uploads → prints eligible / not eligible for the later 1-vs-2 quantity test. |
| 18 | The 1-vs-2 quantity test | **Spec only, not built.** 7 one-video days and 7 two-video days, balanced across weekdays, with candidate rankings chosen before the day's treatment is assigned. Judge the sum of each release day's first-seven-day watch minutes. Promising = ≥ **1.4×** cohort watch time, first-slot median ≥ **90%** of the single-upload-day median, and ≥ **1.2×** after removing the largest second-slot winner. **No second upload is built in this phase.** |
| 19 | Row 18 | Long-form views across 2026-08-24/27 are not comparable (Studio flagged a view-counting change ending 2026-08-27). See *Row 18 decision*. |

## API findings (verified 2026-11-04 on the official reference)

- https://developers.google.com/youtube/analytics/dimensions:
  - `creatorContentType` values are `LIVE_STREAM`, `SHORTS`, `STORY`, `VIDEO_ON_DEMAND` ("a YouTube video that does not fall under one of the other dimension values") and `UNSPECIFIED`. Data starts 2019-01-01.
  - `insightTrafficSourceDetail` under `YT_SEARCH` is "the search term that led viewers to the video".
- https://developers.google.com/youtube/analytics/channel_reports:
  - **Traffic source detail:**
    - dimension `insightTrafficSourceDetail` (required; `creatorContentType` optional);
    - filter `insightTrafficSourceType` required, with 0 or 1 of `video`/`group`;
    - metrics `views`, `estimatedMinutesWatched`, `engagedViews`;
    - `sort` is required (`-views` or `-estimatedMinutesWatched`), and `maxResults` must be **≤ 25**.
  - **Traffic source:**
    - dimension `insightTrafficSourceType`, plus optional `day` and `creatorContentType`;
    - "if you specify multiple values for the video filter, you can also add that filter to the list of dimensions";
    - the number of videos × days must be **≤ 50,000**.
  - **Top videos:** `video` plus optional `creatorContentType`. `sort` is required and `maxResults` must be ≤ 200.
  - `creatorContentType` appears **only as a dimension**. No report lists it as a filter. So VIDEO_ON_DEMAND is selected client-side: `dimensions=creatorContentType` for the total, and `dimensions=video,creatorContentType` for the largest-video share.

## Queries added to the nightly collector (`analytics.collect_m1`, run before the ledger query)

| key in the snapshot | dimensions | filters | window | kill switch |
|---|---|---|---|---|
| `north_star` | `creatorContentType` | — | 28 days ending yesterday | `north_star` |
| `vod_top` | `video,creatorContentType` | — (sort `-estimatedMinutesWatched`, 200) | same | `north_star` |
| `search28` | `video,insightTrafficSourceType` | `video==<ledger long-forms, ≤ 200>` | same | `memory_analytics` |
| `search_terms` | `insightTrafficSourceDetail` | `video==ID;insightTrafficSourceType==YT_SEARCH` (sort `-views`, 25) | same | `memory_analytics` |
| `age_bands` | `video,day,insightTrafficSourceType` | `video==<long-forms published in the last 63 days>` | oldest publish day → today | `memory_analytics` |

Each query has its own `try`. A failure costs only its own key, and never the channel / top-25 / ledger / reach reports. Quota: at most 4 queries + 10 search-term queries a night.

## Delegated decisions (for the owner's report)

| # | Value | Default chosen |
|---|---|---|
| D1 | 28-day window end | **Yesterday**, inclusive (28 days ending today − 1), because that is how the 12.11 h baseline was read (Oct 7 – Nov 3, read on Nov 4). |
| D2 | Which videos get a search-terms query | **≥ 25 28-day search views, at most 10 videos a night, most first**, because 25 is half the trigger: a family split across two videos is still seen, and the quota rule asks for only the videos the rule needs. |
| D3 | How old search-term data may be and still fire | **7 days** after its window end, because a candidate must reflect the *last* 28 days, and a collector outage must not replay an old window. |
| D4 | Candidates per run | **1**, and it goes **first** in the tool lane's list, because the rule says ONE candidate and a follow-up has demonstrated demand. It still costs one of the 3 tries. |
| D5 | Which open question | **The first** non-empty entry of the parent's `questions_open`, because the writer is asked to list the most useful open questions and the rule needs one specific question. |
| D6 | Admissible evidence | `evidence.probe(item)` answers a dict whose `source` is `hosted`, `author` or `sandbox` (the v3-P.1 sources). A missing module, a raise or `None` means **"unknown"** and never fires, because a fail-soft seam's `None` means "did not work", not "no evidence". |
| D7 | Writer field sizes | `question_answered` one line ≤ 200 chars; `questions_open` 1-3 entries, each ≤ 200 chars, newlines collapsed, because the value is later put into a writer prompt and a log line. |
| D8 | 72 h | **Days 1-3** of the video's life, with day 1 = the publish day (UTC), because the API is day-granular. Day 1 holds only ~7 h after the 16:45 slot. |
| D9 | Age-band query window | Long-forms published in the **last 63 days** (the 56-day band + 7 days of API lag). A video that leaves it keeps its last record, read from older snapshots. |
| D10 | Band normalisation | Search views ÷ **observed** days in the band (days up to the newest day in the answer). The scoreboard prints both the pooled views/day and the per-video median. |
| D11 | Stage verdict on a checkpoint day | Judged on the first window that ends on/after the day before the checkpoint. With no such window the stage is "unresolved – insufficient observations". "Hours met" says *on track only if the leading evidence holds*, because most leading evidence (pilot verdicts, continuation) is not in state. |
| D12 | "Two consecutive non-overlapping windows" (50×, 100×) | The previous window ends **1-2 days** before the current one starts, which tolerates a one-day collection gap. |
| D13 | Shadow: candidates per run | **3**, after the no-network screens (title screen + GitHub/HF source). This is build_script's own cut. Measured live on 2026-11-04: three Product Hunt pages ranked ahead of a qualifying repo and spent every slot when the cut came first. |
| D14 | Shadow: network bound | **60 s** hard wall clock for all of the shadow's fetches, enforced with a daemon thread and `join(timeout)`, because `requests`' timeout is never a deadline (CLAUDE.md trap). |
| D15 | Shadow: "job time" | `JOB_STARTED_AT` is stamped by a new first workflow step. Job time = now − stamp, taken when the pipeline step ends. It falls back to the pipeline process's own wall time. The later steps (Reels, analytics, state-save) are not included. |
| D16 | Shadow: which runs record | Automatic publish runs only (no forced format), once per process after `run()` returns, from the first attempt's ranked signals. A duplicate-day skip never ranks, so it records nothing. |
| D17 | Shadow: "qualified" | All four pre-writer gates pass AND the probe says admissible. "unknown" (pre-writer pass, probe missing) is logged but never counted. A day counts once even if it has two rows. |
| D18 | Shadow: window | The 14 days ending today. A window that starts before the first shadow row is unresolved. Today is never counted as a missed upload, because the 14:53 retry cron may still publish. |
| D19 | p95 | Nearest-rank. |
| D20 | Distinct second candidate | Not the primary by URL and not the same repo/model name, because round 4 asks for a different useful question and not another spelling. |

## Row 18 decision: learn's long-form cutoff moves to 2026-08-28

- **Decision:** long-form **comparisons** in `learn.score` (the format and hook arms, and therefore the hook-pattern drop rule) count only videos **published on or after 2026-08-28** (`learn.LONGFORM_FLOOR`). That is the day after Studio's flagged view-counting change ended.
- **Unchanged:** the self-view cutoff `DATA_FLOOR = 2026-08-24` still bounds every query, the ids measured (`ledger_ids`), the Shorts A/B and the reach table.
- **Measured on the real ledger (2026-11-04):** 3 long-forms leave the arms (published 08-24, 08-25, 08-26):
  - `format:evergreen` 26 → 25 videos;
  - `format:news` 29 → 27;
  - `hook:correction` 6 → 5 and `hook:quiet` 6 → 5, both still untrusted.
- No pattern was dropped before the change, and none is dropped after it.

## Files changed

- NEW `factverse/memory.py`: coercion, normalisation, the API-row parsers, the follow-up rule, `followup_items` (the `build_script` seam), `followup_prompt` (the `script_tool` line), `ledger_fields`, `build_record`, and `python -m factverse.memory [n | ids…]`.
- NEW `factverse/northstar.py`: the ladder, day 0, the outlier flag, the live counter, the leading signals, search longevity, and the scoreboard block.
- NEW `factverse/shadow.py`: `prewriter_gate`, `check` (bounded), `after_run`, the evaluator and its block.
- `factverse/analytics.py`: the M.1 args builders (pure) and `collect_m1`, called inside `collect()` before the ledger query.
- `factverse/learn.py`: `LONGFORM_FLOOR`, `ledger_videos(published_from=)`, and the north-star and shadow blocks in `scoreboard()` (each in its own try).
- `factverse/ai_pipeline.py`:
  - the import;
  - the `followup` pop and the two coercions in `_validate_script`;
  - the two fields in `_output_contract` (flag `memory_fields`);
  - three `_CARRY` keys;
  - one `script_tool` prompt line;
  - two `build_script` changes;
  - `LAST_RANKED`;
  - `_ledger_memory` before the upload and `**_ledger_memory` in the PUBLISHED `record_run`;
  - the `shadow.after_run` call in `__main__`.
- `factverse/state_merge.py`: `state/shadow_queue.jsonl` (ordered line union).
- `.github/workflows/publish.yml`: the stash list gets `state/shadow_queue.jsonl`, and a first step stamps `JOB_STARTED_AT`.
- `config.json`, `config.example.json`: `memory_fields`, `memory_analytics`, `north_star`, `followup_candidates`, `shadow_queue` (all `true`).
- NEW `tests/test_m1_memory.py` (45 tests, helpers `_m1_`).

### Integration notes for v3-P.1 (which rewrites `script_tool` in parallel)

`script_tool`: one added line, directly under `SOURCE: {source}  ({url})` in the writer prompt:

```python
{memory.followup_prompt(item)}
```

`build_script`, tool branch: the loop header, and two lines after a successful `script_tool`:

```python
        # v3-M.1 row 9: a follow-up candidate goes first and passes every gate below
        for c in [f for f in memory.followup_items() if not too_many_failures(f["title"])] + ranked:
...
                s["signal_title"] = cand["title"]
                if memory.followup_of(cand):
                    s["followup"] = memory.followup_of(cand)
```

P.1 adds `evidence` to the `_CARRY` tuple and to the pop list. M.1 adds `question_answered`, `questions_open` and `followup` to `_CARRY`, and `followup` to the pop list. Both edits touch the same lines: keep all of them. `record_run` gains `**_ledger_memory`, while P.1 adds `evidence_source` / `evidence_status`. These keys do not overlap.

## Verification

- **Suite:** run on the branch with `py -3 -m pytest tests/ -q`. The count is in the report.
- **Scoreboard over the REAL state files** (2026-11-04, worktree ledger to 2026-10-31):
  - no `north_star` observation exists yet, because the first CI snapshot carries it;
  - the display-only proxy (ledger long-forms since 08-24, collections 10-03..10-31) reads **5.22 h**. It is **not comparable** with the 12.11 h baseline: Studio's figure includes long-forms published before 08-24, which the ledger does not track;
  - day 0 is "not started" and every stage is "not started";
  - the leading signals read: 2 tool videos in the last 7 days, no 7-day data, 0 evidence-backed follow-ups and 0 task families;
  - search longevity has no data yet;
  - the shadow queue is "unresolved – insufficient observations".
- **Memory records for 3 real videos** (ZCode `-zMkp0hnACk`, RemoveMacAI `xm2GvY4QttA`, anatomy `wwI1rTpmnrg`):
  - identity, canonical tool and source come from the ledger plus `tools_index.json`;
  - the cumulative numbers come from the newest snapshot (116 / 252 / 68 views; AVD 61 / 45 / 43 s);
  - viewer need, evidence, delivery, 72 h / 7 d / 28 d and demand are empty, because none of these was recorded before this phase.
- **Follow-up fixture** modelled on nv-uefi-unlocker (100 + 86 views over two spellings, plus an 18-view `gpu unlock`):
  - family `nvuefiunlocker` = 186 → **candidate**, handed to the tool lane with its question;
  - a follow-up published 10-25 → **cooldown**; one published 10-21 (14 days) → candidate again;
  - 10-25 plus a `correction` exemption → candidate;
  - the real probe on this branch (no `evidence.py`) → `evidence_unknown`;
  - no open question → `no_open_question`.
- **Shadow evaluator fixture:**
  - 10 qualified days, p95 53 min, no misses → **ELIGIBLE**;
  - the same with one missed upload → not eligible;
  - 9 days logged → unresolved.
- **Live pre-writer gate pass** (2026-11-04, `signal_engine.rank` over the public feeds, 5 tool signals):
  - two GitHub repos passed every pre-writer gate, with evidence "unknown": `deepseek-ai/dsh-superagent-prototype` (2,556 chars) and `ccch1mneyyy/dsh-Go` (5,000 chars);
  - three Product Hunt pages were ineligible;
  - `shadow.check` with the first repo as primary found `dsh-Go` as the second candidate in 4.5 s.

## Known limits

- **No YouTube token exists locally.** None of the five new queries has run against the real API. Only their args, and the parsers over the documented response shape, are tested. The first CI log lines that show it worked are the north-star block's `now: … h` line and the absence of `⚠️ … query skipped`.
- **Nothing can fire until P.1 merges.** `evidence.py` is missing on this branch, so both the follow-up rule and the shadow "qualified" count read "unknown". This is by design (D6).
- **No old video can seed a follow-up.** None of them recorded `questions_open`. The 186-view nv-uefi-unlocker case cannot fire retroactively.
- **Job time excludes the steps after the pipeline** (Reels, analytics, state-save; a few minutes).
- **The 72 h snapshot is day-granular** (D8).
- **Each age band is a sum of daily rows.** The API omits zero-view days, so a band's observed days come from the newest day in the answer, not from the rows.

## Proposed CLAUDE.md traps (for the integration step)

- **`creatorContentType` is a dimension, never a filter.** No report accepts it in `filters`. Select a content type client-side. A filter would fail the query at runtime, and only CI would show it.
- **Screen before you cut.** Any "first N candidates" bound must apply the no-network screens first, or ineligible pages spend the slots. `build_script` learned this in v3-B.4; the shadow queue relearned it live.
- **Under `python -m`, the running module is `__main__`.** Re-importing `factverse.ai_pipeline` from a helper loads a second copy with empty globals. Pass the module (`sys.modules[__name__]`) instead.

## Owner steps

- None are required to ship. Every kill switch is `true`, and each behaviour stays inert until its data exists.
- After the first CI run, read the north-star block's `now:` line and compare it with Studio's 28-day on-demand long-form number.
- When the pilot starts, nothing needs to be done: day 0 starts itself from the first `pilot_a` row.
- YPP qualified hours stay a manual read in Studio → Earn.

## Done when

- [x] The suite is green with the new tests.
- [x] The scoreboard was run over the real state and read.
- [x] The memory record was built for 3 real videos; the follow-up rule fires on the nv-uefi-unlocker fixture and respects the cooldown; the shadow evaluator was run on a fixture; a live pre-writer gate pass was run.
- [ ] The first CI snapshot carries `north_star`, `vod_top`, `search28`, `search_terms` and `age_bands`.
- [ ] 14 days of `state/shadow_queue.jsonl`, then the evaluator's verdict.
