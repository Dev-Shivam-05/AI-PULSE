"""Tests for the pure, deterministic logic — the pieces that silently corrupt
content when they regress (ranking, dedup, caption timing, script validation,
policy gates). Run:  python -m pytest tests/ -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factverse import captions
from factverse.intelligence import signal_engine
from factverse import ai_pipeline as ap


# --------------------------------------------------------------- captions
def test_ts_never_emits_60_seconds():
    # 59.999s used to format as the invalid "0:00:60.00"
    assert captions._ts(59.999) == "0:01:00.00"
    assert captions._ts(0) == "0:00:00.00"
    assert captions._ts(3661.5) == "1:01:01.50"


def test_build_ass_groups_words(tmp_path):
    words = [(0.0, 0.4, "hello"), (0.45, 0.9, "world"), (3.0, 3.5, "later")]
    out = captions.build_ass(words, str(tmp_path / "t.ass"))
    text = Path(out).read_text(encoding="utf-8")
    # the >0.7s gap must split into two Dialogue lines
    assert text.count("Dialogue:") == 2
    assert "\\k" in text


# --------------------------------------------------------------- ranking
def test_is_used_short_strings_do_not_overblock():
    used = {"ai"}  # a polluted/short state entry must not block everything
    assert not signal_engine._is_used("OpenAI launches a new agent platform", used)
    assert signal_engine._is_used("ai", used)  # exact match still blocks


def test_is_used_real_titles_block_substrings():
    used = {signal_engine._norm("OpenAI launches new agent platform")}
    assert signal_engine._is_used("OpenAI Launches New Agent Platform!", used)


# --------------------------------------------------------------- script contract
def test_validate_script_rejects_thin_scripts():
    assert ap._validate_script({"scenes": [{"narration": "x", "visual_query": "y"}]}, "t") is None
    assert ap._validate_script(None, "t") is None


def test_validate_script_fills_defaults_and_sanitizes():
    s = ap._validate_script(
        {"title": "Best <AI> Video" + "!" * 200,
         "scenes": [{"narration": f"sentence {i}", "visual_query": "server room"} for i in range(6)]},
        "fallback", "https://example.com/story")
    assert s is not None
    assert "<" not in s["title"] and len(s["title"]) <= 95
    assert "https://example.com/story" in s["description"]
    assert "#AI" in s["description"]
    assert any(t == "ai" for t in s["tags"])
    assert s["scenes"][0]["scene_num"] == 1


# --------------------------------------------------------------- policy gate
def test_verbatim_overlap_detects_copying():
    src = "the quick brown fox jumps over the lazy dog every single day without fail in the morning"
    narration_copy = src + " and more words here to extend the sample text for shingles"
    assert ap.verbatim_overlap(narration_copy, src) > 0.3
    rewritten = ("a fast auburn fox regularly leaps across a sleepy hound "
                 "each morning according to the report we reviewed today entirely rephrased")
    assert ap.verbatim_overlap(rewritten, src) == 0.0


# --------------------------------------------------------------- scene sync
def test_scene_durations_tracks_word_weight():
    script = {"scenes": [{"narration": "one two three four five six seven eight nine ten"},
                         {"narration": "just two"}]}
    # 12 words spoken over 12s: 10 words -> ~10s, 2 words -> ~2s
    words = [(i * 1.0, i * 1.0 + 0.8, f"w{i}") for i in range(12)]
    # need >=20 words for the sync to engage; pad the scenes and words
    script["scenes"] *= 2
    words = [(i * 1.0, i * 1.0 + 0.8, f"w{i}") for i in range(24)]
    durs = ap.scene_durations(script, words, 24.0)
    assert durs is not None and len(durs) == 4
    assert abs(sum(durs) - 24.0) < 1.5
    assert durs[0] > durs[1]  # 10-word scene runs longer than the 2-word scene


def test_scene_durations_falls_back_on_thin_data():
    assert ap.scene_durations({"scenes": [{"narration": "hi"}]}, [(0, 1, "hi")], 1.0) is None


# --------------------------------------------------------------- chapters
def test_build_chapters_offline(monkeypatch):
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: None)
    scenes = [{"narration": f"scene number {i} talks about things"} for i in range(12)]
    starts = [i * 45.0 for i in range(12)]
    ch = ap.build_chapters({"scenes": scenes}, starts, shift=2.6)
    assert ch.startswith("Chapters:\n0:00 ")
    lines = ch.splitlines()[1:]
    assert len(lines) >= 3
    # second chapter reflects the cold-open shift (start + 2.6s intro)
    assert lines[1].split(" ")[0] != "0:00"


def test_build_chapters_needs_enough_scenes(monkeypatch):
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: None)
    assert ap.build_chapters({"scenes": [{"narration": "x"}] * 4}, [0, 1, 2, 3], 2.6) == ""


# --------------------------------------------------------------- near-duplicate guard
def test_too_similar_catches_reworded_story():
    used = {signal_engine._norm("AI Development Gets Scalable: NVIDIA & Hugging Face Partners")}
    assert signal_engine._is_used("AI Scale-Up: NVIDIA & Hugging Face Forge New Path", used)
    assert not signal_engine._is_used("Google Releases a Weather Prediction Model", used)


# --------------------------------------------------------------- state merge
def test_state_merge_unions_lists_and_logs():
    from factverse import state_merge as sm
    ours = '["topic a", "topic b"]'
    theirs = '["topic b", "topic c"]'
    merged = sm.merge_file("used_topics.json", ours, theirs)
    assert set(__import__("json").loads(merged)) == {"topic a", "topic b", "topic c"}

    log_a = '[{"timestamp": "1", "title": "x"}]'
    log_b = '[{"timestamp": "2", "title": "y"}, {"timestamp": "1", "title": "x"}]'
    merged = sm.merge_file("output/production_log.json", log_a, log_b)
    assert len(__import__("json").loads(merged)) == 2

    jl = sm.merge_file("state/runs.jsonl", '{"a":1}\n{"b":2}\n', '{"b":2}\n{"c":3}\n')
    assert jl.count("\n") == 3

    counts = sm.merge_file("state/failed_topics.json", '{"t": 2}', '{"t": 1, "u": 1}')
    d = __import__("json").loads(counts)
    assert d["t"] == 2 and d["u"] == 1


# --------------------------------------------------------------- distribution rules
def test_slots_are_spaced_and_future():
    import datetime as dt
    from factverse import scheduling as sch
    base = dt.datetime(2026, 7, 21, 13, 5, tzinfo=dt.timezone.utc)  # 18:35 IST
    slots = sch.next_slots(3, after=base)
    assert len(slots) == 3
    times = [dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
             for s in slots]
    assert times[0] > base
    for a, b in zip(times, times[1:]):
        assert (b - a).total_seconds() >= 4 * 3600


def test_distribution_violations_raise():
    import datetime as dt
    import pytest
    from factverse import scheduling as sch
    t0 = dt.datetime(2026, 7, 21, 7, 0, tzinfo=sch.IST)
    with pytest.raises(sch.PipelineViolation):
        sch.validate_distribution([t0, t0 + dt.timedelta(hours=1)])   # 1h gap
    with pytest.raises(sch.PipelineViolation):
        sch.validate_distribution([t0 + dt.timedelta(hours=5 * i) for i in range(5)])  # 5 shorts
    with pytest.raises(sch.PipelineViolation):
        sch.validate_shorts_batch(["a.mp4", "b.mp4"], ["hook one", ""])  # raw slice


def test_dialogue_segments_grouping():
    script = {"scenes": [
        {"narration": "hook line", "speaker": "host"},
        {"narration": "more host", "speaker": "host"},
        {"narration": "the facts", "speaker": "analyst"},
        {"narration": "back to host", "speaker": "host"},
    ]}
    segs = ap._dialogue_segments(script, "")
    assert segs is not None and len(segs) == 3
    assert "hook line" in segs[0][1] and "more host" in segs[0][1]
    assert segs[1][1] == "the facts"


def test_dialogue_segments_none_for_monologue():
    assert ap._dialogue_segments({"scenes": [{"narration": "x"}] * 6}, "") is None
