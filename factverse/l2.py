"""
L2 batch store — human editorial audio, batched weekly, injected per video.

The monetization policy's qualifying clause is "without adding the creator's
original, authentic insights or perspective". This module is the machine side
of the answer: the operator records a batch of short clips in one weekly
session (cold opens and insight blocks); the pipeline injects one of each into
every long-form video and logs the injection for the originality dossier.

Store layout (committed audio is small):
    l2_store/cold_opens/*.wav|mp3       (~15-30s each)
    l2_store/insight_blocks/*.wav|mp3   (~45-90s each)
Usage tracking in state/l2_usage.json — every clip is used at most once.

If the store is empty the pipeline continues with a loud warning and a
confidence penalty (routing to review). Set require_insight_block=true in
config.json to hard-fail instead once recording is a habit.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from factverse import config as fv
from factverse import captions

STORE = fv.BASE / "l2_store"
USAGE = fv.STATE / "l2_usage.json"
KINDS = {"cold_open": "cold_opens", "insight": "insight_blocks"}


def _usage() -> dict:
    try:
        return json.loads(USAGE.read_text(encoding="utf-8")) if USAGE.exists() else {}
    except Exception:
        return {}


def _mark_used(kind: str, name: str) -> None:
    u = _usage()
    u.setdefault(kind, []).append(name)
    USAGE.write_text(json.dumps(u, ensure_ascii=False), encoding="utf-8")


def next_clip(kind: str):
    """Oldest unused clip of the kind, or None."""
    d = STORE / KINDS[kind]
    if not d.exists():
        return None
    used = set(_usage().get(kind, []))
    clips = sorted([p for p in list(d.glob("*.wav")) + list(d.glob("*.mp3"))
                    if p.name not in used])
    return clips[0] if clips else None


def _dur(path) -> float:
    try:
        r = subprocess.run([fv.FFPROBE or "ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True, timeout=30)
        return float((r.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def build_human_segment(wav, out: str, label: str = "THE TAKE") -> str | None:
    """Render a branded segment carrying the operator's real voice: brand card
    visual + the human audio + karaoke captions (whisper-timed)."""
    from factverse import infographics as ig
    from PIL import Image, ImageDraw
    import shutil

    d = _dur(wav)
    if d < 3:
        return None
    W, H, FPS = 1280, 720, 30
    fdir = fv.TEMP / "l2_frames"
    if fdir.exists():
        shutil.rmtree(fdir, ignore_errors=True)
    fdir.mkdir(parents=True, exist_ok=True)
    from factverse import branding as br
    em = br._alpha(br._emblem(int(H * 0.5)), 0.9)
    n = int(FPS * d) + 2
    base = Image.new("RGB", (W, H))
    dd = ImageDraw.Draw(base)
    for y in range(0, H, 2):
        c = tuple(int(a + (b - a) * y / H) for a, b in zip(ig.NAVY_TOP, ig.NAVY_BOT))
        dd.rectangle([(0, y), (W, y + 2)], fill=c)
    canvas = base.convert("RGBA")
    canvas.alpha_composite(em, ((W - em.width) // 2, int(H * 0.10)))
    dd = ImageDraw.Draw(canvas, "RGBA")
    f = br._font(64)
    bb = dd.textbbox((0, 0), label, font=f)
    dd.text(((W - bb[2] + bb[0]) // 2, int(H * 0.68)), label, font=f,
            fill=(255, 214, 10, 255))
    dd.rectangle([(0, H - 8), (W, H)], fill=(224, 32, 42, 255))
    frame = canvas.convert("RGB")
    frame.save(fdir / "0000.png")
    r = subprocess.run([fv.FFMPEG or "ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS),
                        "-i", str(fdir / "0000.png"), "-i", str(wav),
                        "-t", f"{d:.2f}", "-vf", f"scale={W}:{H},setsar=1,fps={FPS}",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "21",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", str(out)], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print("   ⚠️ human segment encode failed")
        return None
    # karaoke captions from the real audio, same style as the rest of the video
    words = captions.transcribe_words(str(wav))
    if words:
        ass = captions.build_ass(words, str(fv.TEMP / "l2_seg.ass"), play_w=W, play_h=H)
        captions.burn_ass(str(out), ass)
    return str(out)


def splice(video: str, segment: str, at: float) -> str:
    """Insert `segment` into `video` at time `at` (re-encode concat, atomic)."""
    out = str(video).replace(".mp4", "_l2.mp4")
    nv = "scale=1280:720,setsar=1,fps=30"
    fc = (
        f"[0:v]split=2[c0][c1];[0:a]asplit=2[ca0][ca1];"
        f"[c0]trim=0:{at:.3f},setpts=PTS-STARTPTS,{nv}[pre];"
        f"[ca0]atrim=0:{at:.3f},asetpts=PTS-STARTPTS[prea];"
        f"[c1]trim={at:.3f},setpts=PTS-STARTPTS,{nv}[post];"
        f"[ca1]atrim={at:.3f},asetpts=PTS-STARTPTS[posta];"
        f"[1:v]{nv}[seg];"
        f"[pre][prea][seg][1:a][post][posta]concat=n=3:v=1:a=1[v][a]"
    )
    import os
    r = subprocess.run([fv.FFMPEG or "ffmpeg", "-y", "-i", str(video), "-i", str(segment),
                        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "21",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out],
                       capture_output=True, text=True, timeout=1800)
    if r.returncode == 0 and Path(out).exists() and Path(out).stat().st_size > 100000:
        os.replace(out, video)
        return video
    try:
        Path(out).unlink()
    except OSError:
        pass
    print("   ⚠️ human segment splice failed — continuing without it")
    return video


def inject(video: str, insight_at: float | None):
    """Inject this week's cold open (at the very start) and insight block (before
    the final scene). Returns (video, record) — record goes to the run ledger."""
    record = {"cold_open": None, "insight": None}
    co = next_clip("cold_open")
    if co:
        seg = build_human_segment(co, str(fv.TEMP / "l2_cold.mp4"), label=fv.CHANNEL_NAME.upper())
        if seg:
            video = splice(video, seg, 0.01)
            _mark_used("cold_open", co.name)
            record["cold_open"] = co.name
            print(f"  🎙️ Human cold open injected: {co.name}")
    ib = next_clip("insight")
    if ib and insight_at:
        seg = build_human_segment(ib, str(fv.TEMP / "l2_insight.mp4"), label="THE TAKE")
        if seg:
            # position shifts if a cold open was just prepended
            shift = _dur(fv.TEMP / "l2_cold.mp4") if record["cold_open"] else 0.0
            video = splice(video, seg, insight_at + shift)
            _mark_used("insight", ib.name)
            record["insight"] = ib.name
            print(f"  🎙️ Human insight block injected: {ib.name}")
    if not record["insight"]:
        print("  ⚠️ NO HUMAN INSIGHT BLOCK available (l2_store/insight_blocks/ is empty).")
        print("     This is the originality requirement — record a weekly batch. See docs/PROCESS.md.")
    return video, record
