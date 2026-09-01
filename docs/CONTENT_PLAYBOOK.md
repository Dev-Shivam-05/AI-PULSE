# AI Pulse — Content & Posting Playbook (v3)

All times in **IST**. The numbers here are the locked spec values
(`docs/spec/ai-pulse-v3.md`, `docs/spec/ai-pulse-v3c.md`); the learning loop (Phase D) will
tune them once ~2 weeks of v3 data exist. The one metric that decides whether v3 worked:
**average view duration ≥ 2:00** (v2 baseline: 0:38).

## What posts today (implemented)

The GitHub Actions cron fires at **5:53 PM IST** (retry 8:23 PM; the second firing is a no-op
once the day is done). One run = one long video scheduled for the 16:45 UTC slot, then Short #1
about **2 h after the long-form goes live** (≈00:15 IST) and Short #2 on the next
07 / 12 / 17 / 21 IST grid slot, with the ≥4 h minimum preserved
(`scheduling.shorts_slots_after_long`). The lane is chosen per day by
`ai_pipeline.decide_format`:

1. **Sunday** → weekly top-5 roundup.
2. A story scores **≥ 8/10** with the viral judge → news explainer (two voices).
3. A **tool signal** exists (GitHub trending / Hugging Face trending / Product Hunt) → **tool video**. This is the default lane.
4. Otherwise → evergreen explainer.

A FACTCHECK / ADVICE / POLICY block on an automatic run re-runs the day as a forced evergreen
— a blocked story never costs the day.

## The tool video (the product)

A tool video is a **transaction**, not a broadcast. The viewer must be able to DO the thing
within ten minutes of watching.

| Part | Rule |
|---|---|
| Length | 4:00–6:00 · 600–900 words (900 is a hard cap; the critique pass cuts repetition, never pads) |
| Scene 1 (hook) | The specific thing the viewer will be able to do + the most surprising concrete detail (stars, size, speed, price = free). No greetings |
| What it is | 1–2 scenes, attributed to who built it |
| Get it running | The exact real commands from the source — the one place verbatim is required |
| What to make | 3–5 concrete uses, most impressive first |
| One honest limitation | Who should NOT bother / what it can't do yet (the "filter" scene) |
| Final scene | The single next action + "the exact command is in the description" + ONE question + subscribe |
| `deliverable` | Required: `{kind: command|repo|steps, text, url}`. No deliverable → no tool video |
| Visuals | ≥70% original: a screen recording of the tool's real page (headless Chromium, dark, 1920×1080) cut sequentially across scenes, plus a terminal-style code card of the deliverable in the install scene and the final scene. Stock is only the failure fallback |
| Thumbnail | The real page screenshot + 2–4 words, Inter Black, white on #DC2626, red baseline |

## Description template (tool)

Links live **above the fold** — paragraph 1 is the hook + main keyword, then the transaction:

```
<hook paragraph with the main keyword>

🔧 Try it yourself:
<exact command or first step>
<source url>
📄 Free 1-page cheat sheet: https://dev-shivam-05.github.io/AI-PULSE/tools/<date>-<slug>.pdf

<promo_block, only if set in config.json>

<rest of the description>

Source: <url>

#AI #ArtificialIntelligence #TechNews

Chapters:
0:00 ...

▶ Watch next: <previous episode>
```

The cheat sheet is an A4 one-pager (what it is · get it running · make these 3 things · skip it
if · source + video links), written after upload to `docs/tools/` and committed with the run's
state, so the link is live once the state push lands (GitHub Pages, `main` `/docs`).
`promo_block` is the affiliate-ready slot: empty today; fill it when there is something to sell.

## News / evergreen / roundup (unchanged lanes)

News runs only when the judge scores ≥ 8/10 (was 7): hot topics + emotional charge, two-voice
Host + Analyst, source-grounded, stat-cards on numbers, on-screen source chips. Evergreen is
the search-traffic floor. Sunday is curation (added value = policy safety). These lanes still
use relevance-ranked Pexels clips.

## Shorts (2/day, cut from the long video)

`find_best_moments` picks the high-impact moments and labels each one with a hook angle
(`scripts/factverse_engine.py`); every Short ends with "full video → link", which is also
posted as a comment because Shorts hide description links:

- **cliffhanger** — a question or tension the clip does not answer ("Why the price drop backfires").
- **single_fact** — one sourced, surprising number ("54% already had an incident").

Format: vertical 9:16, hook text over the **first 3.5 s**, big live captions, CTA in the
**last 6 s**, no outro so the loop lands back on the hook. Spacing is hard-validated by
`scheduling.validate_distribution` (≥4 h between drops, ≤4 per day).

## SEO — titles, tags, description

**Honest priority order:** 1. thumbnail + title (CTR) · 2. hook + retention · 3. tags/description.

**Title formula:** `[what you can do] + [specific tool noun]`, < 60 chars, keyword near the front.
Tool: "Convert Any File to Markdown in One Command (Free, by Microsoft)".
News: "The AI Chip That Breaks Nvidia's Grip".

**Tag set (15–25, auto-generated):** exact-match tool/model names + broad (`ai tools`, `ai news`)
+ branded (`ai pulse`) + trending (`ai 2026`). The brand tags are appended automatically.

**Engagement boosters (automated):** an automatic question comment (posted, not pinned — the
Data API cannot pin), the watch-next chain link in
the description and comments, one topic playlist per lane ("Free AI Tools, Tested" for tool
videos).

> **Instagram and Facebook Reels are automated through the official Graph API** (v3-F.4,
> `factverse/reels.py`): the day's first Short is re-uploaded to both. That line used to read
> "Instagram stays manual" — it was about the `instagrapi` path, which logs in as a human from
> a datacenter IP and is ban-bait. A first-party, authenticated, rate-limited API is not the
> same act, and `docs/ENGINEERING_AUDIT.md` #6 asked for exactly this.
> The caption carries no YouTube link (it would be dead until 16:45 UTC, and an IG caption
> cannot hold a clickable link anyway) — put the channel link in the IG bio.
