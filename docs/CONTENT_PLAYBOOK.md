# AI Pulse — Content & Posting Playbook

All times in **IST**. These are research-based *starting points*; once the channel
has data, the learning loop will refine them automatically.

## What actually posts today (implemented)

The GitHub Actions cron runs **once daily at 6:30 PM IST** and publishes the long video
first, then its 3 Shorts back-to-back (each Short's description links to the long video).
The format is chosen **virality-first** each day: an LLM judge scores the top stories, a
≥7/10 story runs as news with the judge's viral angle, otherwise the day banks an evergreen
explainer; Sunday is the weekly roundup — see `factverse/ai_pipeline.py:decide_format`.

> Staggered posting (the table below) needs YouTube's `publishAt` scheduling — a good
> future upgrade; do NOT add more daily cron runs, one run already uses ~6.5k of the
> 10k YouTube API quota.

## Aspirational staggered schedule (future `publishAt` upgrade)

| Slot | Time (IST) | What | Why |
|---|---|---|---|
| 1 | **9:00 AM** | **Long video** (YouTube) | Live early so it accumulates all day + Shorts can link to it. |
| 2 | **12:30 PM** | **Short #1** (YouTube) | India lunch scroll; links to today's long video. |
| 3 | **5:30 PM** | **Short #2** (YouTube) | Global prime: India evening + US morning + Europe afternoon. |
| 4 | **9:00 PM** | **Short #3** (YouTube) | India night prime time. |

> Instagram Reels stay manual for now (auto-posting from datacenter IPs = ban risk).
> IG captions can't hold a clickable link — put the YouTube link in the **IG bio**.

## The 3 Shorts — concept (cut from the long video)
Each Short = a different *hook angle* into the same story, ending with "full video → link":

- **Short #1 — The Shock:** the single most surprising fact/number from the video. Hook: "This AI just did something nobody thought possible." Pure curiosity.
- **Short #2 — What It Means For You:** the practical "why you should care" angle. Hook: "Here's how this changes your job / your phone / your money."
- **Short #3 — The Cliffhanger:** a question or tension the full video answers. Hook: "But there's a catch nobody's talking about…"

Format for all: vertical 9:16, the first 1.5 s is the hook text, big live captions throughout, the CTA + link card in the last 3 s. (The engine already picks 3 distinct high-impact moments and adds hook + CTA overlays.)

## SEO — titles, tags, description (organic reach)

**Honest priority order (what actually drives views in 2026):**
1. **Thumbnail + title (CTR)** — ~80% of the battle. Curiosity gap + the key noun.
2. **Hook + retention** — first 3 seconds, then no dead air.
3. **Then** tags/description/SEO — a *minor* ranking signal, but still worth doing well.

**Title formula:** `[Curiosity trigger] + [specific AI noun]`, < 60 chars, keyword near the front.
- e.g. "GPT-5.6 Just Changed Everything (Here's How)", "The AI Chip That Breaks Nvidia's Grip".

**Description:** first 2 lines = hook + main keyword (YouTube weighs the first ~100 chars heavily), then a 2–3 sentence summary, then timestamps/chapters, then 3–5 hashtags, then "Subscribe to AI Pulse". Include `Source: <url>` for credibility.

**Tag set (15–25, auto-generated per video — example for a GPT-5.6 video):**
```
ai, artificial intelligence, ai news, ai news today, gpt 5.6, gpt 5, openai,
chatgpt, new ai model 2026, ai update, machine learning, llm, generative ai,
ai explained, ai breakthrough, future of ai, ai tools, tech news, deep learning,
openai gpt 5.6, ai 2026, ai technology
```
Mix = exact-match (gpt 5.6) + broad (ai news) + branded (ai pulse) + trending (ai 2026).

**Engagement boosters (per upload):** pinned comment asking a question, end screen → next video, a Community poll a few times a week. These lift session time, which the algorithm rewards.
