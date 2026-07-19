"""
Kokoro-82M neural TTS — the default voice (free, Apache-2.0, near-real-time on CPU).

Why Kokoro: it is by far the best fully-free TTS that runs fast enough on a
GitHub Actions runner. It replaces edge-tts as the primary voice; edge-tts stays
as the automatic fallback if Kokoro is unavailable (missing package / failed
model download). The XTTS voice clone remains a LOCAL-ONLY option — Coqui's
CPML license is non-commercial, so it must not be used on monetized uploads.

Model files (~310 MB total) download once into assets/models/ and are cached
by CI between runs. Word-level caption timing comes from faster-whisper
transcription of the finished audio (same as every other voice path).
"""
from __future__ import annotations

import re
from pathlib import Path

import requests

from factverse import config as fv

_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
_MODEL = "kokoro-v1.0.onnx"
_VOICES = "voices-v1.0.bin"
_KOKORO = None

# Chunk long scripts by sentence so we never exceed the model's input window.
_MAX_CHUNK = 350
_GAP_SECONDS = 0.18


def model_dir() -> Path:
    d = fv.ASSETS / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _download(name: str, dest: Path) -> bool:
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        print(f"   ⬇️  Downloading Kokoro model file {name} (one-time)...")
        with requests.get(f"{_RELEASE}/{name}", stream=True, timeout=900) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        tmp.replace(dest)
        return True
    except Exception as e:
        print(f"   ⚠️ Kokoro model download failed: {e}")
        try:
            tmp.unlink()
        except OSError:
            pass
        return False


def ensure_models() -> bool:
    ok = True
    for name in (_MODEL, _VOICES):
        dest = model_dir() / name
        if not dest.exists() or dest.stat().st_size < 1_000_000:
            ok = _download(name, dest) and ok
    return ok


def available() -> bool:
    try:
        import kokoro_onnx  # noqa: F401
        import soundfile    # noqa: F401
    except ImportError:
        return False
    return ensure_models()


def _get():
    global _KOKORO
    if _KOKORO is None:
        from kokoro_onnx import Kokoro
        d = model_dir()
        _KOKORO = Kokoro(str(d / _MODEL), str(d / _VOICES))
    return _KOKORO


def _chunks(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    out, cur = [], ""
    for s in sentences:
        if cur and len(cur) + len(s) + 1 > _MAX_CHUNK:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return [c for c in out if any(ch.isalnum() for ch in c)]


def synth(text: str, out_wav: str, voice: str | None = None, speed: float | None = None):
    """Synthesize `text` to out_wav in the Kokoro voice. Returns out_wav or None."""
    try:
        import numpy as np
        import soundfile as sf

        kokoro = _get()
        voice = voice or fv.KOKORO_VOICE
        speed = float(speed or fv.VOICE_SPEED)
        pieces, rate = [], 24000
        chunks = _chunks(text)
        if not chunks:
            return None
        for i, chunk in enumerate(chunks):
            samples, rate = kokoro.create(chunk, voice=voice, speed=speed, lang="en-us")
            pieces.append(samples)
            if i < len(chunks) - 1:
                pieces.append(np.zeros(int(_GAP_SECONDS * rate), dtype=samples.dtype))
        sf.write(out_wav, np.concatenate(pieces), rate)
        return out_wav
    except Exception as e:
        print(f"   ⚠️ Kokoro synthesis failed: {e}")
        return None


if __name__ == "__main__":
    print("Kokoro self-test...")
    if not available():
        print("  kokoro-onnx not installed or model download failed")
    else:
        out = synth("This is the new AI Pulse voice. Clear, natural, and completely free.",
                    str(fv.TEMP / "kokoro_test.wav"))
        print("  OK →", out if out else "FAILED")
