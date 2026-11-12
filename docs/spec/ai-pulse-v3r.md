# Spec — v3-R: ToolDojo recovery cohort (14 days, read on day 21)

Status: **locked** — the owner said "Go for all" on 2026-11-12 to the decision table below.
Origin: ChatGPT Pro review round `docs/debate/2026-11-12-tooldojo-deep-diagnosis/`
(RESULT.md; kept untracked because `docs/` is published on GitHub Pages and the round holds
private Studio data). "Provisional" marks an operating setting, not a proven optimum.

## Why this phase exists

The 2026-11-04 plan never reached a viewer: in its first week the evidence rule skipped 7/7 tool
videos and the native-Short gate skipped 6/6 days, so filler was published instead. Fresh Studio
data (2026-11-12): non-tool long-forms get a median of 2-7 views (news 7, evergreen 5, roundup 2;
tool 63); Shorts keep ~13% stayed-to-watch and since 2026-10-27 get a median of 5 feed
impressions; 18 returning viewers in 28 days; the channel has never answered a comment. The top
video (gpu-unlock, 2,515 views, CTR 14.5%) loses viewers at 0:07 because it does not answer the
searcher's question (Linux only, RTX 50 unsupported) and over-promises in its title.

## Locked decisions

| # | Decision | Locked value |
|---|---|---|
| D1 | Long-form cadence | 3 per week: **Mon, Wed, Fri**, public at **16:45 UTC**. 6 uploads in the 14-day cohort, starting the first Monday after approval (**2026-11-16**). Provisional. |
| D2 | Shorts | **3 native Shorts per week: Tue, Thu, Sat at 18:45 UTC.** No crop Shorts, no storyboard Shorts. At most **1 Short per subject family in any rolling 168 h**; different headlines do not make different subjects; gpu-unlock and nv-uefi-unlocker are one family. A long-form and a Short may cover the same tool. Provisional. |
| D3 | Paused lanes | news, evergreen essays, roundups, debate, crop Shorts. **Zero exceptions.** |
| D4 | Evidence routes and labels | Observed: **"Tested by ToolDojo — <task/setup>"**. Licensed author demo: **"Author's demo — not tested by ToolDojo"**. Documentation: **"From the docs — not tested by ToolDojo"**. Labels sit on the segment they describe. Downloading a file or opening a page is not testing. |
| D5 | Opening | Viewer's question and evidence status visible at **0:00**; answer or decisive limitation by **0:07**; principal limitation by **0:15**. **No logo bumper and no popularity counter** anywhere in the cohort. Static branding may accompany useful content. Timings provisional. |
| D6 | Titles and thumbnails | Name the tool and one specific question; title, thumbnail and video promise the same answer. No unobserved outcome claim. Never imply compatibility the evidence excludes. The existing gpu-unlock packaging is corrected too (owner action A2). |
| D7 | Reserve and empty slots | Target **3** pre-rendered, source-checked long-form reserves (a target, not a gate). Recheck facts before using one. If the scheduled format has neither a qualified candidate nor a qualified reserve: **publish nothing and log the miss.** No filler. Provisional. |
| D8 | Validators | Only **truth/safety, rights/privacy, and usable-render integrity** (intelligible core audio, readable essential evidence) may block publication. Style failures get **one repair**, then a warning. A false diagram is a truth failure; different wording is not. |
| D9 | Visuals | **0** unrelated stock scenes; no continuous full-desktop scroll longer than **5 s**; essential source excerpts readable at **390 px** width. Provisional. |
| D10 | Series | "Before You Install", "One Task, One Result", "What Changed?" — no quotas. "What Changed?" explains a documented change that affects a practical decision about a covered tool; it is not a news exception. |
| D11 | Replies | Every genuine, on-topic, visible, repliable viewer question answered within **24 h** from the current versions of the video's sources; uncertainty stated when the sources do not settle it. Existing backlog cleared in the first 24 h after launch. One-line answer + evidence status as a channel comment and as the first description line. Pinning optional (the API cannot pin). One genuine unanswered question qualifies a follow-up candidate. |
| D12 | First 6 long-form topics, in order | 1 gpu-unlock (compatibility) · 2 RemoveMacAI (changes and reversibility) · 3 Nemotron-3.5-Transcribe (local-use requirements) · 4 nv-uefi-unlocker (compatibility differences) · 5 OpenBot (prerequisites for a documented task; project identity taken from the original video's source record) · 6 ZCode (setup requirements). Each name is matched to the original demand-producing video's source record; documentation is an admissible default route; a failed candidate uses D7. Order provisional. |
| D13 | Reads | **Day 14** = delivery review: 6 long-forms, 6 native Shorts, 0 filler, 100% of eligible questions answered within 24 h. **Day 21** = outcome review: long-form promising when median 0:07 retention >= **R0 + 8 points** AND median first-7-day watch time > **W0**; Shorts promising at median stayed-to-watch >= **22%**. Evidence floors: usable first-7-day curves for >= 4 of 6 cohort long-forms and >= 4 baseline videos; >= 4 of 6 Shorts with 50+ feed impressions in their first 7 days. Every upload's exposure is shown; nothing is reported on survivors only. Provisional. |
| D14 | Stop rule | At day 21: if median first-7-day watch time <= W0 AND median 0:07 retention <= R0 (with D13's floors met), stop this treatment and re-diagnose with the owner. Mixed = revise without scaling. Thin data = inconclusive. Missing uploads = a delivery failure, not viewer rejection. |
| A1 | Owner one-off | Reply to the RTX 50 comment on gpu-unlock (text in the handoff). |
| A2 | Owner one-off | Correct the gpu-unlock title and description per D6 (text in the handoff). |

**Frozen baseline (2026-11-12):** the 11 tool long-forms published 2026-10-02..11-03
(`-zMkp0hnACk yjgtYZdEWH8 JQbzwDs_zgM FHfd45OkoRE xm2GvY4QttA wwI1rTpmnrg 0PXRcVZ6ls4 -oCxU6iIDak
4MTEDi4MdnQ QFKGh9DhDW4 Q-P_P-Y1-to`). **W0 = 13 min** median first-7-day watch time (collector
`age_bands` 7d, complete). **R0** = median 0:07 retention of their first-7-day curves — to be
measured once in Studio before the day-21 read (phase R.4).

## Out of scope for the cohort
Radar Live, task hubs and the site catalogue, X posting, a second daily long-form, a new voice
(the Kokoro voice stays), Pilot A/B experiments (superseded by this cohort).

## Phases
- **R.2 — cohort launch** (this branch): D1, D2, D3, D4, D5, D7 (no-filler part), D8, D12, plus the
  visible defects found in the frames (literal markdown asterisks in Short hooks).
- **R.3 — answers and visuals**: D11 reply module, D6 title rule as a gate, D9 visual rules,
  D7 reserve, Short subject-family cooldown across weeks, the empty-diagram defect.
- **R.4 — read**: R0 measurement, day-14 delivery report, day-21 outcome report (D13, D14).

## Acceptance (binary)
- [ ] On a Tue/Thu/Sat/Sun run day no long-form is built; on Mon/Wed/Fri at most one is.
- [ ] No news / evergreen / roundup / debate long-form can be produced while the cohort flag is on, including through any fallback.
- [ ] A day with no qualified candidate records a miss in the ledger and uploads nothing.
- [ ] A tool candidate without admissible evidence proceeds with the documentation label instead of being skipped.
- [ ] The cohort long-form has no intro bumper and its first 10 s contain no popularity counter.
- [ ] No crop or storyboard Short is uploaded; a native Short is only uploaded for Tue/Thu/Sat 18:45 UTC.
- [ ] A native Short whose only failures are style rules is published after one repair (warning logged).
- [ ] The topic queue serves D12's items in order and never repeats a served item.
- [ ] Every new flag has a kill switch in config.json; the full suite passes.
