# SPEC LOCK — AI Pulse v3-E.2: receipts.py (safe check-execution + beat + terminal footage)

Status: locked 2026-08-24 ("go"), built on `v3-phase-c`. Split from v3-E per the gap audit's
own scoping (rank 5). The channel's claim is "we checked this" — this phase makes the claim
true and puts the evidence on screen and in the narration.

**The security line, absolute: the check DOWNLOADS, it never EXECUTES.** A pip sdist download
runs `setup.py`; a wheel download runs nothing — so pip is pinned to wheels. `git clone` runs
no hooks. A curl-style deliverable is fetched with `requests`, never piped to a shell.
Anything that would need to execute candidate code (docker, npx, piped sh) is refused.

## Locked decisions

| # | Decision | Value | Why |
|---|----------|-------|-----|
| 1 | Module API | `factverse/receipts.py`: `check_plan(deliverable_text, dest) -> dict\|None` (PURE — parses, returns `{"kind","target","args"}`), `run_check(plan) -> dict\|None` (executes, fail-soft `None`), `install_scene_idx(script) -> int\|None`, `add_beat(script, result) -> bool`, `make_terminal_clip(result, out_mp4, seconds) -> str\|None`, `inject_receipt_clip(script, scene_clips, scene_durs) -> int` | Tests assert on args from the pure function, never run the network — the repo's own test law |
| 2 | Which checks | First matching segment of the deliverable (split on `•`/newlines, same as `command_grounded`): **pip** `pip3? install <pkg>` → `[sys.executable,-m,pip,download,pkg,--no-deps,--only-binary,:all:,--progress-bar,off,--no-input,-d,dest]`; **clone** `git clone <url>` → `git clone --depth 1 <url> dest`; **fetch** `curl/wget <http(s) url>` → requests stream to file, no subprocess. A segment containing a pipe, or docker/npx/sh-substitution, matches nothing. No segment matches → `None` | `--only-binary :all:` is the security line; a piped-sh install's script download is not "the download" and would stamp a misleading number |
| 3 | Package-name parse | First non-flag token after `install`; a token containing `://` or starting `git+` → not pip (a URL install is a source build = execution); strip extras `[...]` and version pins (`[=<>~!;@` split); must match `^[A-Za-z0-9._-]+$` | One hallucination-proof parse; the deliverable is already README-verbatim (v3-E #2) |
| 4 | Measurement | `time.monotonic` around the download; `seconds` 1 decimal (`.0` dropped when whole); `mb` = bytes under dest / 1e6 — 1 decimal < 10, whole ≥ 10; timeouts: pip/clone **180s**, fetch **60s**, PyPI lookup **15s**; timeout / nonzero exit / empty dest → `None`; dest is removed after measuring (a torch wheel is GBs of runner disk) | Mirrors `_ffmpeg`'s subprocess-timeout idiom; a wheel that blows 180s costs the beat, never the day |
| 5 | Registry lookup | pip kind only: `pypi.org/pypi/<pkg>/json` → optional keys `version` (`info.version`), `released` (first `urls[].upload_time[:10]`); `requests` imported inside the function (CI-import rule); any miss omits the keys | Mirrors `_verified_facts` exactly, incl. fail-soft omission |
| 6 | Result shape | `{"kind","target","seconds","mb","lines"(≤8 real stdout/stderr lines),"date"(ISO today),"version"?,"released"?}` → stored `script["receipts"]` (also in `_CARRY` per the documented rewrite-drop trap); PUBLISHED ledger row gets `receipts={kind,seconds,mb}` | `lines` are the footage; the ledger row is v3-D's food |
| 7 | Where it runs | `run()`, tool lane only, `fv.flag("receipts_check", True)`, positioned **after** the fact-check/originality gates and **before** `gates.packaging_payoff`; `install_scene_idx` is consulted BEFORE the network check so an unbeatable script costs zero minutes | Never spend 3 min of network before a gate can still kill the video; beat numbers land before the payoff gate reads narration, so a thumb number spoken only in the beat is supported |
| 8 | Beat placement | Append one sentence to the END of the first `INSTALL_KW` scene (index ≥ 1, never hook, never final scene — `inject_code_card`'s own selection); re-join `narration` after. No install scene → skip beat AND clip entirely | One shared definition of "install scene"; the beat lands before TTS so word timings absorb it |
| 9 | Beat text | `Checked by {fv.CHANNEL_NAME} on {Month D}: the download finished in {seconds} seconds at {mb} megabytes.` — units as words, never "MB" (TTS); date parsed from `result["date"]` so beat and stamp agree | The audit's literal beat, two numbers max, deterministic |
| 10 | Clip look | 1280×720, FPS 30, code-card palette (bg `13,17,23`, card `22,27,34`, outline `48,54,61`, traffic lights, `_mono_font(22)`, `$` prompt `63,185,80`); command line (derived from kind+target: `pip download <pkg> --only-binary :all:` / `git clone --depth 1 <url>` / `curl -L -o <name> <url>`) + real output lines revealed sequentially over the first 70% of the clip; from 70% the summary line `✔ {mb} MB in {seconds}s — checked by {channel} {date}` holds in `63,185,80`; over-long lines truncate with `…`, never wrap | Same design system as `render_code_card_png`; the summary frame is the receipts identity. The `✔` glyph must survive the live frame inspection (the repo has shipped tofu before — "star glyph becomes a word"); if it renders as tofu it becomes the word `OK` |

## REVIEW ADDENDUM (70-agent adversarial pass over the diff: 6 lenses → 32 raw findings
## → 20 confirmed + 5 split + 7 refuted; the 20 collapse to 9 root causes, all fixed, and
## all 5 splits were upheld on adjudication and fixed too. Each fix is pinned by a test.)
- **Fetch is now actually bounded (high):** requests' `timeout` only gaps between reads, so a
  slow-drip URL held the run until the 90-min CI job kill — on both cron firings. The stream
  now has a **60s wall-clock deadline and a `FETCH_MAX_BYTES = 2 GB` cap** (exceed → `None`),
  and the saved filename is **sanitized** (`[^A-Za-z0-9._-]` → `_`, leading dots stripped) so a
  backslash URL segment cannot walk out of dest on the supervised Windows box.
- **`script["receipts"]` is LLM-reachable (high):** `_validate_script` mutates the model's dict
  in place, so a planted top-level `receipts` survived — fabricated footage, and a non-dict
  raised inside the post-upload `record_run` (the double-publish zone). `run()` now **pops
  `receipts`** right after the format re-bind (only `add_beat` may set it) and the ledger read
  is `isinstance(dict)`-guarded.
- **The Saved-line sanitizer was posix-broken (high):** `Path(...).name` cannot split a
  backslash path on ubuntu — the amendment test itself was red on the repo's actual CI. Both
  path rules now use `_basename` (`re.split` on either separator), and git's
  `Cloning into '<abs path>'...` stderr line — the clone branch re-shipping the same leak —
  keeps only the last segment.
- **pip's cache made the number a lie:** `--no-cache-dir` joins the locked arg list; a cached
  wheel produced a physically impossible "download" time and a frame that contradicted it.
- **Refusal screen widened:** `&&`, `;`, `$(` and backticks join `|`/docker/npx/`<(` — the
  non-piped shell forms (`curl x.sh -o i.sh && sh i.sh`) were stamping a 10KB installer stub
  as "the download". `_pip_target` now requires a **leading alphanumeric** (kills `.`/`..` — a
  local-directory target makes pip EXECUTE the build backend) and skips the argument of
  consuming flags (`-r requirements.txt` would have "checked" a PyPI squatter's wheel).
- **`_round_mb` floors nonzero at 0.1** — a 10KB fetch narrated "at 0 megabytes".
- **Frame count CEILS** (`max(2, ceil(FPS·s))`) — the `int()` floor left the clip up to 1/30s
  short of its share, step5_build looped it, and animation frame 0 flashed at the scene cut.
- **Plans carry `dest`** for every kind (the fetch plan's empty `args` made run_check fall back
  to the real repo temp dir — which the fail-soft test then rmtree'd).
- **Render polish from the split findings:** the command row's truncation budget accounts for
  its 2-glyph prompt indent; the summary line truncates against the same measured budget (a
  long configured channel name must not overrun); the tests pin the `download` verb itself
  (`args[1:4]`) — the verb IS the invariant.
- **Refuted (recorded, unchanged):** blind-SSRF-to-published-surface (response bytes never reach
  any shipped surface; the wall-clock + sanitizer shrink the surface anyway), the x0-vs-indent
  overhang variant, summary-measurement (fixed regardless via the split), fetch-name traversal
  on posix (backslash is not a separator there), and the run()-ordering-untested claim.

## LIVE-INSPECTION AMENDMENTS (2026-08-24, first real frames)
- **#10 amended — summary prefix is `OK:`, unconditionally.** The `✔` rendered as tofu in
  JetBrains Mono on the very first live frame, and a width probe cannot detect tofu (tofu HAS
  width) — so the pre-locked contingency is now the rule, not the fallback.
- **#6 amended — `lines` are cleaned by `_clean_lines` (pure, tested):** pip's `[notice]`
  upgrade nags are dropped (runner housekeeping, not tool output) and the `Saved <path>` line
  keeps only the filename — the raw line burned the machine's own directory layout onto a
  to-be-published frame.
| 11 | Clip injection | In `run()`'s tool block AFTER `inject_cards` + `inject_code_card`: lead the same install scene; if `clips[0]` is a statcard/codecard → **replace** (share = `sdur/len(clips)`), else insert (share = `sdur/(len(clips)+1)`); the clip is rendered to exactly that share | The C.3 law: an animated clip is rendered to its real slot or it loops/cuts. The final scene keeps the code card; the install scene upgrades from still card to real footage |
| 12 | Fail-soft + logs | Any failure → `None` → the video ships in its pre-E.2 shape. Success: `🧾 Receipts: {kind} {mb} MB in {seconds}s`; check failed: `⚠️ receipts check failed — shipping without the beat`; deliverable not checkable: `↻ deliverable is not download-checkable — no receipts beat` | The unattended-run law; a fail-soft seam must still SAY whether it worked |

## OUT OF SCOPE (will NOT build)
- docker/npm/npx checks, anything that executes candidate code (ever)
- story lanes, PDF/description/pinned-comment changes, Pages site (v3-F)
- fact-checking the beat against grounding — the numbers are OUR measurement, deliberately
  inserted after `fact_check`

## ACCEPTANCE CRITERIA (binary)
- [x] `check_plan` on a pip/clone/curl deliverable returns args containing
      `--only-binary :all:` / `--depth 1` / no shell; docker & piped-sh (and the review's
      `&&`/`;`/`$(`/backtick forms) return `None` (pure, no network)
- [x] Beat lands at the end of the install scene, narration re-joined; a script with no
      install scene → no beat, no clip, no network spend, no error
- [x] A `thumb_text` number spoken only in the beat passes `packaging_payoff`
- [x] Replace-vs-insert share math matches `card_slot_dur` semantics (test on both branches)
- [x] `run_check` failure at every seam returns `None` (each seam stubbed and tested,
      incl. the endless-stream one); the `run()` wiring itself adds no raise path (pop /
      print / rejoin only) — final proof is the supervised `format=tool` dispatch
- [x] Suite green (137/137); live: real cold check against a real package (openai 3.3.1,
      1.7 MB in 8s, registry version+date fetched), clip rendered to its exact share,
      frames inspected twice (the first inspection found 3 defects, the second is clean),
      beat printed

## RISKS
- Huge wheels (torch) blow 180s on CI → beat absent by design; raise to 300s only if the
  first live runs show it repeatedly — with data, not preemptively.
- `--only-binary :all:` fails for source-only packages → fail-soft, correct: we refuse to
  execute their build.
