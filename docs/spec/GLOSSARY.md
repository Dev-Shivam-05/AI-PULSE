# Project glossary — fixed meanings (do not redefine in later sessions)

- **tool format** — the v3 hands-on video lane: a free AI tool/repo/model the viewer can use
  today. Config flag `tool_format` (default false until the Phase B visual engine lands).
- **deliverable** — required field of a tool script: `{"kind": "command|repo|steps", "text", "url"}`.
  Spoken in the final scene, printed in the description as "🔧 Try it yourself". No deliverable = no video.
- **MAX_WORDS** — 900. The anti-padding cap enforced by `enforce_max_length` (cut, never pad).
- **word floor** — 600–620 sanity floor (`MIN_WORDS`), NOT a target. The old 850–1000 floors are
  banned; they were the root cause of the 0:38 average view duration.
- **utility lane** — decide_format's default when no story scores ≥ 8/10: tool if a tool signal
  exists (and flag on), else evergreen.
- **blocked-day fallback** — a FACTCHECK/ADVICE/POLICY block on an automatic run re-runs the day
  as forced evergreen. Forced runs (`force_format` set) still fail honestly with no fallback.
