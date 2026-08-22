# AI Pulse — project rules

Read `docs/HANDOFF.md` → `docs/PHASES.md` → the spec for the phase you are starting.
The specs in `docs/spec/` are contracts: never introduce a number, colour, threshold, or field
name that is not written there. If a decision is missing, add a row and get one word of approval.

## Environment facts (verified 2026-08-22 — do not re-derive)
- Run everything with system **`py -3`** (Python 3.11.9). It already has playwright + chromium,
  pygments and reportlab. Tests: `py -3 -m pytest tests/ -q`.
- There is **no `.venv` in the repo** despite README/setup.ps1 describing one, and the old
  "CI-mirror venv" lives in a session temp dir that can vanish. Do not depend on it.
- **`gh` CLI is not installed** on this machine (neither Bash nor PowerShell). Do not plan around
  it — ask the owner to click things in the GitHub UI, or use `curl` for public endpoints.
- **No API keys exist locally** — `GEMINI_API_KEY` / `PEXELS_API_KEY` / YouTube OAuth live only in
  Actions secrets. A supervised publish run is therefore a CI `workflow_dispatch`
  (`format` input: news | evergreen | roundup | tool), never a local command.
- Emoji in test/script output crashes the Windows console (`cp1252`). Prefix with
  `PYTHONIOENCODING=utf-8`, or write output to a file and read it.
- Git Bash heredocs choke on nested quotes/emoji — write Python and Markdown files with the
  Write tool, not `cat > file << 'EOF'`.

## Traps in this codebase
- **`_CARRY` (factverse/ai_pipeline.py)** — every LLM rewrite pass (critique, expand, tighten,
  advice-gate) re-validates the script and DROPS any top-level key not in `_CARRY`. A new
  script-level field that is not added there disappears silently and changes the published video.
  This has caused two real bugs (`deliverable`, `filter_segment`). Add the key AND a test.
- **`_validate_script` rebuilds scenes**, keeping only `scene_num / narration / visual_query /
  speaker`. Per-scene markers (e.g. `filter`) must be read BEFORE that rebuild.
- It also appends `\n\nSource: …` and `\n\n#AI …` to the description — any "first paragraph"
  logic must account for that manufactured blank line.
- **Visuals are fetched before audio exists** (`step3_download` at ~line 1027, durations at
  ~1057). Anything visual must be duration-agnostic; `step5_build` loops/cuts clips to fit.
- **A scene's time is split equally between its clips** — adding a clip to a scene shortens the
  others. Replace, don't stack.
- **Importing `ai_pipeline` pulls in the whole package plus `scripts/factverse_engine.py`.** CI's
  test job installs only pytest/requests/Pillow/edge-tts/faster-whisper/soundfile/numpy/pygments/
  reportlab, so heavy or optional deps (playwright, cv2, kokoro) must be imported INSIDE the
  function that uses them — the `faster_whisper` import in `captions.py:87` is the pattern.
- Every provider seam must **fail soft** (return `None`), never raise: the daily run is unattended
  and a raise costs the day. The 14:53 UTC cron is the only retry.
- Tests never run ffmpeg, the LLM, or the network. Build command args in a pure function and
  assert on the args; stub module attributes as the consumer sees them (`ap.llm.generate_json`).

## Definition of done here
A phase is done when the tests pass AND the artifact was produced and inspected — watch the
frames, read the PDF, print the assembled description. "The code runs" is not evidence.
Commit per working unit, push the branch, never push to main, and finish with `/handoff`.
