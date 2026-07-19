"""
Animated channel intro + outro (the AI Pulse brand bumpers).

- Renders frames with Pillow (pulse line draws in, logo fades up, subscribe pulse).
- Synthesizes a minimal music sting with ffmpeg lavfi (or uses a real track if you
  drop one at assets/music/intro.mp3 / outro.mp3).
- Encodes to assets/intro.mp4 and assets/outro.mp4, then concatenates
  intro + content + outro onto each finished video.

Everything is free + offline. Re-generate anytime with:  python -m factverse.branding
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from factverse import config as fv

W, H, FPS = 1280, 720, 30
BG = (9, 13, 24)
CYAN = (34, 211, 238)
BLUE = (59, 130, 246)
VIOLET = (139, 92, 246)
WHITE = (244, 247, 255)
SUBT = (150, 170, 205)
RED = (224, 32, 42)


def _ff() -> str:
    return fv.FFMPEG or "ffmpeg"


def _font(size):
    for c in ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/bahnschrift.ttf",
              "C:/Windows/Fonts/ariblk.ttf", "C:/Windows/Fonts/arialbd.ttf",
              "C:/Windows/Fonts/arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _grad(t):
    return _lerp(CYAN, BLUE, t * 2) if t < 0.5 else _lerp(BLUE, VIOLET, (t - 0.5) * 2)


def _clamp(x):
    return max(0.0, min(1.0, x))


def _ease(x):
    x = _clamp(x)
    return x * x * (3 - 2 * x)


def _alpha(img, a):
    r, g, b, al = img.split()
    al = al.point(lambda p: int(p * _clamp(a)))
    return Image.merge("RGBA", (r, g, b, al))


def _grad_text(text, font):
    tmp = ImageDraw.Draw(Image.new("L", (10, 10)))
    bb = tmp.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    mask = Image.new("L", (tw + 24, th + 30), 0)
    ImageDraw.Draw(mask).text((12 - bb[0], 12 - bb[1]), text, font=font, fill=255)
    grd = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    px = grd.load()
    for x in range(mask.size[0]):
        c = _grad(x / max(1, mask.size[0] - 1))
        for y in range(mask.size[1]):
            px[x, y] = (c[0], c[1], c[2], 255)
    out = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    out.paste(grd, (0, 0), mask)
    return out


def _white_text(text, font, color=WHITE):
    tmp = ImageDraw.Draw(Image.new("L", (10, 10)))
    bb = tmp.textbbox((0, 0), text, font=font)
    layer = Image.new("RGBA", (bb[2] - bb[0] + 24, bb[3] - bb[1] + 30), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((12 - bb[0], 12 - bb[1]), text, font=font, fill=color + (255,))
    return layer


def _pulse_pts(x0, y, w, amp):
    f = [(0.0, 0), (0.20, 0), (0.27, -0.22), (0.34, 0.14), (0.41, 0), (0.47, 0),
         (0.52, -1.0), (0.57, 0.55), (0.62, 0), (0.80, 0), (1.0, 0)]
    return [(x0 + w * fx, y + amp * fy) for fx, fy in f]


def _glow_line(base, pts, color, width, glow):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).line(pts, fill=color + (255,), width=width, joint="curve")
    base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(glow)))
    base.alpha_composite(layer)


def _emblem(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size // 2
    rr = int(size * 0.37)
    for i in range(0, 360, 2):
        c = _grad(i / 360)
        d.arc([cx - rr, cy - rr, cx + rr, cy + rr], i, i + 3, fill=c + (255,), width=max(3, int(size * 0.045)))
    w = int(size * 0.54)
    _glow_line(img, _pulse_pts(cx - w // 2, cy, w, int(size * 0.17)), BLUE, max(3, size // 90), max(5, size // 40))
    return img


def _logo(target_w, tagline=True):
    iw = 430
    img = Image.new("RGBA", (1760, 540), (0, 0, 0, 0))
    img.alpha_composite(_emblem(iw), (10, 540 // 2 - iw // 2))
    f = _font(190)
    ai = _grad_text("AI", f)
    pulse = _white_text("PULSE", f)
    midy = 540 // 2 - 40
    x = 470
    img.alpha_composite(ai, (x, midy - ai.size[1] // 2))
    x += ai.size[0] + 26
    img.alpha_composite(pulse, (x, midy - pulse.size[1] // 2))
    if tagline:
        ft = _font(50)
        tg = Image.new("RGBA", (1760, 110), (0, 0, 0, 0))
        td = ImageDraw.Draw(tg)
        tx = 482
        for ch in "AI NEWS, DECODED":
            td.text((tx, 12), ch, font=ft, fill=SUBT + (255,))
            bb = td.textbbox((0, 0), ch, font=ft)
            tx += (bb[2] - bb[0]) + 16
        img.alpha_composite(tg, (0, midy + 120))
    bb = img.getbbox()
    img = img.crop(bb)
    scale = target_w / img.width
    return img.resize((target_w, int(img.height * scale)), Image.LANCZOS)


def _encode(fr_dir, audio, out, dur, w=W, h=H):
    cmd = [_ff(), "-y", "-framerate", str(FPS), "-i", str(Path(fr_dir) / "%04d.png")]
    if audio:
        cmd += ["-i", str(audio)]
    cmd += ["-t", str(dur), "-vf", f"scale={w}:{h},setsar=1,fps=30",
            "-c:v", "libx264", "-preset", "fast", "-crf", "21", "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        # never leave a half-written bumper behind — it would poison every future video
        print(f"   ⚠️ bumper encode failed ({Path(str(out)).name})")
        try:
            Path(str(out)).unlink()
        except OSError:
            pass


def bumper_ok(path) -> bool:
    """A cached bumper is only trusted if it actually probes as a playable video."""
    p = Path(str(path))
    if not p.exists() or p.stat().st_size < 20_000:
        return False
    try:
        r = subprocess.run([fv.FFPROBE or "ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "csv=p=0", str(p)],
                           capture_output=True, text=True, timeout=30)
        return float((r.stdout or "0").strip() or 0) > 0.5
    except Exception:
        return False


def _audio(expr_file_name, dur, lavfi):
    """Use a real track if dropped in assets/music, else synth one with lavfi."""
    real = fv.MUSIC / expr_file_name
    out = fv.TEMP / (expr_file_name.replace(".mp3", ".wav"))
    if real.exists():
        subprocess.run([_ff(), "-y", "-i", str(real), "-t", str(dur), str(out)],
                       capture_output=True, text=True, timeout=120)
        return out
    subprocess.run([_ff(), "-y"] + lavfi + ["-t", str(dur), str(out)],
                   capture_output=True, text=True, timeout=120)
    return out


def _frames_dir(name):
    d = fv.TEMP / name
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    return d


def make_channel_banner(out=None):
    """YouTube channel banner: 2560x1440, all critical content inside the
    1546x423 'TV-safe' center area (what every device is guaranteed to show)."""
    out = out or (fv.ASSETS / "banner_youtube.png")
    BW, BH = 2560, 1440
    img = Image.new("RGB", (BW, BH))
    d = ImageDraw.Draw(img)
    deep = (16, 26, 48)
    for y in range(BH):
        d.line([(0, y), (BW, y)], fill=_lerp(BG, deep, y / BH))
    # faint oversized emblem, right side (texture, not content — may crop on phones)
    em = _alpha(_emblem(900), 0.14)
    img.paste(em, (BW - 760, BH // 2 - 450), em)
    # subtle pulse line across the safe area
    line = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    _glow_line(line, _pulse_pts(BW // 2 - 700, BH // 2 + 118, 1400, 60), BLUE, 6, 30)
    line = _alpha(line, 0.55)
    img.paste(line, (0, 0), line)
    # logo + promise, dead center (safe area is 1546x423 centered)
    logo = _logo(760, tagline=False)
    canvas = img.convert("RGBA")
    canvas.alpha_composite(logo, ((BW - logo.width) // 2, BH // 2 - logo.height + 30))
    ft = _font(54)
    tag = _white_text("AI NEWS, DECODED  ·  NEW VIDEO EVERY DAY", ft, color=SUBT)
    canvas.alpha_composite(tag, ((BW - tag.width) // 2, BH // 2 + 158))
    canvas.convert("RGB").save(str(out), "PNG")
    print(f"  ✅ Channel banner: {out}")
    return str(out)


def make_intro(out):
    dur = 2.6
    n = int(FPS * dur)
    fr = _frames_dir("intro_fr")
    logo = _logo(int(W * 0.60))
    baseline_y = int(H * 0.74)
    line = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _glow_line(line, _pulse_pts(0, baseline_y, W, int(H * 0.10)), BLUE, 5, 40)
    for i in range(n):
        t = i / (n - 1)
        base = Image.new("RGBA", (W, H), BG + (255,))
        rev = _ease(min(1.0, t / 0.42))
        lx = max(1, int(rev * W))
        base.alpha_composite(line.crop((0, 0, lx, H)), (0, 0))
        a = _ease(_clamp((t - 0.16) / 0.34))
        if a > 0:
            sc = 0.94 + 0.06 * a
            lg = logo.resize((int(logo.width * sc), int(logo.height * sc)), Image.LANCZOS)
            lg = _alpha(lg, a)
            rise = int((1 - a) * 28)
            base.alpha_composite(lg, ((W - lg.width) // 2, (H - lg.height) // 2 - 55 + rise))
        base.convert("RGB").save(fr / f"{i:04d}.png")
    audio = _audio("intro.mp3", dur, [
        "-f", "lavfi", "-i",
        "aevalsrc='0.20*sin(2*PI*(150+220*t)*t)*min(1,t*3)':d=1.5:s=44100",
        "-f", "lavfi", "-i",
        "aevalsrc='exp(-5*t)*(0.32*sin(2*PI*523.25*t)+0.22*sin(2*PI*783.99*t))':d=1.4:s=44100",
        "-filter_complex",
        "[1]adelay=1300|1300[b];[0][b]amix=inputs=2:normalize=0,afade=t=out:st=2.2:d=0.4,volume=1.3[a]",
        "-map", "[a]"])
    _encode(fr, audio, out, dur)
    return out


def make_outro(out):
    dur = 4.5
    n = int(FPS * dur)
    fr = _frames_dir("outro_fr")
    logo = _logo(int(W * 0.46), tagline=False)
    f_sub = _font(70)
    f_small = _font(40)
    sub_layer = _white_text("SUBSCRIBE", f_sub)
    small_layer = _white_text("for daily AI news", f_small, color=SUBT)
    for i in range(n):
        t = i / (n - 1)
        base = Image.new("RGBA", (W, H), BG + (255,))
        a = _ease(_clamp(t / 0.22))
        base.alpha_composite(_alpha(logo, a), ((W - logo.width) // 2, int(H * 0.15)))
        if t > 0.28:
            pulse = 1.0 + 0.05 * math.sin((t - 0.28) * 2 * math.pi * 2.2)
            bw, bh = int(460 * pulse), int(104 * pulse)
            bx, by = (W - bw) // 2, int(H * 0.52)
            d = ImageDraw.Draw(base)
            d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh // 2, fill=RED + (255,))
            s = sub_layer
            base.alpha_composite(s, (bx + (bw - s.width) // 2, by + (bh - s.height) // 2))
            sm = small_layer
            base.alpha_composite(_alpha(sm, _clamp((t - 0.35) / 0.2)),
                                 ((W - sm.width) // 2, by + bh + 26))
        base.convert("RGB").save(fr / f"{i:04d}.png")
    audio = _audio("outro.mp3", dur, [
        "-f", "lavfi", "-i",
        "aevalsrc='0.11*sin(2*PI*261.63*t)+0.09*sin(2*PI*392.0*t)+0.07*sin(2*PI*523.25*t)':d=4.5:s=44100",
        "-af", "afade=t=in:st=0:d=0.6,afade=t=out:st=3.8:d=0.6"])
    _encode(fr, audio, out, dur)
    return out


def ensure_assets(force=False):
    intro, outro = fv.ASSETS / "intro.mp4", fv.ASSETS / "outro.mp4"
    if force or not bumper_ok(intro):
        make_intro(intro)
    if force or not bumper_ok(outro):
        make_outro(outro)
    return intro, outro


def add_intro_outro(video, split_at=None):
    """Brand the video. With `split_at` (end of the hook scene, seconds) the video
    COLD-OPENS: hook scene first, then the intro sting, then the rest + outro —
    the first seconds of a viral video must be payload, never a logo.
    Returns the final path."""
    intro, outro = ensure_assets()
    if not intro.exists() or not outro.exists():
        return video
    out = str(video).replace(".mp4", "_final.mp4")
    nv = "scale=1280:720,setsar=1,fps=30"
    if split_at and float(split_at) > 2.5:
        s = float(split_at)
        fc = (
            f"[1:v]split=2[c0][c1];[1:a]asplit=2[ca0][ca1];"
            f"[c0]trim=0:{s:.3f},setpts=PTS-STARTPTS,{nv}[hook];"
            f"[ca0]atrim=0:{s:.3f},asetpts=PTS-STARTPTS[hooka];"
            f"[c1]trim={s:.3f},setpts=PTS-STARTPTS,{nv}[rest];"
            f"[ca1]atrim={s:.3f},asetpts=PTS-STARTPTS[resta];"
            f"[0:v]{nv}[vi];[2:v]{nv}[vo];"
            f"[hook][hooka][vi][0:a][rest][resta][vo][2:a]concat=n=4:v=1:a=1[v][a]"
        )
    else:
        fc = (
            f"[0:v]{nv}[v0];"
            f"[1:v]{nv}[v1];"
            f"[2:v]{nv}[v2];"
            "[v0][0:a][v1][1:a][v2][2:a]concat=n=3:v=1:a=1[v][a]"
        )
    r = subprocess.run(
        [_ff(), "-y", "-i", str(intro), "-i", str(video), "-i", str(outro),
         "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "fast", "-crf", "21",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out],
        capture_output=True, text=True, timeout=1800)
    if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 100000:
        try:
            os.remove(video)
        except Exception:
            pass
        return out
    try:
        (fv.LOGS / "branding_error.log").write_text((r.stderr or "")[-2000:], encoding="utf-8")
    except Exception:
        pass
    return video


if __name__ == "__main__":
    print("Generating intro + outro...")
    ensure_assets(force=True)
    print("Done:", fv.ASSETS / "intro.mp4", "|", fv.ASSETS / "outro.mp4")
