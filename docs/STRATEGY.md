# FactVerse — North-Star Strategy

## The real goal
Build FactVerse into a system that can run **near-autonomously for 1–2 years**, grow the
channel to **very high view counts**, and generate **meaningful, compounding income** — with
the owner touching it as little as humanly possible.

## Honest reframe (read this first)
**True "zero-touch for 2 years" is impossible** for any platform-dependent income system —
OAuth tokens expire, platform policies change, APIs deprecate. Anyone who promises otherwise
is selling something.

**What IS achievable:** a *resilient, self-healing, self-improving* machine that runs itself,
gets better over time, diversifies its income, and — critically — **alerts you the moment a
human is genuinely required** (a token died, a policy strike landed, an API changed) instead
of silently dying. The target is **"~10 minutes of attention per month,"** not zero.

**The trap we must avoid:** the obvious design — "generate a generic AI facts video from stock
+ TTS and post it 3×/day forever" — is, in 2025–2026, the **exact profile platforms
demonetize and terminate.** YouTube's "inauthentic / mass-produced content" policy and the
"reused content" rule, plus Instagram's anti-automation enforcement, are aimed precisely at
high-volume, low-originality AI content farms. **Volume-spam is a dead end. Originality and
value-density are the only path to durable income.** This single insight reshapes the build.

---

## The 6 pillars of longevity (failure mode → what we build)

| # | What kills a "leave-it-for-years" channel | Countermeasure we build |
|---|---|---|
| 1 | **Monetization/policy death** — AI-slop demonetized, account terminated, reused-content strikes | **Originality & policy-safety engine**: transformative scripts, format variety, value-dense visuals, a pre-publish policy/originality checker, quality-first (not volume-first) cadence |
| 2 | **Auth/API decay** — OAuth refresh token expires (7 days if app is in "testing" mode!), quotas, deprecations | **Resilience layer**: get the OAuth app *verified/published*, auto-refresh, quota-aware scheduling, provider failover, token-health watchdog |
| 3 | **Quality plateau** — static generator's CTR/retention decays, algorithm stops promoting | **Learning loop** (the heart of self-improvement): ingest YouTube/IG analytics, attribute performance to topic/title/thumbnail/format features, and feed winners back into topic + packaging selection |
| 4 | **Sameness / audience fatigue** — 200 near-identical videos, duplicate-detection risk | Format/series variety, semantic novelty checks vs history, trend-driven freshness, a themed content calendar |
| 5 | **Silent death** — one unhandled error / expired key / disk-full stops everything quietly | **Self-healing + alerting**: schema validation, retries, run database, heartbeats, health checks, and an **alert channel (email/Telegram)** that escalates to you only when needed |
| 6 | **Thin revenue** — AdSense alone on a faceless channel is low RPM | **Revenue automation**: auto affiliate links in descriptions, sponsor-slot readiness, funnel CTAs to a future product/membership; diversify beyond ad revenue |

---

## Locked strategic decisions
- **Quality & originality over raw volume.** Fewer, genuinely better, more original videos beat
  a high-volume farm — both for the algorithm and for staying monetizable. Cadence is tuned for
  sustainable quality, not maximum count.
- **Self-improving, not static.** The analytics→learning loop is a first-class pillar, not an
  afterthought. The system must measure itself and adapt.
- **Self-healing with human-in-the-loop-on-exception.** Build for near-zero touch, but always
  have an alert path. Never fail silently.
- **Safest official APIs**, OAuth app published (not "testing") so it survives unattended.
- **Free now, provider-agnostic** so paid quality upgrades are a config flip when revenue allows.

---

## Revised roadmap
1. **Foundation** — portable, secure, runnable. ✅ Done.
2. **Intelligence brain** — pick topics from real trend signals (Google Trends, Reddit, YouTube)
   and score virality. ◀ Next.
3. **Script + packaging quality** — engineered hooks, retention, self-critique; multi-variant
   titles/thumbnails scored for CTR; originality engineering.
4. **Reliability core** — schema validation, run database, no silent failures, success metrics.
5. **Learning loop** — analytics ingestion + performance attribution + strategy feedback.
6. **Self-healing + alerting** — watchdog, token health, heartbeats, email/Telegram alerts.
7. **Revenue automation** — affiliate/description automation, monetization readiness.
8. **Provider abstraction + 24/7 free deploy** — paid-swap interfaces; always-on hosting.

## Honest expectations
- No system guarantees virality or a specific income figure. Platforms control reach.
- Realistic shape: **slow compounding** for months, occasional breakout videos, income that
  *builds* over time rather than appearing overnight. The learning loop is what bends the curve up.
- "Top income, fully hands-off" is the *direction*; the *destination we can guarantee* is a
  resilient machine that maximizes every signal in your control and tells you when it needs you.

---

## Niche (locked 2026-06-28): "AI Intelligence" channel
Chosen over (a) daily automated breaking news — rejected as the riskiest path (accuracy
liability, copyright/reused-content demonetization, speed race, hardest to feel human) — and
(b) the original mystery/facts niche. AI wins because it aligns with the owner's genuine
interest and knowledge, which is a durable moat automation can't fake.

**Formats:** evergreen explainers + benchmark breakdowns; a curated **weekly AI roundup**
(satisfies the "news" goal safely); Shorts/Reels of single insights.

---

## Channel concept v2 (locked 2026-07-17, research-backed)

**Decision: keep the AI niche, pivot the format mix toward evergreen.** 2026 industry data:
AI/tech education is the fastest-growing high-RPM faceless category ($15–22 CPM, ~18× YoY);
the sustainable growth mix is ~60–70% evergreen search content + ~30% trend-reactive;
documentary-style narrative structure holds 40–60% mid-video retention vs the 23.7% platform
average; a hook in the first 5 seconds lifts retention ~23%; and fewer, better videos now
outrank volume (which also keeps us outside the July-2025 "inauthentic content" crackdown).

**The daily shape (decision 2026-07-17: primary goal = go viral; implemented in
`ai_pipeline.decide_format`):** a viral judge scores the day's top stories (shock, stakes
for ordinary people, broad appeal, emotional charge). A story ≥ 7/10 runs as **news**,
steered by the judge's angle — hot stories are the viral ceiling. Otherwise the day banks
an **evergreen explainer** — the watch-hours floor that still compounds toward YPP.
Sunday stays the **weekly roundup**. Daily: 3 Shorts cut from the long video.

**Virality mechanics (implemented):** long-form cold-opens on the hook scene with the brand
sting inserted after it (a logo before the hook kills retention); Shorts are ≤35s, start on
content frame one (no bumpers), snap to real narration boundaries, and end without an outro
so the loop lands back on the hook; visuals cut every ~5–7s (3 clips/scene); thumbnails carry
a 2–4-word curiosity gap, not the title.

**Thumbnail strategy (decision 2026-07-17: person-first).** Analysis of what wins on
YouTube's home feed: virtually every high-CTR thumbnail features a PERSON with visible
emotion; text-only cards lose. Faceless channel ⇒ we mine the video's own stock footage:
`factverse/thumbnail.py` extracts ~36 candidate frames from the run's downloaded clips, runs
face detection (OpenCV, free), scores frames (face size/position, sharpness, lighting,
colorfulness), then composes: person on the right third · huge 2-line white+yellow curiosity
text on the left over a legibility gradient · aggressive-but-clean grade · brand chip + red
baseline. Because the frame comes from the video's own clips, the person is always
content-relevant. Fallbacks: best colorful frame → engine text design. Visual relevance also
improved upstream: Pexels results are ranked by query↔slug overlap instead of taken at random.

**Monetization path (honest math):** the plan is the long-form lane — Tier 1 at 500 subs +
3,000 watch-hours, full YPP at 1,000 subs + 4,000 h. The Shorts-only lane (10M views/90 days)
is a lottery, not a plan; Shorts RPM is pennies anyway. Evergreen explainers are the only
format where watch hours *accumulate* instead of decaying with the news cycle. Industry
average to monetization is ~15 months; a focused single-niche channel with strong packaging
can realistically compress that to 6–9 — no guarantees.

**Voice (quality ask, solved free):** Kokoro-82M ONNX (Apache-2.0) is the default voice —
the best fully-free neural TTS that runs near-real-time on CPU, including CI. edge-tts is the
automatic fallback. The XTTS voice clone stays LOCAL-ONLY: Coqui's CPML license is
non-commercial, so it must never ship on monetized uploads (the #1 paid upgrade later:
ElevenLabs or a commercially-licensed clone).

**Sources (primary = accurate + low-copyright):** AI lab blogs (OpenAI/Anthropic/DeepMind/
Meta/HF), arXiv (cs.AI/CL/LG), Hacker News, ML subreddits (r/MachineLearning, r/LocalLLaMA,
r/artificial, r/singularity, r/OpenAI), GitHub trending, Google Trends.

**Human-feel levers:** consistent host persona + signature intro/outro; on-screen source
citations (credibility AND originality); original screen recordings + generated charts (not
stock); best voice we can afford (the #1 paid upgrade priority); an editorial point of view.

