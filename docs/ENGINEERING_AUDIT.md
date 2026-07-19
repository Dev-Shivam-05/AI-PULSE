# FactVerse / AI Pulse — Engineering Audit (2026-07-17)

A full engineering audit of the repository across seven review dimensions
(correctness, reliability, security, CI/deploy, architecture, platform-policy,
performance): 94 raw findings, **87 confirmed** after independent verification.
This document is the permanent record; the highest-value fixes were applied the
same day (see "What was fixed" below).

---

## 1. Verdict

**Before this audit: NOT production-ready for its stated goal** (1–2 years
near-unattended operation). The renderer was genuinely good; the *operations
around it* would have killed the channel silently. The three fatal patterns:

1. **Silent death by design.** Every failure path exited `0`, reports hard-coded
   `SUCCESS`, no alert channel existed. The owner's whole monitoring model
   ("a red run will be obvious") could never fire. Verified: 9/9 log entries said
   SUCCESS while 8/9 had no published URL.
2. **Armed off-brand traps.** The legacy mystery-content generator was still the
   default entry point of `factverse_engine.py`, `smart_scheduler.py` invoked it,
   and `upload_now.py` carried mystery metadata — any of these would have published
   AI-slop-profile content to the AI Pulse channel with `auto_upload_youtube: true`.
3. **Unattended-hostile auth.** An expired YouTube token made CI fall into an
   *interactive* OAuth flow on a headless runner — hanging every daily run to the
   90-minute timeout, forever, while showing no diagnosable error.

## 2. Architecture (as found)

```
signals: HN / arXiv / lab blogs / tech RSS
   └─ intelligence/sources.py → signal_engine.py (pure-python ranking)
        └─ ai_pipeline.py  (orchestrator; the only supported entry point)
             ├─ llm.py            Gemini facade (retry + model fallback)
             ├─ engine (scripts/factverse_engine.py)  ← legacy lib, reused for
             │    step3_download · step5_build · step7_thumb · step8_meta ·
             │    yt_upload · save_report · cleanup
             ├─ captions.py       whisper word-timing + ASS karaoke burn
             ├─ tts_kokoro.py     Kokoro-82M voice (new, default)
             ├─ voice.py          XTTS clone (LOCAL ONLY — CPML non-commercial)
             ├─ shorts.py         9:16 Shorts + bumpers
             └─ branding.py       animated intro/outro
runtimes: GitHub Actions daily cron (primary) · Windows laptop (smart_scheduler)
state:    used_topics.json · used_urls.json · state/ · output/production_log.json
```

**Strengths worth preserving** (confirmed by the audit):
- The intelligence brain: deterministic, testable, zero-cost ranking; defensive fetchers.
- The ffmpeg cwd-relative tricks for Windows path escaping (subtitles/drawtext) — hard-won.
- Whisper-aligned karaoke captions; shorts cut pre-caption; thumbnail pre-caption ordering.
- llm.py's model-fallback chain; ai_pipeline's topic failover.
- Free-tier discipline throughout; secrets in `.env` + GitHub Secrets; clean `.gitignore`.

## 3. Confirmed findings (87) — by theme

Severity counts: **3 critical, 23 high, 33 medium, 28 low.**

| Theme | Representative confirmed findings |
|---|---|
| Silent death | exit-0 on all failures; status always SUCCESS; no alerts; `git push \|\| echo` swallowed state loss; scheduler marks failed runs done; dead `logging_setup.py` |
| Off-brand traps | legacy engine = live mystery publisher; smart_scheduler ran it; upload_now mystery tags + mass re-publish with no dedup; 18 duplicate publishes of the same fallback topic in history |
| Auth/CI | interactive OAuth on headless CI; unbounded upload retry loop; state save skipped on failure; quota headroom 6,450/10,000 (a 2nd daily run breaks); cron auto-disable after 60 idle days; API-key prefixes printed into CI logs (masking is full-value only) |
| Correctness | Shorts `-ss` after `-i` → hook text never rendered, CTA burned across entire Short; caption `_ts` could emit invalid `0:00:60.00`; non-atomic video swaps could delete both copies; uniform scene timing drifted visuals from narration |
| Content quality | LLM under-delivered length (618-word scripts); no critique pass; thumbnail = full title over random frame; uniform-score feeds (arXiv/RSS) all ranked `src_norm=1.0` → "trending" degenerated to "newest RSS post"; title-substring dedup only |
| Policy (the #1 strategic risk) | no originality/QA gate before public upload; no synthetic-media disclosure; XTTS clone license is NON-commercial (CPML) yet one config flip from monetized use; ungrounded "power words" Shorts metadata; prompt-injection path from scraped pages to published scripts |
| Performance | long video x264-encoded 5× (Shorts 6×); Pexels fetched UHD renditions whole into RAM for a 720p pipeline; unbounded `Retry-After` sleep |
| Hygiene | README documented the retired architecture incl. the dangerous entry point; two used_topics writers (caps 200/300, cp1252/utf-8); config sprawl; zero tests |

## 4. What was fixed (2026-07-17, same change set)

**Silent death → loud death**
- `ai_pipeline` exits non-zero on every failure path; per-step failure statuses recorded.
- `save_report` writes honest statuses (`PUBLISHED` / `RENDER_ONLY` / `UPLOAD_FAILED`); log bounded to 400 entries.
- New `state/runs.jsonl` run ledger (ground truth for the future learning loop).
- CI: state save runs `if: always()` with pull-rebase+retry; push failure is a visible error.
- CI: failure → **GitHub issue** (→ email); weekly cron **keepalive** re-enable step.
- Windows console emoji can no longer kill a run (stdout reconfigured `errors=replace`).

**Traps defused**
- Legacy engine content generation now requires explicit `legacy-run` / `legacy-batch`; bare invocation prints a deprecation and exits 2. `auth` remains.
- `smart_scheduler` now runs `python -m factverse.ai_pipeline publish` (honest exit codes).
- `upload_now.py`: AI-branded metadata + skips anything already uploaded.
- `yt_upload_selenium.py` deleted (ToS-risky, hardcoded paths, interactive `input()`).

**Auth/CI**
- Headless runners never enter interactive OAuth — clear fail-fast message instead.
- Upload connection-retry loop bounded (12); `Retry-After` capped at 60s; 4xx no longer retried.
- Gemini key moved from URL query string to header; API-key prefix prints removed.

**Correctness**
- Shorts use input seeking (`-ss` before `-i`) — hook/CTA overlays now land where designed.
- Atomic `os.replace` swaps in caption/subtitle burns (can no longer lose both copies).
- Caption timestamp rollover fixed; bumper cache validated by ffprobe before reuse (and
  half-written bumpers deleted on encode failure); state files unified UTF-8/cap-300.
- Scene visuals now track narration: per-scene durations derived from whisper word timings.

**Content quality & policy**
- **Voice: Kokoro-82M** (Apache) is the default; edge-tts fallback; XTTS clone gated with an
  explicit non-commercial license warning. Verified locally: model download + short & long
  (multi-chunk) synthesis.
- Three-format week (evergreen ×4 / news ×2 / Sunday roundup) — see STRATEGY.md.
- Retention-engineered prompts (hook formula, open loops, pattern interrupts) + a critique
  pass (guarded against compression) + length enforcement (verified: 618 → 1,380 words).
- 3 title variants + 2–4-word `thumb_text` rendered huge on the thumbnail (yellow-on-dark).
- Pre-publish gates: render QA (duration/size/audio-stream via ffprobe) and a verbatim-overlap
  originality gate (8-word shingles vs source, >8% blocks publish).
- Uploads set `containsSyntheticMedia: true`, sanitize `<>`, byte-safe description truncation,
  category 28 (Science & Tech).
- Topics burn only AFTER success; repeated failures quarantine a topic (`state/failed_topics.json`).
- Ranking: uniform-score feeds neutralized (0.5), research kind down-weighted, general outlets
  keyword-gated, URL-level dedup added, polluted `used_topics.json` rebuilt (211 → 8 real entries).
- Pexels: smallest rendition ≥ 960px instead of UHD.

**Testing**
- `tests/test_pipeline_logic.py` — 9 tests over the pure logic (timing, ranking, dedup,
  validation, overlap gate, scene sync). All pass.

## 5. Remaining roadmap (priority order)

1. **First supervised CI run** (workflow_dispatch, watch it end-to-end) — the publish path has
   never succeeded in CI; the OAuth app must be Published (not Testing) or the token dies in 7 days.
2. **Analytics → learning loop** (strategy pillar #3, still absent): pull YouTube Analytics
   nightly, join with `state/runs.jsonl`, feed CTR/retention winners back into format/topic/title
   selection.
3. **Reduce re-encode chain** (5× → 2–3×): burn captions during the final mux; consider
   `-c copy` concat for bumpers with matched encodes.
4. **Visual originality upgrade** (policy moat): generated stat-cards/charts/text-slides for
   abstract scenes instead of stock; on-screen source citations.
5. **Fact-check pass** for news format (claim extraction → verify against a second source).
6. **Instagram via official Graph API** (current instagrapi path is ban-bait and disabled).
7. **Semantic dedup** (embeddings) to replace substring matching.
8. Pin CI dependency versions; consider a public repo (private repos cap free Actions at
   2,000 min/month — a hung run burns 90/day).

## 6. Production-readiness after fixes

Ready for a **supervised go-live**: run the workflow manually once, watch the video it
publishes, then let the cron take over. The system now fails loudly, refuses to publish
broken or plagiarized output, discloses synthetic media, and can be diagnosed from logs
(`logs/*_error.log`, `state/runs.jsonl`, GitHub issues). The honest expectation remains
"~10 minutes/month," not zero-touch: tokens, quotas, and policies still decay and the
alert channel exists precisely for those moments.
