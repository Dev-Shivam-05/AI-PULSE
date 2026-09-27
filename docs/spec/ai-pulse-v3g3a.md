# Spec — v3-G.3a: honest Shorts titles

Status: **decided 2026-09-26** under the owner's standing instruction for this session ("implement
everything, do not stop"). Every value below was chosen by Claude and is **revisable**: change a
row, not the code. Built on `v3-phase-g3`, which is stacked on `v3-phase-g`.

## Why

The Studio screenshots of 2026-09-26 show a 0.08% subscribe rate. The Shorts carry titles like
"Unlock LLM Secrets: 1 Billion Power!", "Mind-Blowing LLMs: Billions of Brains!",
"AI MELTDOWN! ChatGPT, Grok, Claude DOWN!", "Meta Muse AI EXPOSED" and "AI Breaks Free! NO
Investigation!".

Root cause: `scripts/factverse_engine.py:step8_meta` literally asks the model for titles
"with #Shorts + power words". The repo's own Shorts-hook prompt (`find_best_moments`) already
says "a builder audience discounts hype words like 'insane'/'game-changing' instantly". The two
prompts contradict each other, and the hype one writes the titles. A ToolDojo viewer who taps
"MELTDOWN" and gets an explainer has no reason to subscribe.

## Decisions

| # | Decision | Value |
|---|----------|-------|
| 1 | The prompt | `step8_meta` asks for titles that name the concrete thing the clip shows (the model, tool, company or number), **≤ 70 characters including " #Shorts"**, with no hype words, never all-caps words, and never a claim the clip does not make. The rest of the prompt is unchanged. |
| 2 | The screen | `gates.hype_terms(title)` returns the hype terms a title contains, matched case-insensitively on word boundaries: `mind-blowing`, `mind blowing`, `exposed`, `meltdown`, `unleashed`, `unlock`, `secret`, `secrets`, `shocking`, `insane`, `game-changing`, `game changer`, `won't believe`, `breaks free`, `jaw-dropping`, `crazy`, `nobody is talking`, `blow your mind`. The first eight come from this channel's own published titles; the rest come from the hook prompt's own examples and their common variants. |
| 3 | The fallback | In `normalize_shorts_meta` (before upload — the safe zone), a title with any hype term, or a missing one, is replaced by **that Short's own hook text + " #Shorts"**. The hook is the 4–7-word, fact-checked `hook_text` from `find_best_moments`, recorded by `make_shorts` in `shorts.last_hooks`. With no hook it falls back to today's `"<long title> Part N #Shorts"`. |
| 4 | Log | `✂️ Shorts title had hype (<terms>) — using its hook: "<hook> #Shorts"`. |
| 5 | Kill switch | `"honest_titles": true` in `config.json` and `config.example.json`. |

## Acceptance criteria

- [ ] Tests:
  - `hype_terms` on the channel's five real titles above (each caught) and on five clean
    titles (none caught);
  - word boundaries (`secretary` does not count as `secret`);
  - the fallback uses the hook, and "Part N" when there is no hook;
  - the flag off → no change;
  - the `step8_meta` prompt no longer contains "power words".
- [ ] Full suite green; branch pushed.

## Out of scope

Long-form titles and thumbnails (they already follow the entity-first contract and carry no hype
terms in the ledger). The viral judge's rubric (news now needs 10/10 after v3-B.1, so it rarely
writes a title). A CTR experiment on titles (it needs the impressions data, see Now #7).
