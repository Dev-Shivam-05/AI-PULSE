# Project glossary — fixed meanings (do not redefine in later sessions)

- **tool format** — the v3 hands-on video lane: a free AI tool/repo/model the viewer can use
  today. Config flag `tool_format` (true since Phase B; env `TOOL_FORMAT` overrides).
- **screencap** — `factverse/screencap.py`, the tool-video visual provider: a headless-Chromium
  recording of the tool's real page, trimmed and cut into per-scene chunks (same
  `list[list[path]]` shape as `step3_download`). Returns None on any failure → stock fallback.
- **code card** — the deliverable rendered as a terminal-style still (Pygments bash, JetBrains
  Mono 22px) and injected as the lead clip of the final scene + first post-hook install scene.
- **tool thumbnail** — `thumbnail.make_tool_thumb`: page screenshot + 2–4 word overlay, Inter
  Black, white on #DC2626, red baseline. Used whenever a screenshot exists; else the old chain.
- **cheat sheet** — the v3-C 1-page A4 PDF written per tool video to `docs/tools/<date>-<slug>.pdf`
  and served by GitHub Pages at `<deliverable_base_url>/tools/<file>`. Built by
  `factverse/deliverable.py`; the LLM-extracted sections fall back to title + deliverable. Never absent.
- **promo block** — config `promo_block`: the affiliate-ready description slot. Empty = omitted;
  non-empty = inserted verbatim after the cheat-sheet line (tool) / after paragraph 1 (others).
- **deliverable block** — the description lines `🔧 Try it yourself:` + command + source +
  `📄 Free 1-page cheat sheet: <url>`, placed after paragraph 1 (spec v3-C decision 7).
- **_CARRY** — the top-level script keys every LLM rewrite pass must copy across
  (`format, grounding, roundup_items, signal_title, synthesis_claim, filter_segment,
  hook_pattern, deliverable`). A pass that forgets one silently changes the video.
- **deliverable** — required field of a tool script: `{"kind": "command|repo|steps", "text", "url"}`.
  Spoken in the final scene, printed in the description as "🔧 Try it yourself". No deliverable = no video.
- **MAX_WORDS** — 900. The anti-padding cap enforced by `enforce_max_length` (cut, never pad).
- **word floor** — 600–620 sanity floor (`MIN_WORDS`), NOT a target. The old 850–1000 floors are
  banned; they were the root cause of the 0:38 average view duration.
- **utility lane** — decide_format's default when no story scores ≥ 8/10: tool if a tool signal
  exists (and flag on), else evergreen.
- **blocked-day fallback** — a FACTCHECK/ADVICE/POLICY block on an automatic run re-runs the day
  as forced evergreen. Forced runs (`force_format` set) still fail honestly with no fallback.
