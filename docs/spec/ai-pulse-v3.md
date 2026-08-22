# SPEC LOCK — AI Pulse v3: the utility pivot

*Locked 2026-08-22. Owner approved with `go`. This file is the contract; a session with no
memory of that conversation must be able to build the identical thing from this file.*

## Why v3 exists (the data, 90 days)

1,582 views / 17.6 a day · 16.6 watch-hours · 5 subscribers · **average view duration 0:38**
on 6–9-minute videos. At that rate YPP (1,000 subs + 4,000 h) is decades away. The machine
runs perfectly and produces the wrong thing: "about AI" news essays, padded to a word floor,
illustrated with stock footage. The fix is a pivot, not a tweak:

> **Stop making videos ABOUT AI. Make videos about AI things the viewer can USE today.**

Reference model: HyperAutomation Labs (see `hyperautomation-lab.script.md` in repo root at
time of writing). Their video is a *transaction* — the viewer leaves with a repo link, an
install command, and a shortlist — and their income is a product ladder in the description,
which works from view #1 and needs no YPP gate.

## Locked decisions

| # | Ambiguity | Locked value |
|---|-----------|--------------|
| 1 | Channel direction | **Tool-utility format** ("tool"). Sources: GitHub trending + Hugging Face trending + Product Hunt feed. News runs ONLY when the viral judge scores ≥ 8/10 (was 7). Sunday roundup stays. |
| 2 | "Mind-blowing visuals" | ≥70% of frames = original screen recording (Playwright headless Chromium 1920×1080@30) + code cards (Pygments, JetBrains Mono 22px) + generated charts. Pexels ≤30%, establishing shots only. |
| 3 | Video length | 4:00–6:00. Word floor drops to 600–620 (sanity only), **cap 900** (`MAX_WORDS`). Critique pass instructed to CUT repetition, never pad. Old 850–1000 floors deleted — they were the padding root cause. |
| 4 | Payoff per video | Every tool video carries a `deliverable` (command / repo / steps) spoken in the final scene AND printed in the description ("🔧 Try it yourself"). No deliverable → no tool video. |
| 5 | Success metric | **Average view duration ≥ 2:00** (baseline 0:38). The single metric that decides if v3 worked, measured after 10 v3 videos. |
| 6 | Thumbnail | Screenshot-based: real UI/repo frame + 2–4 word overlay (Inter Black ~130px, white on #DC2626) + red baseline. Person-cutout retired for tool videos. |
| 7 | Blocked-day fallback | FACTCHECK/ADVICE/POLICY block on an automatic run → immediately retry the day as a forced evergreen instead of publishing nothing. (8 of the last 20 runs died at this gate.) |
| 8 | Caption spelling | Captions display the SCRIPT's tokens, force-aligned onto whisper timings ("Haapoja", never "Hoppogja"). Only 1:1 aligned words are replaced; unequal splits keep whisper text. |
| 9 | Income before YPP | One free 1-page PDF per tool video (GitHub Pages, ₹0) + affiliate-ready description slot. |
| 10 | Channel | Keep the existing channel. No reset. |

## OUT OF SCOPE
- Higgsfield / any paid AI video generation (0 credits; screen recording is better evidence anyway)
- Instagram automation; Hindi channel; paid voice upgrade
- New channel or rebrand

## ACCEPTANCE CRITERIA (binary)
- [ ] 10 random frames of a tool video: ≥7 show real UI/code/data, not stock
- [ ] Script ≤900 words; no two scenes restate the same claim
- [ ] Final video 4:00–6:00
- [ ] Avg view duration ≥2:00 after 10 v3 videos
- [ ] A factcheck-blocked automatic run ends the day with a `PUBLISHED` ledger entry (via fallback)
- [ ] Every tool-video description contains a working deliverable link/command

## Phasing (one phase per session — see docs/PHASES.md)
- **A (this build):** signals + tool format (behind `tool_format` config flag, default OFF) +
  length cap + gate fallback + caption alignment + threshold 8. Live for news/evergreen at merge;
  tool lane stays dark until B.
- **B:** Playwright screen-recording visual provider + code cards + screenshot thumbnails +
  CI (`playwright install chromium` step) → flip `tool_format: true`. PoC already proven in Phase A session.
- **C:** deliverable PDF on GitHub Pages + affiliate slot + README/CONTENT_PLAYBOOK rewrite.

## RISKS
- Playwright adds ~2–4 min and ~300MB browser download per CI run (measure on first Phase B run).
- Tool format may be less viral than hot news — mitigated by keeping the news lane open at ≥8/10.
- GitHub search API is a proxy for the trending page (no official API); degrade to [] on failure.
