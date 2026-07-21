"""
Word-level voiceover + "live caption" generation.

Uses the edge-tts Python API (not the CLI) to get per-WORD timings, then builds
an ASS subtitle file with karaoke highlighting: each word lights up (cyan) exactly
as it's spoken. This is the modern, mute-friendly, high-retention caption style.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
from pathlib import Path

import edge_tts

from factverse import config as fv

_LEAD = re.compile(r"^[^0-9A-Za-z]+", re.UNICODE)
_TRAIL = re.compile(r"[^0-9A-Za-z%]+$", re.UNICODE)


def _clean_word(w: str) -> str:
    """Strip ANY leading/trailing punctuation (incl. unicode), keep a trailing %."""
    return _TRAIL.sub("", _LEAD.sub("", w or ""))


def _to_words(raw):
    """raw = list of (type, offset_s, dur_s, text). Expand to per-word (start,end,word)."""
    words = []
    for (typ, off, dur, txt) in raw:
        toks = []
        for w in txt.split():
            c = _clean_word(w)
            if any(ch.isalnum() for ch in c):
                toks.append(c)
        if not toks:
            continue
        if typ == "WordBoundary" and len(toks) == 1:
            words.append((off, off + dur, toks[0]))
            continue
        # distribute the sentence's duration across its words, weighted by length
        total = sum(len(w) for w in toks) or 1
        cur = off
        for w in toks:
            wd = dur * (len(w) / total)
            words.append((cur, cur + wd, w))
            cur += wd
    return words


def synth_with_words(text: str, voice: str, rate: str, out_mp3: str):
    """Synthesize speech AND capture per-word timings (via Word/SentenceBoundary)."""
    async def _run():
        comm = edge_tts.Communicate(text, voice, rate=rate)
        raw = []
        with open(out_mp3, "wb") as f:
            async for ch in comm.stream():
                t = ch.get("type")
                if t == "audio":
                    f.write(ch["data"])
                elif t in ("WordBoundary", "SentenceBoundary"):
                    raw.append((t, ch["offset"] / 1e7, ch["duration"] / 1e7,
                                (ch.get("text") or "").strip()))
        return raw

    try:
        return _to_words(asyncio.run(_run()))
    except Exception as e:
        print(f"   ⚠️ tts error: {e}")
        return []


_WMODEL = None


def transcribe_words(mp3: str):
    """Accurate word timings by transcribing the audio itself (free, local whisper).

    Captions derived from the real audio = perfect sync. Returns [] on any failure
    so the caller can fall back to the edge-tts estimate.
    """
    global _WMODEL
    try:
        if _WMODEL is None:
            from faster_whisper import WhisperModel
            _WMODEL = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = _WMODEL.transcribe(str(mp3), word_timestamps=True, beam_size=1)
        words = []
        for seg in segments:
            for w in (getattr(seg, "words", None) or []):
                txt = _clean_word(w.word or "")
                if any(c.isalnum() for c in txt):
                    words.append((float(w.start), float(w.end), txt))
        return words
    except Exception as e:
        print(f"   ⚠️ whisper align unavailable: {e}")
        return []


def _ts(t: float) -> str:
    # integer centiseconds first, so 59.999s can't format as the invalid "0:00:60.00"
    cs = max(0, int(round(t * 100)))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{c:02d}"


def build_ass(words, out_ass: str, play_w: int = 1280, play_h: int = 720,
              font: str = "Arial", fontsize: int = 50, max_words: int = 4,
              max_gap: float = 0.7, margin_v: int = 70) -> str:
    """Group words into short phrases and write a karaoke ASS (active word = cyan)."""
    lines, cur = [], []
    for (st, en, w) in words:
        if cur and ((st - cur[-1][1]) > max_gap or len(cur) >= max_words):
            lines.append(cur)
            cur = []
        cur.append((st, en, w))
    if cur:
        lines.append(cur)

    # ASS colours are &HAABBGGRR. Primary (active word) = gold, Secondary (pending) = white.
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_w}\nPlayResY: {play_h}\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Live,{font},{fontsize},&H0000D7FF,&H00FFFFFF,&H00101010,&H64000000,"
        f"-1,0,0,0,100,100,0,0,1,4,1,2,80,80,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text\n"
    )
    events = []
    for ln in lines:
        start = ln[0][0]
        end = ln[-1][1] + 0.10
        cursor = start
        text = ""
        for (st, en, w) in ln:
            gap = st - cursor
            if gap > 0.02:
                text += f"{{\\k{int(round(gap * 100))}}}"
            cw = _clean_word(w) or w
            text += f"{{\\k{max(1, int(round((en - st) * 100)))}}}{cw} "
            cursor = en
        events.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Live,,0,0,0,{text.strip()}")

    Path(out_ass).write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out_ass


def _citation_filters(citations, ass_dir: Path) -> str:
    """drawtext chain for on-screen source chips: [(start, end, text), ...].
    Rendered top-right during fact delivery — credibility on screen, not just in
    the description. Uses the same cwd-relative fontfile trick as the Shorts."""
    if not citations:
        return ""
    font = fv.ASSETS / "fonts" / "short.ttf"
    if not font.exists():
        return ""
    try:
        # ffmpeg needs the font reachable from the ass cwd; copy it next to the .ass
        target = ass_dir / "cite.ttf"
        if not target.exists():
            import shutil as _sh
            _sh.copy(str(font), str(target))
    except Exception:
        return ""
    parts = []
    for (st, en, text) in citations:
        t = (str(text).replace("\\", "").replace("'", "").replace('"', "")
                      .replace(":", "\\:").replace("%", "%%"))[:48]
        parts.append(
            f"drawtext=fontfile=cite.ttf:text='{t}':fontsize=26:fontcolor=white@0.85:"
            f"box=1:boxcolor=black@0.45:boxborderw=10:x=w-text_w-28:y=34:"
            f"enable='between(t,{st:.2f},{en:.2f})'")
    return "," + ",".join(parts)


def burn_ass(video: str, ass: str, citations=None) -> str:
    """Burn karaoke captions (plus optional on-screen source citations) into the
    video (cwd-relative to dodge Windows path bugs)."""
    out = str(video).replace(".mp4", "_cap.mp4")
    ap = Path(ass)
    ff = fv.FFMPEG or "ffmpeg"
    try:
        vf = f"ass={ap.name}" + _citation_filters(citations, ap.parent)
        r = subprocess.run(
            [ff, "-y", "-i", str(video), "-vf", vf,
             "-c:v", "libx264", "-preset", "fast", "-crf", "21",
             "-c:a", "copy", "-movflags", "+faststart", out],
            cwd=str(ap.parent), capture_output=True, text=True, timeout=1800)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 100000:
            os.replace(out, video)  # atomic: never leaves us with zero copies
            print("  ✅ Live captions burned!")
            return video
        try:
            (fv.LOGS / "caption_error.log").write_text((r.stderr or "")[-2000:], encoding="utf-8")
        except Exception:
            pass
    except Exception as e:
        print(f"   ⚠️ caption burn error: {e}")
    if os.path.exists(out):
        try:
            os.remove(out)
        except Exception:
            pass
    print("  ⚠️ Caption burn failed (see logs/caption_error.log) — video kept without captions")
    return video
