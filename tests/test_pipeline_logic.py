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
        {"narration": "hook line", "speaker": "a"},
        {"narration": "more host", "speaker": "a"},
        {"narration": "the facts", "speaker": "b"},
        {"narration": "back to host", "speaker": "a"},
    ]}
    segs = ap._dialogue_segments(script, "")
    assert segs is not None and len(segs) == 3
    assert "hook line" in segs[0][1] and "more host" in segs[0][1]
    assert segs[1][1] == "the facts"


def test_dialogue_segments_none_for_monologue():
    assert ap._dialogue_segments({"scenes": [{"narration": "x"}] * 6}, "") is None


# =============================================================== v3: utility pivot
# --------------------------------------------------------------- caption force-align
def test_correct_words_fixes_one_to_one_mistranscription():
    # whisper misheard the proper noun; the script is ground truth for spelling
    words = [(0.0, 0.4, "Hoppogja's"), (0.5, 0.9, "video"), (1.0, 1.4, "went"), (1.5, 1.9, "viral")]
    out = captions.correct_words(words, "Haapoja's video went viral.")
    assert out[0] == (0.0, 0.4, "Haapoja's")            # text fixed, timing untouched
    assert [w for (_, _, w) in out] == ["Haapoja's", "video", "went", "viral"]


def test_correct_words_keeps_unequal_blocks():
    # script "14MB" heard as two tokens: unequal alignment must keep whisper's text
    words = [(0.0, 0.4, "14"), (0.4, 0.9, "megabytes"), (1.0, 1.4, "model")]
    out = captions.correct_words(words, "14MB model")
    assert [w for (_, _, w) in out] == ["14", "megabytes", "model"]


def test_correct_words_adopts_script_casing():
    out = captions.correct_words([(0.0, 1.0, "openai")], "OpenAI")
    assert out[0][2] == "OpenAI"
    assert captions.correct_words([], "text") == []


# --------------------------------------------------------------- format decision
def _sig(kind="news"):
    return {"title": "OpenAI ships a new agent model", "url": "https://x.test/a", "source": "s",
            "score": 50.0, "published": "", "kind": kind, "niche": True, "fit_score": 50.0}


def test_decide_format_news_needs_8(monkeypatch):
    import datetime as dt
    monday = dt.date(2026, 8, 17)
    monkeypatch.setattr(ap.fv, "flag", lambda name, default=False: name == "tool_format")
    monkeypatch.setattr(ap, "viral_pick", lambda r: (r[0], 7.5, "angle", "hook"))
    fmt, _ = ap.decide_format(None, [_sig("tool")], today=monday)
    assert fmt == "tool"                                 # 7.5 no longer clears the bar
    monkeypatch.setattr(ap, "viral_pick", lambda r: (r[0], 8.2, "angle", "hook"))
    fmt, hint = ap.decide_format(None, [_sig("tool")], today=monday)
    assert fmt == "news" and hint[1] == 8.2


def test_decide_format_tool_lane_gated_by_flag(monkeypatch):
    import datetime as dt
    monday = dt.date(2026, 8, 17)
    monkeypatch.setattr(ap, "viral_pick", lambda r: None)
    monkeypatch.setattr(ap.fv, "flag", lambda name, default=False: False)
    fmt, _ = ap.decide_format(None, [_sig("tool")], today=monday)
    assert fmt == "evergreen"                            # flag off -> v2 behavior intact
    monkeypatch.setattr(ap.fv, "flag", lambda name, default=False: name == "tool_format")
    fmt, _ = ap.decide_format(None, [_sig("news")], today=monday)
    assert fmt == "evergreen"                            # flag on but no tool signal
    fmt, hint = ap.decide_format("tool", [])
    assert fmt == "tool" and hint is None                # forced format honored


def test_decide_format_sunday_keeps_roundup(monkeypatch):
    import datetime as dt
    monkeypatch.setattr(ap, "viral_pick", lambda r: (r[0], 9.9, "a", "h"))
    fmt, _ = ap.decide_format(None, [_sig("tool")], today=dt.date(2026, 8, 16))
    assert fmt == "roundup"


# --------------------------------------------------------------- deliverable contract
def test_validate_script_normalizes_deliverable():
    base = {"scenes": [{"narration": f"s {i}", "visual_query": "code"} for i in range(6)]}
    s = ap._validate_script({**base, "deliverable": {"kind": "command", "text": "pip install x",
                                                     "url": "https://g.test/r"}}, "t")
    assert s["deliverable"] == {"kind": "command", "text": "pip install x", "url": "https://g.test/r"}
    s = ap._validate_script({**base, "deliverable": {"text": "   "}}, "t")
    assert s["deliverable"] is None                      # blank text -> no deliverable
    s = ap._validate_script(dict(base), "t")
    assert s["deliverable"] is None                      # news/evergreen scripts unaffected


# --------------------------------------------------------------- length is a cap now
def test_enforce_max_length_cuts_padded_scripts(monkeypatch):
    long_script = {"title": "T", "thumb_text": "X", "description": "d", "tags": [],
                   "source_url": "", "format": "news",
                   "scenes": [{"narration": " ".join(["word"] * 100), "visual_query": "v"}
                              for _ in range(10)]}                     # 1000 words
    tight = {"title": "T", "thumb_text": "X", "description": "d", "tags": [],
             "scenes": [{"narration": " ".join(["word"] * 80), "visual_query": "v"}
                        for _ in range(8)]}                            # 640 words
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: dict(tight))
    out = ap.enforce_max_length(long_script, 900)
    assert sum(len(sc["narration"].split()) for sc in out["scenes"]) == 640
    assert out["format"] == "news"                       # metadata carried across the pass


def test_enforce_max_length_noop_under_cap(monkeypatch):
    called = []
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: called.append(1))
    s = {"scenes": [{"narration": "one two three four five", "visual_query": "v"}] * 5, "title": "t"}
    assert ap.enforce_max_length(s, 900) is s and not called


# === v3-B: original-visuals engine (screencap) ===============================
from factverse import screencap
from factverse import thumbnail as thumb_mod


# --------------------------------------------------------------- segment planning
def test_segment_plan_covers_recording_sequentially():
    plan = screencap.segment_plan(120.0, 12)
    assert len(plan) == 12 and plan[0] == (0.0, 10.0)
    starts = [s for s, _ in plan]
    assert starts == sorted(starts)                      # video progresses down the page
    assert abs(sum(l for _, l in plan) - 120.0) < 0.1    # nothing recorded is wasted


def test_segment_plan_short_recording_yields_fewer_chunks():
    plan = screencap.segment_plan(10.0, 12)
    assert len(plan) == 2                                # 4s minimum respected
    assert all(l >= screencap.MIN_SEG for _, l in plan)


def test_segment_plan_degenerate_inputs():
    assert screencap.segment_plan(0, 5) == []
    assert screencap.segment_plan(60, 0) == []


def test_estimate_video_seconds_tracks_words_and_clamps():
    assert screencap.estimate_video_seconds({"scenes": []}) == screencap.REC_MIN
    est = screencap.estimate_video_seconds({"scenes": [{"narration": " ".join(["w"] * 450)}]})
    assert est == 450 / screencap.WPS
    long = {"scenes": [{"narration": " ".join(["w"] * 2000)}]}
    assert screencap.estimate_video_seconds(long) == screencap.REC_MAX


# --------------------------------------------------------------- ffmpeg args (built, never run)
def test_trim_args_seek_past_blank_head():
    args = screencap._trim_args("in.webm", "out.mp4")
    assert args.index("-ss") < args.index("-i")          # page-load blank is removed
    assert args[args.index("-ss") + 1] == str(screencap.HEAD_TRIM)


def test_cut_args_carry_start_and_length():
    args = screencap._cut_args("rec.mp4", "chunk.mp4", 12.5, 8.0)
    assert args[args.index("-ss") + 1] == "12.5"
    assert args[args.index("-t") + 1] == "8.0"


# --------------------------------------------------------------- capture contract
def test_capture_rejects_missing_url_or_scenes():
    assert screencap.capture({"scenes": [], "source_url": "https://x.test"}) is None
    assert screencap.capture({"scenes": [{"narration": "n"}], "source_url": ""}) is None


def test_capture_fails_soft_when_recorder_dies(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("browser gone")
    monkeypatch.setattr(screencap.fv, "TEMP", tmp_path)
    monkeypatch.setattr(screencap, "_record_page", boom)
    s = {"scenes": [{"narration": "n"}] * 6, "source_url": "https://github.com/x/y"}
    assert screencap.capture(s) is None                  # caller falls back to stock


def test_capture_maps_chunks_onto_scenes(monkeypatch, tmp_path):
    monkeypatch.setattr(screencap.fv, "TEMP", tmp_path)
    monkeypatch.setattr(screencap, "_record_page",
                        lambda url, out, t: (str(Path(out) / "rec.webm"),
                                             str(Path(out) / "page.png"), 3.1))
    seen = []
    def fake_ffmpeg(args, timeout=600):
        seen.append(args)
        Path(args[-1]).write_bytes(b"0" * 2000)
        return True
    monkeypatch.setattr(screencap, "_ffmpeg", fake_ffmpeg)
    monkeypatch.setattr(screencap, "_probe_duration", lambda p: 120.0)
    s = {"scenes": [{"narration": "n"}] * 12, "source_url": "https://github.com/x/y"}
    out = screencap.capture(s)
    assert out and len(out["scene_clips"]) == 12
    assert all(len(c) == 1 for c in out["scene_clips"])  # same shape as step3_download
    assert out["scene_clips"][0][0].endswith("chunk_000.mp4")
    assert out["scene_clips"][-1][0].endswith("chunk_011.mp4")
    assert seen[0][seen[0].index("-ss") + 1] == "3.1"   # measured head, not the constant


def test_capture_shares_chunks_when_recording_is_short(monkeypatch, tmp_path):
    monkeypatch.setattr(screencap.fv, "TEMP", tmp_path)
    monkeypatch.setattr(screencap, "_record_page",
                        lambda url, out, t: (str(Path(out) / "rec.webm"), "", 2.5))
    def fake_ffmpeg(args, timeout=600):
        Path(args[-1]).write_bytes(b"0" * 2000)
        return True
    monkeypatch.setattr(screencap, "_ffmpeg", fake_ffmpeg)
    monkeypatch.setattr(screencap, "_probe_duration", lambda p: 10.0)   # only 2 chunks
    s = {"scenes": [{"narration": "n"}] * 12, "source_url": "",
         "deliverable": {"kind": "repo", "text": "x", "url": "https://github.com/x/y"}}
    out = screencap.capture(s)                           # deliverable URL is the fallback
    assert out and len(out["scene_clips"]) == 12
    assert out["scene_clips"][5][0].endswith("chunk_000.mp4")
    assert out["scene_clips"][6][0].endswith("chunk_001.mp4")
    assert out["screenshot"] == ""                       # no screenshot -> thumb falls back


# --------------------------------------------------------------- code cards
def test_render_code_card_png_real_render(tmp_path):
    out = tmp_path / "card.png"
    res = screencap.render_code_card_png(
        {"kind": "command", "text": "pip install factverse && factverse run demo",
         "url": "https://github.com/x/y"}, str(out))
    assert res and out.exists() and out.stat().st_size > 5000


def test_render_code_card_requires_text(tmp_path):
    assert screencap.render_code_card_png({"kind": "command", "text": "  "},
                                          str(tmp_path / "c.png")) is None


def test_inject_code_card_hits_payoff_scenes(monkeypatch):
    monkeypatch.setattr(screencap, "make_code_card", lambda dl, out, seconds=6.0: "CARD.mp4")
    script = {"deliverable": {"kind": "command", "text": "pip install x", "url": "u"},
              "scenes": [{"narration": "hook"},
                         {"narration": "you install it with one command"},
                         {"narration": "uses"},
                         {"narration": "the exact command is in the description"}]}
    clips = [["a.mp4"], ["b.mp4"], ["c.mp4"], ["d.mp4"]]
    assert screencap.inject_code_card(script, clips) == 2
    assert clips[-1][0] == "CARD.mp4" and clips[1][0] == "CARD.mp4"


def test_inject_code_card_skips_hook_and_replaces_stat_card(monkeypatch):
    monkeypatch.setattr(screencap, "make_code_card", lambda dl, out, seconds=6.0: "CARD.mp4")
    script = {"deliverable": {"kind": "command", "text": "pip install x", "url": "u"},
              "scenes": [{"narration": "install it now"},           # hook mentions install
                         {"narration": "what it is"},
                         {"narration": "the command is in the description"}]}
    clips = [["a.mp4"], ["b.mp4"], ["temp/statcard_02.mp4", "c.mp4"]]
    assert screencap.inject_code_card(script, clips) == 1   # hook never gets the card
    assert clips[0] == ["a.mp4"] and clips[1] == ["b.mp4"]
    assert clips[2] == ["CARD.mp4", "c.mp4"]             # stat card replaced, not stacked


def test_inject_code_card_noop_without_deliverable(monkeypatch):
    called = []
    monkeypatch.setattr(screencap, "make_code_card",
                        lambda *a, **k: called.append(1) or "C")
    clips = [["a"]]
    assert screencap.inject_code_card({"deliverable": None, "scenes": []}, clips) == 0
    assert not called and clips == [["a"]]


# --------------------------------------------------------------- tool thumbnail
def test_make_tool_thumb_from_screenshot(tmp_path):
    from PIL import Image
    shot = tmp_path / "page.png"
    Image.new("RGB", (1920, 1080), (30, 34, 44)).save(shot)
    out = tmp_path / "thumb.jpg"
    res = thumb_mod.make_tool_thumb(str(shot), "free ai tool", str(out))
    assert res and out.exists() and out.stat().st_size > 5000


def test_make_tool_thumb_missing_screenshot(tmp_path):
    assert thumb_mod.make_tool_thumb(str(tmp_path / "nope.png"), "x",
                                     str(tmp_path / "o.jpg")) is None


# --------------------------------------------------------------- rewrite passes keep v3 keys
def _tool_script(words_per_scene: int, n: int = 6) -> dict:
    return {"title": "T", "thumb_text": "X", "description": "d", "tags": [], "format": "tool",
            "source_url": "https://github.com/x/y", "filter_segment": True,
            "deliverable": {"kind": "command", "text": "pip install x", "url": "https://github.com/x/y"},
            "scenes": [{"narration": " ".join(["word"] * words_per_scene), "visual_query": "v"}
                       for _ in range(n)]}


def test_rewrite_passes_carry_deliverable_and_filter(monkeypatch):
    # the LLM never sees deliverable/filter_segment, so it cannot echo them back
    rewrite = {"title": "T", "thumb_text": "X", "description": "new", "tags": [],
               "scenes": [{"narration": " ".join(["word"] * 100), "visual_query": "v"}
                          for _ in range(6)]}                               # 600 words
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: dict(rewrite))
    for run_pass, wps in ((ap.critique_pass, 110),                 # 660 -> 600: accepted cut
                          (lambda s: ap.enforce_length(s, 5000), 50),   # 300 -> 600: expanded
                          (lambda s: ap.enforce_max_length(s, 100), 110)):  # 660 -> 600: tightened
        out = run_pass(_tool_script(wps))
        assert out["description"].startswith("new"), "pass should have applied"
        assert out["deliverable"]["text"] == "pip install x"
        assert out["filter_segment"] is True and out["format"] == "tool"
        assert out["source_url"] == "https://github.com/x/y"
    assert "deliverable" in ap._CARRY and "filter_segment" in ap._CARRY


def test_append_deliverable_is_idempotent():
    s = _tool_script(10)
    ap._append_deliverable(s)
    ap._append_deliverable(s)                            # advice-gate path calls it again
    assert s["description"].count("🔧 Try it yourself") == 1
    assert "pip install x" in s["description"] and "https://github.com/x/y" in s["description"]


# --------------------------------------------------------------- grounding + filter fix
def test_hf_readme_url_models_only():
    assert (ap._hf_readme_url("https://huggingface.co/org/model")
            == "https://huggingface.co/org/model/raw/main/README.md")
    assert (ap._hf_readme_url("https://huggingface.co/gpt2")
            == "https://huggingface.co/gpt2/raw/main/README.md")
    assert ap._hf_readme_url("https://github.com/org/repo") == ""


def test_validate_script_keeps_filter_marker():
    base = {"scenes": [{"narration": f"s {i}", "visual_query": "v"} for i in range(6)]}
    base["scenes"][3]["filter"] = True                   # the honest-limitation scene
    assert ap._validate_script(base, "t")["filter_segment"] is True
    plain = {"scenes": [{"narration": f"s {i}"} for i in range(6)]}
    assert ap._validate_script(plain, "t")["filter_segment"] is False
