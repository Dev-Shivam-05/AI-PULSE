# Spec — v3-H: the AI debate lane

Status: **decided 2026-09-26** under the owner's standing instruction for this session ("implement
everything, do not stop"). Every value below was chosen by Claude and is **revisable**: change a
row, not the code. Built on `v3-phase-h`, which is stacked on `v3-phase-b1`.

## Why this phase exists

The owner asked for 4–5 AIs (ChatGPT, DeepSeek, Grok, Perplexity, Claude, Gemini…) to debate one
topic, and for a video built from their arguments. The proposed route was browser automation of
consumer accounts. It is **not used**, for these reasons (DECISIONS, 2026-09-26):
- It can't run in the unattended CI job.
- It violates every one of those sites' terms, and the owner's main accounts would be at risk.
- It breaks on every redesign.

The same result is available through **official APIs that are free in September 2026**, with no
browser, no login and no ban risk:

| Seat | Lab | Route | Model id (Sep 2026 free lists) |
|---|---|---|---|
| Gemini 2.5 Flash | Google | the Gemini API key we already have | `gemini-2.5-flash` |
| GPT-OSS 120B | OpenAI (open-weight) | Groq free tier (`console.groq.com/docs/rate-limits`: 30 RPM, 1K RPD) | `openai/gpt-oss-120b` |
| Qwen 3.8 27B | Alibaba | Groq free tier | `qwen/qwen3.8-27b` |
| Nemotron 3 Super | NVIDIA | OpenRouter `:free` (50 req/day unfunded) | `nvidia/nemotron-3-super-120b-a12b:free` |
| Inkling | Thinking Machines | OpenRouter `:free` | `thinkingmachines/inkling:free` |

GitHub Models, the other free multi-model route, was **retired on 2026-07-30** (checked). ChatGPT,
Claude, Grok, DeepSeek and Perplexity are free only in their consumer apps; their APIs are paid.
The provider table already knows their endpoints, so adding any of them later is one secret plus
one panel row. A debate is also on-brand for ToolDojo: *we test the AI tools*, with the receipts.

## Decisions

| # | Decision | Value |
|---|----------|-------|
| 1 | When it runs | **Wednesdays** (weekday 2), when `"debate_format": true` and the panel has ≥ **3** usable seats (seat's key present). Precedence: forced → Sunday roundup → news at 10/10 → Wednesday debate → tool → evergreen. `format=debate` can be forced by dispatch/CLI. |
| 2 | Panel | `config.json` → `debate_panel` (the 5 seats above). A seat is usable when its provider is known and its key env is non-empty (`GEMINI_API_KEY` for `gemini`). Max **5** seats; fewer than **3** answering Round 1 → no debate that day. |
| 3 | Providers | OpenAI-compatible `chat/completions`: groq, openrouter, deepseek, xai, openai, perplexity, mistral (URL + key env name in `debate.PROVIDERS`). Key in the `Authorization: Bearer` header only, never in a URL. One call per seat per round, **60 s** timeout, **no retry**. Gemini goes through `llm.generate_exact` (one model, no silent fallback), so the name on screen is the model that answered. |
| 4 | Question | Gemini turns the best of the day's top **3** story candidates into ONE yes/no question about AI that informed people disagree on. No politics, elections, health, finance or legal advice. It is grounded in the story's fetched text (≥ `gates.FACTCHECK_MIN_CHARS`, like news). |
| 5 | Round 1 | Each seat: *"YES or NO as the first word, then your single strongest argument in at most 70 words, from the SOURCE; say so if you use general knowledge; no advice to viewers."* SOURCE is the first **2,500** chars of grounding. Temperature 0.7, 300 max tokens. |
| 6 | Round 2 | Each seat sees the others' Round-1 answers by name: *"rebut the strongest opposing argument in at most 50 words; end with `FINAL: YES` or `FINAL: NO`."* 250 max tokens. A seat that fails Round 2 keeps its Round-1 stance. |
| 7 | Parsing | `<think>…</think>` is stripped. The stance is the first word (YES/NO, else UNCLEAR); the final stance comes from `FINAL:`, else the Round-1 stance. The raw texts are kept whole in the transcript. |
| 8 | Script | Gemini writes the video from the transcript (`_output_contract("14-18", "55-80")`):<br>• hook = question + split + stakes;<br>• each seat named exactly as on the panel, quoting **≤ 25 words verbatim** in double quotes;<br>• the sharpest clash;<br>• any stance change;<br>• what the source actually says (our synthesis);<br>• final scoreboard + *"Which AI got it right? Tell us in the comments"* + subscribe.<br>Title pattern *"N AIs Debated: …"*; thumb_text carries the split (e.g. `3 SAID YES`). |
| 9 | Quote gate | Every double-quoted span of ≥ **4** words in the narration must appear verbatim in some seat's transcript (normalised: lowercase, curly→straight quotes, punctuation and whitespace collapsed). A fabricated quote rejects the script, and the day falls back to tool/evergreen. |
| 10 | Grounding for the gates | `script["grounding"]` = the story text + `DEBATE TRANSCRIPT` (every seat's name, R1, R2). So `gates.fact_check` can verify "Qwen argued…" against what Qwen actually said. |
| 11 | Visuals | 1280×720 **still** cards via PIL (duration-agnostic, like the code card):<br>• a **quote card** per seat (the model name + lab chip, YES/NO in yellow, and a verbatim prefix of its Round-1 answer measured to fit, with "…" if cut) leads the first scene that names the seat;<br>• a **scoreboard card** (every seat's final stance) leads scene 1 and the final scene.<br>Tokens are the stat card's: navy gradient `#0D1426`→`#182E5C`, `#FFD60A` numbers/stance, `#22D3EE` chip text, `#F4F7FF` text, `#96AACD` secondary; `branding._font`; radius 16. Text sizes: stance 0.16×H, quote 0.06×H (the stat label), chip 0.045×H. Fitted with `branding.fit_font`. |
| 12 | Description | A `🤖 The panel` block under the hook: each seat `name (lab)`, and *"each answered through its official API on <date>; quotes are trimmed, never reworded; the models' opinions are not advice."* Idempotent. |
| 13 | State & carry | `script["debate"]` (the transcript) is computed by the pipeline. It is in `_CARRY` and popped in `_validate_script` (the planted-key trap). The transcript is saved with the run's asset record. No new state file. |
| 14 | Kill switch & secrets | `"debate_format": true` in `config.json` and `config.example.json`. `publish.yml`'s publish step gets `GROQ_API_KEY`, `OPENROUTER_API_KEY` (and the optional paid ones: `DEEPSEEK_API_KEY`, `XAI_API_KEY`, `OPENAI_API_KEY`, `PERPLEXITY_API_KEY`, `MISTRAL_API_KEY`). An unset secret is "" and its seat is skipped. |
| 15 | Playlist & length | Playlist `"AI vs AI: The Debates"`; `MIN_WORDS["debate"] = 620`. |

## Owner steps (until then Wednesday runs the normal lane: 1 seat < 3)

1. **groq.com** → sign up (free, no card) → console → API Keys → Create. Then repo → Settings →
   Secrets and variables → Actions → New repository secret: `GROQ_API_KEY`.
2. **openrouter.ai** → sign up → Keys → Create. Add the secret `OPENROUTER_API_KEY`.
3. Optional (paid, cents per debate): `DEEPSEEK_API_KEY`, `XAI_API_KEY`, `OPENAI_API_KEY`,
   `PERPLEXITY_API_KEY`, `MISTRAL_API_KEY`, each with a matching panel row in `config.json`.

## Acceptance criteria

- [ ] Tests (no network, no LLM):
  - panel selection (keys, unknown provider, max 5, the gemini key);
  - `_chat`: bearer header, key never in the URL, `<think>` stripped, every failure returns
    `None` without raising, key never printed;
  - stance/final parsing;
  - verbatim trimming;
  - `run_debate` with stubbed seats (< 3 → None; Round 2 sees the other seats);
  - the quote gate (verbatim passes; fabricated, curly quotes and short spans handled);
  - the planted `debate` key popped and carried;
  - `decide_format` precedence;
  - the `build_script("debate")` fallback;
  - the description block being idempotent;
  - the workflow secrets and config flags.
- [ ] Quote and scoreboard cards rendered from a fixture transcript to `output/demo/debate/` and
      **read** (long quotes, 5 seats, a UNCLEAR stance).
- [ ] A live refusal check: a POST without a key to the Groq and OpenRouter endpoints returns an
      HTTP error that `_chat` handles as `None`. This proves the URLs without spending anything.
- [ ] Full suite green; `v3-phase-h` pushed.

## Out of scope

Browser automation of any consumer AI site. Paid seats by default. Debate Shorts beyond what v3-G.1
does for every Short. Thumbnails from the scoreboard card (v3-G.3).

## Risks

- **The free rosters move.** An OpenRouter `:free` model can disappear; that seat then errors
  and is skipped. The log names it: `↷ seat Inkling skipped: HTTP 404`. Replace the row in
  config. With fewer than 3 answers, the day runs the normal lane.
- **Free providers may log prompts.** The debate inputs are public news text, so this is
  acceptable.
- **Model opinions can be wrong.** They are always attributed; the fact-check reads the transcript
  and the source; the advice gate reads the whole narration.
- **The first real debate happens in CI.** No keys exist locally. Everything but the live answers
  is tested.
