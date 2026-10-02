"""llm.generate's model chain. No network: _gemini_once is stubbed (CLAUDE.md)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factverse import llm  # noqa: E402

OLD = ("gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash")


def test_old_models_keep_their_place_at_the_head_of_the_chain():
    # CI's key still uses these: the new pair must not change which model answers there
    assert llm._FALLBACK_MODELS[:3] == OLD


def test_a_new_key_falls_through_the_2x_models_to_a_current_one(monkeypatch):
    tried = []

    def fake(prompt, model, temperature, max_tokens, retries):
        tried.append(model)
        return None if model in OLD else f"answer from {model}"

    monkeypatch.setattr(llm, "_gemini_once", fake)
    assert llm.generate("hi") == "answer from gemini-3.5-flash-lite"
    assert tried == [*OLD, "gemini-3.5-flash-lite"]


def test_an_old_key_never_reaches_the_new_models(monkeypatch):
    tried = []

    def fake(prompt, model, temperature, max_tokens, retries):
        tried.append(model)
        return "ok"

    monkeypatch.setattr(llm, "_gemini_once", fake)
    assert llm.generate("hi") == "ok"
    assert tried == ["gemini-2.5-flash-lite"]
