"""
9:16 Shorts builder.

Cuts each Short from the CLEAN content video (before long-form captions), reframes
to vertical, adds hook + CTA overlays, burns 9:16-SIZED live captions (so they fit
the vertical frame instead of being chopped), and wraps it with a short vertical
intro + outro.
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from factverse import config as fv
from factverse import captions as cap
from factverse import branding as br

sys.path.insert(0, str(fv.BASE / "scripts"))
import factverse_engine as eng  # noqa: E402

VW, VH = 1080, 1920


def _ff() -> str:
    return fv.FFMPEG or "ffmpeg"


def _ensure_font():
    """drawtext crashes without an explicit font on this ffmpeg (no fontconfig).
    Copy a Windows font once and reference it by relative name (cwd) to dodge the
    colon-escaping that breaks the filtergraph."""
    fdir = fv.ASSETS / "fonts"
    fdir.mkdir(parents=True, exist_ok=True)
    fp = fdir / "short.ttf"
    if not fp.exists():
        for src in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
                    "C:/Windows/Fonts/arial.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
            try:
                shutil.copy(src, str(fp))
                break
            except Exception:
                continue
    return fdir


# --------------------------------------------------------------- vertical bumpers
def _make_vintro(out):
    dur, n = 1.3, int(br.FPS * 1.3)
    fr = br._frames_dir("vintro_fr")
    logo = br._logo(int(VW * 0.84))
    for i in range(n):
        t = i / (n - 1)
        base = Image.new("RGBA", (VW, VH), br.BG + (255,))
        a = br._ease(min(1.0, t / 0.5))
        sc = 0.92 + 0.08 * a
        lg = br._alpha(logo.resize((int(logo.width * sc), int(logo.height * sc)), Image.LANCZOS), a)
        base.alpha_composite(lg, ((VW - lg.width) // 2, (VH - lg.height) // 2))
        base.convert("RGB").save(fr / f"{i:04d}.png")
    audio = br._audio("intro.mp3", dur, [
        "-f", "lavfi", "-i",
        "aevalsrc='0.2*sin(2*PI*(180+260*t)*t)*min(1,t*4)':d=1.3:s=44100"])
    br._encode(fr, audio, out, dur, VW, VH)


def _make_voutro(out):
    dur, n = 2.6, int(br.FPS * 2.6)
    fr = br._frames_dir("voutro_fr")
    logo = br._logo(int(VW * 0.72))
    sub = br._white_text("SUBSCRIBE", br._font(88))
    small = br._white_text("for daily AI news", br._font(48), color=br.SUBT)
    for i in range(n):
        t = i / (n - 1)
        base = Image.new("RGBA", (VW, VH), br.BG + (255,))
        a = br._ease(min(1.0, t / 0.3))
        base.alpha_composite(br._alpha(logo, a), ((VW - logo.width) // 2, int(VH * 0.24)))
        if t > 0.25:
            pulse = 1.0 + 0.05 * math.sin((t - 0.25) * 2 * math.pi * 2.2)
            bw, bh = int(640 * pulse), int(156 * pulse)
            bx, by = (VW - bw) // 2, int(VH * 0.46)
            ImageDraw.Draw(base).rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh // 2, fill=br.RED + (255,))
            base.alpha_composite(sub, (bx + (bw - sub.width) // 2, by + (bh - sub.height) // 2))
            base.alpha_composite(br._alpha(small, br._clamp((t - 0.35) / 0.2)),
                                 ((VW - small.width) // 2, by + bh + 40))
        base.convert("RGB").save(fr / f"{i:04d}.png")
    audio = br._audio("outro.mp3", dur, [
        "-f", "lavfi", "-i",
        "aevalsrc='0.11*sin(2*PI*261.63*t)+0.09*sin(2*PI*392.0*t)+0.07*sin(2*PI*523.25*t)':d=2.6:s=44100",
        "-af", "afade=t=in:st=0:d=0.5,afade=t=out:st=2.0:d=0.5"])
    br._encode(fr, audio, out, dur, VW, VH)


def ensure_vertical_bumpers():
    intro, outro = fv.ASSETS / "intro_v.mp4", fv.ASSETS / "outro_v.mp4"
    if not br.bumper_ok(intro):
        _make_vintro(intro)
    if not br.bumper_ok(outro):
        _make_voutro(outro)
    return intro, outro


# --------------------------------------------------------------- shorts
# Viral Shorts spec: content from frame one (NO intro bumper — the first 0.5s
# decides the swipe), <=35s (loopable), cut snapped to a real narration boundary,
# hook text over the first 3.5s, watermark branding throughout, no outro so the
# loop lands back on the hook.
MAX_SHORT = 35


def make_shorts(content_video, script, words, scene_starts=None,
                cta_text="Full video on the channel", max_count=3, tag=""):
    vdur = eng.dur(content_video)
    num_sc = len(script.get("scenes", []))
    if vdur <= 0 or num_sc <= 0:
        return []
    scene_dur = vdur / num_sc
    moments = eng.find_best_moments(script)
    brand = fv.CHANNEL_NAME
    fonts_dir = _ensure_font()
    out_shorts = []
    print(f"\n[6/10] 📱 Creating {max_count} vertical Shorts (9:16, loop-cut, no bumpers)...")

    for idx, m in enumerate(moments[:max_count]):
        sn = max(1, min(m.get("scene_num", 3), num_sc))
        hook = m.get("hook_text", "Watch this!")
        # snap to the real start of the chosen scene's narration when we have it
        if scene_starts and sn - 1 < len(scene_starts):
            start = max(0.0, float(scene_starts[sn - 1]))
        else:
            start = max(0, (sn - 1) * scene_dur)
        length = min(MAX_SHORT, vdur - start)
        if length < 15:
            start = max(0, start - 30)
            length = min(MAX_SHORT, vdur - start)
        if length < 15:
            continue
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        def _esc(t):
            return (t.replace("\\", "").replace("'", "").replace('"', "")
                     .replace(":", "\\:").replace("%", "%%"))

        # Long hooks overflow the 1080px frame — wrap to <=2 lines, ~16 chars each,
        # and scale the font down for stubborn single words.
        hwords, hlines, cur = hook.split(), [], ""
        for w_ in hwords:
            if cur and len(cur) + len(w_) + 1 > 16:
                hlines.append(cur)
                cur = w_
                if len(hlines) == 2:
                    break
            else:
                cur = f"{cur} {w_}".strip()
        if cur and len(hlines) < 2:
            hlines.append(cur)
        hsize = 64 if max((len(l) for l in hlines), default=0) <= 16 else 50
        hook_draws = "".join(
            f"drawtext=fontfile=short.ttf:text='{_esc(l)}':fontsize={hsize}:fontcolor=white:"
            f"borderw=5:bordercolor=black:x=(w-text_w)/2:y=h*0.10+{i * (hsize + 26)}:"
            f"enable='between(t,0,3.5)',"
            for i, l in enumerate(hlines))

        cta = _esc(cta_text)
        raw = fv.TEMP / f"sh_raw{tag}_{idx}.mp4"
        vf = (
            f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale={VW}:{VH},setsar=1,"
            f"{hook_draws}"
            f"drawtext=fontfile=short.ttf:text='{brand}':fontsize=42:fontcolor=white:borderw=2:bordercolor=black:x=44:y=54,"
            f"drawtext=fontfile=short.ttf:text='{cta}':fontsize=46:fontcolor=yellow:borderw=2:bordercolor=black:"
            f"x=(w-text_w)/2:y=h*0.82:enable='gt(t,{length-5})'"
        )
        # -ss BEFORE -i (input seeking): timestamps reset to 0, so the drawtext
        # enable= windows (hook first 3.5s, CTA last 6s) land where intended.
        rc = subprocess.run([_ff(), "-y", "-ss", str(start), "-i", str(content_video), "-t", str(length),
                             "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                             "-c:a", "aac", "-b:a", "128k", str(raw)],
                            cwd=str(fonts_dir), capture_output=True, text=True, timeout=600)
        if not raw.exists() or raw.stat().st_size < 10000:
            try:
                (fv.LOGS / "shorts_error.log").write_text((rc.stderr or "")[-2000:], encoding="utf-8")
            except Exception:
                pass
            print(f"    ❌ Short {idx+1} cut failed")
            continue

        # 9:16-sized live captions for just this window — this IS the final short
        # (content from frame one; the loop lands straight back on the hook)
        final = fv.SHORTS / f"short{tag}_{idx+1}_{ts}.mp4"
        done = False
        sub = [(max(0.0, s - start), max(0.0, e - start), w) for (s, e, w) in words if start <= s < start + length]
        if sub:
            ass = cap.build_ass(sub, str(fv.TEMP / f"sh{tag}_{idx}.ass"),
                                play_w=VW, play_h=VH, fontsize=68, max_words=3, margin_v=620)
            ap = Path(ass)
            r = subprocess.run([_ff(), "-y", "-i", str(raw), "-vf", f"ass={ap.name}",
                                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                                "-c:a", "copy", "-movflags", "+faststart", str(final)],
                               cwd=str(ap.parent), capture_output=True, text=True, timeout=600)
            done = r.returncode == 0 and final.exists() and final.stat().st_size > 10000
            if not done:
                try:
                    (fv.LOGS / "shorts_error.log").write_text((r.stderr or "")[-2000:], encoding="utf-8")
                except Exception:
                    pass
        if not done:
            # captions failed or no words in window — ship the hooked raw cut
            try:
                shutil.copy2(str(raw), str(final))
                done = final.exists() and final.stat().st_size > 10000
            except Exception:
                done = False
        if done:
            print(f"    ✅ {final.name}")
            out_shorts.append(str(final))
        else:
            print(f"    ⚠️ Short {idx+1} failed (see logs/shorts_error.log)")

    print(f"  ✅ {len(out_shorts)} vertical Shorts created")
    return out_shorts
