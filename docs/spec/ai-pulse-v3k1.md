# Spec — v3-K.1: task catalogue, task-follow, useful tool pages, Challenger spec, distribution

Status: **locked** for the rows marked *locked*; **delegated** rows are Claude's defaults and each
one is revisable by changing a row, not the code. The owner approved the 2026-11-04 review with
*"go for all … do not stop until everything is done"*. The review rows this phase covers are
11, 12, 14 and 15 (site + X) of `docs/debate/2026-11-04-tooldojo-channel-growth/RESULT.md`
(kept local; its values are copied below so this repo stays self-contained). The shared
interface is `docs/spec/ai-pulse-v3-growth.md` → `script["evidence"]`.

## Why this phase exists

- **Row 12, the bet:** exact-name search brings 82% of long-form views, but exact-name demand is
  narrow. A *task* catalogue ("which tool for this job, under these conditions, today?") can
  reach people who do not know a tool's name. It must never say "best" without first-hand
  comparative evidence, and it must not mass-generate pages.
- **Row 14:** a visitor may want to know when the answer for *their task* changes, not every
  upload. The alert must be opt-in and only fire on a material change.
- **Row 15:** the cheat-sheet page was a download wrapper. Google distinguishes useful pages
  from wrappers, and X is no longer free.
- **Row 11:** Challenger becomes a recorded Radar Live segment, not another production quota.

## Decisions

| # | Decision | Value | Kind |
|---|---|---|---|
| 1 | Task families | A fixed list of 6: `speech-to-text`, `text-to-speech`, `ocr`, `background-removal`, `image-upscaling`, `pdf-tables` (`tasks.FAMILIES`). | delegated — default chosen: these 6, because they are the families the 2026-11-04 supply check found hosted Gradio demos for (PDF tables had none running, but it is the review's own example) |
| 2 | Classification | Whole-word terms on the **title, tool name and one-sentence `what`** only, never the README or `uses`. Exactly one family must match; two or more is ambiguous and gives `""`. Stored as `task_family` in `state/tools_index.json`; an older row is recomputed at render. | delegated — default chosen: short surfaces + ambiguity = none, because a keyword means different things on a name and in a document (the C.4 trap) and a wrong family would put a tool on a comparison it does not belong to |
| 3 | "Comparable" | Same family **and** `source == "hosted"` **and** status in `PASSED_FIXED_TEST` / `FAILED_FIXED_TEST` / `TIMED_OUT` **and** the same non-empty `input` string **and** a valid `captured_at`. The group is the input with the most distinct tools (identity = the demo URL, else the tool name). `NOT_RUN` and `INCONCLUSIVE` are not results. | delegated — default chosen: identical fixed input, because the review's comparison is "same inputs, output checks"; a different input is a different test |
| 4 | When a hub renders | Only with **≥ 2 comparable hosted tests from 2 different tools**. Until then the catalogue is dormant by data. | locked (row 12) |
| 5 | Hub states | `withdrawn` (family listed in `task_hubs_withdrawn`) › `outdated` (newest comparable test older than **30 days**) › `inconclusive` (no tool passed) › `current`. A tool page shows an "Outdated:" line on its own test when it is older than 30 days. | locked states (row 12, "What you may be underestimating"); delegated — default chosen: 30 days, because the review says "review monthly" |
| 6 | Change history | Replayed from the catalog, date by date, on the comparable group: `first_answer`, `checked_again` (a new result, same answer), `recommendation_changed`, `now_passes` (a tool that failed or timed out on this input now passes). The answer is the set of tools that passed. No extra state file: the history is a derived artifact. | delegated — default chosen: replay, because a derived artifact needs no both-halves treatment and cannot drift from the catalog |
| 7 | Cap + switch | `task_hubs` (kill switch, default `true`) and `task_hubs_max` (default **1**). With more qualifying families, the one with the most comparable tools wins, then the newest test, then the family name. A withdrawn hub does not count against the cap (it is an existing URL kept stable). Hubs are in the index ("Compare by task") and the sitemap. | locked cap of 1 (row 12: "one task hub"); delegated ordering |
| 8 | The answer | "Among the N options we tested on this input, X and Y passed our fixed test." / "None of the N options … passed …, so we cannot recommend one yet." Plus: "This answer is conditional … It does not say any tool is the best in general." Never "best". No speed ranking (stated on the page). | locked (rows 11-12) |
| 9 | Follow offer | Shown on a hub only when `task_follow_channel` is a valid public Telegram username (5-32 letters/digits/underscores, starting with a letter), `task_alerts` is on and the hub is not withdrawn. Link `https://t.me/<channel>`, per-task hashtag `#speech_to_text` (family with `-` → `_`). | locked route (row 14: opt-in only); delegated hashtag form, because Telegram hashtags allow only letters, digits and `_` |
| 10 | What is a material change | `recommendation_changed` and `now_passes` only. A new star count, a new repo, a first answer and a re-test with the same answer never alert. **A documented requirement change is not detected:** the shared interface has no structured requirement field (see Known limits). | locked (row 14) |
| 11 | Alert delivery | `notify.yml` (16:55 UTC, after the publish slot), at most **1** alert per run, only events dated today or yesterday (**2-day** window). Sent to `@<task_follow_channel>`, never to `TELEGRAM_CHAT_ID`. Body: what changed, the supporting result (label, date, verbatim wording, observed line, input), who should care, the hub link; the video link only when the ledger proves it is already public. Telegram escaping (`_esc`, quote=False); over 4096 chars, whole blocks are shed (observed → input → video → who → result), never sliced. | delegated — default chosen: 1 per run and 2 days, because the first-ever run must not replay history and the existing video announcement uses the same 36 h idea |
| 12 | Alert state | `state/notified_tasks.json` (event ids), its own list; in `state_merge.FILES` (generic list union) **and** in the stash list of `notify.yml` (stash + `git add`) and `publish.yml`. Kill switch `task_alerts` (default `true`; a no-op until a channel is configured). | locked (both-halves rule) |
| 13 | Author demos | Candidate profiles under "Candidate profiles — not tested by us"; never in "Tested options". `clean_evidence` forces `source` `author`/`none` to `NOT_RUN` whatever the dict says, and recomputes `label`/`wording` from the enums. | locked (rows 4, 11) |
| 14 | Tool pages | Video first (directly under the title), then **the decision** (evidence label + verbatim status wording + "Skip it if"), the command, what it is, **Before you start** (the sheet's own steps, now stored as `steps`), what to make, **Evidence** (label, wording, fixed input, what we saw / what the author's demo shows, supported claims, date, demo link, and for an author demo the rights line: asset · commit · licence · copyright · NOTICE · modified), **Limitations** (what this source does not establish, from round 3), the PDF, the source. An entry with no evidence says "Not independently tested." | locked contents (row 15 / R4 rank 1); delegated order, because Google treats a page whose principal purpose is the video differently and the review asked for the video to be prominent |
| 15 | Search Console | `google_site_verification` in config: when it is a valid token, the index `<head>` carries `<meta name="google-site-verification">`. Empty by default. | delegated — default chosen: the HTML-tag method, because a Domain property needs DNS, which `github.io` does not give us |
| 16 | `source_url` | Scheme-checked again **at render** (`safe_link`), not only in `entry_for`. | found in this phase (see Traps) |
| 17 | X | **Off by default**: `"twitter": false` in both config files and `fv.flag("twitter", False)` in `notify.x_enabled()`. The code stays. | owner decision (row 15); see the note below |
| 18 | GitHub | No unsolicited issues, PRs, comments or mentions to tool authors, automated or manual. Nothing in the pipeline does any of this, and nothing will be built for it. | locked (row 15) |
| 19 | Distribution test | Spec only, below. | locked design (R4 rank 4) |
| 20 | Radar Challenger | Spec + draft board row only, below. | locked design (row 11, R3 §7) |

Every function added here is pure or fails soft: `tasks.*` returns `None`/`[]`/`""` and never
raises, `site.rebuild` isolates every hub write, and `notify._post_task_alerts` opens its `try`
before reading the switch or the token and redacts the token on every path.

## X — owner decision note

Verified on 2026-11-04 at `https://docs.x.com/x-api/getting-started/pricing`: the X API is
**pay-per-use**, with no free tier. Write operations are charged per request: **Post: Create
$0.015**, **Post: Create (with URL) $0.200**. Every post `notify.format_post` builds carries the
video URL, so one post a day costs about **$6.20 a month (31 × $0.20)**. The only "free" money is a
one-time incentive (`/x-api/getting-started/free-credits`): $20 after a first credit purchase
and up to $50 matching a first auto-recharge, expiring after 3 months, both needing a payment card.

The board's Now #1.4 ("Create the X app … Free tier, ~500 posts/month") is therefore stale.
**Decision for the owner:** keep X off (the default now), or switch `"twitter": true` and buy
credits. The review's ranking puts X after the site, the opt-in Telegram channel and original
Reels. The integration step fixes the board row; this phase does not edit `PHASES.md`.

## Evidence supply (open point 1) — finding

Read-only check of the public HF Spaces API, each Space's Gradio `/config` and `app.py`,
2026-11-04 13:52-14:15 UTC. Nothing was submitted to any demo. Counts are samples (the top ~12
by likes per search term), not a census.

| Family | Running Gradio Spaces (sample) | Verdict |
|---|---|---|
| Speech to text | ~12 | **3 CPU Spaces with a public named endpoint, audio in → text out** |
| OCR | ~10 | The strong ones are ZeroGPU; CPU ones are old or thin |
| Background removal | ~15 | Best CPU candidate has no stated licence; BRIA 1.4's model licence is non-commercial and it sleeps after 900 s |
| Text to speech | ~15 | Output can only be checked indirectly (an ASR round trip); Kokoro hides its API |
| Upscaling | ~8 | Mostly ZeroGPU, no clean correctness check |
| PDF tables | 0 | Every hit was sleeping or erroring |

**Recommended first family: speech to text.** It is the only family with 3 comparable,
CPU-hosted demos (so no ZeroGPU quota: anonymous users get about 2 GPU-minutes a day at low
priority, and GitHub runners share IPs):

- https://huggingface.co/spaces/k2-fsa/automatic-speech-recognition — cpu-basic, apache-2.0;
  the default model is "Medical dictation English", so a test must pin language + model.
- https://huggingface.co/spaces/microsoft/vibevoice-asr-bitnet-demo — cpu-upgrade, MIT; ships 4
  examples including two LibriSpeech English clips.
- https://huggingface.co/spaces/istupakov/onnx-asr — cpu-basic, MIT; `/recognize_en`, 1-30 s.
- Optional 4th: https://huggingface.co/spaces/openai/whisper (ZeroGPU, quota risk).

Excluded: Spaces that are thin wrappers around a vendor API with the owner's key
(`CohereLabs/cohere-transcribe`, `Qwen/Qwen3-ASR-Demo`): they look hosted but hide a quota.

**Proposed fixed input and check** (for v3-P.1 / Challenger, not built here): one committed
English WAV under 30 s (the tightest cap), either an edge-tts sentence or a public-domain
LibriSpeech clip with its published transcript; check = WER after normalising (lowercase, strip
punctuation) plus non-empty text within 120 s. **The WER pass threshold is in no spec and needs
the owner's one word.** Not verified: real latency, whether each finishes within 120 s, queue
limits, and the HF terms for automated use (`show_api=True` suggests API use is intended).

## Site discovery (open point 2) — finding

Checked live on 2026-11-04 (`https://dev-shivam-05.github.io/AI-PULSE/`):

- `robots.txt` answers **404** at the host root and at `/AI-PULSE/robots.txt`. A 404 robots file
  means "crawl everything"; nothing is blocked. Crawlers only read robots at the host root, which
  needs a repo named `Dev-Shivam-05.github.io`; it is not needed.
- `sitemap.xml` answers 200 `application/xml`, 12 URLs, **all 12 answer 200**.
- Every page has a self-referencing `<link rel="canonical">` on the live host, no `noindex` meta,
  and no `X-Robots-Tag` header. Server: GitHub.com, `text/html; charset=utf-8`.
- **Nothing in our HTML blocks indexing.** Whether Google has indexed any page, and any organic
  traffic, is **unmeasured**: that needs Search Console.
- Noted, not changed: `docs/*.md` (PHASES, HANDOFF, …) are served as raw text (`/AI-PULSE/PHASES.md`
  answers 200). They are not linked and the repo is public anyway.

Changes in this phase: hubs join the sitemap and the index; the verification meta tag (row 15).

**Owner steps for Search Console** (about 10 minutes):
1. Open https://search.google.com/search-console → Add property → **URL prefix** →
   `https://dev-shivam-05.github.io/AI-PULSE/` (a Domain property needs DNS, impossible on github.io).
2. Pick **HTML tag**, copy only the `content="…"` value, put it in `config.json` as
   `"google_site_verification": "<value>"`, merge to main. The next publish run (or
   `python -m factverse.site` + commit) writes it into `docs/index.html`. Click **Verify**.
   (Alternative: the **HTML file** method — commit Google's `google<…>.html` into `docs/`; it is
   served inside the prefix and the site rebuild never deletes it.)
3. Sitemaps → submit `sitemap.xml`.
4. URL Inspection → the index and one tool page → **Request indexing**.
5. After 7 days, read Performance → Search results (clicks, impressions, queries).

## Distribution test design (spec only, not started)

From review round 4, rank 4: **one surface at a time**, **6 distinct, useful items over 14 days**,
measuring **landing-page visits, attributable onward viewing and opt-ins**, not native impressions.

- **Surface order:** 1) the public opt-in Telegram channel (`@tooldojo`, not created yet — owner
  step), 2) the site via Search Console, 3) original-concept Reels (v3-S.1). X only after an owner
  budget decision. No GitHub outreach (row 18).
- **An item** is a result worth reading where it appears: a test outcome, a comparison change or a
  limitation, with the link to the page that explains it. "New video out" alone is not an item.
- **Measures:** opt-ins = channel subscriber count at day 0 and day 14 (Telegram shows it);
  attention = per-post views (Telegram shows them); onward viewing = YouTube Analytics traffic
  source "External" / referrer `t.me` and the site's domain, per video; landing visits = Search
  Console clicks for the site. **GitHub Pages has no visit log** and the site deliberately ships
  no analytics (v3-F.1 #9), so raw landing visits are unmeasurable without an owner decision.
- **Reading it:** repeated onward viewing from **≥ 3 separate items** is a continue signal; one
  successful repost is not. Impressions without onward use → revise the offer. No impressions →
  distribution unproven, not "nobody wants it".
- **Task-follow cohort (row 14):** the first 30 genuine visitors shown the offer; promising =
  ≥ 3 opt-ins and ≥ 2 attributable returns after a genuine update. Fewer than 30 exposed = unresolved.

## Radar Challenger (row 11) — spec, not built

Source: review round 3 §7, confirmed as row 11. It folds into Radar Live (L.2/L.6), it does not
add an upload.

1. **Segment:** a **recorded 2-3 minute** test segment inside Radar Live. Opening: task,
   incumbent, challenger and the actual distinguishing result. Middle: the same inputs, the output
   checks, observed failures. Ending: a narrow verdict — new leader, incumbent retained, tie, or
   inconclusive.
2. **Two separate boards:** "**Trending now**" (popularity/activity signals, labelled as not a
   quality ranking — today's board) and "**Challenger results**" (observed outcomes on a named,
   versioned test, with test date, conditions and evidence status). An author demo may appear as
   a preview; it **never** gets a tested position.
3. **Test:** one task family (speech to text, per the finding above), **3 fixed inputs per tool**,
   explicit correctness checks per input (WER threshold: owner word needed), the same 120 s
   bound as hosted evidence. **No speed ranking** across hosted demos (uncontrolled hardware and
   queues).
4. **Rate:** at most **1 new challenger evaluation per day**. The 15-minute board refresh does not
   need a new test.
5. **Replays** carry a "**Recorded test**" label with the recording timestamp.
6. **No new result:** show the last tested result and its date, never "today's winner".
7. **Pilot A:** both arms get **equal Radar promotion** while the pilot runs; otherwise the stream
   is an uncontrolled traffic intervention.
8. **Counters stay separate:** on-demand long-form watch time (12.11 h baseline, 100× target),
   **live + archived-live watch time on its own counter**, and qualified YPP hours read from Earn.
   For the first 14 days judge reliability and valid result production, not segment retention.
9. **Data path:** each Challenger result is a shared-interface `evidence` dict (`source: "hosted"`,
   the fixed `input`), recorded into the same catalog the hub reads, so a Challenger result moves
   the hub and can fire a task alert without any new code path in K.1.

**Draft PHASES row** (for the integrator; this phase does not edit the board):

| Phase | Scope | Status | Branch / notes |
|---|---|---|---|
| v3-K.2: Radar Challenger segment | review row 11 (spec `docs/spec/ai-pulse-v3k1.md` § Radar Challenger): a recorded 2-3 min segment inside Radar Live; two boards ("Trending now" vs "Challenger results", an author demo never gets a tested position); one task family (speech to text), 3 fixed inputs per tool with explicit correctness checks, no speed ranking; ≤ 1 new challenger a day; "Recorded test" + timestamp on replays; the last tested result and its date when there is no new one; equal Radar promotion for both Pilot A arms; a separate live watch-time counter; each result written as a hosted `evidence` record into the catalog | ⏳ queued | depends on v3-P.1 (hosted-evidence runner + `evidence` interface) and v3-L.7 (CI broadcast + LIVE/ON_DEMAND measurement); open: the WER pass threshold (owner word) |

## Files changed

- `factverse/tasks.py` (new): families, `clean_evidence`, comparability, hub states, history
  replay, cap, follow channel, alert events. Pure.
- `factverse/site.py`: `entry_for` stores `steps`, `evidence`, `task_family`; the tool page
  rewritten (row 14); `render_hub`; hubs in `rebuild`, index and sitemap; verification meta;
  `source_url` guarded at render.
- `factverse/notify.py`: `x_enabled` default off; `format_task_alert`, `_public_video`,
  `_post_task_alerts`, `NOTIFIED_TASKS`; `main()` runs the alert after the two announcements.
- `factverse/state_merge.py`: `state/notified_tasks.json`.
- `.github/workflows/notify.yml`, `publish.yml`: stash lists (+ `git add` in notify.yml); the X
  comment corrected.
- `config.json`, `config.example.json`: `twitter: false`, `task_hubs`, `task_hubs_max`,
  `task_hubs_withdrawn`, `task_follow_channel`, `task_alerts`, `google_site_verification`.
- `tests/test_k1_catalogue.py` (new); `tests/test_pipeline_logic.py`: the one F.3 test that relied
  on X being on by default now switches it on through `CONFIG`.

## Verification

- **Suite:** see the phase report (full `py -3 -m pytest tests/ -q` on the branch).
- **Fixture site** (`k1_fixture.py`, scratchpad, not committed): a catalog with one speech-to-text
  hub of 2 hosted tools on the same input (one failed then passed: `now_passes`), an author demo
  in that family with a `javascript:` URL and a `javascript:` `source_url`, a family with only 2
  author demos (no hub rendered), and a hosted OCR test from 2026-09-20 (outdated). Rendered:
  7 tool pages, 1 hub, index, sitemap. Screenshots of the index, the hub, the hub forced 40 days
  ahead (outdated state), and the hosted / author / outdated tool pages at 1280 and 390 px were
  read: no horizontal scroll (scrollWidth = viewport at both widths), the author demo shows "Not
  independently tested." although its dict claimed a pass, its rights line renders, no
  `javascript` string anywhere in the rendered output.
- **Found by looking:** the first render showed "Skip it if" twice on a tool page (decision box
  and Limitations); Limitations now carries only the source's "does not establish" line. The
  first render also leaked a `javascript:` `source_url` from the catalog into the Source link →
  row 16.
- **Task-alert body** rendered for the fixture and read (821 chars).
- **Real catalog:** `task_family` over the 10 live entries gives 1 family (Nemotron-Transcribe →
  speech-to-text) and 9 empty, which is right for coding agents, a Mac debloater, a GPU unlock, etc.

## Known limits

- **Dormant by data.** No catalog entry has `evidence` until v3-P.1 merges, and even then a hub
  needs two different tools tested on the **same** input string. One tool video a day may take
  weeks to produce two comparable speech-to-text results; the Challenger segment is the real
  supply. Coordinate the fixed-input string with v3-P.1 / K.2.
- **Merge order: P.1 before (or with) K.1.** K.1 reads `script["evidence"]`; P.1 pops a
  model-planted `evidence` inside `_validate_script`. Before that pop exists, a model could plant a
  top-level `evidence` key and it would reach the catalog. `clean_evidence` limits the damage
  (labels and wording are recomputed, author/none are forced to `NOT_RUN`), but a planted
  "hosted, passed" dict would still render as a pass.
- **"Tested versions"** are shown as the test date plus the demo URL: the shared interface has no
  version field for a hosted Space. Proposal for P.1: add the Space's `sha` from the HF API.
- **"A documented requirement changes" is not detected** (row 10): there is no structured
  requirement field, and comparing LLM prose (`skip_if`) across videos would alert on rewording.
- A re-test without a video creates no catalog row, so "checked again" needs a new video or a
  Challenger record.
- A hub switched off (or a family that stops qualifying) leaves its HTML file at its URL, unlisted;
  the rebuild never deletes files (same as tool pages past `MAX_PAGES`).
- The public Telegram channel does not exist; the bot must be an admin of it (owner step).
- Landing visits are unmeasurable on GitHub Pages without analytics (see the distribution test).

## Traps found (proposed for CLAUDE.md by the integrator)

- **A catalog href must be guarded at RENDER, not only when the row is written.** `entry_for`
  scheme-checked `source_url`, but `render_page` printed whatever the merged catalog held; a row
  from any other writer reached the `href` unchecked. Found by rendering a fixture, not by a test.
- **A field with a verbatim contract is recomputed, never carried.** `label`/`wording` come from
  the enums in `tasks.clean_evidence`; a dict that says "Best tool ever" cannot reach the page.
- **Prefer a replayed history over a new state file.** The hub's change history is derived from
  the catalog, so it needs no both-halves treatment and cannot drift.
- **Python's text mode on Windows writes CRLF.** `open(p, "w")` after a read rewrote whole files
  with CRLF (git normalises them, but the diff tools did not). Use `newline=""` when editing.
- **A test that relies on a config DEFAULT breaks when the default flips.** Turning X off broke
  one F.3 test that assumed `twitter` was on; it now sets the value it needs.

## Done when

- [x] Tests green with the new module (see report for the count).
- [x] Fixture site rendered and screenshots read at 1280 and 390 px; alert body read;
      `javascript:` neutralised.
- [ ] Owner: Search Console (5 steps above).
- [ ] Owner: create the public channel, make the bot an admin, set `task_follow_channel`.
- [ ] Owner: the X decision (stays off unless a budget is set).
- [ ] v3-P.1 merged and two speech-to-text tools tested on one fixed input → the first hub.
