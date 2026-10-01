# Spec — v3-L.2: ToolDojo Radar Live (zero-human live stream)

Status: **decided 2026-10-01** under the owner's standing instruction for this session ("build it
as soon as possible, do not stop until everything is finished") and the hard constraint "zero
human in the loop". Every value below was chosen by Claude and is **revisable**: change a row,
not the code. It replaces the human-hosted Live Lab of `ai-pulse-v3l.md` §6, which the
zero-human constraint rules out. §2-§3 of that spec (baseline, policy) still apply unchanged.

Going **public** is not decided here. The code streams to whatever key the owner configures, and
visibility is the owner's Studio setting. §6 is the gate.

## 1. What a viewer sees and hears

A 1920×1080 broadcast of **AI tools trending right now** on GitHub and Hugging Face. The data is
re-fetched every 15 minutes during the stream, so the numbers on screen are genuinely live.

- **Spotlight** (most of the time):
  - one tool on a large card: name, owner, its own description, and real numbers (stars or
    likes, age, average stars per day, language, licence);
  - a synthetic voice explains it while word-timed captions run underneath;
  - the board of the top tools sits on the right.
- **Board** (every 4th segment): the ranked list, with stars gained **since this stream started**
  measured by our own refreshes.
- **Footer, always on screen:** "Automated stream · AI voice · data from GitHub and Hugging
  Face". There is nobody in chat, and the stream never pretends otherwise.

Why it is not a loop:
- every session's tools and numbers come from that day's live data;
- a tool is spotlighted at most once per session;
- a tool can be spotlighted again only after a cooldown, and then it is framed as an update
  with its new numbers (row 12);
- a session that runs out of fresh tools ends; it does not repeat itself.

## 2. Decisions

| # | Decision | Value |
|---|----------|-------|
| 1 | Name | **ToolDojo Radar Live** |
| 2 | Canvas | 1920×1080, 30 fps: YouTube's 1080p30 row (v3l §5); the laptop measured 2.31× real time |
| 3 | Video/audio | H.264 x264 veryfast, CRF 20 (the storyboard's, v3g1 row 7) capped at 14,000 kbps, 2 s GOP, **no B-frames** (measured: B-frames put a segment's first DTS before the previous segment's last one); AAC 128 kbps 44.1 kHz stereo (v3l §5) |
| 4 | Session length | **ends at whichever comes first**: 120 min, or the fresh pool running out. 120 min matches the owner's own example; every session stays far below the 12 h archive limit (P4) |
| 5 | Minimum to go live | **≥ 10 fresh tools** after screening, otherwise the session is skipped and logged. A thin stream is worse than none |
| 6 | Sources | GitHub search API (the `sources.github_trending` query: `ai OR llm OR agent OR diffusion`, created in the last 14 days, > 120 stars, sorted by stars) **50** results; Hugging Face `/api/models?sort=trendingScore` **50** results. No key needed |
| 7 | Screen | every tool passes `gates.tool_unsuitable(name, description)`, the tool lane's own screen |
| 8 | Refresh | every **15 min** (GitHub's unauthenticated search allows 10 calls a minute; we use 2 an hour) |
| 9 | Order | spotlights in board order: GitHub by average stars per day since creation, HF by trending score, interleaved GitHub / HF |
| 10 | Board | top **8**, every **4th** segment, **20 s**, narrated only when the board changed since it was last narrated |
| 11 | Spotlight length | narration + **3 s** of tail, rounded **up to an even number of seconds** (so every segment is whole 2 s GOPs) |
| 12 | Cooldown | a tool spotlighted in the last **3 days** is skipped. After that it may return as "back on the radar", with the change since last time. History: `temp/live/radar_history.json` (gitignored, local only, never committed) |
| 13 | Narration | if `GEMINI_API_KEY` is set in the local `.env`: a **50-90 word** explanation from the tool's README + facts, which passes the gate (row 14). Otherwise: a data template (row 15) |
| 14 | Narration gate | every number in the narration appears in the facts or the README; no `gates.hype_terms`; 30-120 words. A failure falls back to the template, never to silence |
| 15a | Readable | a template spotlight needs a description whose letters are ≥ **70%** Latin script. Measured 2026-10-01: several of the top GitHub repos describe themselves only in Chinese or Japanese, which the English voice would garble and the brand font cannot draw. Such a tool still appears on the board, and can be spotlighted with written narration (row 13) |
| 15 | Template | `"<name>, from <owner>. <facts sentence>. In its own words: <description>."` The template is the higher P5 risk, so the owner is told to add the free key (§6) |
| 16 | Voice | edge-tts, `voice` / `voice_rate` from `config.json` (`en-US-GuyNeural`, `+5%`). Kokoro, the channel's main voice, is not installed on the laptop |
| 17 | Look | the storyboard palette and fonts (`assets/storyboard/storyboard.html`: `#090D18` background, `#22D3EE` cyan, `#FFD60A` yellow, Inter Black + JetBrains Mono). Text is fitted by measurement in the page, never by character count |
| 18 | Frames | one screenshot at every caption-phrase start and every whole second, held until the next. Phrases are ≤ **6 words** |
| 19 | Pipeline | producer renders segments ahead (queue of **3**) → each is remuxed with a running timestamp offset → a writer thread pipes it to one `ffmpeg -re … -f flv` (video copied; audio re-encoded through `aresample` with `min_hard_comp=0.01`, which trims the ~23 ms of AAC priming at each seam). The writer always holds the **next** segment in reserve: an OS pipe buffers almost nothing, and a 2.2 s input gap was measured without it |
| 20 | Gap filler | when no segment is ready **and the reserve is used up**, a **10 s** standby board (silent) is sent, so the ingest never starves |
| 21a | Dead producer | **5** spotlights in a row that fail (voice or render) end the session. A tool whose voice failed is put back, since that is usually the network |
| 21 | Reconnect | if the streaming ffmpeg exits, restart it up to **5** times per session, **10 s** apart; then end the session |
| 22 | Ingest | `YT_STREAM_URL` + `YT_STREAM_KEY` in the local `.env`, copied from Studio (the RTMPS URL behind the lock icon). The URL must be `rtmps://` and its host must end in `.youtube.com`, so the key cannot be sent anywhere else. The key is redacted from every log line |
| 23 | Keep awake | `SetThreadExecutionState` while a session runs, released at the end. No global power-plan change |
| 24 | Schedule | daily **20:00 local (IST) = 14:30 UTC**, Windows Task Scheduler (`scripts/radar_schedule.ps1`): current user, no admin, wakes the PC, never starts on battery, never two at once, Windows stops it after 3 h. This is a test assumption, the same reasoning as v3l §6.5 (India evening, US morning). Installed by the owner (§6 step 5), not by Claude |
| 25 | Logs | `logs/radar_live.log` (text) and `logs/radar_sessions.jsonl` (one summary per session: start, end, segments, standbys, restarts, tools). Both are gitignored |
| 26 | Kill switch | no `YT_STREAM_KEY` = the script logs one line and exits 0. To stop for good: `scripts/radar_schedule.ps1 -Uninstall` |

## 3. Owner-facing metadata (set once in Studio, not by code)

- **Title:** `ToolDojo Radar LIVE: trending AI tools on GitHub & Hugging Face, updated every
  15 min`
- **Description, paragraph 1:** "An automated live board of AI tools trending right now. Data
  refreshes every 15 minutes from the GitHub and Hugging Face public APIs; the narration is an
  AI voice. Nobody is watching chat during the stream; comments are read afterwards."
- **Stream settings** (Studio → Stream → Edit, names as seen in Studio, not re-verified here):
  enable auto-start and auto-stop, DVR on. Visibility: **Private for the first test**.

## 4. Acceptance criteria

- [ ] Unit tests: parsing and screening, pool order and cooldown, the narration gate, phrases and
  frame times, segment length, every ffmpeg argument list, URL validation and key redaction
- [ ] Live data fetched and the pool printed (real network)
- [ ] Segments rendered from live data, and **frames looked at**
- [ ] An end-to-end session streamed to a **local RTMP listener**, never YouTube, for ≥ 5 min:
  - the received file's timeline is continuous and lasts as long as the wall clock;
  - keyframes every 2 s, audio present;
  - frames sampled and read;
  - a standby insertion exercised;
  - CPU load recorded
- [ ] Full suite green, branch pushed
- [ ] Owner: the private test to YouTube (§6 step 4): **not something Claude can do**

## 5. Out of scope

- A vertical Shorts-feed live (needs its own canvas and a second key; revisit after the pilot).
- Creating broadcasts through the Live API (needs the OAuth token, which exists only in Actions
  secrets).
- Chat replies (zero human, and an unattended bot answering chat is its own policy question).
- Music.

## 6. Owner steps (in order)

1. In Studio, check live streaming is enabled (Create → Go live).
2. Studio → Stream: create a new stream key; copy the **RTMPS** Stream URL (lock icon) and the
   key into `E:/YOUTUBE/AI-PULSE/.env` as `YT_STREAM_URL=…` and `YT_STREAM_KEY=…`. `.env` is
   gitignored and must never be committed.
3. Optional, recommended: add `GEMINI_API_KEY=…` (the same free key as the Actions secret) to the
   same `.env`, for written narration instead of the template (row 13).
4. **Private test:** set the stream's visibility to Private, run
   `py -3 scripts/radar_live.py --minutes 10`, and watch it in Studio. Check stream health,
   picture, voice, and that it ends by itself.
5. Only after step 4 looks right: set visibility Public and install the schedule with
   `powershell -File scripts/radar_schedule.ps1 -Install`. Keep the laptop plugged in with the
   lid open, and set Windows Update "active hours" to cover 19:30-22:30.
6. Every 7 days, fill a row per session in the v3l scorecard log (Studio numbers) and run
   `py -3 scripts/live_scorecard.py`. Same CONTINUE / REVISE / STOP rules (v3l §7).
