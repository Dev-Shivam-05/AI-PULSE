"""v3-B original-visuals engine: screen-record the tool's real page.

For kind="tool" videos the visual source is the tool itself — a headless-Chromium
recording of its GitHub repo / HF model / Product Hunt page (1920x1080, dark),
cut into sequential per-scene clips so the video progresses down the page —
plus a Pygments code card for the deliverable and the page screenshot for the
thumbnail. Replaces Pexels stock entirely when it succeeds; every entry point
fails soft (returns None) so the caller can fall back to stock.

Import rule: this module is imported by ai_pipeline at module level, and CI's
test job installs neither playwright nor a browser — so playwright and pygments
are ONLY imported inside the functions that use them (same pattern as
faster_whisper in captions.py).
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from factverse import config as fv

REC_W, REC_H = 1920, 1080     # record above delivery size; engine scales to 720p
HEAD_TRIM = 2.5               # first seconds of every recording are page-load blank
MIN_SEG = 4.0                 # a scene clip shorter than this reads as a glitch
REC_MIN, REC_MAX = 60.0, 300.0
WPS = 2.4                     # observed narration pace, words per second


# ------------------------------------------------------------- pure planners
def estimate_video_seconds(script: dict, wps: float = WPS) -> float:
    """Size the recording to the video we are about to make (script exists
    before visuals are fetched), so per-scene chunks rarely need looping."""
    words = sum(len(str(sc.get("narration", "")).split())
                for sc in (script.get("scenes") or []))
    if words <= 0:
        return REC_MIN
    return max(REC_MIN, min(REC_MAX, words / wps))


def segment_plan(total_seconds: float, n_scenes: int,
                 min_len: float = MIN_SEG) -> list[tuple[float, float]]:
    """Split [0, total] into up to n_scenes sequential (start, length) chunks.
    A short recording yields fewer, longer chunks (scenes then share them)."""
    if total_seconds <= 0 or n_scenes <= 0:
        return []
    k = min(n_scenes, max(1, int(total_seconds // min_len)))
    length = total_seconds / k
    return [(round(i * length, 3), round(length, 3)) for i in range(k)]


def _trim_args(src: str, dst: str, head: float = HEAD_TRIM) -> list[str]:
    return [fv.FFMPEG or "ffmpeg", "-y", "-ss", str(head), "-i", src,
            "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", dst]


def _cut_args(src: str, dst: str, start: float, length: float) -> list[str]:
    return [fv.FFMPEG or "ffmpeg", "-y", "-ss", str(start), "-i", src,
            "-t", str(length), "-an", "-c:v", "libx264", "-preset", "ultrafast",
            "-crf", "23", dst]


def _still_args(png: str, mp4: str, seconds: float) -> list[str]:
    return [fv.FFMPEG or "ffmpeg", "-y", "-loop", "1", "-i", png,
            "-t", str(seconds), "-r", "30", "-c:v", "libx264", "-preset", "fast",
            "-crf", "20", "-pix_fmt", "yuv420p", "-an", mp4]


# ------------------------------------------------------------- process seams
def _ffmpeg(args: list[str], timeout: int = 600) -> bool:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0
    except Exception as e:
        print(f"   ⚠️ ffmpeg step failed: {e}")
        return False


def _probe_duration(path: str) -> float:
    try:
        r = subprocess.run([fv.FFPROBE or "ffprobe", "-v", "error",
                            "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", path],
                           capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


# ------------------------------------------------------------- recording
def _record_page(url: str, out_dir: str, target_seconds: float) -> tuple[str, str, float]:
    """Record a slow human-style browse of `url`; returns (webm, screenshot, head)
    where head = seconds of blank page-load at the start of the recording.
    Playwright is imported here, not at module level — CI tests have no browser."""
    from playwright.sync_api import sync_playwright

    out = Path(out_dir)
    shot = str(out / "page.png")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": REC_W, "height": REC_H},
            record_video_dir=str(out),
            record_video_size={"width": REC_W, "height": REC_H},
            color_scheme="dark",
        )
        page = ctx.new_page()                # recording starts here: blank until paint
        t0 = time.monotonic()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        head = max(HEAD_TRIM, time.monotonic() - t0 + 0.3)   # slow pages: longer blank
        page.wait_for_timeout(3000)          # settle (real content, kept)
        try:
            page.screenshot(path=shot)       # thumbnail base; recording matters more
        except Exception:
            shot = ""
        deadline = time.monotonic() + target_seconds
        step = 0
        while time.monotonic() < deadline:
            try:
                at_bottom = page.evaluate(
                    "() => window.innerHeight + window.scrollY"
                    " >= document.body.scrollHeight - 80")
                if at_bottom:
                    page.evaluate("() => window.scrollTo({top: 0, behavior: 'smooth'})")
                    page.wait_for_timeout(2200)
                else:
                    page.mouse.wheel(0, 300)
                    # reading rhythm: two quick scrolls, then a longer pause
                    page.wait_for_timeout(650 if step % 3 else 1400)
            except Exception:
                page.wait_for_timeout(1000)  # keep recording even if a scroll fails
            step += 1
        ctx.close()                          # finalizes the .webm
        browser.close()
    webms = sorted(out.glob("*.webm"), key=lambda f: f.stat().st_mtime)
    if not webms:
        raise RuntimeError("no recording produced")
    return str(webms[-1]), shot, head


def capture(script: dict) -> dict | None:
    """Record the tool's page and return {'scene_clips': list[list[path]] one
    per scene, 'screenshot': png_path_or_empty}. None on any failure — the
    caller falls back to stock, and the second cron firing retries the day."""
    scenes = script.get("scenes") or []
    url = str(script.get("source_url") or "").strip()
    if not url.startswith("http"):
        url = str((script.get("deliverable") or {}).get("url", "")).strip()
    if not scenes or not url.startswith("http"):
        return None
    try:
        rec_dir = fv.TEMP / "screencap"
        shutil.rmtree(rec_dir, ignore_errors=True)
        rec_dir.mkdir(parents=True, exist_ok=True)
        webm, shot, head = _record_page(url, str(rec_dir), estimate_video_seconds(script))
        trimmed = str(rec_dir / "recording.mp4")
        if not _ffmpeg(_trim_args(webm, trimmed, head)):
            return None
        total = _probe_duration(trimmed)
        if total < MIN_SEG:
            return None
        chunks = []
        for i, (start, length) in enumerate(segment_plan(total, len(scenes))):
            dst = str(rec_dir / f"chunk_{i:03d}.mp4")
            if (_ffmpeg(_cut_args(trimmed, dst, start, length))
                    and Path(dst).exists() and Path(dst).stat().st_size > 1000):
                chunks.append(dst)
        if not chunks:
            return None
        k, n = len(chunks), len(scenes)
        scene_clips = [[chunks[min(i * k // n, k - 1)]] for i in range(n)]
        return {"scene_clips": scene_clips, "screenshot": shot}
    except Exception as e:
        print(f"   ⚠️ screen capture failed ({e}) — stock fallback.")
        return None


# ------------------------------------------------------------- code cards
def _mono_font(size: int):
    from PIL import ImageFont
    for c in [str(fv.FONTS / "JetBrainsMono-Regular.ttf"),
              "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
              "C:/Windows/Fonts/consola.ttf"]:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_code_card_png(deliverable: dict, out_png: str,
                         size: tuple[int, int] = (1280, 720),
                         font_size: int = 22) -> str | None:
    """Terminal-style card for the deliverable (Pygments bash highlighting,
    JetBrains Mono 22px per spec decision 2). Returns out_png or None."""
    from PIL import Image, ImageDraw
    from pygments import lex
    from pygments.lexers import BashLexer
    from pygments.styles import get_style_by_name

    text = str((deliverable or {}).get("text", "")).strip()
    if not text:
        return None
    W, H = size
    img = Image.new("RGB", (W, H), (13, 17, 23))
    d = ImageDraw.Draw(img)
    cx0, cy0, cx1, cy1 = int(W * 0.08), int(H * 0.18), int(W * 0.92), int(H * 0.82)
    d.rounded_rectangle([cx0, cy0, cx1, cy1], radius=16,
                        fill=(22, 27, 34), outline=(48, 54, 61), width=2)
    for j, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([cx0 + 24 + j * 34, cy0 + 22, cx0 + 40 + j * 34, cy0 + 38], fill=c)
    kind = str((deliverable or {}).get("kind", "steps"))
    label = {"command": "RUN THIS", "repo": "GET THE REPO"}.get(kind, "DO THIS")
    fnt = _mono_font(font_size)
    d.text((cx0 + 24, cy0 + 60), f"{label} — free, link in description",
           font=_mono_font(max(16, font_size - 4)), fill=(139, 148, 158))

    style = get_style_by_name("monokai")
    cw = d.textlength("M", font=fnt) or font_size * 0.6
    x0, y = cx0 + 48, cy0 + 60 + int(font_size * 2.4)
    line_h = int(font_size * 1.7)
    d.text((x0, y), "$", font=fnt, fill=(63, 185, 80))
    x = x0 + int(cw * 2)
    for tok, val in lex(text, BashLexer()):
        color = (230, 237, 243)
        try:
            s = style.style_for_token(tok)
            if s and s.get("color"):
                color = tuple(int(s["color"][i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            pass
        for piece in val.splitlines(True):
            seg = piece.rstrip("\n")
            while seg and y <= cy1 - 2 * line_h:
                room = max(1, int((cx1 - 48 - x) / cw))
                head, seg = seg[:room], seg[room:]
                d.text((x, y), head, font=fnt, fill=color)
                x += int(d.textlength(head, font=fnt))
                if seg:
                    x, y = x0, y + line_h
            if piece.endswith("\n"):
                x, y = x0, y + line_h
    url = str((deliverable or {}).get("url", "")).strip()
    if url:
        d.text((cx0 + 24, cy1 - int(font_size * 1.8)), url[:90],
               font=_mono_font(max(16, font_size - 4)), fill=(110, 118, 129))
    d.rectangle([(0, H - 8), (W, H)], fill=(220, 38, 38))  # brand baseline
    img.save(out_png)
    return out_png if Path(out_png).exists() else None


def make_code_card(deliverable: dict, out_mp4: str, seconds: float = 6.0) -> str | None:
    """Still card -> silent mp4 clip (same contract as infographics cards)."""
    try:
        png = str(Path(out_mp4).with_suffix(".png"))
        if not render_code_card_png(deliverable, png):
            return None
        if (_ffmpeg(_still_args(png, out_mp4, seconds))
                and Path(out_mp4).exists() and Path(out_mp4).stat().st_size > 1000):
            return out_mp4
    except Exception as e:
        print(f"   ⚠️ code card failed: {e}")
    return None


def _lead_with(clips: list, card: str) -> None:
    """Put the card first. A stat card already leading the scene is replaced —
    step5_build time-shares a scene equally between its clips, and a third clip
    would squeeze the command below readable length."""
    if clips and "statcard" in str(clips[0]):
        clips[0] = card
    else:
        clips.insert(0, card)


def inject_code_card(script: dict, scene_clips: list) -> int:
    """Lead the payoff scenes with the deliverable card: always the final scene
    ("the exact command is in the description"), plus the first scene after the
    hook that narrates installing/running it. Mirrors infographics.inject_cards."""
    dl = script.get("deliverable")
    if not dl or not scene_clips:
        return 0
    card = make_code_card(dl, str(fv.TEMP / "codecard.mp4"))
    if not card:
        return 0
    _lead_with(scene_clips[-1], card)
    placed = 1
    kw = ("install", "command", "clone", "pip ", "terminal", "run it", "set it up")
    scenes = script.get("scenes") or []
    for i in range(1, min(len(scenes), len(scene_clips)) - 1):   # never the hook
        if any(w in str(scenes[i].get("narration", "")).lower() for w in kw):
            _lead_with(scene_clips[i], card)
            placed += 1
            break
    return placed
