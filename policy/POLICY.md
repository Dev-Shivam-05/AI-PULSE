# AI Pulse — Platform Policy Rules (binding)

*Governing policy: YouTube Channel Monetisation Policies, three-bucket
inauthentic-content clarification (16 July 2026). Review quarterly and any time
the visual pipeline changes.*

## 1. The AI-disclosure decision rule (per video, not per channel)

Check YouTube's "altered or synthetic content" box **if and only if** the video contains:
- a synthesized voice of a **real, identifiable person**, or
- AI-generated imagery a viewer could **mistake for real footage** of a real person/place/event, or
- a real event **altered** from what occurred, or
- a **realistic scene that never happened**.

Do **not** check it for: generic synthetic narration impersonating nobody, AI-assisted
scripts/titles, AI-generated thumbnails or stylized graphics, standard color correction.

**Structural assertion:** the render pipeline contains no generative-video source today.
The moment any scene asset is AI-generated realistic imagery, the disclosure flag must be
forced on for that video (`scripts/factverse_engine.py`, upload body — the flag is
currently hard-off with a comment referencing this file).

## 2. Bucket-3 rules (AI personas / sensitive topics)

- Narration voices are **narrators of the channel** — never named personas, never roles
  implying human expertise (no "Analyst", no credentials).
- **Reporting is allowed; advising is prohibited.** "NVIDIA reported X" ✓.
  "Here's what this means for your portfolio" ✗. Enforced by the advice-framing gate
  (`factverse/gates.py`) — hard fail.
- No advice framing, ever, on finance, health, legal, or political topics.

## 3. Bucket-1 rules (templated mass production)

- Every long-form video carries a **synthesis claim** (an insight not present in any
  source) and passes the **replication test** — enforced in the pipeline, recorded in
  `state/assets/` for the originality dossier.
- Human editorial audio (cold open + insight block) is injected from `l2_store/`;
  `require_insight_block` flips to hard-fail once weekly recording is established.
- No stock asset reuse within 30 days (`state/stock_ledger.json`, hard gate).
- Hook structures rotate; no repeat within the recent window.

## 4. Bucket-2 rules (misleading content)

- Every hook/thumbnail claim must be traceable to a cited source — fact-check gate,
  hard fail.
- Corrections: pinned comment within 24 hours of any confirmed error.

## 5. Standing prohibitions

- No purchased engagement of any kind.
- No synthesis of any real person's voice or likeness.
- No conversational comment automation (structural comments only — source lists, links).
- No content posted to communities that prohibit self-promotion.
- One long-form publish per day (pipeline-enforced); max 4 scheduled Shorts, ≥4h apart.
