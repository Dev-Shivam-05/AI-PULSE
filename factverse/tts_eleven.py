"""ElevenLabs TTS seam — spec v3-E #11.

OFF by default: it activates only when the `elevenlabs_tts` flag, the
`ELEVENLABS_API_KEY` secret AND an `elevenlabs_voice_id` all exist — the
~$11 Creator-first-month run covers exactly the 10-video verdict window.
Every failure returns None so the free kokoro→edge chain runs unchanged;
this seam must never be the reason a day published nothing.
`requests` is imported inside the function per the CI-import rule.
"""
from __future__ import annotations

import base64
import os

from factverse import config as fv


def available() -> bool:
    return (fv.flag("elevenlabs_tts", False)
            and bool(os.environ.get("ELEVENLABS_API_KEY"))
            and bool(fv.setting("elevenlabs_voice_id", "")))


def _words_from_chars(chars, starts, ends):
    """Character alignment -> [(start, end, word)], the shape captions.build_ass eats."""
    words, cur, st, en = [], "", None, None
    for c, s, e in zip(chars, starts, ends):
        if str(c).strip():
            if st is None:
                st = s
            cur += c
            en = e
        elif cur:
            # the narration joins scenes with " . . . " — a lone "." is not a word,
            # and captions/scene-sync were never built to receive one.
            if any(ch.isalnum() for ch in cur):
                words.append((st, en, cur))
            cur, st = "", None
    if cur and any(ch.isalnum() for ch in cur):
        words.append((st, en, cur))
    return words


def synth(text: str, out_mp3: str):
    """(mp3_path, words) or None — None on ANY failure, per the fail-soft contract."""
    try:
        import requests
        vid = fv.setting("elevenlabs_voice_id", "")
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{vid}/with-timestamps",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": os.environ.get("ELEVENLABS_API_KEY", "")},
            json={"text": text,
                  "model_id": fv.setting("elevenlabs_model", "eleven_turbo_v2_5")},
            timeout=600)
        if r.status_code != 200:
            print(f"   ⚠️ elevenlabs HTTP {r.status_code} — falling back.")
            return None
        d = r.json()
        with open(out_mp3, "wb") as f:
            f.write(base64.b64decode(d["audio_base64"]))
        al = d.get("alignment") or {}
        words = _words_from_chars(al.get("characters") or [],
                                  al.get("character_start_times_seconds") or [],
                                  al.get("character_end_times_seconds") or [])
        return (out_mp3, words) if words else None
    except Exception as e:
        print(f"   ⚠️ elevenlabs failed ({e}) — falling back.")
        return None
