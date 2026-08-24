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
- [ ] `check_plan` on a pip/clone/curl deliverable returns args containing
      `--only-binary :all:` / `--depth 1` / no shell; docker & piped-sh return `None`
      (pure, no network)
- [ ] Beat lands at the end of the install scene, narration re-joined; a script with no
      install scene → no beat, no clip, no network spend, no error
- [ ] A `thumb_text` number spoken only in the beat passes `packaging_payoff`
- [ ] Replace-vs-insert share math matches `card_slot_dur` semantics (test on both branches)
- [ ] `run_check` failure at every seam returns `None` and `run()` still reaches upload
- [ ] Suite green; live: real check against a real package, clip rendered, frames inspected,
      beat printed

## RISKS
- Huge wheels (torch) blow 180s on CI → beat absent by design; raise to 300s only if the
  first live runs show it repeatedly — with data, not preemptively.
- `--only-binary :all:` fails for source-only packages → fail-soft, correct: we refuse to
  execute their build.
