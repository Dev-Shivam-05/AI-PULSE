"""
v3-H: the AI debate lane (docs/spec/ai-pulse-v3h.md).

Up to five models from different labs answer one yes/no question about the day's
story, rebut each other once, and the pipeline narrates what they actually said.
Every seat is reached through its provider's OFFICIAL API — never a browser
session on a consumer account (terms, bans, CI: see DECISIONS 2026-09-26).

Every seam fails soft: a seat that errors is skipped, fewer than MIN_SEATS
answers means no debate today, and the caller falls back to the normal lane.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import time
from pathlib import Path

import requests

from factverse import config as fv
from factverse import gates
from factverse import llm

# ------------------------------------------------------------------ decisions
DEBATE_WEEKDAY = 2          # Wednesday (spec #1)
MIN_SEATS = 3               # spec #2
MAX_SEATS = 5
R1_WORDS, R2_WORDS = 70, 50  # spec #5 / #6
SOURCE_CHARS = 2500
CALL_TIMEOUT = (10, 60)     # connect, read — per call (spec #3)
DEBATE_DEADLINE_S = 240     # requests' timeout is not a deadline (CLAUDE.md): cap the whole debate
QUOTE_MIN_WORDS = 4         # spec #9
CARD_SECONDS = 6.0          # a still, like the code card (screencap.py:253); step5 loops/cuts it
PANEL_MARK = "🤖 The panel"

# OpenAI-compatible chat/completions endpoints; the key only ever goes in a header.
PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY"),
    "deepseek": ("https://api.deepseek.com/chat/completions", "DEEPSEEK_API_KEY"),
    "xai": ("https://api.x.ai/v1/chat/completions", "XAI_API_KEY"),
    "openai": ("https://api.openai.com/v1/chat/completions", "OPENAI_API_KEY"),
    "perplexity": ("https://api.perplexity.ai/chat/completions", "PERPLEXITY_API_KEY"),
    "mistral": ("https://api.mistral.ai/v1/chat/completions", "MISTRAL_API_KEY"),
}

DEFAULT_PANEL = [
    {"name": "Gemini 2.5 Flash", "lab": "Google", "provider": "gemini", "model": "gemini-2.5-flash"},
    {"name": "GPT-OSS 120B", "lab": "OpenAI", "provider": "groq", "model": "openai/gpt-oss-120b"},
    {"name": "Qwen 3.8", "lab": "Alibaba", "provider": "groq", "model": "qwen/qwen3.8-27b"},
    {"name": "Nemotron 3 Super", "lab": "NVIDIA", "provider": "openrouter",
     "model": "nvidia/nemotron-3-super-120b-a12b:free"},
    {"name": "Inkling", "lab": "Thinking Machines", "provider": "openrouter",
     "model": "thinkingmachines/inkling:free"},
]


# ------------------------------------------------------------------ panel
def _key(provider: str) -> str:
    if provider == "gemini":
        k = str(fv.GEMINI_KEY or "")
        return "" if "PASTE" in k else k
    spec = PROVIDERS.get(provider)
    return os.environ.get(spec[1], "").strip() if spec else ""


def panel() -> list[dict]:
    """Usable seats: known provider, key present, well-formed row; at most MAX_SEATS."""
    raw = fv.setting("debate_panel", None)
    rows = raw if isinstance(raw, list) and raw else DEFAULT_PANEL
    seats = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        name, lab = str(r.get("name") or "").strip(), str(r.get("lab") or "").strip()
        prov, model = str(r.get("provider") or "").strip(), str(r.get("model") or "").strip()
        if not (name and lab and model) or (prov != "gemini" and prov not in PROVIDERS):
            continue
        if not _key(prov):
            continue
        short = str(r.get("short") or name.split()[0]).strip()
        seats.append({"name": name[:40], "lab": lab[:40], "provider": prov,
                      "model": model[:120], "short": short[:24]})
        if len(seats) == MAX_SEATS:
            break
    return seats


# ------------------------------------------------------------------ text helpers
def _clean(text) -> str:
    """Model output as plain text: reasoning blocks and control characters out."""
    s = str(text or "")
    s = re.sub(r"<think>[\s\S]*?</think>", " ", s, flags=re.I)
    s = re.sub(r"<think>[\s\S]*$", " ", s, flags=re.I)        # an unclosed block
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", s)
    s = re.sub(r"[*_#`]+", "", s)                               # markdown decoration
    return re.sub(r"\s+", " ", s).strip()


def stance(text: str) -> str:
    m = re.match(r"\W*(yes|no)\b", str(text or ""), re.I)
    return m.group(1).upper() if m else "UNCLEAR"


def final_stance(text: str, fallback: str) -> str:
    m = re.search(r"final\s*:\s*\**\s*(yes|no)\b", str(text or ""), re.I)
    return m.group(1).upper() if m else fallback


def trim_words(text: str, limit: int) -> str:
    """A VERBATIM prefix of at most `limit` words: whole sentences when they fit,
    else a word cut marked with an ellipsis. Never rewords the model."""
    words = str(text or "").split()
    if len(words) <= limit:
        return " ".join(words)
    head = " ".join(words[:limit])
    m = re.search(r"^(.*[.!?])[\"')\]]?\s", head + " ")
    if m and len(m.group(1).split()) >= limit // 2:
        return m.group(1)
    return head.rstrip(",;:") + "…"


def norm(s: str) -> str:
    s = str(s or "").lower().replace("’", "'").replace("‘", "'")
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------ provider call
def _chat(seat: dict, prompt: str, max_tokens: int) -> tuple[str | None, str]:
    """(clean text, model that answered) or (None, reason). Never raises, never logs a key."""
    prov, model = seat.get("provider"), seat.get("model")
    try:
        if prov == "gemini":
            out = llm.generate_exact(prompt, model, temperature=0.7, max_tokens=max_tokens)
            txt = _clean(out)
            return (txt or None), (model if txt else "no answer")
        url, env = PROVIDERS[prov]
        key = _key(prov)
        if not key:
            return None, "no key"
        r = requests.post(url, json={"model": model, "temperature": 0.7, "max_tokens": max_tokens,
                                     "messages": [{"role": "user", "content": prompt}]},
                          headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"},
                          timeout=CALL_TIMEOUT)
        if r.status_code >= 400:
            return None, f"HTTP {r.status_code}"
        d = r.json()
        msg = ((d.get("choices") or [{}])[0].get("message") or {}) if isinstance(d, dict) else {}
        txt = _clean(msg.get("content"))
        return (txt or None), str(d.get("model") or model)[:120]
    except Exception as e:  # noqa: BLE001 — a seat must never cost the day
        # the type only: requests quotes the URL in its messages, and some
        # providers accept keys in URLs — never print the message itself
        return None, type(e).__name__


# ------------------------------------------------------------------ question
def pick_question(cands: list[dict], fetch) -> dict | None:
    """Turn one of the day's top stories into a yes/no question; ground it.
    `fetch(url) -> str` is the pipeline's own page fetcher (no import cycle)."""
    top = [c for c in (cands or []) if isinstance(c, dict) and c.get("title")][:3]
    if not top:
        return None
    listing = "\n".join(f"{i + 1}. {c['title']}  ({c.get('source', '')})" for i, c in enumerate(top))
    d = llm.generate_json(
        f"You pick today's debate for {fv.CHANNEL_NAME}, a channel where AI models debate one "
        f"question.\nSTORIES:\n{listing}\n\n"
        "For each story, write the ONE yes/no question about AI that informed people genuinely "
        "disagree on and that the story itself informs. Never politics, elections, religion, "
        "health, finance or legal advice. Rank them, best debate first.\n"
        'Return ONLY JSON {"picks":[{"n":1,"question":"Will ...?"}]}', temperature=0.4)
    picks = d.get("picks") if isinstance(d, dict) else None
    for p in picks if isinstance(picks, list) else []:
        if not isinstance(p, dict):
            continue
        try:
            n = int(p.get("n", 0))
        except (TypeError, ValueError):
            continue
        q = re.sub(r"\s+", " ", str(p.get("question") or "")).strip()
        if not (1 <= n <= len(top)) or not (20 <= len(q) <= 160) or not q.endswith("?"):
            continue
        story = top[n - 1]
        if gates.sensitive_topic_risk(q, story["title"]):
            continue
        text = str(fetch(story.get("url", "")) or "")
        if len(text) < gates.FACTCHECK_MIN_CHARS:
            print(f"     ↻ debate grounding too thin ({len(text)} chars) — next story.")
            continue
        return {"question": q, "title": story["title"], "url": story.get("url", ""),
                "source": story.get("source", ""), "grounding": text}
    return None


# ------------------------------------------------------------------ the debate
def _r1_prompt(seat: dict, q: dict) -> str:
    return (f"You are {seat['name']}, an AI model made by {seat['lab']}, in a short public debate "
            f"for a YouTube channel.\nQUESTION: {q['question']}\n"
            f"SOURCE (the facts you may use):\n{q['grounding'][:SOURCE_CHARS]}\n\n"
            f"Answer with YES or NO as your very first word. Then give your single strongest "
            f"argument in at most {R1_WORDS} words. Use facts from the SOURCE; if you rely on "
            f"general knowledge, say so. Do not give advice to viewers. Plain text only.")


def _r2_prompt(seat: dict, q: dict, mine: str, others: list[dict]) -> str:
    said = "\n".join(f"- {o['name']} ({o['lab']}): {o['r1']}" for o in others)
    return (f"You are {seat['name']} (made by {seat['lab']}) in the same debate.\n"
            f"QUESTION: {q['question']}\nYOUR FIRST ANSWER: {mine}\n"
            f"THE OTHER DEBATERS SAID:\n{said}\n\n"
            f"Rebut the strongest argument that disagrees with you (if everyone agrees, the "
            f"weakest point among them) in at most {R2_WORDS} words. End with exactly "
            f"'FINAL: YES' or 'FINAL: NO'. Plain text only.")


def run_debate(q: dict, seats: list[dict] | None = None) -> dict | None:
    """Two rounds across the panel. None when fewer than MIN_SEATS answer round 1."""
    if not isinstance(q, dict) or not q.get("question"):
        return None
    seats = panel() if seats is None else seats
    if len(seats) < MIN_SEATS:
        print(f"  ↷ debate panel has {len(seats)} usable seat(s) — need {MIN_SEATS}.")
        return None
    t0 = time.monotonic()
    answered = []
    for seat in seats:
        if time.monotonic() - t0 > DEBATE_DEADLINE_S:
            print("  ⏱️ debate deadline reached — no more seats this round.")
            break
        txt, served = _chat(seat, _r1_prompt(seat, q), 300)
        if not txt:
            print(f"  ↷ seat {seat['name']} skipped: {served}")
            continue
        answered.append(dict(seat, served=served, r1=txt, stance=stance(txt), r2="", final=""))
    if len(answered) < MIN_SEATS:
        print(f"  ↷ only {len(answered)} seat(s) answered — need {MIN_SEATS}; no debate today.")
        return None
    for seat in answered:
        seat["final"] = seat["stance"]
        if time.monotonic() - t0 > DEBATE_DEADLINE_S:
            continue
        others = [o for o in answered if o is not seat]
        txt, _ = _chat(seat, _r2_prompt(seat, q, seat["r1"], others), 250)
        if txt:
            seat["r2"] = txt
            seat["final"] = final_stance(txt, seat["stance"])
    print("  🥊 Debate: " + ", ".join(f"{s['short']} {s['final']}" for s in answered))
    return {"question": q["question"], "date": _dt.date.today().isoformat(),
            "story": {"title": q.get("title", ""), "url": q.get("url", ""),
                      "source": q.get("source", "")},
            "seats": answered}


def split(t: dict) -> tuple[int, int]:
    finals = [s.get("final") for s in (t or {}).get("seats") or []]
    return finals.count("YES"), finals.count("NO")


def transcript_text(t: dict) -> str:
    lines = [f"DEBATE TRANSCRIPT ({t.get('date', '')}) — QUESTION: {t.get('question', '')}"]
    for s in t.get("seats") or []:
        lines.append(f"{s['name']} ({s['lab']}), round 1: {s.get('r1', '')}")
        if s.get("r2"):
            lines.append(f"{s['name']} ({s['lab']}), round 2: {s['r2']}")
    return "\n".join(lines)


def panel_block(t: dict) -> str:
    names = " · ".join(f"{s['name']} ({s['lab']})" for s in t.get("seats") or [])
    return (f"{PANEL_MARK}: {names}\nEach answered through its official API on {t.get('date', '')}; "
            f"quotes are trimmed, never reworded. The models' opinions are not advice.")


_QUOTE = re.compile(r"[\"“]([^\"“”]{6,600})[\"”]")


def fabricated_quotes(script: dict) -> list[str]:
    """Quoted spans (>= QUOTE_MIN_WORDS words) in the narration that no seat said."""
    t = script.get("debate") if isinstance(script, dict) else None
    if not isinstance(t, dict):
        return []
    said = [norm(s.get(k, "")) for s in t.get("seats") or [] for k in ("r1", "r2") if s.get(k)]
    # quoting the question itself (or the story's headline) is not putting words in a model's mouth
    said += [norm(t.get("question", "")), norm((t.get("story") or {}).get("title", ""))]
    bad = []
    for sc in script.get("scenes") or []:
        for span in _QUOTE.findall(str(sc.get("narration", ""))):
            n = norm(span)
            if len(n.split()) >= QUOTE_MIN_WORDS and not any(n in s for s in said):
                bad.append(span.strip()[:120])
    return bad


# ------------------------------------------------------------------ cards
def _wrap(text: str, font, budget: float, max_lines: int):
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("L", (8, 8)))
    lines, cur = [], ""
    words = str(text or "").split()
    for i, w in enumerate(words):
        trial = f"{cur} {w}".strip()
        if cur and d.textlength(trial, font=font) > budget:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                lines[-1] = lines[-1].rstrip(",;:") + "…"
                return lines
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines[:max_lines]


def _canvas(W: int, H: int):
    from PIL import Image
    from factverse import infographics as ig
    col = Image.new("RGB", (1, H))          # one column, stretched: the stat card's gradient
    for y in range(H):
        t = y / max(1, H - 1)
        col.putpixel((0, y), tuple(int(ig.NAVY_TOP[i] + (ig.NAVY_BOT[i] - ig.NAVY_TOP[i]) * t)
                                   for i in range(3)))
    return col.resize((W, H))


def render_quote_card(seat: dict, date: str, out_png: str, W: int = 1280, H: int = 720) -> str | None:
    try:
        from PIL import ImageDraw
        from factverse import branding as br
        from factverse import infographics as ig
        img = _canvas(W, H)
        d = ImageDraw.Draw(img)
        x = int(W * 0.035)
        chip_f = br._font(int(H * 0.045))
        chip = f"{seat['name']} · {seat['lab']}"
        cw = d.textlength(chip, font=chip_f)
        cy = int(H * 0.075)
        ch = int(H * 0.045) + 24
        d.rounded_rectangle([x, cy, x + cw + 40, cy + ch], radius=16, fill=ig.NAVY_BOT)
        d.text((x + 20, cy + 10), chip, font=chip_f, fill=br.CYAN)
        st_size, st_f = br.fit_font(br._font, [seat.get("final") or "UNCLEAR"], int(H * 0.16), W - 2 * x)
        sy = cy + ch + 30
        fin = seat.get("final") or "UNCLEAR"
        # the scoreboard's colours, so a stance reads the same on every card
        d.text((x, sy), fin, font=st_f, fill={"YES": ig.YELLOW, "NO": br.CYAN}.get(fin, br.SUBT))
        q_f = br._font(int(H * 0.06))
        qy = sy + st_size + 30
        room = int(H * 0.88) - qy
        max_lines = max(1, room // (int(H * 0.06) + 26))
        # the stance is already on the card in yellow; trimming its echo ("Yes. …")
        # is a cut, not a rewording — the rest stays verbatim
        r1 = str(seat.get("r1", ""))
        quote = trim_words(re.sub(r"^\W*(yes|no)\b[\s.,;:!—-]*", "", r1, flags=re.I) or r1,
                           R1_WORDS)
        for i, line in enumerate(_wrap(f"“{quote}”", q_f, W - 2 * x, max_lines)):
            d.text((x, qy + i * (int(H * 0.06) + 26)), line, font=q_f, fill=br.WHITE)
        d.text((x, H - int(H * 0.075)), f"via official API · {date}", font=br._font(int(H * 0.035)),
               fill=br.SUBT)
        img.save(out_png)
        return out_png
    except Exception as e:  # noqa: BLE001
        print(f"   ⚠️ quote card failed: {type(e).__name__}")
        return None


def render_scoreboard(t: dict, out_png: str, W: int = 1280, H: int = 720) -> str | None:
    try:
        from PIL import ImageDraw
        from factverse import branding as br
        from factverse import infographics as ig
        img = _canvas(W, H)
        d = ImageDraw.Draw(img)
        x = int(W * 0.035)
        row = int(H * 0.06)
        q_f = br._font(row)
        y = int(H * 0.075)
        for line in _wrap(t.get("question", ""), q_f, W - 2 * x, 2):
            d.text((x, y), line, font=q_f, fill=br.WHITE)
            y += row + 26
        y += 20
        colour = {"YES": ig.YELLOW, "NO": br.CYAN}
        for s in (t.get("seats") or [])[:MAX_SEATS]:
            d.text((x, y), s["name"], font=q_f, fill=br.WHITE)
            fin = s.get("final") or "UNCLEAR"
            fw = d.textlength(fin, font=q_f)
            d.text((W - x - fw, y), fin, font=q_f, fill=colour.get(fin, br.SUBT))
            y += row + 26
        yes, no = split(t)
        d.text((x, H - int(H * 0.075)), f"{yes} YES · {no} NO — via official APIs · {t.get('date', '')}",
               font=br._font(int(H * 0.035)), fill=br.SUBT)
        img.save(out_png)
        return out_png
    except Exception as e:  # noqa: BLE001
        print(f"   ⚠️ scoreboard card failed: {type(e).__name__}")
        return None


def _clip(png: str | None, mp4: str) -> str | None:
    from factverse import screencap
    if png and screencap._ffmpeg(screencap._still_args(png, mp4, CARD_SECONDS)) \
            and Path(mp4).exists() and Path(mp4).stat().st_size > 1000:
        return mp4
    return None


def inject_cards(script: dict, scene_clips: list) -> int:
    """Scoreboard leads the hook and the final scene; each seat's quote card
    leads the first middle scene that names it (mirrors inject_code_card)."""
    from factverse import screencap
    t = script.get("debate") if isinstance(script, dict) else None
    if not isinstance(t, dict) or not scene_clips:
        return 0
    placed = 0
    board = _clip(render_scoreboard(t, str(fv.TEMP / "debate_board.png")),
                  str(fv.TEMP / "debate_board.mp4"))
    if board:
        screencap._lead_with(scene_clips[0], board)
        screencap._lead_with(scene_clips[-1], board)
        placed += 2
    scenes = script.get("scenes") or []
    for k, seat in enumerate(t.get("seats") or []):
        pat = re.compile(rf"(?<![\w-]){re.escape(seat.get('short', ''))}(?![\w-])", re.I)
        for i in range(1, min(len(scenes), len(scene_clips)) - 1):
            if seat.get("short") and pat.search(str(scenes[i].get("narration", ""))):
                clip = _clip(render_quote_card(seat, t.get("date", ""),
                                               str(fv.TEMP / f"debate_seat{k}.png")),
                             str(fv.TEMP / f"debate_seat{k}.mp4"))
                if clip:
                    screencap._lead_with(scene_clips[i], clip)
                    placed += 1
                break
    if placed:
        print(f"  🥊 {placed} debate card(s) placed")
    return placed
