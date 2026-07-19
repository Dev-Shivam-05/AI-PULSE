"""
Provider-agnostic LLM facade with retry + model fallback.

Today this routes to Google Gemini; tomorrow swap the backend via
config.LLM_PROVIDER without touching callers. Both the pipeline engine and the
intelligence brain should call THIS, not the Gemini REST endpoint directly.

Resilience (critical for unattended multi-month operation):
  * 429 / 5xx are retried with exponential backoff (honoring Retry-After).
  * If a model is unavailable/limited, we fall back across a model chain.
"""
from __future__ import annotations

import json
import re
import time

import requests

from factverse import config as fv

_RETRYABLE = {429, 500, 502, 503, 504}
# If one model is down/limited, try the next. Order = cheapest/fastest first.
_FALLBACK_MODELS = ("gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash")


def _strip_json(text: str | None):
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    m = re.search(r"[\[{][\s\S]*[\]}]", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def _gemini_once(prompt: str, model: str, temperature: float, max_tokens: int, retries: int) -> str | None:
    """Call a single Gemini model with backoff on 429/5xx. None on give-up."""
    key = fv.GEMINI_KEY
    if not key or "PASTE" in key:
        return None
    # Key goes in a header, not the URL, so it can never leak into logged URLs.
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    for attempt in range(retries):
        try:
            r = requests.post(url, json=body, headers=headers, timeout=90)
            if r.status_code in _RETRYABLE:
                ra = r.headers.get("Retry-After")
                # Cap Retry-After so one hostile/broken response can't stall an unattended run.
                wait = min(60, int(ra)) if (ra and ra.isdigit()) else min(45, (2 ** attempt) * 5)
                time.sleep(wait)
                continue
            if r.status_code >= 400:
                # Non-retryable client error (bad key, bad request): fail fast, try next model.
                print(f"   ⚠️ Gemini {model} HTTP {r.status_code}: {r.text[:200]}")
                return None
            cands = r.json().get("candidates", [])
            if not cands:
                return None
            parts = cands[0].get("content", {}).get("parts", [])
            return parts[0].get("text") if parts else None
        except requests.RequestException:
            time.sleep(min(30, (2 ** attempt) * 3))
        except Exception:
            return None
    return None


def generate(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.85,
    max_tokens: int = 8192,
    retries: int = 3,
) -> str | None:
    """Return raw text from the configured LLM (with model fallback), or None."""
    # provider switch point (only gemini implemented today)
    models: list[str] = []
    if model:
        models.append(model)
    for m in _FALLBACK_MODELS:
        if m not in models:
            models.append(m)
    for m in models:
        out = _gemini_once(prompt, m, temperature, max_tokens, retries)
        if out:
            return out
    return None


def generate_json(prompt: str, **kw):
    """Generate and parse the first JSON object/array found in the response."""
    return _strip_json(generate(prompt, **kw))
