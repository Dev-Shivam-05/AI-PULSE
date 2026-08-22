
## 2026-08-22 — v3 utility pivot (Phase A)
- **Pivot locked:** "about AI" news essays → "AI you can use today" tool videos. Driver: 90-day
  data (0:38 AVD, 5 subs); reference model = HyperAutomation Labs transcript (video as a
  transaction: viewer leaves with repo link + command + shortlist).
- News viral bar 7→8/10; word floors are sanity-only (600-620); **cap 900** is the new law.
- Blocked gate on an auto run falls back to forced evergreen — a blocked story never costs the day.
- Captions display script spelling force-aligned onto whisper timings (1:1 blocks only).
- Tool lane gated behind `tool_format:false` until the Phase-B screen-recording engine exists.
- Income path pre-YPP = description deliverables (PDF in Phase C), NOT ads.

## 2026-08-22 — v3 original-visuals engine (Phase B)
- **Tool videos are illustrated by the tool itself.** `factverse/screencap.py` records the tool's
  real page with headless Chromium (1920×1080, dark) and cuts it into sequential per-scene clips;
  Pexels is used for tool videos ONLY when capture fails (soft fallback), not as a ≤30% mix.
- Recording length is sized from the script's word count (60–300 s) because the script exists
  before visuals are fetched; scenes keep `step5_build`'s loop/cut fitting, so no exact cuts.
- Blank page-load head is trimmed by MEASURED `goto` latency (floor 2.5 s), not a constant.
- Code card = the deliverable rendered as a terminal card (Pygments bash, JetBrains Mono 22px);
  it leads the final scene and the first post-hook install/run scene, and REPLACES a stat card
  there rather than stacking (a scene's time is shared equally between its clips).
- Tool thumbnail = page screenshot + 2–4 word overlay (Inter Black, white on #DC2626, red
  baseline). Person-cutout retired for tool videos; fonts are bundled (OFL) in assets/fonts.
- Every LLM rewrite pass carries the same `_CARRY` key set — the advice-gate rewrite had carried
  only 4 keys and silently dropped `deliverable`. The deliverable description block is idempotent
  and re-appended before render for the same reason.
- CI: playwright pinned exactly (the browser cache key hashes requirements-ci.txt); the chromium
  install step is `continue-on-error` — a missing browser degrades to stock, never a lost day.
- `tool_format: true` at merge. The supervised first tool run happens in CI (no API keys exist
  locally): `workflow_dispatch` with `format=tool`, before the day's 12:23 UTC cron.
- HF model pages are JS-thin: `script_tool` grounds from `/raw/main/README.md` as a fallback.
