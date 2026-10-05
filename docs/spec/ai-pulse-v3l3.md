# v3-L.3 — Radar Live quality pass

Status: **locked 2026-10-05** (owner: `go`). Builds on v3-L.2 (`docs/spec/ai-pulse-v3l2.md`);
every L.2 row not named here is unchanged.

## 1. Why

The first private YouTube session (2026-10-05, 15:53-16:05 UTC, 10 min) passed: health
Excellent, 21 segments, 16/16 narrations written by Gemini, 0 restarts, auto-stop worked.
It also showed:

- **3 silent standby boards in the first minute.** The stream connected as soon as ONE
  segment existed, so the second one was still being written. The shared `llm` chain on main
  starts with `gemini-2.5-flash-lite` / `2.5-flash` / `2.0-flash`, which answered slowly or
  not at all in the 2026-10-05 sessions before a model that works was reached.
- **Facts row overflow** ("text did not fit at the floor: ['facts']", 4 times in the
  2026-10-01 session; seen in a frame as the "text classification" chip cut off).
- No music bed and short narration (50-90 words).

## 2. Locked values

| # | Ambiguity | Locked value | Why |
|---|---|---|---|
| 1 | "fix the empty standby" | Radar narration asks **`gemini-3.5-flash-lite` first** (`llm.generate_json(model=…)`), then the existing `llm` chain. `llm._FALLBACK_MODELS` is not touched. The stream connects only once **3** segments are ready (pre-roll), or `READY_TIMEOUT` (300 s) has passed with at least 1 | The silences were the start-up gap, not the steady state. The shared chain belongs to the daily pipeline (`v3-gemini-fallback` branch) |
| 2 | "card clipping" | The facts row is **measured** in the page. While it overflows its box, the **last** fact chip is removed. The first fact chip (the headline number) is never removed. The rank and source chips (the top row) are fixed and never removed. `facts` is reported unfit only if one chip still overflows | CLAUDE.md: text burned on a frame is measured, never sized by character count |
| 3 | "very large script" | Narration asked at **100-160 words** (was 50-90). The gate accepts **70-200** (was 30-120). The model text cap goes from 900 to **1,400** characters (160 words of English is about 1,000). The number-grounding and hype gates are unchanged | About 45-70 s per tool. Longer than that is one static card under an AI voice |
| 4 | "music that looks good" | Bed volume **0.07** under the voice, the long-form's constant (`factverse_engine.py`). It plays in every segment: spotlight, board and standby. Tracks: `assets/music/radar/*.mp3`. One track per session, picked by day of the year from the sorted list, looped, and continued across segments (each segment seeks to the session's running music time). No file there = silent, as before | Matches the existing mix. The owner supplies license-clean tracks |
| 5 | Acceptance | see §4 | |

## 3. Out of scope (rows in `docs/PHASES.md`)

- **v3-L.4 vertical dual stream:** a 1080×1920 layout and a second stream key for the
  Shorts feed. Needs a CPU measurement first: two x264 encodes on this laptop.
- **v3-L.5 live link announcer:** `youtube.com/@tooldojo/live` to the Telegram group 60 s
  after the stream connects. Instagram and LinkedIn have no allowed API for this.
- **Declined:** driving the ChatGPT or Gemini consumer web apps from a browser to write
  scripts. Both providers' terms forbid automated use of the chat UI, the Google account is
  the channel's account, and an unattended stream cannot solve a captcha. The same
  evaluation was made for v3-H.

## 4. Acceptance criteria

- [ ] Unit tests: the narration word bounds, the model asked first, music args (with and
  without a track, volume 0.07, session seek), pre-roll order. Full suite green.
- [ ] A 10-min session to a **local** RTMP listener: frames read, no `facts` unfit line in
  the log, at most 1 standby, music audible in the received file when a track exists.
- [ ] A private YouTube session (`py -3 scripts/radar_live.py --minutes 10`): Studio health
  read, the session ends by itself.
- [ ] Branch pushed (`v3-phase-l3`), never main.

## 5. Owner steps

1. Studio → **Audio library** → filter **Attribution not required** → download calm/ambient
   tracks → put the `.mp3` files in `E:\YOUTUBE\AI-PULSE\assets\music\radar\`.
2. Upload `output/brand/banner_tooldojo_2560x1440.png` as the channel banner
   (Customization → Branding → Banner image). Generated 2026-10-05 by
   `branding.make_channel_banner`, which reads `channel_name` = ToolDojo.
3. Keep **Dual stream OFF** until v3-L.4: the auto-crop cuts the card in half.
