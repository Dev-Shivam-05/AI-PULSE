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
- **The suite takes ~2 minutes and will blow a 120 s tool timeout** — even a `-k` subset,
  because collection imports the whole package. Run it in the background and read the output
  file; do not shorten the run to fit a timeout.
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
- **Anything published under `docs/` must be HTML.** `docs/.nojekyll` is committed, so
  GitHub Pages serves the directory verbatim — markdown is served as raw text and no Jekyll
  plugin (readme-index, relative-links) is available. `factverse/site.py` renders the pages.
- **A DERIVED artifact should be regenerated after `state_merge`, not stashed.** The site's
  HTML is rebuilt from `state/tools_index.json` in CI; only the source of truth needs the
  both-halves treatment (stash list AND `state_merge.FILES` AND merge semantics). The cheat
  sheet PDFs are the exception — an LLM wrote them once and they cannot be reproduced.
- **A key run() computes itself must be popped inside `_validate_script`, not once in run().**
  `cheat_sheet` and `receipts` are both `_CARRY` keys the model can plant. Popping in run()
  only covers the FIRST validation: `critique_pass` / `enforce_length` / `enforce_max_length`
  each validate again afterwards, and `_carry_over` restores only a key it finds in the source
  — so a value planted in a later rewrite answer survives. `_validate_script` pops both, and
  `_carry_over` hands the legitimate value back a line later. A planted `cheat_sheet` reached
  the PUBLISHED description (`.../tools/` with no file name) and escaped `docs/tools` via
  `../../../`. **Any artifact name derived from model output goes through
  `deliverable.safe_name`** — note its first cut split on `/` only, the Windows-green/CI-red
  separator trap for the third time in this repo.
- **A URL from the model is not safe to put in an `href` just because it is escaped.**
  `html.escape` does nothing about a scheme: `deliverable.url` is written by a model grounded
  in a third-party README, and `javascript:` on our own Pages origin is script execution.
  `screencap.py` guards this field with `startswith("http")`; `site.safe_link` is the same
  guard. Any NEW consumer of a model-supplied URL needs it too.
- **A loop that writes artifacts must isolate each item.** One unreadable page file aborted
  `site.rebuild`'s loop, skipping the index and sitemap writes below it — the site froze at
  its last good state on every future run while `publish_page` still returned a URL and the
  ledger still said `tool_page=True`. Per-item `try/except: continue`; a whole-loop `try` is
  a silent freeze waiting to happen.
- Tests never run ffmpeg, the LLM, or the network. Build command args in a pure function and
  assert on the args; stub module attributes as the consumer sees them (`ap.llm.generate_json`).

- **The long-form is PRIVATE until `publishAt` fires.** `eng.yt_upload` schedules
  (`longform_slot_utc`, 16:45 UTC) while the run itself happens at ~12:23 UTC. Anything that
  ANNOUNCES the video — Telegram (`notify.py`), X, Reels — must run after that slot, off the
  ledger, not from `run()`'s post-upload zone; a link posted at upload time is dead for four
  and a half hours. `notify.pick_row` refuses a row whose `publish_at` is still in the future.
- **A secret in a URL leaks through the library's own exception messages.** `requests` quotes
  the full request URL inside `ConnectionError` ("Max retries exceeded with url:
  /bot<TOKEN>/sendMessage"), and Actions logs are public. Any seam that puts a token in a path
  must redact before printing — `notify._redact` is the pattern. Actions masks its own secrets;
  a local run and a fork do not.
- **Escape for the destination, not for Python.** `html.escape(quote=True)` emits the numeric
  reference `&#x27;` for an apostrophe; Telegram documents only `&`/`<`/`>` and never promises
  to decode numeric references, so every "OpenAI's …" title was at risk. And a hard size limit
  (4096 chars) is handled by shedding whole blocks, never by slicing — a cut mid-tag is its own
  API error.
- **A platform's character cap may not be measured in characters.** X's 280 limit counts
  WEIGHTED chars (twitter-text v3): every URL is 23 whatever its length, every emoji and
  CJK char is 2, everything else 1. `notify.weighted_len` is the count; `len()` would ship
  posts the API refuses with "Text is too long". Read the platform's counting rules before
  assuming a limit is a length.
- **Two surfaces announcing the same video need two idempotence lists.** `notified.json`
  (Telegram) and `notified_x.json` (X) are separate because ONE list would mark a video
  done for X the moment Telegram took it, and X would never post it. Each still needs the
  full both-halves treatment (`state_merge.FILES` AND every workflow's stash list) — the
  count of files that trap applies to now grows with every surface.
- **A fail-soft seam has to be fail-soft all the way to the top.** `_post_x` read its
  config flag and its secrets OUTSIDE its `try`, and `main()` has no handler of its own —
  a raise there fails the workflow the module exists to keep green. `_post_telegram` had
  the same shape. Both now open the `try` first; note the handler redacts with the token
  it captured rather than calling `_token()` again, because the read that raised must not
  be re-run inside the handler meant to survive it. The test that finds this stubs EVERY
  seam name to raise — a happy-path test never will.

- **A surface that re-uploads a FILE cannot live on the notify workflow.** `output/shorts/`
  is gitignored and dies with the runner, so the Short exists only inside publish.yml's job:
  `reels.py` runs as a step there, above the state-save. And the 16:45 publish-slot rule is
  about LINKS, not about content — a Reel carries no YouTube URL, so it may ship at 12:30 UTC
  while the long-form is still private. Before moving any future surface, ask which of the two
  it is.
- **A token in a query string is a token in a public log.** `requests` quotes the whole
  request URL inside its own exception text. Graph API POSTs send `access_token` as a form
  field and the GET sends `Authorization: Bearer` — verified live: a bad token in that header
  answers OAuthException **190** ("could not be decrypted"), no token at all answers **2500**,
  so the header is genuinely read and the URL stays clean.
- **A URL the SERVER hands back is still a URL you have to check.** Meta returns `upload_url`
  so clients need not hard-code a host, but that URL is where the Page token is about to be
  sent. `reels._upload_url` honours it only on `https://rupload.facebook.com/` (note
  `https://rupload.facebook.com.evil.test/` passes a naive `in` test and fails this one) and
  falls back to our constant otherwise — `site.safe_link` one layer down.
- **Every new surface repeats the same three files, and the count keeps growing.** A config
  kill switch, an entry in `state_merge.FILES`, and an entry in the writing workflow's stash
  list — now four times over (`notified.json`, `notified_x.json`, `notified_ig.json`,
  `notified_fb.json`). Never share one list between two surfaces: whichever posts first
  retires the video for the other, which then never posts it at all.

## Definition of done here
A phase is done when the tests pass AND the artifact was produced and inspected — watch the
frames, read the PDF, print the assembled description. "The code runs" is not evidence.
Commit per working unit, push the branch, never push to main, and finish with `/handoff`.
