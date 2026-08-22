# AI Pulse — autonomous "AI you can use today" video engine

Turns trending AI tools and real AI-news signals into retention-engineered YouTube videos
(long-form + Shorts) and publishes them daily, unattended, for **₹0** — GitHub Actions is
the runtime, every model and API is free-tier.

```
signals (GitHub trending · Hugging Face trending · Product Hunt · HN · arXiv · lab blogs · RSS)
  → intelligence/signal_engine.py   rank signals (pure python, deterministic; kind=tool|news)
  → ai_pipeline.py                  decide the lane, write + critique the script (≤900 words),
                                    require a deliverable for tool videos
  → screencap.py                    TOOL videos: screen-record the tool's real page (headless
                                    Chromium 1920×1080, dark) + Pygments code card of the command
    Pexels clips                    news / evergreen only
  → Kokoro voice · whisper word-timing · ffmpeg build · karaoke captions
  → thumbnail (tool: real page screenshot + 2–4 words) · Shorts · branded cold-open
  → originality / advice / fact gates → YouTube upload (scheduled slot)
  → deliverable.py                  1-page cheat-sheet PDF → docs/tools/ → GitHub Pages
  → state committed back to the repo · failures open a GitHub issue
```

## The content model (v3: utility first)

The 90-day v2 data said it plainly: 0:38 average view duration on "about AI" essays. v3 makes
videos about AI things the viewer can **use today** — every tool video is a transaction: the
viewer leaves with a command, a repo link and a free cheat sheet. Full contract:
[docs/spec/ai-pulse-v3.md](docs/spec/ai-pulse-v3.md) · [docs/spec/ai-pulse-v3c.md](docs/spec/ai-pulse-v3c.md).

| Condition | Lane | What the viewer gets |
|---|---|---|
| A tool signal exists (default) | **Tool video** — hands-on, 4:00–6:00, screen-recorded | A `deliverable` (command / repo / steps) spoken in the last scene, printed at the top of the description, plus a 1-page PDF cheat sheet |
| A story scores ≥ 8/10 with the viral judge | News explainer (two-voice) | The hot take, source-grounded |
| No tool signal, nothing hot | Evergreen explainer | Search traffic that compounds |
| Sunday | Weekly top-5 roundup | Curated news, policy-safe |

Retention mechanics in every render: cold-open hook before the brand sting, ≤900-word scripts
(the critique pass CUTS repetition, never pads), karaoke captions force-aligned to the script's
spelling, a visual cut every ~5–7s, loopable Shorts, 2–4-word thumbnails.

Posting details: [docs/CONTENT_PLAYBOOK.md](docs/CONTENT_PLAYBOOK.md). Strategy and money
math: [docs/STRATEGY.md](docs/STRATEGY.md). Current truth: [docs/STATUS.md](docs/STATUS.md).

## Run it

```powershell
# one-time setup (Windows)
powershell -ExecutionPolicy Bypass -File setup.ps1        # ffmpeg, venv, deps, .env template
py -3 -m playwright install chromium                       # tool-video screen recording
.\.venv\Scripts\python scripts\factverse_engine.py auth    # one-time YouTube OAuth

# make a video
py -3 -m factverse.ai_pipeline                 # render only (safe)
py -3 -m factverse.ai_pipeline publish         # render + upload
py -3 -m factverse.ai_pipeline publish tool    # force a lane: news | evergreen | roundup | tool

# tests (pure logic; no network, no ffmpeg)
py -3 -m pytest tests/ -q

# always-on: .github/workflows/publish.yml (daily cron, see docs/GO_LIVE.md).
# Supervised run: Actions tab → "AI Pulse — Auto Publish" → Run workflow → format = tool
```

Exit code is honest: `0` only when a video was actually produced (and published, in
publish mode). Anything else is a real failure — in CI that means a red run plus an
auto-created GitHub issue. A gate block on an automatic run re-runs the day as evergreen
instead of publishing nothing.

## Layout

```
factverse/                the pipeline package
  ai_pipeline.py          orchestrator + lanes + safety gates (THE entry point)
  intelligence/           signal feeds (tools + news) + ranking brain
  screencap.py            v3-B: screen-recording visual provider + code cards (tool videos)
  deliverable.py          v3-C: cheat-sheet PDF + naming/URL helpers
  thumbnail.py            person-first thumbnails (news) · make_tool_thumb (tool)
  llm.py                  Gemini facade (retry, model fallback, key in header)
  tts_kokoro.py           Kokoro-82M voice (default; Apache; ~310MB models auto-download)
  captions.py             whisper word alignment + script force-align + ASS karaoke captions
  shorts.py / branding.py 9:16 Shorts, animated intro/outro
  voice.py                XTTS voice clone — LOCAL ONLY (CPML: non-commercial license)
scripts/
  factverse_engine.py     render/upload LIBRARY (ffmpeg build, YouTube API; `auth` lives here)
  smart_scheduler.py      laptop scheduler with missed-slot catch-up
docs/                     STATUS · STRATEGY · GO_LIVE · CONTENT_PLAYBOOK · spec/ · tools/ (PDFs)
assets/fonts/             Inter Black + JetBrains Mono (OFL) for thumbnails, code cards, PDFs
tests/                    pytest suite for the deterministic logic
```

## Configuration

- Secrets: `.env` (copy `.env.example`) locally; GitHub Secrets in CI
  (`GEMINI_API_KEY`, `PEXELS_API_KEY`, `YT_CLIENT_SECRET_B64`, `YT_TOKEN_B64`).
- Everything else: `config.json` (committed, no secrets). Any key can be overridden by an
  UPPER_CASE env var (e.g. `TOOL_FORMAT=0` turns the tool lane off for one run).
  - `tool_format` — the tool lane switch (true since v3-B).
  - `deliverable_base_url` — where cheat sheets are served; GitHub Pages from `main` `/docs`
    (**enable once:** Settings → Pages → Deploy from branch → `main` / `docs`).
  - `promo_block` — affiliate-ready description slot; empty = omitted, otherwise inserted
    verbatim under the cheat-sheet line.
  - Voice: `tts_provider` (`kokoro` | `edge` | `clone`), `kokoro_voice`; `shorts_per_day`.
- State the pipeline maintains: `used_topics.json`, `used_urls.json`,
  `state/failed_topics.json`, `state/runs.jsonl`, `output/production_log.json`, `docs/tools/*.pdf`.

## Engineering status

See [docs/STATUS.md](docs/STATUS.md) for the current truth and open owner actions, and
[docs/PHASES.md](docs/PHASES.md) for the phase board. The original 87-finding audit lives in
[docs/ENGINEERING_AUDIT.md](docs/ENGINEERING_AUDIT.md).
