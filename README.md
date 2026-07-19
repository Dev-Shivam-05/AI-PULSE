# AI Pulse — autonomous AI-education video engine

Turns real AI-news signals into retention-engineered YouTube videos (long-form + 3 Shorts)
and publishes them daily, unattended, for **₹0** — GitHub Actions is the runtime, every
model and API is free-tier.

```
signals (HN · arXiv · lab blogs · tech RSS)
  → intelligence/signal_engine.py      rank stories (pure python, deterministic)
  → ai_pipeline.py                     pick weekday format, write + critique script
  → Pexels clips · Kokoro voice · whisper word-timing · ffmpeg build
  → karaoke captions · thumbnail · 3 vertical Shorts · branded intro/outro
  → QA + originality gates → YouTube upload (synthetic-media disclosed)
  → state committed back to the repo · failures open a GitHub issue
```

## The content model (viral-first)

Every day an LLM **viral judge** scores the top-ranked stories on shock, stakes for
ordinary people, and broad appeal:

| Condition | Format | Purpose |
|---|---|---|
| A story scores ≥ 7/10 | News explainer (~6–7 min), steered by the judge's viral angle | The viral ceiling — hot topics + emotional charge |
| Nothing is hot | Evergreen explainer (~8–9 min) | Search traffic that compounds — the watch-hours floor |
| Sunday | Weekly top-5 roundup | News appetite, served policy-safely (curation = added value) |

Virality mechanics baked into every render: cold-open (hook scene *before* the brand
sting), a visual cut every ~5–7s, karaoke captions, ≤35s loopable Shorts that start on
content frame one (no bumpers), and thumbnails built from a 2–4-word curiosity gap.

Full rationale and monetization math: [docs/STRATEGY.md](docs/STRATEGY.md).
Posting details: [docs/CONTENT_PLAYBOOK.md](docs/CONTENT_PLAYBOOK.md).

## Run it

```powershell
# one-time setup (Windows)
powershell -ExecutionPolicy Bypass -File setup.ps1     # ffmpeg, venv, deps, .env template
.\.venv\Scripts\python scripts\factverse_engine.py auth  # one-time YouTube OAuth

# make a video
.\.venv\Scripts\python -m factverse.ai_pipeline          # render only (safe)
.\.venv\Scripts\python -m factverse.ai_pipeline publish  # render + upload
.\.venv\Scripts\python -m factverse.ai_pipeline publish roundup  # force a format

# always-on (either one):
#   cloud  → .github/workflows/publish.yml (daily cron; see docs/GO_LIVE.md)
#   laptop → .\.venv\Scripts\python scripts\smart_scheduler.py
```

Exit code is honest: `0` only when a video was actually produced (and published, in
publish mode). Anything else is a real failure — in CI that means a red run plus an
auto-created GitHub issue.

## Layout

```
factverse/                the pipeline package
  ai_pipeline.py          orchestrator + formats + safety gates (THE entry point)
  intelligence/           signal feeds + ranking brain
  llm.py                  Gemini facade (retry, model fallback, key in header)
  tts_kokoro.py           Kokoro-82M voice (default; Apache; ~310MB models auto-download)
  captions.py             whisper word alignment + ASS karaoke captions
  shorts.py / branding.py 9:16 Shorts, animated intro/outro
  voice.py                XTTS voice clone — LOCAL ONLY (CPML: non-commercial license)
scripts/
  factverse_engine.py     legacy engine, used as a render/upload LIBRARY
                          (direct content generation is deprecated; `auth` still lives here)
  smart_scheduler.py      laptop scheduler with missed-slot catch-up
  upload_now.py           bulk-upload rendered-but-unpublished output
docs/                     STRATEGY · GO_LIVE · CONTENT_PLAYBOOK · ENGINEERING_AUDIT
tests/                    pytest suite for the deterministic logic
```

## Configuration

- Secrets: `.env` (copy `.env.example`) locally; GitHub Secrets in CI
  (`GEMINI_API_KEY`, `PEXELS_API_KEY`, `YT_CLIENT_SECRET_B64`, `YT_TOKEN_B64`).
- Everything else: `config.json` (committed, no secrets). Any key can be overridden by an
  UPPER_CASE env var. Voice: `tts_provider` (`kokoro` | `edge` | `clone`), `kokoro_voice`.
- State the pipeline maintains: `used_topics.json`, `used_urls.json`,
  `state/failed_topics.json`, `state/runs.jsonl`, `output/production_log.json`.

## Engineering status

See [docs/ENGINEERING_AUDIT.md](docs/ENGINEERING_AUDIT.md) — 87-finding audit
(2026-07-17), what was fixed, and the prioritized roadmap (next up: first supervised CI
run, then the analytics→learning loop).
