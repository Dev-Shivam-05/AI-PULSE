# Spec — v3-P.1: evidence engine + claim substantiation

Status: **locked**. The owner approved the 2026-11-04 review ("go for all … do not stop until
everything is done"). This phase implements rows 3, 4 and 17 of
`docs/debate/2026-11-04-tooldojo-channel-growth/RESULT.md` and the shared `script["evidence"]`
interface in `docs/spec/ai-pulse-v3-growth.md`. Values marked *locked* come from review round 3
(`03_chatgpt.md` §1, §3) as amended in round 4; every other value is a **delegated decision**
listed with its default and the reason, for the owner's report.

## Why this phase exists

1. **No tool video ever showed the tool working.** `screencap.py` records a scrolling README;
   `receipts.py` only downloads. Retention on every tool video falls from 95% to 55-60% by 0:07.
2. **Packaging promised outcomes nobody observed.** "Double Your AI Speed: gpu-unlock for GeForce
   RTX" (2026-10-29) and its thumb "2X AI SPEED. FREE." The packaging gate checks only that a
   number is *spoken*, not that ToolDojo *saw* it.
3. **Row 17:** with no functional evidence, the video is skipped by default.

## Locked decisions (from the review)

| # | Decision | Value |
|---|----------|-------|
| 1 | Evidence sources built | (a) hosted demo, (c) author demo. Preference: hosted first, then author. |
| 2 | (a) hosted | Driven by the pipeline in a clean browser with a fixed synthetic input, recorded. **120-second total capture deadline.** A sleeping, queued or inaccessible demo is *unavailable evidence*, never a fabricated result. Success needs an independent check of the output: a page saying "success" is not success. Allowed claim: "In our hosted-demo run, this input produced this output." Not: installation works, works offline, works on your hardware. |
| 3 | (c) author | Demo media committed in the repo and referenced by its README, under MIT or Apache-2.0. Rights record: asset path, commit, licence, copyright notice, NOTICE material, modification disclosure. Unresolved provenance is rejected. Clip = one complete action-to-result sequence, ordinarily **8-20 s**. Status `NOT_RUN`, label "Author demo". Allowed claim: "The author's demo shows …", never "we tested". Required licence material goes into the published description. |
| 4 | Five statuses + wording | `NOT_RUN` "Not independently tested." · `PASSED_FIXED_TEST` "Passed this specific test." · `FAILED_FIXED_TEST` "This test failed under these conditions." · `TIMED_OUT` "Did not complete within our 120-second execution limit." · `INCONCLUSIVE` "We could not establish a result." (`evidence.WORDING`, verbatim). |
| 5 | Failure | A hosted run that does not pass is not published (row 4 "skip on failure"; round 3: the pilot uses successful, interpretable demonstrations). |
| 6 | Row 17 | No admissible evidence → skip the candidate by default (`evidence_required`). |
| 7 | Row 3 | An outcome claim in the long-form title or thumbnail that ToolDojo did not observe is attributed ("claims 2×") or dropped. A standard, not a test. |
| 8 | Source labels | "Hosted test", "Author demo", "Sandbox test"; at least 32 px at 1920×1080; visible throughout third-party footage. |
| 9 | Interface | `script["evidence"]` exactly as in the growth spec, `_CARRY` + popped in `_validate_script` + restored by `_carry_over`; ledger `evidence_source` / `evidence_status`; `tools_index.json` entries get `evidence` without `clip`. |

### (b) Sandboxed execution — NOT built; admission gates for a later phase

(b) may be built only when **all** of these hold (round 3 table, verbatim values):

| Area | Gate |
|---|---|
| Boundary | A separate, disposable runner **plus** a gVisor-class sandbox for untrusted code. No secrets, inherited credentials, host workspace, runner-control files, Docker socket, shared cache or publishing credentials inside. Candidate code never runs as the runner user. |
| Isolation | Non-root; read-only base filesystem; restricted writable scratch; externally enforced resource and network limits. |
| Acquisition | A trusted fetch stage downloads pinned versions from approved registries and records hashes; no candidate code runs during acquisition. Python: pinned, hash-checked, binary-only. npm: install scripts disabled. |
| Network | **Zero** during install and execution, including DNS and host services. |
| Quickstarts | CPU-only, offline, fixed input, constrained command templates. No README shell blocks, privileged installers, OS changes, firmware, or network administration. |
| Resources | **2 CPU, 2 GiB RAM, 128 processes, 512 MiB scratch, 250 MiB dependencies.** Acquisition **120 s**; install + run **120 s**; whole job **300 s**; one candidate, one attempt per day. |
| Outputs | **1 MiB** terminal log, **50 MiB** artifacts, both untrusted: control sequences sanitised, artifacts validated/transcoded in quarantine, never executed. |
| Success | Exit code 0 **and** an independent check of the expected output. |
| Account | A documented GitHub-terms check (software-testing purpose, no disproportionate burden); ambiguity resolved with GitHub before treating Actions as a demo service. Stars/age are selection metadata, never a security pass. |
| Status | A policy violation quarantines the candidate; it is not a product review. |

## Delegated decisions ("default chosen: X, because Y")

| # | Decision | Default chosen | Because |
|---|----------|----------------|---------|
| D1 | Hosted hosts | Hugging Face Spaces only: linked from the README/model card, or owned by the model's owner (HF API `spaces`). Driven only when `/config` is a Gradio app. | Gradio's `/config` declares the examples, the button and the output components, so a fixed input and an independent output check are possible without guessing. Today: 3 of 4 linked Spaces were docker/static or had no examples. |
| D2 | Fixed input | The Space's **own** Examples (a `gr.Examples` dataset, or a gallery whose `select` fills the inputs). The first example; the **second** when the result region already shows a result at load. No examples → not driven. | "Its own examples" is the round's wording. A Space that pre-loads example 1's output (measured: `gradio/image_mod`) would otherwise make a real run look like "no change". No invented prompt. |
| D3 | Independent check | (i) the declared output components' DOM signature changed after submit, or a pending state was seen; **and** (ii) for visual outputs, the result region's pixels differ from the load or in-progress baseline by a mean of **≥ 2.0/255** and the region is not blank (**stdev ≥ 8**); for text outputs, non-empty text. | The first live run passed a DOM-only check while the 3D result sat off-screen. Thresholds measured on one Space (60.7 diff / 85.6 stdev on a pass; 0.0 diff on the pre-loaded case). |
| D4 | Outcome → status | Error text matching quota / log in / sleeping / paused / rate limit → unavailable (`None`); any other error → `FAILED_FIXED_TEST`; DOM done but pixels not → `INCONCLUSIVE`; deadline while queued → unavailable; deadline after submit → `TIMED_OUT`; a page that never offered its button/examples → `INCONCLUSIVE`. | Round 3: queue/sleep/quota walls are unavailable evidence, not results. The ZeroGPU quota toast arrives a beat after the output's bare "Error" badge, so the toast is re-read after 1 s. |
| D5 | Recording + cut | Viewport 1280×720, light scheme, clean context, software WebGL. Clip = 1.0 s before the example click to 2.5 s after the result; longer than 20 s → sped up uniformly, at most 4×, and `observed` says "Waiting shown at N× speed". | UI text stays legible at 1280 wide; round 3 asks for marked sped-up waiting. |
| D6 | Author media types | GIF, MP4, WebM. Stills (PNG/JPG/WebP/SVG) are rejected; a clip under 2.0 s is decoration. | A still is not an action-to-result sequence. Animated WebP decoding is not relied on. |
| D7 | Long author assets | ≤ 20 s: whole at 1×; ≤ 40 s: whole, sped up to 20 s (≤ 2×); longer: the first 20 s. Shorter than 8 s: last frame held to 8 s. All disclosed in `rights.modified`. | Keeps the sequence complete whenever possible; the exception is a known limit below. |
| D8 | Author download caps | 60 s wall clock, 50 MiB, streamed into its own empty directory. | `receipts.FETCH_TIMEOUT` and round 3's 50 MiB artifact ceiling. |
| D9 | Provenance | Accepted: relative paths, `raw.githubusercontent.com/<same repo>`, `github.com/<same repo>/(raw\|blob)/`, `huggingface.co/<same repo>/(resolve\|raw\|blob)/`. Rejected: `github.com/user-attachments`, `user-images`/`private-user-images`, release downloads, other repos, external hosts, `..` or backslash paths. Downloaded from the **pinned commit** (default-branch HEAD at gather time). | Only a file committed in the repo is covered by the repo's licence and has a commit to cite. |
| D10 | Licences | MIT and Apache-2.0 only. **Not widened** (today CC-BY-4.0 appeared once, AGPL-3.0 once). MIT needs a copyright line found in LICENSE/NOTICE, else unresolved. A NOTICE longer than 300 chars is rejected. | The round approved exactly these two. MIT's condition is the copyright + permission notice; a NOTICE that cannot ride in one line cannot be "preserved" in one line (measured: `digital-human-koubo`, 544 chars). |
| D11 | Attribution line | One description line, directly under the deliverable block (else under the hook): `🎞️ Author demo footage: <pinned blob URL> — <licence> License — <copyright> — NOTICE: <text> — Modified by ToolDojo: …`. Idempotent; a mangled copy is replaced. | The owner asked for one line; the pinned URL is the asset path + commit in clickable form. |
| D12 | Source label | `"Hosted test · YYYY-MM-DD"` / `"Author demo · owner/repo"`, Inter Black **40 px** at 1080p, white on a dark pill with a red outline, top-left (48, 40), burned into the evidence clip for its whole slot, measured with `branding.fit_font`. | ≥ 32 px floor; the date is round 3's "with the capture date"; the repo name is the "persistent attribution". v3-P.2 may replace it with its own overlay (`with_label=False`). |
| D13 | Slot fit | Clip shorter than the slot → played once, last frame (the result) held; longer → sped up to at most 1.5×, then the **head** is dropped (the result is at the end). Output = share + 0.5 s. | The C.3 law; `screencap.TAIL_PAD` so `step5_build` never loops it. |
| D14 | Placement | Scene 1's first non-card clip (the recording or stock clip) is removed and the evidence clip is inserted at index 0; the clip count never grows. A failed render leaves scene 1 untouched. | "Replace, don't stack" (CLAUDE.md). |
| D15 | Probe pre-filter | With `evidence_required` on, `build_script` probes tool candidates in rank order and skips a `"none"` probe **before** the three slots; a probe that could not look keeps the candidate. | A probe costs seconds; gather + writer cost minutes. Without it, three evidence-less candidates would empty the tool day before an eligible one was reached. |
| D16 | Overclaim gate | After every rewrite pass, `evidence.overclaims`: over an author demo, any first-person testing claim ("we tested/tried/ran/benchmarked/installed", "our test", "in our testing"); over a hosted test, "we installed/benchmarked", "works offline", "runs/works on your machine/hardware/GPU/laptop/PC/computer". A hit → `OVERCLAIM_BLOCKED`, `_fall_back`. | Round 3's "never 'we tested'" and "not installation works / offline / your hardware", enforced after the passes that rewrite the narration. |
| D17 | Substantiation scope | Every format's long-form title and thumb_text (the standard names no lane). | Measured: it changes 3 of 100 published videos, 2 of them news. |
| D18 | Outcome-claim classes | `N×`/`Nx`; "N times faster/cheaper/…"; double/triple/quadruple/halve (+ your/the/its); `N%` with a gain word within 2 words ("60% Sales Boost", "56% GPU Cost Cut"); verb-first "cuts … by N%"; "N hrs saved"/"saves N hours"; "in/under N seconds/ms". A share ("Half of All Uploads", "68% of Americans") is not an outcome claim. | The corpus' own cases plus their obvious variants; deterministic regexes. |
| D19 | Attribution wording | The word **"Claimed"** before the claim, a verb multiplier becoming its noun ("Double Your AI Speed" → "Claimed 2× AI Speed"; thumb "CLAIMED 2X AI SPEED."). Only when the claim starts its clause; otherwise a claim-free alternate from `titles`, otherwise the claim's clause is dropped (tool lane: `How to use <tool> (free)` if under 3 words remain). | "Make Llama Claimed 3x Faster" is not a sentence. Order attribute → alternate → drop keeps the creator's title whenever honest. |
| D20 | Observed | A claim is observed only if a `PASSED_FIXED_TEST` lists it in `supported_claims`. A hosted pass supports its own observed sentence; an author demo supports nothing. | Row 3's "did not observe". |
| D21 | Thumb fit | ≤ 26 chars, ≤ 4 words (`make_tool_thumb` burns the first 4), and measured with both composers' fonts and budgets. Non-claim parts are shed from the end first; an attribution that cannot fit drops the claim part instead. | Burned text is measured, never sized by character count (CLAUDE.md). |
| D22 | "Before you install" verdict | **Not built.** Row 17 makes it optional. | It needs two decisive verifiable facts and its own format; skip is the default. |
| D23 | `version` key | Optional `evidence["version"]`: the Space's git sha (hosted) or the pinned commit (author). | Requested by v3-K.1 for the tool page and hub. |
| D24 | Ledger | `evidence_source`, `evidence_status` ("" for a script with no evidence dict) and `claims_fixed` (the fields the standard changed), computed before the upload. | Coerced strings/lists; nothing new can raise past `eng.yt_upload`. |
| D26 | Text fetches | Every README / JSON / `/config` read is streamed under a **30 s** wall clock and a **5 MiB** cap. | A Space's own server answers `/config`; requests' `timeout` is not a deadline (CLAUDE.md). |
| D25 | Test defaults | `tests/conftest.py` sets `EVIDENCE_ENGINE=0`, `EVIDENCE_REQUIRED=0`, `CLAIM_SUBSTANTIATION=0` for every test; P.1 tests turn them on. | The switches are on in `config.json`; without this, every older test reaching script_tool would hit the network or skip its fixture. |

## Files changed

- `factverse/evidence.py` (new): `probe`, `gather`, `try_hosted`, `try_author`, `gradio_plan`,
  `classify`, `visible_result`, `bounded_download`, `readme_media`, `resolve_asset`,
  `readme_spaces`, `copyright_line`, `author_plan`, `hosted_cut`, `master_args`, `modification`,
  `attribution_line`, `writer_brief`, `overclaims`, `fact_lines`, `slot_plan`, `slot_args`,
  `label_text`, `render_label_png`, `render_slot_clip`, `lead_index`, `place_clip`,
  `admissible`, `ledger_fields`, `catalog_view`, `empty`, `wording`, `label`.
- `factverse/gates.py`: `outcome_claims`, `claim_observed`, `thumb_fits`, `substantiate_claims`;
  `fact_sources` also reads the evidence.
- `factverse/ai_pipeline.py`: `evidence` popped in `_validate_script` and in `_CARRY`;
  `script_tool` gathers after the suitability screen and before the writer, skips without
  evidence; `build_script` probe pre-filter; `place_description_blocks` attribution line;
  `run()`: overclaim gate, `substantiate_claims` after the hype screen and before the ledger
  fields, `evidence.place_clip` after every `inject_*` and before `screencap.recut`, ledger fields.
- `factverse/site.py`: `publish_page` adds `evidence` (without `clip`) to the catalog entry.
- `config.json`, `config.example.json`: `evidence_engine`, `evidence_required`,
  `claim_substantiation` (all `true`).
- `tests/test_p1_evidence.py` (new, 64 tests), `tests/conftest.py` (new),
  `tests/test_pipeline_logic.py` (the fallback-helper count is now 5: the new gate uses it).

## For v3-P.2 (the opening contract)

- Placement: `evidence.place_clip(script, scene_clips, scene_durs, with_label=True) -> float | None`
  (slot seconds; `None` = nothing placed, scene 1 untouched). Pure pieces: `slot_plan`,
  `lead_index`, `slot_args`; renderer `render_slot_clip(ev, share, out, with_label)`.
- Label: `evidence.label_text(ev)` (text), `evidence.render_label_png(text, out_png)`,
  `evidence.LABELS`, `evidence.wording(status)`. Pass `with_label=False` to draw your own overlay.
- Gate helpers: `evidence.admissible(ev)`, `evidence.overclaims(script)`.

## Verification

**Suite: 513 passed** (2026-11-04, full `py -3 -m pytest tests/ -q` on the branch). The first full
run had 1 failure: `test_every_gate_uses_the_fallback_helper` pins the number of gates that call
`_fall_back`; the new overclaim gate is the fifth, and the test now says so.

**Live supply, today's real candidates** (2026-11-04, `sources.github_trending()` +
`huggingface_trending()`, read-only public network):

| probe answer | candidates |
|---|---|
| hosted could exist | 4 (all HF models: idol, Pika-H3-Flex, Nemotron-Transcribe, Mistral-Large-4) |
| author could exist | 3 (wangzan101/Mika, modelflare-ai/AnyModelBot, andyhuo520/digital-human-koubo) |
| none | 18 |
| could not look | 2 (gated model cards: LTX-2.5, Sulphur-3) |

Full `gather` on all 7 "could exist": **3 admissible** — speridlabs/idol (hosted PASSED on the
first run; the re-run hit the ZeroGPU quota and fell back to its author reel), Mika (author,
Apache-2.0), AnyModelBot (author, MIT). Not admissible: Pika (no examples), Nemotron and all
three Mistral Spaces (not Gradio), digital-human-koubo (NOTICE 544 chars). **3 of 27 candidates
(11%)** have admissible evidence today. Probe cost: 2.5-9.2 s per candidate.

**Hosted end-to-end** on `gradio/image_mod` (a CPU Gradio Space, because idol's ZeroGPU quota
was spent): example 2 (lion.jpg) was chosen because the page pre-loaded example 1's result;
`PASSED_FIXED_TEST`, pixels diff 60.7 / stdev 85.6, 31 s total. Frames read: page → input →
pending → rotated lion. **Author end-to-end** on AnyModelBot (`docs/assets/hero/hero-demo.gif`,
20.0 s, MIT, commit aa2d5eb) and Mika (`docs/media/wechat-send-side.gif`, 15.7 s, Apache-2.0
with NOTICE, commit 6b90394). Each was rendered through `place_clip` into a scene-1 slot
(14.0 s, 22.0 s, 15.0 s): probed 14.5 / 22.5 / 15.5 s at 1920×1080, evidence first, the stat
card kept second, no clip added. Frames read: label legible from frame 0, the action-to-result
sequence intact, the held last frame is the result.

**Substantiation on the real ledger** (100 published videos in `state/runs.jsonl`):
3 have an unobserved outcome claim, 3 change.

| date | format | before (title / thumb) | after |
|---|---|---|---|
| 09-25 | news | Codex: 60% Sales Boost, 75+ Hrs Saved / — | Codex: Claimed 60% Sales Boost, Claimed 75+ Hrs Saved / — |
| 10-27 | news | Nvidia Backs AI Startup Cutting GPU Costs / 56% GPU Cost Cut | unchanged / "" (5 words cannot burn; the composer falls back to the title) |
| 10-29 | tool | Double Your AI Speed: gpu-unlock for GeForce RTX / 2X AI SPEED. FREE. | Claimed 2× AI Speed: gpu-unlock for GeForce RTX / CLAIMED 2X AI SPEED. |

Over all 164 distinct titles/thumbs in the ledger (any status) the detector also flags two
blocked runs ("GPT-5.6: 10x Cheaper…", "…Runs Websites in 7 Secs") and nothing else; no share
or count ("97% Democrat", "2,408 STARS", "40 Languages") is flagged.

## Known limits

- **Supply is thin**: 3 of 27 today. With `evidence_required` on, most weekdays will fall back
  from the tool lane. That is row 17's intent; the ledger's `evidence_source` will show the rate.
- **ZeroGPU quota.** Anonymous use is metered per IP (measured: 180 s requested vs 156 s left after
  one 27 s run; reset in ~24 h). On CI the runner IP decides. A quota wall is unavailable
  evidence; the author fallback then applies. A token would raise the quota but would put a
  credential inside the "clean context" — not done.
- Only Gradio Spaces with Examples are drivable. Docker/static Spaces and other hosts are not.
- The author demo's `observed` is the README's alt text and heading: nothing checks what the GIF
  actually shows.
- An author asset longer than 40 s contributes its first 20 s, which may stop mid-action
  (idol's 44.9 s reel).
- The hosted clip's frame 0 is the page before the example click, not the result. Frame-0
  rules are v3-P.2's.
- The 120 s deadline bounds the capture; browser teardown and video finalisation come after it.
  One run that waited out the deadline took 151 s in total.
- Thumb fit is measured with the fonts on the machine; Montserrat is not in `assets/fonts`, so
  the person-composer measures with Arial (Windows) or DejaVu (CI).
- The claim regexes are English-only, and an unquantified comparative ("Faster") is not a claim.

## Traps found (for the integration step to copy into CLAUDE.md)

- **Gradio 6 renders no `component-<id>` DOM ids.** `gradio/image_mod` (6.31) has empty ids on
  every block. Locate a component by its id when present, else by the button's own text and the
  output block's label (`evidence._button_locator` / `_output_locator`).
- **A DOM change is not a visible result.** The first idol run "passed" while the 3D output sat
  off-screen. Scroll the result region into view and compare its pixels.
- **A Space can pre-load its first example's output.** A baseline taken after load makes your own
  run look like "no change". Run example 2 when the region already shows a result, and compare
  against both the load state and the in-progress state.
- **The Gradio output badge only says "Error".** The reason (a ZeroGPU quota, which is
  unavailable evidence, not a failure) is in a toast that lands about a second later.
- **`fetch_text` strips tags, and demo media live in `<img>`/`<video>` tags.** Anything that looks
  for media must read the RAW README.
- **A switch that is on in `config.json` changes every older test that reaches its path.**
  `tests/conftest.py` pins the P.1 switches off; a phase adding a network-backed switch needs
  the same.

## Done when

- [x] The suite is green with the new tests.
- [x] A real hosted demo and two real author demos captured end-to-end, rendered to their slots,
      frames read.
- [x] The assembled description printed with the attribution line.
- [x] The substantiation standard measured on the real ledger.
- [ ] The first CI tool day logs either `🎞️ Evidence` or `↻ no admissible evidence`, and the ledger
      row carries `evidence_source`.
