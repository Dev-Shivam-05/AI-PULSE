# SPEC LOCK — AI Pulse v3-E: receipts + packaging precision (part 1)

Status: building 2026-08-24 on `v3-phase-c`. Source: the 12-rank adversarial gap audit vs
Hyperautomation Labs (workflow wf_708a427c, evidence in the session scratchpad) — ranks
1, 2, 3, 4 (grounding half), 7, 9, 10, 12 plus the voice seam. Rank 5 (`receipts.py` real
check-execution + terminal footage) is deliberately split to **v3-E.2**: the audit itself
scoped it as a full phase.

Owner approvals carried in: "go" (2026-08-24, twice), minimal-spend authorisation
("agar sach me boht jyada effect padega toh buy kijiye… jitna ho sake utna kam"),
model-change authorisation ("fark dikhai dena chaiye").

## Locked decisions

| # | Decision | Value | Why |
|---|----------|-------|-----|
| 1 | `verified_facts` | `ai_pipeline._verified_facts(url) -> dict`. GitHub repo: `stars`, `license` (spdx id), `pushed_at`, `open_issues` from `api.github.com/repos/{o}/{r}`; HF model: `downloads`, `likes` from `huggingface.co/api/models/{id}`. Uses `GH_TOKEN`/`GITHUB_TOKEN` env when present (publish.yml already passes it — C.1 #7). Fail-soft `{}`. Injected into the tool prompt as a `VERIFIED FACTS (fetched <ISO date> from the official API — use these numbers verbatim)` block; stored as `script["verified_facts"]`; **added to `_CARRY`** (the documented rewrite-drop trap) with a test | The prompt demands "stars, size, price" but the pipeline never hands the writer a single number — `sources.py` fetches stars and throws them away. Measured: last two scripts ≈ 0.1–0.25 digit-tokens/100 words, `plan_cards` returned `[]` |
| 2 | Command containment | `ai_pipeline.command_grounded(text, grounding) -> bool`: split the deliverable on `•` and newlines; every segment, whitespace-normalized, must be a substring of the whitespace-normalized grounding. On miss, `script_tool` substitutes the grounding's **first fenced code block**; if none exists the candidate is rejected exactly like the existing no-deliverable path | Only prompt text enforces the copy-paste contract today; one hallucinated flag on the code card + description + PDF kills the channel thesis. Pure function, no network |
| 3 | Packaging payoff | `gates.packaging_payoff(script) -> {ok, fixed, evidence}` pure: every digit token in `title`/`thumb_text` (commas stripped) must appear in the joined narration OR in `verified_facts` values. Deterministic fix, never a raise: unsupported tokens are stripped from `thumb_text` (empty → falls back to title, a fallback the thumbnail callers already have); a title left under 4 words after stripping becomes `How to use <tool> (free)` where `<tool>` is the repo/model short name. Applied in `run()` before render; result recorded in the ledger row as `packaging` | The 0821 run shipped title "Secret AI Cash Cow?", hook "you won't believe how much" — and zero dollar figures in 17 scenes. An ABSENT promised number is invisible to fact_check; unkept promises are the AVD killer |
| 4 | Limitation grounding | `ai_pipeline._top_issues(url) -> list[str]`: top 5 open issues by comments (`/repos/{o}/{r}/issues?sort=comments`), titles only, fail-soft `[]`. When non-empty, the tool prompt's limitation-scene instruction says: base it ONLY on these real issue titles or limits stated in the source excerpt | The "honest limitation" is currently invented from a vendor README that never admits limits — the least-grounded scene is the one viewers use to calibrate trust. Rides the same auth/fail-soft pattern as #1 |
| 5 | Thumb contract | The `thumb_text` line in `_output_contract` becomes: declarative, 2–4 words, no question mark, MUST contain one number from the source/verified facts or the word FREE | Both example strings in the old contract were hedge questions; HAL ships numeric declaratives. #3 guarantees the number is also spoken |
| 6 | Tool chapters | `ai_pipeline.tool_chapters(script, starts, shift) -> str` pure, LLM-free, tool lane only. Roles by scene: 0:00 `What <Tool> Does`; first scene ≥1 matching the existing install keyword tuple (from `inject_code_card`) → `Install <Tool>`; the scene after it → `3 Things to Build`; first scene matching skip/limit wording → `Who Should Skip It`; last scene → `The Exact Command`. Any missing role → return `""` and the existing `build_chapters` runs unchanged | The tool video's anatomy is fixed by its own prompt, so its chapters are derivable; the LLM version shipped casing bugs on two live descriptions. `<Tool>` = short name from `signal_title` (`owner/repo` → `repo`) |
| 7 | Per-lane pinned comment | Tool lane comment: the deliverable command + the cheat-sheet URL + one question; other lanes keep the existing text | The only API-writable engagement surface posts a news question under tool videos; the two things a tool viewer opens comments for are the command and the PDF |
| 8 | PDF meta line | `build_pdf` renders `★ <stars> · <license> · checked <date>` under the title when `verified_facts` is present; absent → line omitted, layout unchanged (still 1 page) | HAL's field guide stamps stars+license+date per item — the receipts identity on the deliverable itself |
| 9 | Writer model | `config.WRITER_MODEL = setting("writer_model", "gemini-2.5-flash")`; the four script-writer calls pass `model=fv.WRITER_MODEL`; gates/utility calls unchanged (flash-lite). `llm.generate()`'s existing fallback chain makes a quota miss degrade to lite, never fail | Owner authorised a model change with "fark dikhai dena chaiye" — the measure is digit-tokens/100 words and hook specificity in the ledger, comparable before/after |
| 10 | Tagline | `config.TAGLINE = setting("tagline", "AI YOU CAN USE")`; both branding sites render it (intro sting + banner, banner keeps `· NEW VIDEO EVERY DAY`); `ensure_assets` writes `assets/.brand` = `channel_name|tagline` and force-regenerates when the stamp mismatches — so the ToolDojo rename applies itself on the next run | Every branded surface still sells v2 news ("AI NEWS, DECODED") while the default lane is tools; 0.33% sub conversion. Audit rank 10 |
| 11 | ElevenLabs seam | New `factverse/tts_eleven.py`: `available()` = `ELEVENLABS_API_KEY` env AND flag `elevenlabs_tts` (default **false**); `synth(text)` posts to `/v1/text-to-speech/{voice_id}/with-timestamps`, converts character alignment → word timings, returns `(mp3, words)`. Settings: `elevenlabs_voice_id` (default "", = disabled), `elevenlabs_model` (default `eleven_turbo_v2_5`). `synthesize_voice` tries it FIRST when available; ANY failure falls through to the existing kokoro→edge chain. `requests` imported inside the function per the CI-import rule | Owner authorised ~$11 once (Creator first-month) for exactly the 10-video verdict window; flag default-off means merging this costs nothing until the key exists |
| 12 | Rename support | `config.json` `channel_name` + `youtube_channel_name` → "ToolDojo" ships with this phase (decision + verification recorded on the board 2026-08-24); playlist fallback string and `_output_contract`'s subscribe line already read `fv.CHANNEL_NAME`, so they follow automatically | The rename is decided; the code must not hard-code the old name anywhere the run regenerates |

## OUT OF SCOPE (queued as v3-E.2)
- `receipts.py` — safe CI check-execution (pip download timing/size, registry lookups) +
  "Checked by <channel> on <date>" narration beat + real terminal footage clip. Full phase.
- Newsletter, Pages site HTML (v3-F), any paid sponsorship machinery.
- Coercing story lanes onto `verified_facts` — tool lane only this phase.

## ACCEPTANCE CRITERIA (binary)
- [ ] A tool script's prompt contains real fetched stars/license, and `verified_facts`
      survives every rewrite pass (the `_CARRY` test)
- [ ] A deliverable not present in the README is replaced by the README's first fenced
      command, and a README with neither yields no tool script
- [ ] A title/thumb number the narration never speaks is stripped deterministically;
      a supported number passes untouched
- [ ] With issues available, the tool prompt names them as the only limitation basis
- [ ] Tool chapters are generated with zero LLM calls for a conforming script and label
      the real scene starts; a non-conforming script falls back unchanged
- [ ] The tool lane's auto-comment carries the exact command + PDF URL
- [ ] The PDF meta line renders with facts and disappears without them (still 1 page)
- [ ] Writer calls request `gemini-2.5-flash`; a quota miss still produces a script
- [ ] Brand assets regenerate when name/tagline changes (stamp mismatch), not otherwise
- [ ] `tts_eleven` OFF by default; with a stubbed API it returns word timings; any
      failure reaches kokoro unchanged
- [ ] Full suite green; the demo re-render shows fetched numbers on at least one surface
