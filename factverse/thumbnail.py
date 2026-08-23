"""
Click-optimized thumbnail engine (person-first).

What performs on YouTube in 2026 is remarkably consistent: a real PERSON with a
readable emotional presence on one side, a 2-4 word curiosity text block on the
other, aggressive-but-clean grading. Text-only cards lose.

This module mines the video's OWN downloaded stock clips for the best
human-face frame (OpenCV Haar cascade — free, CPU, works in CI), so the person
is always content-relevant. Composition:

    [ dark gradient | HUGE 2-line text ]  [ person, right third ]
    brand chip top-left · brand-red baseline bar

Fallback chain: face frame -> most colorful/sharp frame -> None (caller then
uses the engine's text-only design).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from factverse import config as fv

W, H = 1280, 720
YELLOW = (255, 214, 10)
RED = (224, 32, 42)
NAVY_TOP = (13, 20, 38)
NAVY_BOT = (24, 46, 92)

try:
    import cv2
    import numpy as np
except Exception:  # opencv optional — module degrades to colorful-frame mode
    cv2 = None
    np = None

# Cascade failure must NOT kill frame scoring — no-face mode still beats text-only.
_CASCADE = None
if cv2 is not None:
    try:
        _c = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if not _c.empty():
            _CASCADE = _c
    except Exception:
        _CASCADE = None

# YuNet DNN face detector (230KB, one-time download) — far fewer false positives
# than Haar; Haar remains the offline fallback.
_YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
              "face_detection_yunet/face_detection_yunet_2023mar.onnx")
_yunet = None


def _get_yunet():
    global _yunet
    if _yunet is not None or cv2 is None or not hasattr(cv2, "FaceDetectorYN_create"):
        return _yunet
    try:
        import requests
        mdir = fv.ASSETS / "models"
        mdir.mkdir(parents=True, exist_ok=True)
        mpath = mdir / "face_detection_yunet_2023mar.onnx"
        if not mpath.exists() or mpath.stat().st_size < 100_000:
            r = requests.get(_YUNET_URL, timeout=120)
            r.raise_for_status()
            mpath.write_bytes(r.content)
        _yunet = cv2.FaceDetectorYN_create(str(mpath), "", (320, 320), 0.8, 0.3, 500)
    except Exception as e:
        print(f"   ⚠️ YuNet unavailable ({e}) — using Haar fallback")
        _yunet = None
    return _yunet


def _detect_faces(img, gray):
    """Return [(x, y, w, h), ...] using YuNet when possible, else Haar."""
    h, w = img.shape[:2]
    det = _get_yunet()
    if det is not None:
        try:
            det.setInputSize((w, h))
            _, faces = det.detect(img)
            if faces is None:
                return []
            return [(int(f[0]), int(f[1]), int(f[2]), int(f[3]))
                    for f in faces if float(f[-1]) >= 0.8]
        except Exception:
            pass
    if _CASCADE is not None:
        try:
            return list(_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6,
                                                  minSize=(int(h * 0.12), int(h * 0.12))))
        except Exception:
            return []
    return []


def _dur(path: str) -> float:
    try:
        r = subprocess.run([fv.FFPROBE or "ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True, timeout=30)
        return float((r.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def _grab(video: str, t: float, out: Path) -> bool:
    r = subprocess.run([fv.FFMPEG or "ffmpeg", "-y", "-ss", f"{max(0.0, t):.2f}", "-i", str(video),
                        "-vframes", "1", "-q:v", "2", str(out)],
                       capture_output=True, text=True, timeout=60)
    return r.returncode == 0 and out.exists() and out.stat().st_size > 5000


def _candidates(temp_root: Path, video: str, limit: int = 36) -> list[Path]:
    """Extract candidate frames from the run's stock clips (plus the video itself)."""
    fdir = temp_root / "thumb_frames"
    fdir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    clips = sorted(temp_root.glob("sc_*/clip_*.mp4"))
    for i, clip in enumerate(clips):
        if len(frames) >= limit:
            break
        d = _dur(str(clip))
        if d <= 0.5:
            continue
        for frac in (0.3, 0.7):
            fp = fdir / f"c{i}_{int(frac * 10)}.jpg"
            if _grab(str(clip), d * frac, fp):
                frames.append(fp)
    # a few frames from the finished video as backstop
    vd = _dur(video)
    if vd > 10:
        for j, frac in enumerate((0.15, 0.4, 0.65)):
            fp = fdir / f"v{j}.jpg"
            if _grab(video, vd * frac, fp):
                frames.append(fp)
    return frames


def _score(path: Path):
    """Return (score, face_box|None). Prefers a large, sharp, well-lit face."""
    if cv2 is None:
        return 0.0, None
    try:
        img = cv2.imread(str(path))
        if img is None:
            return 0.0, None
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        sharp = min(1.0, cv2.Laplacian(gray, cv2.CV_64F).var() / 400.0)
        bright = gray.mean() / 255.0
        light = 1.0 - abs(bright - 0.5) * 2          # punish too dark / blown out
        color = min(1.0, img.std() / 70.0)
        score = sharp + light + color
    except Exception:
        return 0.0, None

    best_face, best_area = None, 0.0
    for (x, y, fw, fh) in _detect_faces(img, gray):
        area = (fw * fh) / float(w * h)
        # want a substantial face, fully inside the frame with margin
        if 0.008 <= area <= 0.45 and x > 5 and y > 5 and x + fw < w - 5 and y + fh < h - 5:
            if area > best_area:
                best_area, best_face = area, (int(x), int(y), int(fw), int(fh))
    if best_face:
        score += 3.0 + min(1.5, best_area * 10)   # a usable face dominates the ranking
    return score, best_face


def _font(size: int):
    for fp in [str(fv.FONTS / "Montserrat-Bold.ttf"), "C:/Windows/Fonts/arialbd.ttf",
               "C:/Windows/Fonts/impact.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _fit_cover(img: Image.Image, face=None) -> Image.Image:
    """Scale to cover 1280x720; if a face is known, zoom it to real presence
    (~1/3 of frame height, like every high-CTR reference) on the right third."""
    sw, sh = img.size
    scale = max(W / sw, H / sh)
    if face:
        z = (H * 0.32) / max(1.0, face[3] * scale)
        scale *= min(max(z, 1.0), 1.9)   # cap zoom so we don't dissolve into pixels
    img = img.resize((int(sw * scale) + 1, int(sh * scale) + 1), Image.LANCZOS)
    nw, nh = img.size
    if face:
        fx = (face[0] + face[2] / 2) * scale
        x0 = int(min(max(fx - W * 0.70, 0), nw - W))
    else:
        x0 = (nw - W) // 2
    y0 = (nh - H) // 2
    if face:
        fy = (face[1] + face[3] / 2) * scale
        y0 = int(min(max(fy - H * 0.42, 0), nh - H))
    return img.crop((x0, y0, x0 + W, y0 + H))


X_EDGE = 54               # the left inset both composers already drew at
_SIZE_LADDER = (150, 118, 92)
_FIT_FLOOR, _FIT_STEP = 72, 6    # make_tool_thumb's own shrink, reused


def _headline(thumb_text: str, title: str) -> str:
    """The words to burn: thumb_text if it has any, else the title.

    thumb_text is optional (`_validate_script` never requires it) and run()
    passes `script.get("thumb_text", "")`. `_wrap_two("")` returns [], so both
    composers skipped the headline block and still saved and returned the
    image — publishing a graded photo with no text on it. A whitespace value is
    truthy, so the `or` fallbacks already in the callers never fired for it.
    """
    return " ".join(str(thumb_text or "").split()) or " ".join(str(title or "").split())


def _headline_font(lines, x_edge: int = X_EDGE, start: int | None = None):
    """Pick the ladder size for these lines, then MEASURE it against the frame.

    The ladder is keyed on character count, which is not width: "OPENAI QUIETLY
    SHIPPED A NEW REASONING MODEL" measures 1296px at the ladder's own floor of
    92px, 72px off a 1280px frame.
    """
    from factverse import branding as _br
    longest = max((len(l) for l in lines), default=0)
    if start is None:
        start = _SIZE_LADDER[0] if longest <= 9 else (
            _SIZE_LADDER[1] if longest <= 13 else _SIZE_LADDER[2])
    return _br.fit_font(_font, lines, start, W - 2 * x_edge, floor=_FIT_FLOOR, step=_FIT_STEP)


def _wrap_two(text: str) -> list[str]:
    words = text.upper().split()
    if len(words) <= 2:
        return [" ".join(words)] if words else []
    half = (len(words) + 1) // 2
    return [" ".join(words[:half]), " ".join(words[half:])]


# ------------------------------------------------------------------ creator style
# The pattern that dominates high-CTR thumbnails: person CUTOUT with a thick
# white stroke on a designed gradient background, radial glow behind the head,
# 2-line text with the key word in a filled highlight pill, small accents,
# real brand logo. All free and automatic.

def _cutout(img: Image.Image):
    """Background-removed RGBA of the person, or None if segmentation is unusable."""
    try:
        from rembg import remove
        rgba = remove(img.convert("RGB"))
        if np is None:
            return rgba
        alpha = np.asarray(rgba.getchannel("A"), dtype="float32") / 255.0
        cover = float(alpha.mean())
        if not 0.06 <= cover <= 0.85:      # nothing found, or "everything is subject"
            return None
        return rgba
    except Exception as e:
        print(f"   ⚠️ cutout unavailable: {e}")
        return None


def _person_crop(img: Image.Image, face) -> Image.Image:
    """Crop generously around the face (head + shoulders + torso to frame bottom)."""
    sw, sh = img.size
    x, y, fw, fh = face
    x0 = max(0, int(x - fw * 1.7))
    x1 = min(sw, int(x + fw + fw * 1.7))
    y0 = max(0, int(y - fh * 0.9))
    return img.crop((x0, y0, x1, sh))


def _grad_bg() -> Image.Image:
    bg = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(bg)
    for yy in range(H):
        t = yy / H
        d.line([(0, yy), (W, yy)], fill=tuple(int(a + (b - a) * t) for a, b in zip(NAVY_TOP, NAVY_BOT)))
    return bg


def _glow(bg: Image.Image, cx: int, cy: int, radius: int, color=(255, 190, 60)):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=color + (110,))
    layer = layer.filter(ImageFilter.GaussianBlur(radius // 2))
    bg.paste(layer, (0, 0), layer)
    return bg


def _stroke_and_shadow(person: Image.Image, stroke=9) -> Image.Image:
    """White outline + soft drop shadow behind the cutout (the signature look)."""
    pw, ph = person.size
    pad = stroke * 3
    canvas = Image.new("RGBA", (pw + pad * 2, ph + pad * 2), (0, 0, 0, 0))
    mask = person.getchannel("A")
    grown = mask.filter(ImageFilter.MaxFilter(stroke * 2 + 1))
    # shadow
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sh_l = Image.new("RGBA", (pw, ph), (0, 0, 0, 190))
    sh_l.putalpha(grown)
    sh.paste(sh_l, (pad + 10, pad + 12), sh_l)
    canvas = Image.alpha_composite(canvas, sh.filter(ImageFilter.GaussianBlur(9)))
    # white stroke
    st = Image.new("RGBA", (pw, ph), (255, 255, 255, 255))
    st.putalpha(grown)
    canvas.paste(st, (pad, pad), st)
    canvas.paste(person, (pad, pad), person)
    return canvas


def _accents(d: ImageDraw.ImageDraw):
    # halftone dot grid, bottom-left, subtle
    for gx in range(7):
        for gy in range(4):
            r = 5
            cx, cy = 46 + gx * 26, H - 120 + gy * 26
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=YELLOW + (46,))
    # spark accents near the text block (the "wow" marks in the references)
    for ang_dx, ang_dy in ((-26, -34), (0, -44), (26, -34)):
        x0, y0 = 630, 190
        d.line([(x0, y0), (x0 + ang_dx, y0 + ang_dy)], fill=YELLOW + (235,), width=9)


def _brand(img: Image.Image, d: ImageDraw.ImageDraw):
    logo = fv.ASSETS / "logo_icon.png"
    try:
        lg = Image.open(logo).convert("RGBA")
        lg.thumbnail((64, 64), Image.LANCZOS)
        img.paste(lg, (24, 22), lg)
        d.text((100, 36), fv.CHANNEL_NAME.upper(), font=_font(30), fill=(255, 255, 255, 235))
    except Exception:
        d.ellipse([(22, 26), (56, 60)], fill=RED + (255,))
        d.polygon([(33, 33), (33, 53), (49, 43)], fill=(255, 255, 255, 255))
        d.text((66, 30), fv.CHANNEL_NAME.upper(), font=_font(30), fill=(255, 255, 255, 235))


def _text_block(img: Image.Image, d: ImageDraw.ImageDraw, thumb_text: str):
    lines = _wrap_two(thumb_text or "")
    if not lines:
        return
    size, f = _headline_font(lines)
    line_h = size + 30
    y = H // 2 - (line_h * len(lines)) // 2 + 6
    x = X_EDGE
    for i, line in enumerate(lines):
        last = i == len(lines) - 1
        if last and len(lines) > 1:
            # key line inside a filled highlight pill — the reference pattern
            bb = d.textbbox((0, 0), line, font=f)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            pad_x, pad_y = 26, 14
            py0 = y - pad_y + bb[1]
            d.rounded_rectangle([x - pad_x, py0, x + tw + pad_x, py0 + th + pad_y * 2],
                                radius=18, fill=RED + (255,))
            d.text((x + 4, y + 5), line, font=f, fill=(0, 0, 0, 160))
            d.text((x, y), line, font=f, fill=(255, 255, 255, 255))
        else:
            for ox in range(-4, 5, 2):
                for oy in range(-4, 5, 2):
                    if ox or oy:
                        d.text((x + ox, y + oy), line, font=f, fill=(0, 0, 0, 220))
            d.text((x + 6, y + 8), line, font=f, fill=(0, 0, 0, 255))
            d.text((x, y), line, font=f, fill=(255, 255, 255, 255) if len(lines) > 1 else YELLOW + (255,))
        y += line_h


def compose_creator(frame: Path, face, thumb_text: str, out: str, title: str = "") -> str | None:
    """Cutout-person creator-style thumbnail. None if segmentation fails."""
    try:
        src = Image.open(frame).convert("RGB")
        person_src = _person_crop(src, face) if face else src
        rgba = _cutout(person_src)
        if rgba is None:
            return None
        rgba = ImageEnhance.Color(rgba).enhance(1.3)
        rgba = ImageEnhance.Contrast(rgba).enhance(1.15)
        rgba = ImageEnhance.Sharpness(rgba).enhance(1.2)

        bg = _grad_bg()
        bg = _glow(bg, int(W * 0.74), int(H * 0.36), 300)
        canvas = bg.convert("RGBA")

        person = _stroke_and_shadow(rgba)
        scale = (H * 1.02) / person.height
        person = person.resize((int(person.width * scale), int(person.height * scale)), Image.LANCZOS)
        px = int(W * 0.74 - person.width / 2)
        px = min(max(px, int(W * 0.38)), W - int(person.width * 0.55))
        canvas.alpha_composite(person, (px, H - person.height + 18))

        d = ImageDraw.Draw(canvas, "RGBA")
        _accents(d)
        _text_block(canvas, d, _headline(thumb_text, title))
        _brand(canvas, d)
        d.rectangle([(0, H - 10), (W, H)], fill=RED + (255,))

        canvas.convert("RGB").save(out, "JPEG", quality=93)
        return out
    except Exception as e:
        print(f"   ⚠️ creator-style compose failed: {e}")
        return None


def compose(frame: Path, thumb_text: str, out: str, face=None, title: str = "") -> str | None:
    try:
        img = Image.open(frame).convert("RGB")
        img = _fit_cover(img, face)
        # the grade: pop without looking fried
        img = ImageEnhance.Color(img).enhance(1.45)
        img = ImageEnhance.Contrast(img).enhance(1.22)
        img = ImageEnhance.Sharpness(img).enhance(1.25)
        img = ImageEnhance.Brightness(img).enhance(1.03)

        d = ImageDraw.Draw(img, "RGBA")
        # legibility gradient behind the text (left 58%), stronger at the edge
        for x in range(0, int(W * 0.58)):
            a = int(215 * (1 - x / (W * 0.58)) ** 1.4)
            d.rectangle([(x, 0), (x + 1, H)], fill=(6, 8, 16, a))
        # baseline brand bar + top-left brand chip
        d.rectangle([(0, H - 10), (W, H)], fill=RED + (255,))
        d.ellipse([(22, 26), (56, 60)], fill=RED + (255,))
        d.polygon([(33, 33), (33, 53), (49, 43)], fill=(255, 255, 255, 255))
        d.text((66, 30), fv.CHANNEL_NAME.upper(), font=_font(30), fill=(255, 255, 255, 235))

        lines = _wrap_two(_headline(thumb_text, title))
        if lines:
            size, f = _headline_font(lines)
            line_h = size + 18
            y = H // 2 - (line_h * len(lines)) // 2 + 10
            for i, line in enumerate(lines):
                x = X_EDGE
                for ox in range(-4, 5, 2):
                    for oy in range(-4, 5, 2):
                        if ox or oy:
                            d.text((x + ox, y + oy), line, font=f, fill=(0, 0, 0, 230))
                d.text((x + 6, y + 8), line, font=f, fill=(0, 0, 0, 255))
                d.text((x, y), line, font=f, fill=(YELLOW if i == len(lines) - 1 else (255, 255, 255)) + (255,))
                y += line_h

        img.save(out, "JPEG", quality=93)
        return out
    except Exception as e:
        print(f"   ⚠️ thumbnail compose failed: {e}")
        return None


def make(video: str, temp_root: Path, thumb_text: str, out: str, title: str = "") -> str | None:
    """Person-first thumbnail from the run's own footage. None if we can't do
    better than the engine's fallback design."""
    try:
        frames = _candidates(Path(temp_root), video)
        if not frames:
            return None
        scored = sorted((( *_score(p), p) for p in frames), key=lambda t: t[0], reverse=True)
        best_score, face, frame = scored[0]
        if best_score <= 0.8:
            return None
        kind = "person" if face else "scene"
        print(f"  🖼️ Thumbnail base: best {kind} frame (score {best_score:.1f}, {len(frames)} candidates)")
        if face:
            # creator-style cutout first; graceful fall-through to the framed style
            res = compose_creator(frame, face, thumb_text, out, title=title)
            if res:
                print("  🖼️ Creator-style cutout thumbnail composed.")
                return res
        return compose(frame, thumb_text, out, face, title=title)
    except Exception as e:
        print(f"   ⚠️ thumbnail engine failed: {e}")
        return None


# ------------------------------------------------------------------ v3 tool style
TOOL_RED = (220, 38, 38)   # spec decision 6: #DC2626, not the brand RED above


def _tool_font(size: int):
    try:
        return ImageFont.truetype(str(fv.FONTS / "Inter-Black.ttf"), size)
    except Exception:
        return _font(size)


def make_tool_thumb(screenshot: str, thumb_text: str, out: str) -> str | None:
    """v3 tool-format thumbnail (spec decision 6): the tool's REAL page frame +
    2-4 word overlay — Inter Black ~130px, white on #DC2626 — + red baseline.
    Person-cutout is retired for tool videos; caller falls back on None."""
    try:
        p = Path(screenshot or "")
        if not p.exists():
            return None
        img = Image.open(p).convert("RGB").resize((W, H), Image.LANCZOS)
        img = ImageEnhance.Contrast(img).enhance(1.15)
        img = ImageEnhance.Color(img).enhance(1.25)
        d = ImageDraw.Draw(img, "RGBA")
        y_scrim = int(H * 0.45)
        for y in range(y_scrim, H):              # legibility scrim over bottom half
            a = int(165 * ((y - y_scrim) / (H - y_scrim)))
            d.rectangle([(0, y), (W, y + 1)], fill=(0, 0, 0, a))

        words = " ".join((_headline(thumb_text, "") or "FREE AI TOOL").split()[:4])
        lines = _wrap_two(words)
        from factverse import branding as _br
        size, pad_x, pad_y, gap, x_edge = 130, 28, 10, 14, 48
        size, f = _br.fit_font(_tool_font, lines, size, W - 2 * x_edge - 2 * pad_x,
                               floor=_FIT_FLOOR, step=_FIT_STEP)
        metrics = []
        for ln in lines:
            bb = d.textbbox((0, 0), ln, font=f)
            metrics.append((ln, bb, bb[3] - bb[1]))
        total = sum(h + 2 * pad_y for _, _, h in metrics) + gap * (len(metrics) - 1)
        y = H - 12 - 26 - total                  # block sits above the baseline bar
        for ln, bb, h in metrics:
            tw = d.textlength(ln, font=f)
            d.rectangle([(x_edge, y), (x_edge + tw + 2 * pad_x, y + h + 2 * pad_y)],
                        fill=TOOL_RED + (255,))
            d.text((x_edge + pad_x, y + pad_y - bb[1]), ln, font=f,
                   fill=(255, 255, 255, 255))
            y += h + 2 * pad_y + gap
        d.rectangle([(0, H - 12), (W, H)], fill=TOOL_RED + (255,))
        img.save(out, "JPEG", quality=92)
        print("  🖼️ Tool thumbnail: real page screenshot + overlay.")
        return out if Path(out).exists() else None
    except Exception as e:
        print(f"   ⚠️ tool thumbnail failed: {e}")
        return None
