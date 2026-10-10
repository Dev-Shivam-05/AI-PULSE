# Spec — v3-G.3: packaging

Status: **approved 2026-10-10** (owner: "go" on the spec-lock table below). Built on
`v3-phase-g3` from `origin/main` @ 937c4b2. Every value below is from the approved table; a
change is a new row, not a code edit.

## Why

The channel's audience builds with and uses AI, but the packaging was written for fear.

- The viral judge (`ai_pipeline.viral_pick`) rewarded "genuine shock/surprise", "emotional
  charge (awe / fear / outrage / wonder)" and "stop scrolling" framing, and **punished "niche
  developer tooling"** — the tool lane's whole subject. Its angle was injected into the news
  prompt as "lean into this — it is why the story can go viral".
- The critique pass asked for "an irresistible curiosity gap" thumbnail, contradicting the
  v3-E #5 thumb contract (declarative, 2-4 words, no "?", one sourced number or FREE).
- `gates.packaging_payoff` strips an unsupported number and ships the leftover. **8 of 78
  published titles are broken leftovers** (ledger rows with `packaging: ["title"]`):

  | date | shipped | the model's own clean alternate (state/assets/…/script.json `titles`) |
  |---|---|---|
  | 09-01 | AI Creates Art: Your Job Safe? Faster | AI vs. Human Art: Who's Really Creating? |
  | 09-06 | Stable Diffusion: Million Images Trained | DALL-E: How AI Creates Anything |
  | 09-13 | AI Agents Gone Rogue: Scenarios | Rogue AI: What Happens Next? |
  | 09-16 | AI's Real Impact: Industries Transformed | *(lost: `titles` dropped by a rewrite pass)* |
  | 09-18 | Open vs Closed AI: Your Guide | AI Models: Open vs Closed Explained |
  | 09-24 | LLMs: How Billion Parameters Understand You | Beyond Buzzwords: LLM Language Decoding Explained |
  | 10-01 | ZCode: Get a Coding AI Running in Min (7,286 Stars) | *(lost: `titles` dropped by a rewrite pass)* |
  | 10-08 | LLM Inner Workings: How Trillion Parameters Learn | AI's Brain: Demystifying Large Language Models |

  The right column is what the new rule picks when re-run over the real stored scripts
  (real narration, title restored to `titles[0]`). `titles` was not in `_CARRY`, which is why
  two runs had no alternates left.
- `gates.hype_terms` guarded only the Shorts titles; "AI Image Generators: The 5 Billion Image
  Secret" shipped as a long-form.
- Impressions and CTR were never measured: they exist only in the YouTube **Reporting API**
  (report type `channel_reach_basic_a1`), not in the Analytics API queries `analytics.py` runs.

## Decisions (the approved table)

| # | Decision | Value |
|---|----------|-------|
| 1 | Title length / entity | ≤60 chars, entity in the first 30 — unchanged, not newly enforced. |
| 2 | Output contract | `_output_contract` adds: "the title says what the viewer can DO, USE, or what CHANGES for them — never how scared or angry to be". The tool lane additionally gets the formula `[what you can do] + [tool name]`. |
| 3 | Viral judge | Removed: "genuine shock/surprise", "emotional charge (awe / fear / outrage / wonder)", "stop scrolling", "Punish … niche developer tooling". Score high for a concrete change for people who build with or use AI (what they can now do, what breaks, what it costs), a verifiable primary source, and broad relevance across those users; punish version bumps with no usable change, papers with no usable artifact, and fear or outrage with nothing for the viewer to do (worded in the prompt as "stories whose only pull is how scared or angry to be", so the prompt itself never says "fear"/"outrage"). The angle label becomes "why a builder should care". `VIRAL_THRESHOLD` unchanged (10). |
| 4 | Critique pass | (1) hook = the concrete thing the viewer will be able to do or understand by the end, in the first 8 words; (4) title = entity early + what the viewer can do or what changes, no hype words; (5) thumb = the v3-E #5 contract (declarative, 2-4 words, no question mark, one number from the source/verified facts or the word FREE). No "curiosity gap" left. |
| 5 | `_RETENTION_RULES` | The scene-1 PROMISE must name what the viewer will be able to do, use or decide by the end. Lane-specific hooks unchanged. |
| 6 | `packaging_payoff` | When the title has an unsupported number, first take the first entry of `titles` whose number tokens are all supported and which has no `hype_terms`; only if none, today's behaviour (strip / tool template), byte-identical. `titles` is coerced to `list[str]` and added to `_CARRY`. The pop-in-`_validate_script` trap does **not** apply: `titles` is model-authored by contract, not a value `run()` computes. |
| 7 | Long-form hype screen | `gates.hype_terms` (unchanged list) runs on the long-form `title` before render; on a hit, the first clean alternate from `titles`; if none, keep it and log `✂️ Long-form title had hype (<terms>) — kept: no clean alternate`. |
| 8 | Fear terms | Recorded only, never blocking: ledger `title_terms` = hype terms + rogue, threat, threats, nightmare, fear, fears, worried, crisis, scary, existential, chaos, outrage (word boundary, case-insensitive). |
| 9 | Ledger fields | `record_run` gets `thumb_text` (str), `title_alt` (bool: a #6/#7 alternate was used), `title_terms` (list[str]) — all computed and coerced BEFORE `eng.yt_upload`. |
| 10 | CTR collection | In `analytics.collect`, own `try`, `googleapiclient` imported inside: `jobs.list`; no job with `reportTypeId == "channel_reach_basic_a1"` → `jobs.create` named `tooldojo-reach`; `jobs.reports.list`; download each report whose date is not already stored, capped at **35** per run. Fail soft: `↷ reach report: <reason>`, never touching the other reports. |
| 11 | Storage | No new state file. The same `analytics.jsonl` snapshot gets `reach_headers` and `reach_rows: [[date, video_id, impressions, ctr], …]`, filtered to `learn.ledger_ids`, CTR exactly as the CSV gives it. "Already stored" = a date that has reach rows in any earlier snapshot. |
| 12 | Scoreboard | Per format: `impr` and `CTR` = Σ(impr×ctr)/Σimpr, deduplicated by (date, video_id) keeping the newest snapshot. Display only. |
| 13 | Kill switches | `honest_titles` gates #6 and #7; new `"reach_report": true` gates #10-12. |
| 14 | Out of scope | Title/thumb A/B, the evergreen topic picker, `channel_reach_combined_a1`, `find_best_moments` fallback hooks. |

## Files

- `factverse/ai_pipeline.py` — `_validate_script` coerces `titles`; `_RETENTION_RULES` promise;
  `_output_contract(…, tool=False)`; `viral_pick` rubric; news angle label; `script_tool` passes
  `tool=True`; `_CARRY += "titles"`; `critique_pass` rubric; `run()` calls
  `gates.longform_title_screen` after `packaging_payoff` and computes the three ledger values
  there; `record_run` writes them.
- `factverse/gates.py` — `_number_support`, `title_options`, `clean_alternate`;
  `packaging_payoff` tries the alternate first and returns `title_alt`; `FEAR_TERMS`,
  `title_terms`, `longform_title_screen`.
- `factverse/analytics.py` — `REACH_*` constants, `_download_report` (the Reporting API's own
  sample recipe), `parse_reach_csv`, `collect_reach`; `collect(yta=None, ytr=None)`.
- `factverse/learn.py` — `reach_metrics`, `reach_by_format`, a `reach` block in the scoreboard.
- `config.json`, `config.example.json` — `"reach_report": true` after `honest_titles`.
- `tests/test_g3_packaging.py` — new module (25 tests).

## Verification

- `tests/test_g3_packaging.py`: prompt contents (viral, angle, critique, contract, retention);
  the 8 real leftovers take the clean alternate; with no alternate, only unclean ones, or the
  flag off, the result is byte-identical to what shipped; `titles` as string / None / dict / int /
  junk list never raises; `titles` survives `enforce_length` and `enforce_max_length`; the
  "5 Billion Image Secret" case through #6 and #7, and with the flag off; `title_terms` word
  boundaries; a stubbed `run(publish=False)` writes `thumb_text` / `title_alt` / `title_terms`,
  and source order puts them before `eng.yt_upload`; the reach collector with a client that
  raises on every call, a 2-row CSV (filtered), a second run downloading 0 stored reports, job
  creation, the 35 cap, the kill switch; the scoreboard's dedupe.
- Real-data run (read-only, over `state/`): see the table above for #6. `title_terms` over the
  78 published titles: **13 non-empty** (fears ×3, shocking, secret ×2, existential, rogue ×2,
  nightmare, threats, fear+worried, crisis). Fear framing the approved list does not name
  ("Hacks", "Danger", "Risks", "Worries", "Backlash", "Goes Dark") is not counted.
  The scoreboard over the real state files renders the new `reach` block with `0 / -` per format.

## Owner steps

1. **Enable the YouTube Reporting API** in the GCP project that owns the OAuth client
   (APIs & Services → Library → "YouTube Reporting API" → Enable). Without it the first CI run
   logs `↷ reach report: HttpError 403 … has not been used in project … or it is disabled`.
2. If the log instead says **403 insufficient scope / insufficientPermissions**: the token was
   minted before `yt-analytics.readonly` was requested. Re-mint it locally with `yt_auth`
   (`scripts/factverse_engine.py`), base64 the new `youtube_token.pickle` and update the
   `YT_TOKEN_B64` Actions secret.

## Post-merge live check

1. The first CI "Collect channel analytics" step shows either
   `↷ reach report: job created (…) — the first report arrives within 48 h` or a clear 403
   (then do the owner step it names).
2. Within 48 h, a snapshot in `state/analytics.jsonl` has non-empty `reach_rows`, and the
   scoreboard's `reach` block shows impressions.
3. **Record the CTR scale** (0-1 or 0-100) from the first real rows here — it is stored raw and
   the scoreboard prints it raw.

## Known limits

- A report day on which none of the ledger's videos had impressions stores no rows, so it is
  not "stored" and is downloaded again on later runs. Bounded: 35 per run, and the API only
  lists recent reports. Newest days are always downloaded first, so fresh data is never starved.
- The report download uses the Google client's own HTTP stack (per-read timeout, no wall clock),
  the same as every Analytics API call already in `analytics.py`. It runs in the analytics step
  (`continue-on-error: true`), after the publish.
- An alternate is only screened for hype and unsupported numbers; a fear-framed alternate
  ("Rogue AI: What Happens Next?") can still win. Fear terms are recorded, not blocked (#8).
