"""
Free local voice cloning via Coqui XTTS-v2.

Clones the owner's voice from assets/voice_sample.wav and speaks any script in it.
Runs fully offline on CPU (no GPU) — quality is great, but generation is SLOW on
this hardware, so it's opt-in via config tts_provider="clone".
"""
from __future__ import annotations

import os
from pathlib import Path

from factverse import config as fv

_TTS = None
_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"


def reference() -> Path:
    return fv.ASSETS / "voice_sample.wav"


def available() -> bool:
    return reference().exists()


def _get_tts():
    global _TTS
    if _TTS is None:
        os.environ["COQUI_TOS_AGREED"] = "1"
        from TTS.api import TTS
        _TTS = TTS(_MODEL)
        try:
            _TTS.to("cpu")
        except Exception:
            pass
    return _TTS


def synth_clone(text: str, out_wav: str, language: str = "en"):
    """Speak `text` in the cloned voice. Returns out_wav path or None on failure."""
    ref = reference()
    if not ref.exists():
        print("   ⚠️ no voice_sample.wav reference — cannot clone")
        return None
    try:
        tts = _get_tts()
        tts.tts_to_file(text=text, speaker_wav=str(ref), language=language, file_path=str(out_wav))
        return out_wav
    except Exception as e:
        print(f"   ⚠️ voice clone failed: {e}")
        return None
