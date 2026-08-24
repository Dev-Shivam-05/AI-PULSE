# HANDOFF — ToolDojo (was AI Pulse) — Phase v3-E part 1 + the strategy day — 2026-08-24

*One session, three layers. (1) v3-C.4 shipped in the morning (suitability screen measured
and fixed — see git history). (2) The strategy layer: the owner disclosed that ~94-98% of all
channel analytics to date were self-generated views; a 9-agent gap audit vs Hyperautomation
Labs produced 12 ranked actions; the channel rename was decided and verified (**ToolDojo**);
an 11-agent platform/name audit mapped the distribution rollout; a full demo tool video was
rendered locally and inspected. (3) **v3-E part 1 built**: the receipts + packaging layer,
12 locked decisions, then a 16-agent adversarial review of the diff found 11 real defects
which were all fixed. 129/129 tests. Branch `v3-phase-c` pushed (`dfa72f7`+docs), still
stacked on `v3-phase-b` — merge PR #23 first.*

## The strategy facts this session established (do not re-derive)
- **All analytics before 2026-08-24 are invalid.** Owner: only 2-6% of views were organic —
  the rest self-generated via different accounts/IPs. Told to stop permanently (fake-engagement
  policy = termination risk). Real baseline ≈ 45-130 views/28d — a NORMAL day-30 channel.
  v3-D learns only from post-2026-08-24 data. Board rows updated.
- **The rename is decided: ToolDojo** (@tooldojo free on YouTube/GitHub/X, clean SERP, no
  live domains; every proof/stack/tool dictionary compound was taken 4-6x over — verified by
  11 agents + calibrated curl). Owner must rename in Studio BEFORE the first tool dispatch;
  config + brand assets already follow (this phase).
- **Platform rollout order** (from the live API audit): 1. Meta Graph API for IG+FB Reels
  (never-expiring Page token, ~40 min owner setup), 2. Telegram bot (~5 min, carries the PDF
  natively), 3. Pinterest (start approval now, 2-4 wks). X free tier is DEAD (Feb 2026,
  pay-per-use only) — SKIP. TikTok unaudited = private-only — SKIP. **Never run the old
  instagrapi `ig_upload` from CI** — fresh Azure IPs trigger unanswerable challenges.
- **ElevenLabs math:** need ~200 min/mo; Starter $6=30min, Creator $22=100min. The one sane
  buy = Creator first-month ~$11 covering exactly the 10-video verdict window. Seam is built
  and inert (see below).
- **HAL reference artifacts** live in `hyperautomation Labs/` (their 3-page field-guide PDF).
  The demo artifacts live in `output/demo/` (video, thumb, PDFs, contact sheet).

## Done (v3-E part 1 — spec `docs/spec/ai-pulse-v3e.md`, 12 decisions + review addendum)
- **`_verified_facts`**: real stars/license/last-update per candidate from the official APIs
  into the prompt, `_CARRY`, the stat cards and the PDF. Live-verified: 179,325 · MIT.
- **Command containment**: a deliverable not verbatim in the source is replaced by the
  source's own first fenced block, else rejected. The review proved the repair was DEAD code
  (`fetch_text` collapsed newlines) and the test had faked the only passable shape —
  `fetch_text` now preserves newlines; proven live against the real Ollama README.
- **`gates.packaging_payoff`**: token-exact, suffix-aware ("180K" strips whole — the review
  reproduced residue "K STARS" burned on a thumbnail), support = narration+grounding+numeric
  facts, digitless thumb residue blanks, GPT-5.6-style names immune, tool template tool-only.
- **Limitation scene from the tool's own tracker** (top-commented open issues, PRs filtered).
  Live: "digest mismatch on download", "Slow first token on CPU" for ollama.
- **LLM-free tool chapters** (10s YouTube floor, falls back to the LLM path), **per-lane
  pinned comment** (command + PDF link), **PDF receipts line** (mutation-tested via a canvas
  spy after the review deleted the render block and the suite stayed green).
- **Brand follows config**: wordmark/tagline/banner/PDF header render from `channel_name`/
  `tagline`; `assets/.brand` stamp forces regen on mismatch; ToolDojo bumpers rendered,
  frame-inspected (TOOL gradient + DOJO white, "AI YOU CAN USE") and committed; brand files
  ride publish.yml's stash + git add (the tracked-file trap).
- **ElevenLabs seam** (`tts_eleven.py`): flag+key+voice-id gated, dialogue scripts skip it,
  punctuation-only words filtered, `ELEVENLABS_API_KEY` passed through publish.yml (unset =
  inert). **Writer model** → `gemini-2.5-flash` behind `writer_model` (fallback chain absorbs
  quota misses).
- **16-agent adversarial review of the diff**: 12 findings, 11 confirmed, all fixed, each
  pinned by a regression test. 1 refuted (recorded in the spec addendum).

## Files changed (v3-E part 1)
`factverse/gates.py` (+`packaging_payoff`, `_NUM_TOKEN`, `_num_core`), `factverse/ai_pipeline.py`
(+`_gh_repo`, `_gh_headers`, `_verified_facts`, `_top_issues`, `command_grounded`,
`_first_fenced`, `_squash`, `tool_chapters`, `pinned_comment`, `_tool_short_name`; `fetch_text`
newline-preserving; `_CARRY`+verified_facts; script_tool wiring; payoff in run(); eleven-first
voice), `factverse/tts_eleven.py` (NEW), `factverse/deliverable.py` (`meta_line` + render +
header), `factverse/branding.py` (`_wordmark_parts`, `_brand_stamp`, config tagline, measured
wordmark), `factverse/screencap.py` (`INSTALL_KW` hoisted), `factverse/config.py`
(`WRITER_MODEL`, `TAGLINE`), `config.json`/`config.example.json` (ToolDojo + new keys),
`.github/workflows/publish.yml` (eleven secret + brand stash/add), `assets/` (ToolDojo bumpers
+ `.brand`), `tests/` (+12 tests → 129), specs/DECISIONS/PHASES.

## Known broken / deliberately skipped
- **v3-E.2 queued**: `receipts.py` (safe CI check-execution + terminal footage) — split per
  the audit's own scoping. v3-F (Pages site + Telegram/Meta seams) queued behind it.
- **The story lanes don't use `verified_facts`** — tool lane only, by spec.
- **`stat_card_share` still counts the whole scene** (C.3 leftover, waiting on v3-D).
- **Owner actions outstanding** (board "Now" list): stop self-views (permanent), Studio
  rename to ToolDojo + @tooldojo, merge PR #23 then `v3-phase-c`, enable Pages, Telegram/Meta
  one-time setups, supervised `format=tool` dispatch, weekly L2 batch, promo_block affiliate.
- The pre-2026-08-24 ledger is analytically dead (self-views) but structurally fine.

## Next session starts here
- **v3-E.2 (`receipts.py`)** if building; otherwise the next real milestone is entirely on
  the owner's clicks (merge → rename → Pages → first tool dispatch). After the first live
  tool run, read its log against the board's step-5 checklist.
- First command: `/boot`
- Watch out for: **the payoff gate on the first live runs.** It mutates title/thumb
  deterministically; expect `✂️ Packaging promised numbers...` lines. One per run is the gate
  working; every run = the writer model is over-promising and the contract needs tightening,
  not the gate loosening. And keep the two session traps in mind: a keyword screen means
  different things on a name vs a document, and narrowing what the writer reads must never
  narrow what a gate reads.
