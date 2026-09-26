# Spec — v3-G.1: storyboard Shorts

Status: **locked** (15 decisions, approved with `go` on 2026-09-26). **Not built yet.**
Build **after v3-B.1**, on a branch stacked on it (`v3-phase-g`).
The code goes in a NEW `factverse/storyboard.py`, a NEW `assets/storyboard/storyboard.html`, and an
integration into `factverse/shorts.py`.

## Why this phase exists

The channel audit of 2026-09-26 (YouTube Studio, last 28 days, plus `state/`) found:

- **Reach is Shorts.** Of 3,920 views, about 9 in 10 were Shorts. The 11 long-forms in the
  newest 7-day snapshot got 44 views between them. Subscribers: 10 total, +3 in 28 days (0.08%).
- **Shorts are tested, then dropped.** The top 9 Shorts were 23–61% viewed (median 44%), with an
  8–21 s average view duration. The one Short that was rewatched (187% viewed) is the pattern
  that spreads.
- **The pictures cannot show what is said.** The only visual instruction per scene is
  `visual_query`, "2-4 SIMPLE words … a real, concrete scene a stock site actually has … NEVER use
  metaphors" (`factverse/ai_pipeline.py:392-400`). Pexels supplies 3 clips per ~18 s scene
  (`scripts/factverse_engine.py:176-241`), so the picture changes every ~6 s whatever is being
  said. A Short is a 405×720 centre crop of the 1280×720 long-form, scaled up 2.67× to 1080×1920
  (`factverse/shorts.py:265`): soft, often cropping the subject out, starting mid-thought.

The better channels build the picture from the sentence: the same names, nouns and numbers
appear on screen at the word they are spoken, one idea per screen, and motion points at the
thing being said. This phase does that for Shorts first, because Shorts are where the reach is
and their % viewed gives a verdict in ~10 days. A long-form readout at ~4 views per video would
take months.

**Worked example (one beat).**
> Narration: *"Type 'I'll be there in five' and your keyboard suggests 'minutes'. A language
> model does the same, one word at a time, for a whole essay."*
> Today: `visual_query: "person using smartphone"` gives a random stock clip.
> Storyboard: a `chat` beat. A message box types *I'll be there in five*, and a *minutes* chip
> appears on the word "minutes". Then a `steps` beat lights *word → next word → essay* in step
> with the sentence. Every on-screen word is in the narration, so it passes the grounding gate.

## Locked decisions

| # | Decision | Value |
|---|----------|-------|
| 1 | Scope | One of the 2 daily Shorts keeps the same moment, audio and captions, but its **picture is rendered from a storyboard**. The other Short stays on today's crop path as the **control**. |
| 2 | Which one | Even day-of-year (`date.timetuple().tm_yday`) → Short 1; odd → Short 2. |
| 3 | Storyboard | **One extra call** to the Gemini API we already use (`llm.generate_json`, free tier), given the Short's exact narration. It returns **3–8 beats** `{cue, template, slots}`. Prompt rule: *"Draw the narration's own example; never decorate; never add a fact."* |
| 4 | Templates | `statement` (≤6 words) · `number` (value + label ≤7 words) · `compare` (2 sides × ≤3 items of ≤5 words) · `steps` (3–5) · `chat` (user ≤12 words / AI ≤18 words) · `bars` (2–5) · `headline` (our real source domain + a ≤16-word line). |
| 5 | Grounding gate | Every number on screen must be spoken in that beat. Every text element must share **≥1 word of 4+ letters that is not a stop-word** with the beat's narration. A failing beat becomes a `statement` of its narration's first 6 words. |
| 6 | Timing | A beat starts on its cue word; each element appears on its own word. **Frame 1 is the hook, fully drawn.** The picture never goes **more than 2.5 s** without a change. |
| 7 | Canvas | Native **1080×1920, 30 fps**, x264 preset `medium`, **CRF 20**, `yuv420p`. Visual area **y 300–1150**; captions **y 1180–1400**; nothing below **y 1450** or right of **x 960** (the YouTube Shorts UI). |
| 8 | Design | Existing brand colours: background `#090D18`, text `#F4F7FF`, accents `#22D3EE` / `#3B82F6` / `#8B5CF6`, numbers `#FFD60A`. Fonts: **Inter Black** and **JetBrains Mono** from `assets/fonts`. **No emoji** (they rendered as empty boxes on CI before). |
| 9 | Motion | Enter **320 ms**, `cubic-bezier(0.16, 1, 0.3, 1)`, with a **28 px** rise and a fade. Highlight **240 ms**. Count-up **700 ms**. Bars **700 ms** with a **120 ms** stagger. Typing **32 chars/s**. |
| 10 | Text fit | Measured in the browser: shrink **4 px** at a time, minimum **44 px**. If it still does not fit, the beat becomes a `statement`. |
| 11 | Renderer | Headless Chromium stepped frame by frame, capturing only while something moves. **Playwright is imported inside the function.** Model text is set as **text, never HTML**. |
| 12 | Failure | Any storyboard or render failure → that Short uses today's crop path, and the log says `↻ storyboard short fell back: <reason>`. It never blocks the run. |
| 13 | Measurement | The PUBLISHED ledger row gains `shorts: [{"url", "engine"}]`, with `engine` being `storyboard` or `crop`. The scoreboard gets `short:storyboard` vs `short:crop`: views-weighted % viewed, counted from **2 days** after publishing. |
| 14 | Decision rule | After **10** daily pairs: storyboard wins ≥ **8** → build v3-G.2; ≤ **5** → stop and rethink; 6–7 → run 10 more pairs. |
| 15 | Kill switch | `"storyboard_shorts": true` in `config.json` **and** `config.example.json`. |

## Derived details — traced to existing code, no new decisions

Every value below comes from an approved row or from a constant already in the repo. A builder
who needs any other raw number must stop and add a spec row.

### Integration (factverse/shorts.py:217-318)

- `make_shorts(..., source_domain="")` gains one keyword argument. `run()` passes `src_domain`
  (already computed at `ai_pipeline.py:1584` by `source_chip`). An empty domain disables the
  `headline` template: a beat using it becomes a `statement`.
- **Engine index** = `0` if the day-of-year is even, else `1` (row 2). It applies only when
  `fv.flag("storyboard_shorts")` is on and that index exists among the day's moments.
- For the engine index:
  1. `sub` — the window's words, exactly as the captions compute them (`shorts.py:289`).
  2. `board = storyboard.plan(sub, source_domain)` → `dict | None`.
  3. `vis = storyboard.render(board, length, out)` → an mp4 path or `None`: 1080×1920, silent.
  4. **Mux:** `vis` for the picture, the audio slice `[start, start+length)` from
     `content_video`, and **the same three drawtext overlays as the control**. Those are the
     hook (first 3.5 s, `shorts.py:255-260`), the watermark (`:267`) and the CTA (`:268-269`).
     Only the picture differs between the arms. The caption pass (`:285-303`) is unchanged.
  5. The file is named `short{tag}_{idx+1}_sb_{ts}.mp4`. The `_sb_` marker is how `run()`
     labels the engine.
  6. Any `None` or exception → log `↻ storyboard short fell back: <reason>` and run the existing
     crop path for that index. `make_shorts` never raises because of the storyboard.
- **Frame 1 (row 6).** The hook overlay is visible from t = 0, as in the control. Beat 1 of the
  storyboard starts at 0.0 **fully revealed**, with no entrance animation, whatever its cue.

### Storyboard JSON (what the model returns; `storyboard.plan` validates it)

Every text element is `{"text": str, "cue": str}`. `cue` is a 1–3 word phrase copied from the
narration: where the element appears. Each beat is `{"cue": str, "template": name, "slots": {…}}`.

| Template | `slots` |
|---|---|
| `statement` | `{"line": el, "accent": str?}`, where `line` ≤ 6 words and `accent` is one word of `line` |
| `number` | `{"value": el, "label": el}`, where `value` is a number as spoken (e.g. `71%`) and `label` ≤ 7 words |
| `compare` | `{"left": [el…], "right": [el…]}`: 1–3 elements per side, each ≤ 5 words. **Element 1 of each side is rendered as that column's title.** |
| `steps` | `{"steps": [el…]}`: 3–5 elements |
| `chat` | `{"user": el, "ai": el}`, where `user` ≤ 12 words and `ai` ≤ 18 words |
| `bars` | `{"bars": [{"label": el, "value": str}…]}`: 2–5 bars. `value` must parse as a number; bar length is proportional to it. |
| `headline` | `{"line": el, "accent": str?}`, where `line` ≤ 16 words. Shown next to the source-domain chip **without quotation marks**, because it is our sentence, not the source's. |

**Validation** (hostile output never raises; coerce every field, following
`deliverable._as_list`):
- If the top level is not a dict with a list `beats`, return `None`.
- An unknown template, a slot of the wrong shape, or an element over its word limit makes that
  beat a `statement` (see the gate below).
- More than 8 beats → keep the first 8.
- Fewer than 3 usable beats → `None`.
- Control characters are stripped. Nothing from the model is ever used as a URL.

### Grounding gate (row 5)

- **A beat's narration** = the words whose start time lies in `[beat start, next beat start)`.
- **Numbers:** every `\d+(?:[.,]\d+)?` in an element (thousands commas removed) must occur among
  the beat narration's numbers.
- **Words:** tokens are lowercase alphanumeric runs. An element needs ≥ 1 token with ≥ 4
  letters, not in `STOP_WORDS`, that also occurs in the beat narration. This is an exact token
  match with no stemming; the prompt tells the model to copy words.
- `STOP_WORDS` = `about also been being could does done each even from have into just like make
  made more most much only over same some such than that them then there these they this those
  very what when where which while will with would your`.
- **Failure:** the beat becomes a `statement` whose line is the first 6 words of its narration,
  with no accent.
- **Exempt:** the hook overlay. It is the existing, fact-checked hook text, not part of the
  storyboard.
- **Log:** `🎨 Storyboard: k/n beats kept` (k = beats that passed as written).

### Timing (row 6)

- **Normalisation:** lowercase; strip everything except letters, digits and `%`.
- **Beat cues** match the first run of consecutive narration words equal to the cue, at or after
  the previous beat's matched index (monotonic). The beat start is that word's start time.
  - An unmatched beat cue drops the beat, and its time goes to the previous beat.
  - Beat 1 always starts at 0.0.
- **Element cues** are matched inside their beat's word range. The element appears at the matched
  word's start time.
  - An unmatched element appears with the previous element of its beat; the first element appears
    at the beat start.
  - When two bars resolve to the same time, the later one is offset by 120 ms (row 9's stagger).
- **2.5 s rule:** change events are beat starts and element reveals. For any gap longer than
  2.5 s (including the gap to the end of the Short), the most recently revealed element's
  highlight (240 ms) is replayed at the gap's midpoint. Repeat until no gap exceeds 2.5 s.
- **Beat changes are hard cuts** at the beat start. Elements then animate in on their cues.

### Design tokens (row 8, plus existing constants)

| Token | Value | Source |
|---|---|---|
| Visual area | x 120–960 (the mirror of the approved 960 limit), y 300–1150; content vertically centred | rows 7 |
| Background | `#090D18`, flat | `branding.BG` |
| Card surface | vertical gradient `#0D1426` → `#182E5C` | `infographics.NAVY_TOP` / `NAVY_BOT` (the stat card) |
| Text / secondary | `#F4F7FF` / `#96AACD` | `branding.WHITE` / `SUBT` |
| Highlight, active step, first bar series, left column title | `#22D3EE` | `branding.CYAN` |
| User chat bubble | `#3B82F6` | `branding.BLUE` |
| Right column title | `#8B5CF6` | `branding.VIOLET` |
| Numbers (number value, bar values) | `#FFD60A` | `infographics.YELLOW` |
| `#E0202A` | not used in G.1 | `branding.RED` |
| Card radius | 16 px | code / receipts card, `screencap.py:209` |
| Pill radius | height / 2 | `branding.py:332` |
| Block gap | 60 px | `shorts.HOOK_MARGIN` |
| Card padding | 28 px | tool thumbnail `pad_x`, `thumbnail.py:510` |
| `statement` line start size | 130 px | tool-thumbnail text, `thumbnail.py:510` |
| `number` value / label start size | 307 px (0.16 × 1920) / 67 px (0.035 × 1920) | the stat card's vertical proportions, `infographics.py:125-126` |
| Body text (compare, steps, bar labels, headline line) | 68 px | Shorts captions, `shorts.py:292` |
| Chat bubbles | 64 px | hook size, `shorts.HOOK_SIZES` |
| Chips (source domain) and bar values | 46 px | the CTA, `shorts.py:268` |
| Line height | size + 26 px | hook line spacing, `shorts.py:258` |
| Fonts | Inter Black for all text except chips and bar values, which use JetBrains Mono. Loaded with `@font-face` from `assets/fonts` by relative path; nothing is fetched from the network | row 8 |
| Count-up curve | `1 - (1 - t)^3` over 700 ms; the final frame is the exact spoken value string | `infographics.py:100-112` |

### Renderer (row 11)

- **One page:** `assets/storyboard/storyboard.html`, with inline CSS and JS. It exposes
  - `window.__load(board)`, which builds the DOM with `textContent` only and returns the list of
    beats whose text did not fit at 44 px;
  - `window.__timeline()`, which returns the animation intervals;
  - `window.__seek(t)`, which sets every element's style for time `t`, using row 9's curves and a
    cubic-bezier solver in the JS.

  The page contains no `innerHTML`, no `<script src>` and no network URLs.
- **Two-pass fit:** load, and replace the unfit beats with `statement` (row 10). If the statement
  itself does not fit either, that beat keeps the last fitting size, 44 px.
- **Frames:** one at t = 0, plus every 1/30 s inside each animation interval, plus one at each
  interval's end. Each is a PNG screenshot of a 1080×1920 viewport. Holds are not captured.
- **Encode:** the ffmpeg concat demuxer with per-image `duration` lines (the last image holds to
  the Short's length), then `-r 30 -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -an`.
  The concat list and the ffmpeg arguments are built by pure functions (tests assert on them;
  tests never run ffmpeg or Chromium).
- **Log:** the render time, e.g. `🎨 Storyboard short rendered in 38.2s`.

### Measurement (rows 13–14; `factverse/learn.py`)

- **Building `shorts`:** the ledger field is built inside the existing upload loop
  (`ai_pipeline.py:1762-1772`) from values already in hand. `engine` is `"storyboard"` if
  `"_sb_" in path` (a substring test, not a path split — see the separator trap in `CLAUDE.md`),
  else `"crop"`. This code is in the post-upload zone, so it must not raise.
- **Collecting the ids:** `learn.ledger_ids` adds the Shorts ids from the `shorts` fields, so the
  v3-D analytics query (which already asks for `averageViewPercentage`) fetches them. The most
  recent 200 ids in total are kept. `latest_metrics` also keeps `averageViewPercentage`.
- **Grouping:** Shorts never enter the `format:` / `hook:` arms. The new arms are
  `short:storyboard` and `short:crop`: views-weighted average % viewed over the Shorts that are
  ≥ 2 days past their row's `publish_at` date.
- **Pairs:** a pair is one ledger row with exactly one mature Short of each engine, both with
  views > 0. The storyboard Short wins if its % viewed is higher.
- **Scoreboard:** it prints `A/B pairs: N · storyboard wins: W` and, once N ≥ 10, the row 14
  verdict.

### The prompt (skeleton; `storyboard.plan`)

> You are storyboarding a {length:.0f}-second vertical explainer. Draw the narration's own
> example; never decorate; never add a fact. Every word on screen must be copied from the
> narration below, and every number exactly as written there. Choose 3-8 beats. Each beat
> starts where its cue phrase (1-3 words copied from the narration) is spoken, and each element
> appears on its own cue. Templates: {the table above, with limits}. {"headline" only if a source
> domain was given}. Return ONLY JSON {"beats":[…]}.
> NARRATION: {the exact words of the window}

## Files (8)

- `factverse/storyboard.py` (NEW): `plan`, validation, the gate, timing, frame schedule,
  ffmpeg/concat builders, `render`.
- `assets/storyboard/storyboard.html` (NEW): the 7 templates and the `__load` / `__timeline` /
  `__seek` API.
- `factverse/shorts.py`: the engine index, the storyboard branch, the mux, the file name.
- `factverse/ai_pipeline.py`: pass `source_domain`, and the ledger `shorts` field.
- `factverse/learn.py`: the Shorts ids, `averageViewPercentage`, the Shorts arms, the pair tally.
- `config.json`, `config.example.json`: `"storyboard_shorts": true`.
- `tests/test_pipeline_logic.py`.

Docs: this spec, `docs/PHASES.md`, `docs/DECISIONS.md`, `docs/HANDOFF.md`, `docs/spec/GLOSSARY.md`.
Demo artifacts: `output/demo/storyboard/`.

## Acceptance criteria

- [ ] **All 7 templates** are rendered from fixture boards at 3 moments each (entering,
      mid-reveal, holding), saved to `output/demo/storyboard/`, and **each screenshot has been
      read**.
- [ ] **One full sample Short, rendered locally:**
      - fixture narration (the keyboard example above);
      - a real `edge-tts` voice (`en-US-GuyNeural`, `config.json`), with its word-boundary
        timings standing in for faster-whisper, which is not installed locally;
      - a hand-written fixture board;
      - the same mux, overlays and caption pass as production.

      A 12-frame contact sheet has been read, and the gate report is printed.
- [ ] **Tests (pure; no Chromium, ffmpeg, LLM or network):**
      - hostile model output: non-dict, wrong types, `<script>` in text, unknown template,
        40 beats, 2 beats, over-limit words;
      - the gate: invented number, no shared content word, stop-words ignored, hook exempt;
      - timing: monotonic cues, an unmatched beat, an unmatched element, beat 1 at 0, the
        2.5 s rule, the bar stagger;
      - the frame schedule, the concat list and the ffmpeg arguments;
      - the engine index by day-of-year and flag;
      - the fallback: `plan`/`render` returning `None` or raising → the crop path runs and no
        `_sb_` file is produced;
      - the ledger `shorts` field and the engine label;
      - learn: Shorts ids in `ledger_ids`, Shorts kept out of the format/hook arms, the pair
        tally;
      - importing `storyboard` does not import Playwright;
      - `storyboard.html` contains no `innerHTML`;
      - the flag is in both config files.
- [ ] The sample Short's render time is printed and is **≤ 120 s on the owner's PC**.
- [ ] The full suite is green (run it in the background, ~2.5 min), and `v3-phase-g` is pushed.

## Out of scope

- Long-form visuals, and zoomed or highlighted tool-UI callouts (v3-G.2, only if row 14 says
  build).
- Titles, hooks, the viral judge's rubric, and impressions/CTR data (v3-G.3).
- 1080p long-form, a music bed (`assets/music` is empty and untracked, so CI mixes none),
  transitions (v3-G.4).
- AI-generated images or video. Browser automation of consumer AI sites (evaluated 2026-09-26
  and not adopted; see DECISIONS).
- Snapping a Short's end to a sentence boundary: today it is `min(35 s, …)` from the scene
  start.

## Risks

- **The prompt first meets the real model in CI.** There is no Gemini key on the owner's PC.
  The local sample proves the renderer, gate and timing on a fixture board. The first CI log's
  `🎨 Storyboard: k/n beats kept` line shows how the model does.
- **CI render time is unknown until the first run.** It is logged. A slow render only delays the
  run, and a failure falls back to the crop path.
- **The literal gate can be strict.** A bare 3-letter label such as "GPU" has no 4+-letter word,
  so its beat becomes a `statement`. Watch the kept ratio; loosening the rule is a new spec row.
- **The hook overlay's second line** reaches y ≈ 346, and the visual area starts at y 300.
  Content is vertically centred, so it rarely reaches the top edge; the template screenshots
  will show it. Any fix that needs a new number is a new spec row.
- **The verdict is the 10-pair A/B, not the sample.** One extra Gemini call a day on the free
  tier; if it is rate-limited, that day's Short falls back to crop.
