"""
Information-dense motion graphics: animated stat-cards for abstract moments.

Generic stock footage is the weakest part of any narrated explainer. For scenes
built around a number ("54% of enterprises...", "$2 billion...", "10x faster"),
this module renders a branded stat-card clip — dark gradient, the number
counting up with easing, a one-line label, source chip — and the pipeline plays
it as that scene's lead visual. Free, offline, ~2s to render.

The card plan comes from one LLM call (which scenes deserve a card, what number,
what label); a regex fallback keeps it working when the LLM is down.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

from factverse import config as fv
from factverse import branding as br

FPS = 30
NAVY_TOP = (13, 20, 38)
NAVY_BOT = (24, 46, 92)
YELLOW = (255, 214, 10)
RED = (224, 32, 42)

_STAT_RE = re.compile(
    r"(\$ ?\d[\d,.]*|\d[\d,.]*\s?(?:%|percent|billion|million|trillion|x\b|times\b))",
    re.IGNORECASE)


def plan_cards(script: dict, max_cards: int = 4) -> list[dict]:
    """Which scenes get a stat-card. LLM plans it; regex fallback."""
    from factverse import llm
    import json as _json
    scenes = script.get("scenes", [])
    snippets = [{"n": i + 1, "text": sc.get("narration", "")[:160]}
                for i, sc in enumerate(scenes) if _STAT_RE.search(sc.get("narration", ""))]
    if not snippets:
        return []
    try:
        d = llm.generate_json(
            "These video-script snippets contain statistics. Pick the {k} MOST impactful, and for "
            "each give the stat exactly as spoken (e.g. \"54%\", \"$2B\", \"10x\") and a punchy "
            "<=7-word label a viewer reads in 2 seconds. Return ONLY JSON "
            '{{"cards":[{{"n":<scene n>,"stat":"...","label":"..."}}]}}\n'.format(k=max_cards)
            + _json.dumps(snippets, ensure_ascii=False))
        cards = []
        for c in (d or {}).get("cards", []):
            n, stat, label = int(c.get("n", 0)), str(c.get("stat", "")).strip(), str(c.get("label", "")).strip()
            if 1 <= n <= len(scenes) and stat and label:
                cards.append({"n": n, "stat": stat[:12], "label": label[:60]})
        if cards:
            return cards[:max_cards]
    except Exception as e:
        print(f"   ⚠️ card plan LLM skipped: {e}")
    # fallback: first stats found, label = trailing words of the sentence
    cards = []
    for s in snippets[:max_cards]:
        m = _STAT_RE.search(s["text"])
        if m:
            tail = s["text"][m.end():].strip().split(".")[0]
            cards.append({"n": s["n"], "stat": m.group(0).strip()[:12],
                          "label": " ".join(tail.split()[:7]) or "the number that matters"})
    return cards


def _count_seq(stat: str, t: float) -> str:
    """Ease the numeric part from 0 to its value; keep prefix/suffix fixed."""
    m = re.search(r"\d[\d,.]*", stat)
    if not m:
        return stat
    raw = m.group(0)
    try:
        val = float(raw.replace(",", ""))
    except ValueError:
        return stat
    ease = 1 - (1 - min(1.0, t)) ** 3
    cur = val * ease
    if "." in raw and val < 100:
        s = f"{cur:.1f}"
    else:
        s = f"{int(round(cur)):,}" if "," in raw or val >= 1000 else f"{int(round(cur))}"
    return stat[:m.start()] + s + stat[m.end():]


def make_card_clip(stat: str, label: str, out: str, source: str = "",
                   dur: float = 4.0, size=(1280, 720)) -> str | None:
    """Render the animated stat-card as a silent video clip."""
    W, H = size
    vertical = H > W
    fdir = fv.TEMP / f"card_fr_{abs(hash((stat, label))) % 99999}"
    if fdir.exists():
        shutil.rmtree(fdir, ignore_errors=True)
    fdir.mkdir(parents=True, exist_ok=True)
    n = int(FPS * dur)
    stat_size = int(H * (0.30 if not vertical else 0.16))
    label_size = int(H * (0.06 if not vertical else 0.035))
    try:
        em = br._alpha(br._emblem(int(H * 0.85)), 0.10)
        for i in range(n):
            t = i / (n - 1)
            img = Image.new("RGB", (W, H))
            d = ImageDraw.Draw(img)
            for y in range(0, H, 2):
                c = tuple(int(a + (b - a) * y / H) for a, b in zip(NAVY_TOP, NAVY_BOT))
                d.rectangle([(0, y), (W, y + 2)], fill=c)
            canvas = img.convert("RGBA")
            canvas.alpha_composite(em, (W - em.width + int(W * 0.12), (H - em.height) // 2))
            dd = ImageDraw.Draw(canvas, "RGBA")
            # stat count-up (fade+rise in the first 15%)
            a = min(1.0, t / 0.15)
            fstat = br._font(stat_size)
            txt = _count_seq(stat, min(1.0, t / 0.6))
            bb = dd.textbbox((0, 0), txt, font=fstat)
            sx, sy = (W - (bb[2] - bb[0])) // 2, int(H * (0.30 if not vertical else 0.34) + (1 - a) * 30)
            dd.text((sx + 6, sy + 8), txt, font=fstat, fill=(0, 0, 0, int(200 * a)))
            dd.text((sx, sy), txt, font=fstat, fill=YELLOW + (int(255 * a),))
            # label (arrives at 25%)
            la = max(0.0, min(1.0, (t - 0.22) / 0.18))
            flab = br._font(label_size)
            lb = dd.textbbox((0, 0), label, font=flab)
            lx = (W - (lb[2] - lb[0])) // 2
            ly = sy + bb[3] + int(H * 0.06)   # bb[3] = true glyph bottom incl. descender
            dd.text((lx, ly), label, font=flab, fill=(255, 255, 255, int(240 * la)))
            # source chip + brand bar
            if source:
                fs = br._font(int(label_size * 0.62))
                dd.text((int(W * 0.035), H - int(H * 0.075)), f"Source: {source}",
                        font=fs, fill=(150, 170, 205, 210))
            dd.rectangle([(0, H - 8), (int(W * min(1.0, t / 0.92)), H)], fill=RED + (255,))
            frame = canvas.convert("RGB")
            frame = ImageEnhance.Contrast(frame).enhance(1.04)
            frame.save(fdir / f"{i:04d}.png")
        r = subprocess.run([fv.FFMPEG or "ffmpeg", "-y", "-framerate", str(FPS),
                            "-i", str(fdir / "%04d.png"),
                            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                            "-pix_fmt", "yuv420p", "-an", str(out)],
                           capture_output=True, text=True, timeout=300)
        shutil.rmtree(fdir, ignore_errors=True)
        if r.returncode == 0 and Path(out).exists() and Path(out).stat().st_size > 20000:
            return str(out)
    except Exception as e:
        print(f"   ⚠️ stat-card render failed: {e}")
    return None


def inject_cards(script: dict, scene_clips: list, source_domain: str = "") -> int:
    """Render planned cards and make each one its scene's lead visual."""
    cards = plan_cards(script)
    made = 0
    for card in cards:
        i = card["n"] - 1
        if not 0 <= i < len(scene_clips):
            continue
        out = fv.TEMP / f"statcard_{card['n']:02d}.mp4"
        clip = make_card_clip(card["stat"], card["label"], str(out), source=source_domain)
        if clip:
            scene_clips[i].insert(0, clip)
            made += 1
    if made:
        print(f"  📊 {made} stat-card scene(s) generated")
    return made
