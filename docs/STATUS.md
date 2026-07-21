# AI Pulse — Project Status Report

*Updated: 2026-07-20 · Local `main @ c34aeac` (2 commits ahead of GitHub, awaiting push)*

## Overall Project Status
- **Live.** The channel launched 2026-07-19 and publishes autonomously via GitHub Actions (1 long video + 3 spaced Shorts daily), end-to-end: topic selection → script → render → thumbnail → upload → state sync → alerting.
- The full reliability layer (publish-once-per-day guard, conflict-proof state sync, retry cron) and the engagement engine (stat-cards, two-voice show, citations, chain design, playlists, scheduled Shorts) are implemented, tested (17/17), and committed locally — **they activate on the next `git push`**.

## Completed Features
- **Intelligence**: primary-source signal ranking (HN, arXiv, lab blogs, tech RSS), daily LLM viral judge (≥7/10 story overrides the calendar), URL + fuzzy + token-overlap topic dedup, failed-topic quarantine.
- **Three formats**: viral news explainer (two-voice Host + Analyst show), evergreen search explainer, Sunday top-5 roundup.
- **Script engine**: retention-engineered prompts (cold-open hook, open loops, pattern interrupts), critique pass (compression-guarded), length enforcement, title variants, thumbnail text.
- **Production**: Kokoro-82M neural voice (multi-voice), whisper word alignment driving captions *and* scene-visual sync *and* Shorts cut points, animated stat-card scenes, on-screen source citations, karaoke captions, cold-open branding, relevance-ranked Pexels clips (3/scene).
- **Packaging**: creator-style cutout thumbnails (YuNet face detection + rembg + face-zoom), auto-chapters, byte-safe metadata, tag strategy.
- **Distribution**: Shorts scheduled on the 07/12/17/21 IST grid via `publishAt` (≥4h spacing, hard-validated), watch-next chain links, auto playlist-by-format, engagement comments (pending re-auth).
- **Safety/ops**: render QA gate, plagiarism gate, honest exit codes, publish-once-per-day guard, union state merge, dual retry cron, failure→GitHub-issue alerts, cron keepalive, nightly analytics snapshots, 17 unit tests.

## In Progress
- **Comment chain** (Short→long link comments, episode-chain comments): code shipped, activates after a one-time OAuth re-consent (new `force-ssl` scope) + `YT_TOKEN_B64` secret update.
- **Learning loop**: data collection is live (`state/runs.jsonl` + `state/analytics.jsonl`); the decision layer that tunes topics/packaging from it is not yet built.

## Pending Features
- Native vertical (infographic-style) Short as a 4th daily drop — deferred for API-quota headroom; engine already supports vertical rendering.
- Fact-check pass (verify claims against a second source before publish).
- Instagram publishing via official Graph API (manual posting until the channel is established).
- Semantic (embedding-based) topic dedup; Hindi sister channel (pipeline ~95% reusable).

## Planned Future Enhancements
- Learning-loop decision layer (feed CTR/retention back into viral judge, titles, thumbnails).
- `publishAt` staggering for long-form; end-screen/next-video optimization.
- Revenue diversification (affiliate links, sponsor-slot readiness) once monetized.
- Oracle free-tier VM migration if render time or Actions limits ever bind.

## Architecture Overview
- **Monorepo Python pipeline**: `factverse/` (modern package: pipeline, intelligence, voice, captions, thumbnail, infographics, scheduling, state merge, analytics) reusing `scripts/factverse_engine.py` as a render/upload library (legacy content paths gated behind `legacy-run`).
- **Runtime**: GitHub Actions daily cron (primary) or the owner's laptop (`smart_scheduler.py`); identical code paths.
- **State**: flat JSON/JSONL files committed back to the repo each run (topic history, run ledger, production log, analytics) with union-merge semantics.
- **External services** (all free tier): Gemini (scripts/judging), Pexels (stock), YouTube Data + Analytics APIs (OAuth), GitHub (runtime + state + alerts). Local models: Kokoro TTS, faster-whisper, YuNet, U2Net.

## Current Workflow (daily)
- Cron fires 12:23 UTC (retry 14:53) → guard checks origin's ledger, exits if today already published → ranks signals, viral judge picks format → script + critique → clips + stat-cards → voice (dialogue or solo) → whisper sync → build → thumbnail → 3 Shorts → captions + citations → cold-open → QA + policy gates → upload long (public) + playlist + chain comments + Shorts (scheduled private, 4h grid) → burn topic → analytics snapshot → union-merge state push → keepalive; on failure, a GitHub issue emails the owner.

## Major Accomplishments
- Idea → audited → rebuilt → **live channel** with zero paid services.
- 87-finding engineering audit closed; every silent-failure mode from v1 eliminated.
- First-48h forensics diagnosed real platform behavior (late crons, state races, stale re-runs) and hardened against all three.
- Retention design validated by first data: two Shorts already loop >100% (104%, 138.6%).

## Strengths
- Fails loudly, never silently; every gate is honest (exit codes, statuses, alerts).
- Zero recurring cost; no server to maintain; state and history fully inspectable in git.
- Policy-defensive by design (originality gate, source grounding, added-value analysis, quality cadence).
- Every subsystem has a fallback chain (voice, thumbnails, captions, LLM models).

## Weaknesses
- Stock footage remains the visual ceiling for non-stat scenes.
- Kokoro voice is good but recognizably synthetic; no emotional range control.
- Thumbnail person selection is frame-luck (no gaze/emotion scoring yet).
- No automated fact-check: an LLM attribution slip can reach a hook overlay.

## Limitations
- One publish run/day by quota design (~6.8k of 10k YouTube API units used).
- English only; YouTube-only distribution (IG manual).
- Analytics API lags ~48h for new channels; learning loop needs weeks of data to matter.
- Laptop renders are slow and sleep-prone; CI is the reliable runtime.

## Known Issues
- A near-duplicate video pair (NVIDIA/HF) is live on the channel from a stale re-run — **owner should set one to Private**; the guard + similarity dedup prevent recurrence.
- Already-published videos carry the "AI" disclosure badge (new uploads won't).
- Comment features log "skipped" until the OAuth re-consent happens.
- GitHub cron still fires late (observed up to ~2h); mitigated by dual crons + guard, not eliminated.

## Technical Debt
- Legacy engine coupled via `sys.path` import; mystery-era prompt code still present (gated, unused).
- Print-based logging (no structured logs); no CI job running the test suite on push.
- CI dependencies unpinned (`>=` ranges); mixed LF/CRLF line endings produce git warnings.

## Risks
- **Platform policy** (#1): YPP review of an AI-heavy channel; mitigated by originality gates, curation value, disclosure-when-required.
- Free-tier changes: Gemini model/rate deprecations, Pexels limits, YouTube quota policy.
- OAuth token invalidation (recoverable in ~10 min via re-auth + secret update; alerts fire).
- Single-owner bus factor: all accounts/secrets belong to one person.

## Assumptions
- OAuth consent screen stays **Published** (Testing mode kills tokens in 7 days).
- Free tiers persist at current limits; repo stays public (unlimited Actions minutes).
- Owner glances at email/Actions ~monthly and can do a 10-minute fix when alerted.
- One video/day of grounded, transformed content stays within YouTube policy.

## Pros / Cons of the Current Implementation
- **Pros**: fully autonomous; ₹0 cost; self-healing state; data flywheel already recording; each subsystem independently replaceable (provider swaps are config flips).
- **Cons**: quality ceiling bound to free tools; LLM variability requires gates rather than guarantees; GitHub cron timing is best-effort; two-runtime split (laptop/CI) needs occasional model-file sync.

## Production Readiness
- **In production now.** Publishing daily with monitoring, alerting, idempotence, and quota discipline. The unpushed local commits complete the reliability + engagement layer.

## Remaining Tasks Before "Release Complete"
1. `git push origin main` (owner) — activates everything above.
2. One-time OAuth re-consent + update `YT_TOKEN_B64` (enables comment chains + analytics scope).
3. Set one of the duplicate NVIDIA/HF videos to Private.
4. Watch two consecutive cron cycles run green with the new save path.

## Recommended Next Priorities
1. Learning-loop decision layer (once ~2 weeks of analytics accumulate).
2. Fact-check pass for news scripts (kills the attribution-slip class).
3. Native vertical Short (quota-aware) + thumbnail gaze/emotion scoring.
4. CI test workflow + dependency pinning (repo hygiene).

## Blockers / Dependencies
- Owner-only: the push, the re-consent, channel-level actions (dupe cleanup, cosmetics).
- External: YouTube/Gemini/Pexels free-tier stability; GitHub cron behavior.

## Overall Health Assessment
- **Green.** The system is live, self-publishing, self-reporting, and self-protecting; content quality now has a real upgrade path (dialogue + infographics + citations) and a data flywheel to steer it. The dominant open risk is platform policy at monetization review — addressed by design, provable only by outcome. Momentum is strong; the next leverage is learning from real audience data rather than adding more machinery.
