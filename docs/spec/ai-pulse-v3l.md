# Spec — v3-L: live-streaming pilot

Status: **PROPOSED 2026-10-01.** §5 copies YouTube's published numbers. §6 and §7 are Claude's
proposals and need the owner's one-word approval before the first public stream. Built on
`v3-phase-l` (cut from `origin/main` at `984fb6a`), in a separate worktree, so the other
session's `v3-phase-g4` working directory was never touched.

Labels used below: **[policy]** official YouTube text, fetched on the date given · **[observed]**
read from this repo's state files · **[measured]** run on the owner's laptop this session ·
**[estimate]** arithmetic on observed numbers · **[proposal]** needs approval · **[unknown]**.

## 1. The question, and the short answer

The hypothesis (from the owner's friend): *live streaming, e.g. relaxing gameplay or a looping
video, is a faster route to monetization.*

Answer on the evidence: **no — not for this channel, and not as a watch-hour farm.** The binding
constraint is not the format. It is that almost nobody who finds a ToolDojo long-form keeps
watching or subscribes:

- Subscribers are the slower bar. Both YPP tiers need 500+ subscribers. The channel gains about
  4 per 28 days, so 500 is roughly a decade away at today's rate.
- Live streaming converts an existing audience; it does not create discovery for a channel with
  a handful of subscribers.

What *is* worth testing is a small, niche-fit live format whose purpose is **subscriber
conversion and an evergreen replay**, not hours. Primary pilot: **ToolDojo Live Lab** (§6).
Fallback: **Premiere of the Sunday roundup** (§4 E).

## 2. Baseline

All [observed] from `state/analytics.jsonl` and `state/runs.jsonl` on `origin/main` (snapshot
collected 2026-09-30T19:42Z). The channel-level days run to 2026-09-28 because the API lags 2
days.

| Metric | Value | Note |
|---|---|---|
| Watch hours, 2026-09-01..09-28 | **15.7 h** | channel total, Shorts included, so an upper bound on YPP-qualified hours |
| — excluding 2026-09-02 | **8.0 h** | 09-02 = 465 min from 127 views, average view % 150.9: the same shape as 08-23/08-24 (self-view period, PHASES "Now #0") |
| Subscribers gained, same 28 days | **4** | 12 across all 73 reported days |
| Views, 2026-09-03..09-30 | 4,052 | 1,221 of them on 09-25 (one Short, `wG-KozRcTuM`) |
| Long-forms in the ledger query | 32 videos, **376 views, 161 min total** | median average view duration **32 s** |
| Subscribe rate | 0.08% | Studio screenshot 2026-09-26 (spec v3-G.3a) |
| Publishing | 69 `PUBLISHED` runs | news 50, evergreen 14, roundup 5, tool 0 |
| Live streams ever | **none** | no live code in the repo; OBS installed but never launched (no `%APPDATA%\obs-studio`) |

[unknown]: audience country and age, live viewer behaviour (no live history exists), returning
viewers, discovery sources, impressions and CTR (not in the Analytics API this repo uses; see
PHASES "Now #7"), whether live streaming is already enabled on the channel, upload bandwidth,
microphone quality. Monetization status is assumed **not in YPP**, since the numbers are far
below every tier.

[estimate] The gap, in the YPP's own rolling-12-month terms:
- 3,000 h a year needs **230 h per 28 days**. Today's rate is 8.0, so the channel has about
  3.5% of the rate it needs.
- 500 subscribers a year needs **38 per 28 days**. Today's rate is 4.

## 3. Policy and eligibility (verified 2026-10-01)

| # | Finding | Source |
|---|---|---|
| P1 | [policy] Expanded YPP (fan funding): "500 subscribers with 3 valid public uploads in the last 90 days and 3,000 valid public watch hours in the last 12 months" (or 3M Shorts views / 90 days); **India is an eligible country**. Ad revenue: 1,000 subscribers + 4,000 hours / 12 months, or 10M Shorts views / 90 days. | [answer/13429240](https://support.google.com/youtube/answer/13429240), [answer/72851](https://support.google.com/youtube/answer/72851) |
| P2 | [policy] Ineligible toward watch hours: "Private videos, Unlisted videos, Deleted videos, Ad campaigns, YouTube Shorts, **Livestreams that are unlisted, deleted, or not converted to VOD**". So a public live stream counts **only if its archive stays public**. | answer/72851 |
| P3 | [policy] "Every channel that meets the threshold will go through a standard review process" (about a month). Meeting the numbers is not acceptance. | answer/72851 |
| P4 | [policy] Archives: "If your stream exceeds 12 hours, it may not be captured at all." A 24-hour stream risks producing no VOD, and so (P2) **no countable hours**. | [answer/6247592](https://support.google.com/youtube/answer/6247592) |
| P5 | [policy] Inauthentic content: content must "not be mass-produced, generic, repetitive, or manipulative". Examples not allowed: "Image slideshows, templated storylines, or scrolling text with minimal or no narrative", "AI-generated content made with generic or unoriginal templates giving the impression of mass production", "Videos where characters are put in the same situation over and over again". | [answer/1311392](https://support.google.com/youtube/answer/1311392) |
| P6 | [policy] Reused content: "repurpose content that's already on YouTube or another online source without adding significant original commentary, substantive modifications, or educational or entertainment value". | answer/1311392 |
| P7 | [policy] Games: monetizing game content needs "commercial use rights granted to you by the license from the video game publisher". Publishers "may not grant commercial rights for videos that simply show game play for extended periods of time". Owning the game is not that licence. | [answer/2490020](https://support.google.com/youtube/answer/2490020) |
| P8 | [policy] Fake engagement covers "anything that artificially increases the number of views, likes, comments, or other metrics", sub4sub, and "viewbotting" of live traffic. Repeated violations lead to strikes, and severe cases to termination. **This includes watching our own streams from other accounts or devices.** | [answer/3399767](https://support.google.com/youtube/answer/3399767) |
| P9 | [policy] Misleading metadata: "titles, thumbnails, descriptions … to trick users into clicking on a video that does not deliver what was promised". | [answer/2801973](https://support.google.com/youtube/answer/2801973) |
| P10 | [policy] Live streaming needs a verified channel and "no live streaming restrictions in the past 90 days". | [answer/2853700](https://support.google.com/youtube/answer/2853700) |
| P11 | [policy] Live API: `liveBroadcasts.insert` takes `scheduledStartTime` and `privacyStatus` with the `youtube` or `youtube.force-ssl` scope. Its quota cost was not on the page. | [liveBroadcasts/insert](https://developers.google.com/youtube/v3/live/docs/liveBroadcasts/insert) |

Not verified, and nothing below depends on them:
- **The list of what YPP reviewers look at** (main theme, most-watched, newest). The official
  page was searched and not found.
- **Whether a Premiere can be set through the Data API.** A third-party source says it is
  Studio-only, which is why fallback E is a Studio click.
- **Any written rule about prerecorded content labelled "live"**. None was found in the spam
  policy (P9 still governs misleading titles).

Four separate questions, answered for each format in §4: may it be **broadcast**, do we hold the
**rights**, is it **monetizable**, and does its viewing **count** toward the hour bar.

## 4. Formats compared

| | A. Looping relaxing video (friend) | B. Satisfying gameplay (friend) | **C. ToolDojo Live Lab** | D. Automated "tool radar" live | **E. Premiere of the Sunday roundup** |
|---|---|---|---|---|---|
| Viewer sees / hears | the same calm footage + music, for hours | someone playing a calm game, little talk | the owner's screen: a real terminal and browser installing and trying this week's trending AI tool, the owner's voice, chat questions answered | generated dashboards of GitHub/HF trends with pre-rendered narration | the normal weekly roundup with a countdown and live chat at release |
| Audience | ambient/sleep viewers, not ToolDojo's builders | gamers, not ToolDojo's builders | **the existing audience**: developers trying AI tools | existing audience | existing audience |
| Reason to stay | mood | mood | will it actually work? (genuine suspense), ask your own question | low: no one is there | release-moment chat |
| Original contribution | none, unless the footage is ours | play + commentary | **all of it**: our setup, our failures, our verdict | templated, P5 risk | the video itself (already original) |
| Variation | none, a P5 example | per session | a different tool every session | template repeats | weekly |
| Broadcast OK? | yes | yes | yes | likely, but labelling it "live" is P9 risk | yes |
| Rights | music + footage licences required | publisher commercial licence per game (P7) | own screen + voice; open-source tool UIs shown for education | our own renders | ours |
| Monetizable? | high P5/P6 risk | only with licence + commentary (P7) | yes (education, commentary) | P5 risk | yes |
| Counts toward hours? | only the part under 12 h that stays public (P2/P4) | if archived public | **yes**, the public archive (< 12 h) | if archived | yes, as a normal long-form |
| Owner effort | low after setup, but a PC on 24/7 or a paid host | high: plays every session | **~60 min/session** | build cost; unattended | ~10 min (one Studio toggle + join chat) |
| Cost | electricity/host + licences | game + licence | ₹0 (laptop, OBS, mic owned) | ₹0 | ₹0 |
| Verdict | **rejected for ToolDojo** | **rejected for ToolDojo** | **primary pilot** | held: policy risk and no viewer value | **fallback** |

Why A is rejected, with the arithmetic shown, not waved away [estimate]:
- Hours would need 230 per 28 days, i.e. 8.2 watch-hours a day. Spread over two sub-12-hour
  streams a day (P4), that is about **0.36 average concurrent viewers around the clock**.
  Numerically that is not absurd. It fails on everything else:
  1. a looping stream is the "same situation over and over" (P5) unless the footage changes;
  2. unowned footage or music is reused content (P6) or a Content ID match;
  3. it would put most of the channel's watch time in a loop, which is the channel a YPP
     reviewer then sees (P3; reviewer criteria unverified);
  4. hours were never the slow bar: 500 subscribers are (§2), and there is no evidence that
     ambient viewers subscribe to an AI-tools channel.
- If the owner wants to test ambient content anyway, it belongs on a **separate channel with
  original footage and licensed music**. That is a different project and out of scope here.

## 5. Encoder settings, and the readiness measured on this laptop

[policy] [answer/2853702](https://support.google.com/youtube/answer/2853702), read 2026-10-01:
H.264; keyframe "Recommended 2 seconds", "Do not exceed 4 seconds"; AAC "128 Kbps for stereo",
"44.1 KHz for stereo audio"; 1080p30 minimum 5 Mbps, recommended 14 Mbps; 720p30 minimum 3 Mbps,
recommended 8 Mbps; RTMPS preferred.

| # | OBS setting (owner types these) | Value | Where it comes from |
|---|---|---|---|
| 5.1 | Output → Encoder | x264, preset veryfast, profile high | OBS default preset; the preflight measures this exact cost |
| 5.2 | Rate control / bitrate | CBR **14,000 Kbps** (never below 5,000) | policy, 1080p30 |
| 5.3 | Keyframe interval | **2 s** | policy |
| 5.4 | Audio | AAC **128 Kbps**, **44.1 kHz** stereo | policy |
| 5.5 | Video → Base and Output resolution | **1920×1080**, **30 fps** | the display is 1920×1080 physical, so there is no scaling (see 5.7) |
| 5.6 | Source | Display Capture (Desktop Duplication) + mic | measured below |
| 5.7 | Preflight tolerance | ≤ 1 s of duplicated frames, 0 dropped | 3 start-up duplicates measured; [proposal] |

[measured] `scripts/live_preflight.py` (ffmpeg 8.1.2, i9-13900H, 20 threads, Iris Xe), 2026-10-01:

| Run | Result |
|---|---|
| 1080p30 test pattern, 20 s | **ready**: x264 at **2.31×** real time, 0 drops, keyframes exactly 2.0 s, AAC 44.1 kHz stereo, 13.2 Mbps measured |
| 720p30 test pattern, 20 s | ready, 6.85× |
| 1080p30 desktop via `gdigrab` (GDI), 10 s | **not ready**: 102 duplicated frames, so GDI capture only manages ~20 of 30 fps. The preflight no longer uses it |
| 1080p30 desktop via `ddagrab` (Desktop Duplication), 15 s ×3 | **ready** 3/3: 3, 20 and 13 duplicates, 0 drops |
| 720p30 desktop via `ddagrab` + CPU scale, 15 s ×3 | not ready 3/3: 47, 37 and 31 duplicates, from ffmpeg's CPU scaler. OBS scales on the GPU, so this does not carry over (unverified), and 1080p needs no scale anyway |

Not measured, and blocking a public stream:
- **upload bandwidth.** 14 Mbps CBR needs a stable uplink above that. Lower 5.2 toward the
  5,000 floor if the uplink cannot hold it.
- **OBS itself** (never launched).
- **A real ingest to YouTube.** That needs approval: the private test in §8, step 3.

## 6. Pilot design [proposal]

| # | Decision | Value |
|---|---|---|
| 6.1 | Format | **ToolDojo Live Lab**: the owner installs and tries one AI tool live, from a clean folder, on screen, voice only (no camera). The tool is a trending GitHub/HF tool that passes `gates.tool_unsuitable`, the same screen as the tool lane. |
| 6.2 | Run sheet | 0-3 min: what the tool claims and who it is for · 3-25: install + first real task, failures included · 25-40: one harder task from chat · 40-45: verdict ("use it if… skip it if…") + where the commands are |
| 6.3 | Length | **45 min** of content per session |
| 6.4 | Cadence | **2 per week** for 2 weeks = **4 sessions** |
| 6.5 | Slot | **Tue and Fri, start 15:30 UTC (21:00 IST)**. This is a test assumption: it ends before the 16:45 UTC long-form slot so the two do not compete. Replace it with Studio → Audience → "When your viewers are on YouTube" if that card has data. |
| 6.6 | Title | `LIVE: Installing <tool> from scratch, does it actually work? · Live Lab #<n>`. After the stream, edit the replay's title to drop "LIVE:" and state the verdict, for example `Installing <tool> from scratch: it works, with one catch · Live Lab #<n>`. Never claim a result before it happens (P9). |
| 6.7 | Thumbnail | the tool's real page screenshot + "LIVE LAB" (the tool-lane thumbnail recipe), no invented numbers |
| 6.8 | Description | paragraph 1 = the tool and the question; the install command(s) used; chapters added after the stream; a link to the latest tool video; no subscribe-for-reward wording (P8) |
| 6.9 | Subscribe prompt | twice, naturally: after the first thing works, and in the verdict. No sub4sub and no "sub to unlock" (P8) |
| 6.10 | Chat | Studio → Settings → Community: hold potentially inappropriate messages for review, and block links. The owner answers questions in the 25-40 block |
| 6.11 | Visibility | **Public**, and the archive is **kept public and never deleted** (P2). Every session is < 12 h (P4) |
| 6.12 | Stream key | a **new key created for the pilot**, entered only in OBS. It is never pasted into the repo, a chat, an issue or a log. The repo never reads it |
| 6.13 | Not allowed | watching our own stream from a second account or device (P8), prerecorded segments presented as live, music without a licence (use none) |

The sessions are human-hosted, so they cost owner time, not money: about 4 h across the pilot.
That is the honest price of the one format here that is original by construction.

## 7. Measurement and decision rules [proposal]

Data source: YouTube Studio, per stream, read **7 days after it ends** so the replay is included.
The repo's Analytics API collector does not list live streams. The owner fills one row of
`temp/live/pilot_log.csv` (`py -3 scripts/live_scorecard.py --init`) per session and runs
`py -3 scripts/live_scorecard.py`.

| # | Rule | Value | Why this number |
|---|---|---|---|
| 7.1 | Sessions before a verdict | **4** | the whole pilot |
| 7.2 | CONTINUE: median watch hours per session (live + 7-day replay) | **≥ 2.0 h** | = the whole channel's average WEEK today (8.0 h / 4) |
| 7.3 | CONTINUE: subscribers gained across the pilot | **≥ 4** | = the whole channel's last 28 days, so the pilot must at least double the subscriber rate |
| 7.4 | STOP: median watch hours per session | **< 0.5 h** | a quarter of 7.2 |
| 7.5 | STOP: …and every session's peak concurrent viewers | **< 3** | no session drew even a small crowd |
| 7.6 | STOP at once | any policy, copyright or Content ID notice | priority 1 |
| 7.7 | REVISE | anything between the bars: change **one** variable, in this order: slot (6.5) → title (6.6) → length (6.3); then 4 more sessions | one variable at a time |

These are **targets, not predictions**. Hitting CONTINUE does not get the channel into YPP. At
exactly the CONTINUE bar, 8 sessions per 28 days adds 16 h to the 8.0 h baseline. Over a rolling
year that is **313 h, against 3,000 needed** [estimate, the scorecard prints this]. Live Lab is
judged on subscribers and on replays that keep earning search views, not on hours.

Timeline:
- **Day 0**: approval.
- **Day 1**: OBS setup + private test.
- **Days 2-14**: the 4 public sessions.
- **Day 7**: health-only check (sessions 1-2 streamed cleanly?).
- **Day 14**: live numbers read.
- **Day 21**: final verdict, once session 4's 7-day replay window closes.

Confounders:
- The long-form keeps changing during the pilot: the b2/b3/g4 merges, the 1080p switch and the
  G.1 Shorts A/B.
- The first stream's notification reaches only ~12 subscribers.
- Studio data lags ~48 h.
- 4 sessions is a tiny sample, so treat a REVISE as normal, not as failure.

## 8. Approval gates (owner, in order)

1. **Approve §6 and §7** (one word, or name the rows to change).
2. **Check that live streaming is enabled**: Studio → Create → Go live. A first enable may not
   be instant; the official page read on 2026-10-01 gives no delay. If the channel shows a live restriction, stop (P10).
3. **Private test stream, 5 minutes.**
   - Studio → Stream → create a new stream key (6.12) → OBS settings from §5 → visibility
     **Private** → stream → read Studio's stream health → end.
   - Private viewing does not count (P2) and nobody is notified.
   - This is the only way to verify the real ingest and the uplink. Claude cannot do it: there
     is no key, and it must not handle one.
4. **Session 1 public**, then a row in the log after 7 days.
5. **Fallback E**, if the owner cannot give ~60 min twice a week: when scheduling the Sunday
   roundup in Studio, set it as a Premiere and join the chat at release. It is weekly and stays
   a normal long-form.

## 9. Rollback

- Nothing in production changed. No file the daily pipeline imports was touched, and the CI
  workflows, `config.json`, `state/` and the YouTube API quota are untouched.
- To roll back the code, delete the branch `v3-phase-l`.
- To roll back on the channel:
  - end the stream;
  - set a replay to Private only if it violates something; otherwise keep it, since public
    archives count (P2);
  - delete the pilot stream key in Studio.

## 10. Acceptance criteria

- [x] Baseline computed from the state files, with sources and dates (§2)
- [x] Policy verified against official pages, dated, with unverified items named (§3)
- [x] Formats compared, with a primary and a fallback (§4)
- [x] Preflight run on the real laptop at both profiles and both sources, results recorded (§5)
- [x] Scorecard decides from the §7 table; 20 tests (`tests/test_live.py`); stdlib only, so the
  CI test job needs no new dependency
- [ ] Owner approves §6/§7
- [ ] Private test stream healthy (§8, step 3): **blocked on the owner**
- [ ] 4 sessions logged and the verdict printed (day 21)
