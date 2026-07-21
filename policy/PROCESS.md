# AI Pulse — Production Process (originality dossier)

*This document describes how every video on the channel is made. It exists as
evidence of human editorial control and original insight — the qualifying
requirements of YouTube's monetization policy — and is attachable to any review
or appeal, together with the per-video records in `state/assets/`.*

## The process, per video

1. **Topic selection** — candidate stories are gathered from primary sources
   (lab blogs, arXiv, Hacker News, tech RSS), ranked, deduplicated against the
   channel's history, and filtered by hard policy rules (no advice-framed
   sensitive topics). Editorial policy for what qualifies is set by the operator.
2. **Script** — drafted against the bound source texts with strict accuracy
   rules, then rewritten by a critique pass. Every script must contain a named
   **synthesis claim** (an insight not present in any source) and pass a
   **replication test** (could a competitor produce the same video from the same
   sources?). Failures regenerate or abort — publishing nothing is preferred.
3. **Fact-check** — specific claims (numbers, dates, names, quotes,
   attributions) are extracted and verified against the sources. An unsupported
   headline/thumbnail claim kills the run.
4. **Human editorial audio** — the operator records weekly batches of cold opens
   and insight blocks in their own voice (`l2_store/`); one of each is injected
   into every long-form video. Usage is logged per video.
5. **Production** — narration (synthetic, disclosed in the channel description),
   licensed stock footage with a 30-day no-reuse ledger, per-video generated
   stat-card graphics, word-level caption alignment, on-screen source citations.
6. **Confidence routing** — every asset is scored (format, novelty, facts,
   packaging, policy proximity). Low-confidence assets are held for explicit
   human approval; mid-confidence assets open a review window before their
   scheduled publish time. Human overrides are logged.
7. **Publication** — fixed daily slot via scheduled publishing; chapters,
   source links, playlist assignment; two funnel Shorts on a spaced grid.
8. **Review** — the operator reviews performance weekly against pre-registered
   kill rules and replies to comments personally. Comment conversation is never
   automated.

## Records kept (continuously)

- Per-video: script drafts, claims with source bindings, synthesis claim,
  replication-test result, gate outcomes, confidence score and routing, human
  audio used (`state/assets/<id>/`).
- Channel-level: run ledger (`state/runs.jsonl`), analytics snapshots,
  stock-asset ledger, experiment log.
