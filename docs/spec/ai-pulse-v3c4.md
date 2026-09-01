# SPEC LOCK — AI Pulse v3-C.4: tool suitability screen precision

Status: built 2026-08-24 on `v3-phase-c`. 117/117 tests.

Why this exists: `docs/PHASES.md` carried an owner action — *"Read `gates.UNSUITABLE_TOOL`
and edit it. It will both miss things and over-block."* C.1 wrote it in one sitting against
one day's candidate list and fenced it as "deliberately narrow". This session measured what
it actually does: the gate was run over the live tool feeds, over 28 flagship AI tools, and
over 11 defensive tools, and the verdicts were read rather than assumed. It refuses tools
this channel exists to teach, and it missed the day's real provenance stripper on the title.

Every number below was produced by running the shipped gate. Evidence and the probe scripts:
the session scratchpad `EVIDENCE_unsuitable_tool.md`, `probe_*.py`, `verify_c4.py`.

## Locked decisions

| # | Decision | Value | Why |
|---|----------|-------|-----|
| 1 | Screen by surface | `gates.UNSUITABLE_NAME_ONLY = ("bypass", "crack", "torrent", "unfiltered")` matches the **title only**. `UNSUITABLE_TOOL` keeps matching title + source text | A term does not mean the same thing in a 90-char repo name as in 5,000 chars of prose. Measured over 28 flagship AI tools: `bypass` refused **unsloth** (its own Windows install line is `set-executionpolicy -scope process -executionpolicy bypass` — the exact text a cheat sheet copies), **ComfyUI** (`ctrl+b` = "bypass selected nodes") and **yt-dlp**; `crack` refused **transformers** ("a sassy, wise-cracking robot" in an example prompt). On the title the same words still catch `GPTBypass` and `cracked-ai: keygen for paid AI apps` |
| 2 | Defensive-reading exemption | `gates.UNSUITABLE_SUBJECT = ("nsfw", "deepfake", "deep fake", "face swap", "faceswap", "c2pa", "synthid", "jailbreak")` rejects **unless** some occurrence has a `_DEFENSIVE` word within `DETECTOR_WINDOW` and no `_EVASION` word in that same window | A tool that DETECTS the thing is the opposite of a tool that DOES it, and "how to detect this" is the utility lane's best content. Measured: 6 of 11 defensive tools were refused — the **official C2PA SDK and CLI** (the term was added to block provenance STRIPPERS and it blocked the STANDARD), two deepfake **detectors**, two **NSFW safety classifiers**. `jailbreak` joins them because decision 4 changes what is read: NVIDIA **NeMo-Guardrails** says "protect your LLM-powered chat application against common LLM vulnerabilities, such as jailbreaks" |
| 3 | `DETECTOR_WINDOW = 120` chars | The distance a defensive word may sit from the subject term | Measured across the six blocked defensive tools, the nearest defensive word was **5–69 chars** away (nsfw_model 5, Falconsai 11, dfdc 9, FaceForensics 69). In the live provenance stripper the nearest was **1,049**. 120 covers the observed 69 with ~1.7× margin and sits ~9× below the control — the same derivation shape as `TOOL_GROUNDING_MIN = 1200` |
| 4 | Ground on the raw README, screen on both | `ai_pipeline._gh_readme_url()` maps a github.com repo to `raw.githubusercontent.com/<owner>/<repo>/HEAD/README.md`. `script_tool` grounds the script in it and passes `grounding + page` to `tool_unsuitable` | `fetch_text` on a github.com page returns a mean **1,637 chars of chrome** first ("You signed in with another tab or window", the file listing) — measured aider 1,171 / OpenBot 1,544 / ollama 1,797 / ComfyUI 2,038 — so only ~3,360 chars of README were ever read, and that chrome was handed to the LLM as *"SOURCE EXCERPT (ground every claim in this)"* and to `gates.fact_check`. Same 28 tools, same list, two windows: **1/28 blocked on `page[:5000]` vs 4/28 on the full README** — the verdict depended on where a word fell in a document. HF got the raw card in C.1 #2; GitHub never did |
| 5 | Name normalisation | `_norm_terms` maps `-`, `_` and `/` to spaces before matching | Repo names spell phrases with punctuation. Measured: the live `ShadowAqueduct/watermark-remover: Purge multi-vendor AI watermarks` **PASSED the title screen** — the list held `watermark remov` (space) and `watermarks-remover` (plural). It reached `script_tool` and was refused only because its README quotes the *other* repo's name in ASCII art. One line closes the whole class |
| 6 | Names added, inside the locked scope | `abliterated`, `obliterated`, `nudify`, `deepnude`, `unwatermark`, `remove any watermark`, `remove all watermark`, `humanizer`, `voice clon`, `clone voice`, `watermarks remov`. Removed as standalone terms: none — `c2pa`/`synthid` moved to #2 | All measured as **passing** before this change. `OBLITERATUS/Qwen3.8-27B-OBLITERATED` ranked live on 2026-08-24, passed the title screen, and was caught only because its model card also said "uncensored". `abliterated` is the current naming convention for uncensored forks. `voice clone` is not a substring of "voice cloning" |

## Why GitHub keeps its page fallback when Hugging Face may not (C.1 #2)
The hub's fallback text was a Jinja `chat_template` that **reads as real** — grounding a whole
video in it produces confident fiction. GitHub's fallback is merely chrome-padded: it is the
text shipping today. So a repo whose readme is `.rst`, lowercase or absent still lands exactly
where it lands now, and nothing regresses.

## OUT OF SCOPE
- Widening the policy beyond circumvention / safety-defeat / piracy — still C.1's fence.
  `captcha solver`, `anti-detect browser`, `residential proxy` and `account generator` were
  measured as passing and deliberately **not** added; that is a policy call, not a defect.
- An LLM suitability judge. The screen stays a cheap deterministic keyword pass.
- `gates.fact_check` / `sensitive_topic_risk` / the confidence router — untouched.

## ACCEPTANCE CRITERIA (binary)
- [x] unsloth, ComfyUI, transformers, ollama and aider pass the screen on their real READMEs
- [x] The C2PA SDK, the C2PA CLI, two NSFW classifiers, the DFDC detector, NeMo-Guardrails
      and llm-guard all pass on their real source text
- [x] `ShadowAqueduct/watermark-remover` is refused **on its title**, not by luck
- [x] The original stripper, all five `Uncensored` forks and `OBLITERATED` stay refused
- [x] `facefusion` stays refused — decision 4 would have lost it, decision 4's screen keeps it
- [x] `Qwen3.8-27B`, the GGUF quant and MarkItDown stay teachable (C.1's criterion)
- [x] A healthy raw README is the only text the writer and the fact-checker see
- [x] A missing raw README still falls back to the page
- [x] 117/117 tests

## VERIFIED, NOT ASSUMED
`verify_c4.py` re-runs every probe against the shipped code and the live network: 8 abuse
cases refused, 5 former false positives passing, 7 defensive tools passing, 2 controls
(the stripper's README, facefusion) still refused. All checks passed.

## KNOWN REMAINING
- **`ondyari/FaceForensics` is still refused, and that is correct.** It was on the defensive
  list until its README was read: it ships "the two stage FaceShifter face swapping method …
  able to generate high fidelity identity preserving face swap results". A hands-on video
  would teach face-swap generation. Recorded because the first instinct was to force it green.
- **"Clone any voice from 3s" still passes.** `clone voice` is not a substring of "clone any
  voice". Left rather than adding a regex for one phrasing; the tool's own name almost always
  carries `voice clon`.
- **Decision 6 makes `voice clon` match READMEs**, so a legitimate open TTS project that
  describes itself as voice cloning (F5-TTS, RVC, XTTS) is now refused where it passed before.
  That is the existing policy applied without its spelling hole, not a new policy — but it is
  the most likely row the owner will want to loosen. Loosening it is one tuple edit.
- **`piracy` is still an identity term**, so an *anti*-piracy tool would be refused. Not
  measured against a real candidate; left alone.
- The screen now costs one extra HTTP GET per GitHub candidate (≤3 per day).
