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
- **Nothing may raise between `eng.yt_upload` and `record_run` in `run()`.** Past that upload the
  video is live on YouTube; if no `PUBLISHED` row is written, `already_published_today()` answers
  False and the retry cron publishes a SECOND video into the same slot. Put new validation
  *before* the upload (see `normalize_shorts_meta`), or wrap it.
- **`_validate_script` mutates the LLM's dict IN PLACE, so a top-level key the model invents
  SURVIVES into the script.** Any key that run() computes itself (`receipts`) must be popped
  before the computing code runs, or a planted value impersonates the real one — and a planted
  non-dict read in the post-upload zone raises into the double-publish window.
- **requests' `timeout` is never a deadline.** It bounds the gap between socket reads; a
  slow-drip URL streams forever and holds the unattended run until the CI job kill. Every
  streamed download needs its own `time.monotonic` wall clock and a byte cap (`receipts.py`
  is the pattern).
- **Path strings burned into artifacts must split on BOTH separators** (`receipts._basename`).
  `pathlib .name` is platform-native: a backslash path keeps its full machine layout on the
  ubuntu CI runner — the test was green on Windows and red on CI. git's `Cloning into
  '<abs path>'` stderr is the same leak from the other direction.
- **Raw LLM output is never type-safe.** `_validate_script` had `setdefault("tags", [])`, which
  fills a missing key but does not coerce a wrong type — a comma-string answer raised and killed
  the run. Coerce every list/dict field you read from the model; `deliverable._as_list` is the
  pattern.
- The tool lane **teaches** its subject, so `gates.tool_unsuitable` rejects candidates rather than
  penalising them. It is the only gate in the repo that refuses a topic outright. It guards the
  tool lane ONLY — nothing stops another lane picking the same candidate up.
- **`signal_engine.rank()` returns ONE mixed list**, tool signals included (v3-A added the
  GitHub/HF/Product Hunt trending feeds for the tool lane). Anything that treats `ranked` as
  stories must go through `ai_pipeline.news_candidates()` first, or a repo becomes the news story.
- **A roundup's `source_url` is story 1's URL**, because that is what `_validate_script` is
  handed. Never read it as "the" source of a roundup: doing so stamped one outlet on the caption
  chip and every stat card. Use `source_chip()`; per-story data lives in `roundup_items`.
- **A clip is rendered before its duration is known — unless you move the call.** `step5_build`
  gives each clip in a scene `scene_dur/len(clips)`, so any GENERATED clip with an animation
  (the stat card) must be rendered to that exact share or it loops or gets cut mid-animation.
  `inject_cards` now runs after `scene_durations`; `inject_code_card` must stay after it,
  because `_lead_with` replaces a leading stat card rather than stacking a third clip.
- **Text burned on a frame must be MEASURED, never sized by character count.** Every surface got
  this wrong independently (Shorts hook, both thumbnail composers, the stat card) and every one
  of them shipped clipped or silently truncated text. `branding.fit_font` is the shared loop —
  and measure with the font that will actually be drawn (Shorts render with `short.ttf`, not
  `br._font`).
- **A tracked state file the run writes must be in BOTH `publish.yml`'s stash list AND
  `state_merge.FILES`.** `git checkout -B main origin/main` reverts anything that is in neither,
  silently, on every CI run. `state_merge` also needs merge semantics for its shape first — the
  fallback is a list union and raises on a dict, which under `bash -e` would lose ALL state.
- **A fail-soft seam must still SAY whether it worked.** `l2.splice` returned its input on both
  success and failure, so the caller burned a one-use clip and recorded it as injected on a
  failure. Fail soft means return `None`, not return something indistinguishable from success.
- **A keyword screen means different things on a name and in a document.** `UNSUITABLE_TOOL`
  was matched against both a 90-char repo title and 5,000 chars of README, so `bypass` refused
  unsloth's own PowerShell install line and ComfyUI's ctrl+b hotkey, while `c2pa`/`nsfw`/
  `deepfake` refused the C2PA SDK and two detectors — the tools that DEFEND against the subject.
  A term list needs a surface (`UNSUITABLE_NAME_ONLY`) and subject terms need a defensive
  exemption. Measure a policy list against real candidates before trusting it; every one of
  those was found by running the gate over live feeds, not by reading it.
- **Grounding and SCREENING are different jobs.** `script_tool` grounds the writer in the raw
  README (the rendered GitHub page is a mean 1,637 chars of chrome first) but passes README +
  page to `gates.tool_unsuitable`, because the page's topic tags are the only place a repo like
  `facefusion` declares itself. Narrowing what the writer reads must not narrow what the gate
  reads.
- Tests never run ffmpeg, the LLM, or the network. Build command args in a pure function and
  assert on the args; stub module attributes as the consumer sees them (`ap.llm.generate_json`).

## Definition of done here
A phase is done when the tests pass AND the artifact was produced and inspected — watch the
frames, read the PDF, print the assembled description. "The code runs" is not evidence.
Commit per working unit, push the branch, never push to main, and finish with `/handoff`.
