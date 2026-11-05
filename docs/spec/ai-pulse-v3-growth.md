# Spec — v3 growth programme (2026-11-04 review, owner: "go for all")

Status: **approved**. On 2026-11-04 the owner answered the review's 18-row table with
*"go for all … do not stop until everything is done"*. The review table is
`docs/debate/2026-11-04-tooldojo-channel-growth/RESULT.md`; the numeric contract is round 3's
reply (`03_chatgpt.md`) as amended in round 4 (`04_claude.md` A1-A3, accepted in `04_chatgpt.md`).
That folder is kept local only, like every earlier review folder: it holds Studio analytics,
and this repo is public. Each phase spec copies the values it uses, so this repo stays
self-contained.

Every number in a phase spec must come from those rounds or from this file. A value nobody
wrote down is recorded in the phase spec as **"delegated — default chosen: X, because Y"**,
and it appears in that phase's report for the owner.

## Rows → phases

| Row | Point | Phase | Branch |
|---|---|---|---|
| 1, 2, 18 | diagnosis, bottleneck order, data corrections | docs only (DECISIONS) | integration |
| 3 | unobserved outcome claims are attributed or dropped | v3-P.1 | `v3-phase-p1` |
| 4 | evidence sources (a) hosted demo, (c) author demo + rights record; five statuses; (b) spec only | v3-P.1 | `v3-phase-p1` |
| 17 | no evidence → skip by default; the "before you install" verdict is the only exception | v3-P.1 | `v3-phase-p1` |
| 5 | long-form opening rules, checked against the encoded output | v3-P.2 | `v3-phase-p2` (stacked on p1) |
| 6 | Pilot A: proof-first vs context-first, 6 pairs | v3-P.2 | `v3-phase-p2` |
| 13 | query-map packaging, descriptive chapters, first description sentence | v3-P.2 | `v3-phase-p2` |
| 7 | native concept Short rules | v3-S.1 | `v3-phase-s1` |
| 8 | Pilot B: native vs crop, 6 day-pairs, slots alternated | v3-S.1 | `v3-phase-s1` |
| 15 (Reels) | Reels only from ToolDojo-owned concept visuals | v3-S.1 | `v3-phase-s1` |
| 9 | memory record + follow-up candidate rule | v3-M.1 | `v3-phase-m1` |
| 10 | north star: 100× on-demand long-form watch time per 28 days, ladder | v3-M.1 | `v3-phase-m1` |
| 16 | second daily long-form: 14-day shadow queue + gate | v3-M.1 | `v3-phase-m1` |
| 11 | Challenger as a Radar Live segment, two boards | v3-K.1 (spec + board row) | `v3-phase-k1` |
| 12 | task-based evidence catalogue (hub pages, dormant until supply) | v3-K.1 | `v3-phase-k1` |
| 14 | "follow this task": opt-in alert only on a material change | v3-K.1 | `v3-phase-k1` |
| 15 (site, X) | useful HTML tool pages; X stays off (pay-per-use since 2026) | v3-K.1 | `v3-phase-k1` |

## Shared interface (every phase codes against this; v3-P.1 implements it)

### `script["evidence"]`: one dict per tool video, computed by `run()`'s side, never by the model

```python
{
  "source":  "hosted" | "author" | "sandbox" | "none",
  "status":  "NOT_RUN" | "PASSED_FIXED_TEST" | "FAILED_FIXED_TEST" | "TIMED_OUT" | "INCONCLUSIVE",
  "label":   "Hosted test" | "Author demo" | "Sandbox test" | "",   # on-screen source label
  "wording": "<viewer-facing wording of the status, table below>",
  "clip":    "<local path of the evidence clip, mp4>" | "",
  "clip_seconds": float,
  "url":     "<demo URL or asset URL>",
  "captured_at": "YYYY-MM-DD",
  "input":   "<fixed input used for a hosted test>" | "",
  "observed": "<one sentence: what the output showed>" | "",
  "supported_claims": ["<claim text the evidence supports>", ...],
  "rights":  None | {"path", "commit", "license", "copyright", "notice", "modified"},
}
```

| status | viewer wording (verbatim, round 3) |
|---|---|
| `NOT_RUN` | "Not independently tested." |
| `PASSED_FIXED_TEST` | "Passed this specific test." |
| `FAILED_FIXED_TEST` | "This test failed under these conditions." |
| `TIMED_OUT` | "Did not complete within our 120-second execution limit." |
| `INCONCLUSIVE` | "We could not establish a result." |

- `evidence` is a `_CARRY` key **and** is popped inside `_validate_script`, then handed back by
  `_carry_over`. This is the `receipts`/`cheat_sheet` trap: the model must not be able to plant it.
- `factverse/evidence.py` exposes `probe(item) -> dict | None`. It is cheap (no browser, no
  download), answers which evidence source *could* exist for a candidate, and never raises.
  v3-M.1's shadow queue calls it inside a `try`.
- The ledger row gets `evidence_source` and `evidence_status` (strings, coerced).
- `state/tools_index.json` entries get `evidence` (the dict without `clip`) and `task_family`
  (v3-K.1 owns `task_family`).

### Experiment fields (v3-P.2 and v3-S.1)
- Ledger: `experiment` (`"pilot_a"` / `"pilot_b"` / `None`), `pair_id`, `arm`, `slot`.
- Shorts rows keep `{"url", "engine"}`. The native Short's engine name is `"native"`.

## Rules for every phase in this programme
- Base: `v3-growth-1104` (= `v3-integration-1101` + this file). One worktree per phase.
- Do not edit `docs/PHASES.md`, `docs/HANDOFF.md`, `docs/DECISIONS.md` or `CLAUDE.md`. Put the
  decisions and any new trap in the phase spec; the integration step writes the shared docs.
- Any new tracked state file needs the both-halves treatment: an entry in
  `state_merge.FILES` with merge semantics for its shape, **and** the stash list of every
  workflow that writes it.
- Every new seam fails soft (returns `None`) and never raises in the post-upload zone.
- Each new behaviour gets a config kill switch in `config.json` and `config.example.json`.
- Tests never touch the network, ffmpeg or the LLM, and helper names in shared test modules
  carry the phase prefix.
- Done means tests green **and** the artifact produced and inspected.
