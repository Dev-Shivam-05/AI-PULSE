"""Tests for the pure, deterministic logic — the pieces that silently corrupt
content when they regress (ranking, dedup, caption timing, script validation,
policy gates). Run:  python -m pytest tests/ -q
"""
import json
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


def test_place_description_blocks_is_idempotent(monkeypatch):
    monkeypatch.setattr(ap.fv, "setting", lambda name, default=None: "" if name == "promo_block" else default)
    s = _tool_script(10)
    ap.place_description_blocks(s)
    ap.place_description_blocks(s)                       # advice-gate path calls it again
    assert s["description"].count("🔧 Try it yourself") == 1
    assert s["description"].count("📄 Free 1-page cheat sheet") == 1
    assert "pip install x" in s["description"] and "https://github.com/x/y" in s["description"]


# === v3-C: cheat sheet + description blocks ==================================
import datetime as _dt
from factverse import deliverable as dlv


def _settings(**over):
    return lambda name, default=None: over.get(name, default)


def test_slug_and_pdf_name_are_deterministic():
    assert dlv.slug("Hello, World!  Tool v2") == "hello-world-tool-v2"
    assert len(dlv.slug("x" * 100)) == 40
    assert dlv.slug("???") == "tool"
    assert dlv.pdf_name("Hello World", _dt.date(2026, 8, 22)) == "2026-08-22-hello-world.pdf"


def test_public_url_uses_config_base(monkeypatch):
    monkeypatch.setattr(dlv.fv, "setting", _settings(deliverable_base_url="https://x.test/site/"))
    assert dlv.public_url("a.pdf") == "https://x.test/site/tools/a.pdf"
    monkeypatch.setattr(dlv.fv, "setting", _settings())
    assert dlv.public_url("a.pdf") == dlv.DEFAULT_BASE_URL + "/tools/a.pdf"


def test_description_blocks_land_after_hook_in_order(monkeypatch):
    monkeypatch.setattr(ap.fv, "setting", _settings(promo_block="⭐ Promo: https://aff.test/x"))
    s = _tool_script(10)
    s["description"] = "Hook line with keyword.\n\nBody paragraph two.\n\nSource: u\n\n#AI"
    ap.place_description_blocks(s)
    d = s["description"]
    order = [d.index("Hook line"), d.index("🔧 Try it yourself"), d.index("pip install x"),
             d.index("📄 Free 1-page cheat sheet: "), d.index("⭐ Promo"), d.index("Body paragraph two")]
    assert order == sorted(order)
    assert s["cheat_sheet"].endswith("-t.pdf") and s["cheat_sheet"] in d
    ap.place_description_blocks(s)                       # idempotent incl. promo
    assert d == s["description"]


def test_promo_block_empty_never_appears_and_non_tool_placement(monkeypatch):
    monkeypatch.setattr(ap.fv, "setting", _settings(promo_block=""))
    news = {"format": "news", "description": "Hook.\n\nBody.", "deliverable": None}
    ap.place_description_blocks(news)
    assert news["description"] == "Hook.\n\nBody." and "cheat_sheet" not in news
    monkeypatch.setattr(ap.fv, "setting", _settings(promo_block="PROMO"))
    ap.place_description_blocks(news)
    assert news["description"] == "Hook.\n\nPROMO\n\nBody."   # after paragraph 1


def test_description_clamped_before_blocks(monkeypatch):
    monkeypatch.setattr(ap.fv, "setting", _settings(promo_block=""))
    s = _tool_script(10)
    s["description"] = "Hook.\n\n" + "x" * 6000
    ap.place_description_blocks(s)
    assert len(s["description"]) < 4400 and "🔧 Try it yourself" in s["description"]


def test_cheat_sheet_name_is_carried_across_rewrites():
    assert "cheat_sheet" in ap._CARRY


def test_fallback_sheet_is_the_deliverable():
    assert dlv.fallback_sheet(_tool_script(5))["steps"] == ["pip install x"]
    assert dlv.fallback_sheet({"deliverable": None})["steps"] == []


def test_extract_sheet_validates_llm_output(monkeypatch):
    monkeypatch.setattr(dlv.llm, "generate_json", lambda *a, **k: {
        "what": "  A   tool.  ", "steps": ["pip install x", ""], "uses": ["a", "b", "c", "d"], "skip_if": "no"})
    sh = dlv.extract_sheet(_tool_script(5))
    assert sh == {"what": "A tool.", "steps": ["pip install x"], "uses": ["a", "b", "c"], "skip_if": "no"}
    monkeypatch.setattr(dlv.llm, "generate_json", lambda *a, **k: None)
    assert dlv.extract_sheet(_tool_script(5)) is None


def test_build_pdf_real_render_single_page(tmp_path):
    out = tmp_path / "sheet.pdf"
    sheet = {"what": "MarkItDown converts Office files and PDFs to Markdown. Built by Microsoft.",
             "steps": ["pip install markitdown", "markitdown report.pdf -o report.md"],
             "uses": ["Feed a 200-page PDF to an LLM", "Turn slide decks into notes", "Index a docs folder"],
             "skip_if": "You need pixel-perfect layout preservation."}
    res = dlv.build_pdf(_tool_script(5), sheet, str(out), video_url="https://youtu.be/abc")
    assert res and out.stat().st_size > 5000
    import re as _re
    data = out.read_bytes()
    assert len(_re.findall(rb"/Type\s*/Page[^s]", data)) == 1   # exactly one page


def test_make_cheat_sheet_without_llm_uses_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(dlv, "TOOLS_DIR", tmp_path)
    monkeypatch.setattr(dlv.llm, "generate_json", lambda *a, **k: None)
    captured = {}
    def fake_build(script, sheet, out, video_url=""):
        captured.update(sheet=sheet, out=out, video_url=video_url)
        Path(out).write_bytes(b"%PDF-1.4 fake" + b"0" * 2000)
        return out
    monkeypatch.setattr(dlv, "build_pdf", fake_build)
    s = _tool_script(5)
    s["cheat_sheet"] = "2026-08-22-t.pdf"
    res = dlv.make_cheat_sheet(s, video_url="https://youtu.be/v")
    assert res and Path(res).name == "2026-08-22-t.pdf"
    assert captured["sheet"]["steps"] == ["pip install x"] and captured["video_url"] == "https://youtu.be/v"


def test_extract_sheet_coerces_string_lists(monkeypatch):
    # the LLM returns a bare string often enough; iterating one yields CHARACTERS
    monkeypatch.setattr(dlv.llm, "generate_json", lambda *a, **k: {
        "what": "x", "steps": "pip install x\nmarkitdown a.pdf", "uses": "only one", "skip_if": ""})
    sh = dlv.extract_sheet(_tool_script(5))
    assert sh["steps"] == ["pip install x", "markitdown a.pdf"]
    assert sh["uses"] == ["only one"]
    monkeypatch.setattr(dlv.llm, "generate_json", lambda *a, **k: {"steps": 42, "uses": None})
    assert dlv.extract_sheet(_tool_script(5))["steps"] == ["pip install x"]   # falls back


def test_build_pdf_hard_wraps_unbreakable_commands(tmp_path):
    long_cmd = "pip install git+https://github.com/some-org/a-really-long-repository-name@v1.2.3#egg=pkg"
    out = tmp_path / "long.pdf"
    assert dlv.build_pdf(_tool_script(5), {"what": "", "steps": [long_cmd], "uses": [], "skip_if": ""},
                         str(out))
    from reportlab.lib.utils import simpleSplit
    rows = simpleSplit(long_cmd, "Courier", 11, 499)
    assert any(len(r) > dlv._MONO_COLS for r in rows)      # simpleSplit alone overflows
    assert len(long_cmd[:dlv._MONO_COLS]) == dlv._MONO_COLS


def test_long_command_is_not_cut_mid_line_and_stays_one_page(tmp_path):
    """The wrapped rows used to be sliced [:2], so a 152-char docker line shipped as
    '... ollama/ollama serve && docker' — still copy-pasteable, no longer valid.
    A deliverable may be 300 chars (_validate_script), so this is the normal case."""
    import re as _re
    from reportlab.lib.utils import simpleSplit
    cmd = ("docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama "
           "ollama/ollama serve && docker exec -it ollama ollama pull llama3.1:8b-instruct-q4_K_M")
    assert len(simpleSplit(cmd, "Courier", 11, 499)) > 2, "must actually overflow two rows"
    out = tmp_path / "long.pdf"
    assert dlv.build_pdf(_tool_script(5),
                         {"what": "w", "steps": [cmd], "uses": ["a", "b", "c"], "skip_if": "s"},
                         str(out), video_url="https://youtu.be/abc")
    assert len(_re.findall(rb"/Type\s*/Page[^s]", out.read_bytes())) == 1

    # and an overflowing sheet says it was cut instead of ending mid-command
    over = tmp_path / "over.pdf"
    assert dlv.build_pdf(_tool_script(5),
                         {"what": "w", "steps": [f"step{i} " + "y" * 120 for i in range(5)],
                          "uses": ["a", "b", "c"], "skip_if": "s"}, str(over))
    assert len(_re.findall(rb"/Type\s*/Page[^s]", over.read_bytes())) == 1


def test_insert_after_hook_handles_manufactured_blank_line():
    # _validate_script appends "\n\nSource: ..." — the block must not land below the body
    d = ap._insert_after_hook("Hook.\nBody two.\nBody three.\n\nSource: u", "BLOCK")
    assert d.startswith("Hook.\n\nBLOCK\n\nBody two.")
    assert ap._insert_after_hook("\n\nHook.\n\nBody.", "BLOCK").startswith("Hook.\n\nBLOCK")
    assert ap._insert_after_hook("Only one line.", "BLOCK") == "Only one line.\n\nBLOCK"


def test_cheat_sheet_link_only_when_a_pdf_will_be_written(monkeypatch):
    monkeypatch.setattr(ap.fv, "setting", _settings())
    ever = {"format": "evergreen", "description": "Hook.\n\nBody.",
            "deliverable": {"kind": "command", "text": "pip install x", "url": "u"}}
    ap.place_description_blocks(ever)                    # make_cheat_sheet skips non-tool
    assert "cheat_sheet" not in ever and "📄" not in ever["description"]
    assert "🔧 Try it yourself" in ever["description"]


def test_mangled_block_is_repaired_not_trusted(monkeypatch):
    monkeypatch.setattr(ap.fv, "setting", _settings())
    s = _tool_script(10)
    ap.place_description_blocks(s)
    good = s["description"]
    # an LLM rewrite echoes the block back without the cheat-sheet line
    s["description"] = good.replace("\n📄 Free 1-page cheat sheet: "
                                    + dlv.public_url(s["cheat_sheet"]), "")
    ap.place_description_blocks(s)
    assert s["description"].count("🔧 Try it yourself") == 1
    assert dlv.public_url(s["cheat_sheet"]) in s["description"]   # link == file we write


def test_make_cheat_sheet_fails_soft(monkeypatch, tmp_path):
    monkeypatch.setattr(dlv, "TOOLS_DIR", tmp_path)
    monkeypatch.setattr(dlv, "extract_sheet", lambda s: (_ for _ in ()).throw(RuntimeError("x")))
    assert dlv.make_cheat_sheet(_tool_script(5)) is None


# --------------------------------------------------------------- grounding + filter fix
def test_tool_grounding_prefers_the_hf_model_card(monkeypatch):
    """The hub page is a JS shell whose readable text is inlined tokenizer JSON —
    and it is LONG, so the old `if not grounding` repair could never fire and the
    model card was never read. The card must be asked for first."""
    calls = []

    def fake_fetch(u, limit=4000):
        calls.append(u)
        return "REAL MODEL CARD. " * 40 if u.endswith("README.md") else "junk " * 1000

    monkeypatch.setattr(ap, "fetch_text", fake_fetch)
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: None)
    ap.script_tool({"title": "T", "source": "hf", "url": "https://huggingface.co/org/model"})
    assert calls and calls[0].endswith("/raw/main/README.md")
    assert len(calls) == 1, "the card answered; the junk page must not be fetched at all"


def test_gated_hf_model_is_rejected_not_grounded_on_the_js_shell(monkeypatch):
    """A gated or README-less model 401s on /raw/main/README.md. Falling back to the
    page would ground the whole video in the shell's inlined chat_template JSON —
    long enough to look real, so every claim in the video would be invented."""
    calls = []

    def fake_fetch(u, limit=4000):
        calls.append(u)
        return "" if u.endswith("README.md") else "{jinja chat_template junk} " * 300

    monkeypatch.setattr(ap, "fetch_text", fake_fetch)
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: None)
    assert ap.script_tool({"title": "T", "source": "hf",
                           "url": "https://huggingface.co/org/model"}) is None
    assert calls == ["https://huggingface.co/org/model/raw/main/README.md"]


def test_chrome_only_page_is_too_thin_to_ground_a_tool_video(monkeypatch):
    """Product Hunt's server HTML is ~640 chars of nav chrome. It cleared the old
    400-char floor and gates.fact_check's 200-char one, so claims were verified
    against 'Overview Reviews Team More' and came back unsupported."""
    chrome = ("Notion AI | Product Hunt Overview Reviews 1 Team More "
              "Visit website Be the first to leave a review ") * 6
    assert 400 < len(chrome) < ap.TOOL_GROUNDING_MIN
    monkeypatch.setattr(ap, "fetch_text", lambda u, limit=4000: chrome)
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: None)
    assert ap.script_tool({"title": "T", "source": "ph",
                           "url": "https://www.producthunt.com/posts/x"}) is None


def test_validate_script_coerces_a_non_list_tags(monkeypatch):
    """The model answers `tags` as a comma string / null / an object often enough
    that trusting the type raised out of a bare _validate_script call and killed
    the whole unattended run."""
    for bad, want in (("ai, machine learning", "machine learning"),
                      (None, None), ({"a": 1}, None), (42, None)):
        base = {"title": "T", "description": "d", "tags": bad,
                "scenes": [{"narration": f"s {i}", "visual_query": "v"} for i in range(6)]}
        out = ap._validate_script(base, "t")
        assert isinstance(out["tags"], list) and out["tags"], "brand tags must still land"
        assert all(isinstance(t, str) for t in out["tags"])
        if want:
            assert want in out["tags"]


def test_mangled_block_split_across_a_blank_line_is_fully_excised(monkeypatch):
    """A rewrite that puts a blank line inside the block strands the 📄 line as its
    own paragraph; cutting back to the first blank line only shipped it twice."""
    monkeypatch.setattr(ap.fv, "setting", _settings())
    s = _tool_script(10)
    ap.place_description_blocks(s)
    good = s["description"]
    # the LLM hands back the block reformatted with a blank line before the PDF line
    s["description"] = good.replace("\n" + ap._PDF_MARK, "\n\n" + ap._PDF_MARK)
    s["description"] = s["description"].replace("tools/", "tools/STALE-")
    ap.place_description_blocks(s)
    assert s["description"].count(ap._PDF_MARK) == 1
    assert "STALE-" not in s["description"]
    assert s["description"].count(ap._DL_MARK) == 1


def test_non_hf_tool_grounds_on_the_page_only(monkeypatch):
    calls = []
    monkeypatch.setattr(ap, "fetch_text",
                        lambda u, limit=4000: calls.append(u) or "GITHUB README. " * 60)
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: None)
    ap.script_tool({"title": "T", "source": "gh", "url": "https://github.com/org/repo"})
    assert calls == ["https://github.com/org/repo"]


def test_tool_fallback_returns_an_evergreen_labelled_script(monkeypatch):
    """run() re-binds fmt from the returned script so the ledger stops stamping a
    fallback video as format=tool. That is only sound because the fallback really
    does label itself, and because "format" is carried across the rewrite passes."""
    monkeypatch.setattr(ap, "pick_evergreen_topic", lambda ranked: {"title_idea": "how x works"})
    monkeypatch.setattr(ap, "script_evergreen",
                        lambda topic: {"format": "evergreen", "title": "E", "scenes": []})
    out = ap.build_script("tool", [{"title": "n", "kind": "news"}])
    assert out["format"] == "evergreen"
    assert "format" in ap._CARRY


def test_shorts_meta_normalised_so_the_tripwire_cannot_fire_after_upload():
    """A short/ragged shorts_meta used to raise PipelineViolation inside the publish
    block — after the long-form was live and before any PUBLISHED row existed, so
    the retry cron published a second video for the same day."""
    from factverse import scheduling as sch
    script = {"title": "A Very Long Tool Title That Goes On", "description": "d" * 900}
    for bad in (None, [], [{"title": "one #Shorts"}], ["a string", "another"],
                [{"title": "  "}, {"title": "real #Shorts"}], [{}] * 5):
        out = ap.normalize_shorts_meta(bad, 2, script)
        assert len(out) == 2
        assert all(isinstance(m, dict) for m in out)
        titles = [m["title"] for m in out]
        assert all(t and t.strip() for t in titles), f"empty title from {bad!r}"
        # this is exactly what validate_shorts_batch counts
        sch.validate_shorts_batch([object(), object()], titles)
    # a good payload is left alone
    good = [{"title": "t1 #Shorts", "description": "d1"}, {"title": "t2 #Shorts", "description": "d2"}]
    assert ap.normalize_shorts_meta(good, 2, script) == good


def test_unsuitable_tools_are_skipped_before_a_tutorial_is_written(monkeypatch):
    """A tool video TEACHES the tool, so this rejects where sensitive_topic_risk
    only penalises. On 2026-08-23 the live #1 tool candidate was a multi-vendor
    AI-provenance stripper and two 'Uncensored' model forks sat in the queue."""
    from factverse import gates
    assert gates.tool_unsuitable("guillaumemeyer/watermarks-remover: Strip AI provenance")[0]
    assert gates.tool_unsuitable("orcarouter/Qwen3.8-27B-Uncensored-MLX")[0]
    assert not gates.tool_unsuitable("unsloth/Qwen3.8-27B-GGUF — trending model")[0]
    assert not gates.tool_unsuitable("MarkItDown converts Office files to Markdown")[0]

    tried = []
    monkeypatch.setattr(ap, "script_tool", lambda c: tried.append(c["title"]) or None)
    monkeypatch.setattr(ap, "mark_failed", lambda t: None)
    monkeypatch.setattr(ap, "pick_evergreen_topic", lambda r: None)
    monkeypatch.setattr(ap, "script_news", lambda *a, **k: None)
    ap.build_script("tool", [{"title": "watermarks-remover: strip provenance", "kind": "tool"},
                             {"title": "MarkItDown converts files", "kind": "tool"}])
    assert tried == ["MarkItDown converts files"], "the stripper must never reach script_tool"


def test_script_tool_rejects_when_only_the_readme_reveals_it(monkeypatch):
    """A repo can be titled innocuously; intent shows in the README."""
    monkeypatch.setattr(ap, "fetch_text",
                        lambda u, limit=4000: "This tool will strip provenance marks. " * 60)
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: {"scenes": []})
    assert ap.script_tool({"title": "helpful-utility", "source": "gh",
                           "url": "https://github.com/x/y"}) is None


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


# --------------------------------------------------------------- tool lane, composed
def test_tool_lane_advertises_the_pdf_it_actually_writes(monkeypatch, tmp_path):
    """The exact chain run() walks: validate -> place blocks -> advice-gate rewrite ->
    carry -> place again -> write the PDF. Every link is covered above; this asserts
    they COMPOSE, because a drift between the linked name and the written file is a
    permanent 404 on a video that is already published."""
    monkeypatch.setattr(ap.fv, "setting", _settings())
    monkeypatch.setattr(dlv, "TOOLS_DIR", tmp_path)
    monkeypatch.setattr(dlv.llm, "generate_json", lambda *a, **k: None)   # fallback sheet

    s = ap._validate_script(_tool_script(20), "fallback", "https://github.com/x/y")
    ap.place_description_blocks(s)
    name = s["cheat_sheet"]

    # the advice gate re-generates the script; the LLM echoes back neither v3 key
    rewritten = ap._validate_script(
        {"title": "T2", "description": "brand new hook.\n\nbody", "scenes": s["scenes"]},
        s["title"], s["source_url"])
    assert rewritten["deliverable"] is None                  # the documented reset
    rewritten = ap._carry_over(s, rewritten)
    ap.place_description_blocks(rewritten)

    # a re-slug here would point the description at a file nobody writes
    assert rewritten["cheat_sheet"] == name
    assert rewritten["description"].count(ap._PDF_MARK) == 1
    assert dlv.public_url(name) in rewritten["description"]

    written = dlv.make_cheat_sheet(rewritten, video_url="https://youtu.be/ID")
    assert written and Path(written).name == name
    assert dlv.public_url(name).endswith(Path(written).name)


# =============================================================== v3-C.2
# The news / evergreen / roundup lanes. C.1 audited the tool lane only; its
# shared fixes (_validate_script, the publish window) already protected these
# three, but the lanes themselves had never been searched for their own defects.

def _capture(store, result=None):
    """Stub for llm.generate_json that records the prompt it was handed."""
    def _f(prompt, **kw):
        store.append(prompt)
        return result
    return _f


def _mixed_ranked():
    """The live top-6 of 2026-08-23, kinds and order preserved. rank() returns ONE
    list and v3-A added the GitHub/HF/Product Hunt trending feeds to it."""
    return [
        {"title": "guillaumemeyer/watermarks-remover: Strip multi-vendor AI provenance marks",
         "url": "https://github.com/guillaumemeyer/watermarks-remover", "source": "github",
         "kind": "tool", "fit_score": 70.5},
        {"title": "Qwen/Qwen3.8-27B - trending image text to text on Hugging Face",
         "url": "https://huggingface.co/Qwen/Qwen3.8-27B", "source": "hf",
         "kind": "tool", "fit_score": 70.5},
        {"title": "Inherent, founded by DeepMind alumni, says its AI teammate outperformed humans",
         "url": "https://tc.test/inherent", "source": "techcrunch", "kind": "news", "fit_score": 68.1},
        {"title": "unsloth/Qwen3.8-27B-GGUF - trending model on Hugging Face",
         "url": "https://huggingface.co/unsloth/Qwen3.8-27B-GGUF", "source": "hf",
         "kind": "tool", "fit_score": 58.9},
        {"title": "OpenAI says California should strengthen its AI safety bill",
         "url": "https://vg.test/openai-ca", "source": "verge", "kind": "news", "fit_score": 55.2},
        {"title": "Frontier AI labs still won't say how they'd contain a rogue model",
         "url": "https://ax.test/rogue", "source": "axios", "kind": "news", "fit_score": 55.1},
    ]


# --------------------------------------------------------------- candidate leakage
def test_news_lane_never_writes_about_a_tool_candidate(monkeypatch):
    """gates.tool_unsuitable guards the tool lane and nothing else, so the same
    provenance stripper it refuses to TEACH could still be written up as the day's
    news story — it was ranked #1 on 2026-08-23 and #2 was a model card."""
    tried = []
    monkeypatch.setattr(ap, "script_news", lambda c, **k: tried.append(c["title"]) or None)
    monkeypatch.setattr(ap, "mark_failed", lambda t: None)
    monkeypatch.setattr(ap.gates, "pick_hook_pattern", lambda r: "number")
    monkeypatch.setattr(ap, "_recent_hook_patterns", lambda n=6: [])
    ap.build_script("news", _mixed_ranked())
    assert tried, "the news lane must still have candidates to try"
    assert not any(("watermarks-remover" in t) or ("Qwen" in t) for t in tried), \
        f"a tool signal reached script_news: {tried}"


def test_viral_judge_scores_stories_not_repos(monkeypatch):
    """viral_pick decides the DAY's format. Scoring 'Strip multi-vendor AI provenance
    marks' for shock value is how a repo becomes the news story."""
    prompts = []
    monkeypatch.setattr(ap.llm, "generate_json", _capture(prompts))
    ap.viral_pick(_mixed_ranked())
    listing = prompts[0]
    assert "Inherent" in listing, "real stories must still be judged"
    assert "watermarks-remover" not in listing and "Qwen" not in listing


def test_roundup_counts_stories_not_model_cards(monkeypatch):
    """'The 5 AI stories that actually mattered this week' drew from the same mixed
    list — 4 of the live top 5 were HF/GitHub repos."""
    monkeypatch.setattr(ap, "fetch_text", lambda u, limit=4000: "real article text " * 60)
    prompts = []
    monkeypatch.setattr(ap.llm, "generate_json", _capture(prompts))
    ap.script_roundup(_mixed_ranked())
    block = prompts[0]
    assert "Inherent" in block and "California" in block
    assert "watermarks-remover" not in block and "GGUF" not in block


def test_roundup_keeps_the_sunday_when_stories_are_scarce(monkeypatch):
    """Filtering must not cost the week: with fewer than 3 story signals the
    roundup tops up from what is left rather than returning nothing."""
    monkeypatch.setattr(ap, "fetch_text", lambda u, limit=4000: "text " * 300)
    prompts = []
    monkeypatch.setattr(ap.llm, "generate_json", _capture(prompts))
    thin = [_mixed_ranked()[2]] + [c for c in _mixed_ranked() if c["kind"] == "tool"]
    ap.script_roundup(thin)
    assert "STORY 3:" in prompts[0], "a one-story week must still fill the countdown"


# --------------------------------------------------------------- roundup grounding
def test_roundup_gates_read_the_text_the_prompt_read(monkeypatch):
    """The grounding was fetched TWICE — once for the prompt, once for the gates.
    A transient failure on the second pass empties script['grounding'], and an
    empty grounding makes verbatim_overlap 0.0 and fact_check skip: the copy gate
    then passes trivially on a script written from real source text."""
    seen_urls = set()

    def flaky(url, limit=4000):
        # the second fetch of the same page is the one that comes back empty
        if url in seen_urls:
            return ""
        seen_urls.add(url)
        return "genuine article sentence about the model launch. " * 40

    monkeypatch.setattr(ap, "fetch_text", flaky)
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: {
        "title": "This Week in AI",
        "scenes": [{"narration": f"scene {i} narration text", "visual_query": "v"}
                   for i in range(6)]})
    s = ap.script_roundup([c for c in _mixed_ranked() if c["kind"] == "news"])
    assert s and "genuine article sentence" in s["grounding"],         "the gates must see the same text the prompt was written from"
    assert ap.verbatim_overlap("genuine article sentence about the model launch . " * 3,
                               s["grounding"]) > 0.5, "the copy gate must still have teeth"


def test_roundup_grounding_covers_every_story(monkeypatch):
    """Only picked[:3] was re-fetched for the gates, so stories 4 and 5 were never
    fact-checked or copy-checked — and the tail is where lifted prose hides."""
    marks = {}

    def per_story(url, limit=4000):
        marks[url] = f"UNIQUEMARK{len(marks)} " + "body text " * 40
        return marks[url]

    items = [{"title": f"Story {i}", "url": f"https://s{i}.test/a", "source": f"src{i}",
              "kind": "news"} for i in range(5)]
    monkeypatch.setattr(ap, "fetch_text", per_story)
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: {
        "title": "This Week in AI",
        "scenes": [{"narration": f"scene {i} text", "visual_query": "v"} for i in range(6)]})
    s = ap.script_roundup(items)
    for i in range(5):
        assert f"UNIQUEMARK{i}" in s["grounding"], f"story {i + 1} is ungated"


def test_roundup_description_lists_every_source(monkeypatch):
    """The video burns 'Sources in description' on screen. _validate_script adds
    exactly one Source line — story 1's — so four outlets went uncredited."""
    monkeypatch.setattr(ap.fv, "setting", lambda k, d=None: "" if k == "promo_block" else d)
    script = {"format": "roundup", "description": "Hook line.\n\nBody paragraph.",
              "roundup_items": [{"title": f"Story {i}", "url": f"https://s{i}.test/a"}
                                for i in range(5)]}
    ap.place_description_blocks(script)
    for i in range(5):
        assert f"https://s{i}.test/a" in script["description"]
    before = script["description"]
    ap.place_description_blocks(script)
    assert script["description"] == before, "must be idempotent — run() calls it twice"


def test_roundup_does_not_brand_five_outlets_with_one():
    """src_domain came from source_url, which _validate_script sets to picked[0]'s
    URL — so the on-screen chip and every stat card stamped story 1's outlet across
    the whole video, and the 'Sources in description' branch was unreachable."""
    roundup = {"format": "roundup", "source_url": "https://techcrunch.test/story-one"}
    assert ap.source_chip(roundup) == ("", "Sources in description")
    news = {"format": "news", "source_url": "https://www.theverge.com/2026/x"}
    assert ap.source_chip(news) == ("theverge.com", "Source: theverge.com")
    assert ap.source_chip({"format": "evergreen", "source_url": ""}) == ("", "")


# --------------------------------------------------------------- advice gate window
def test_advice_gate_reads_the_whole_narration(monkeypatch):
    """The LLM confirmation was armed from script_text[:2000]. A 900-word script is
    ~5,500 chars, so anything prescriptive in the last two thirds was never checked."""
    from factverse import gates
    asked = []
    monkeypatch.setattr(gates.llm, "generate_json",
                        _capture(asked, {"advice": True, "evidence": "late"}))
    late = ("A neutral sentence about model design. " * 90
            + "Put your savings into that stock before the earnings call.")
    assert len(late) > 3000
    out = gates.advice_framing(late)
    assert asked, "a sensitive term past char 2000 must still arm the LLM check"
    assert out["advice"] is True


# --------------------------------------------------------------- evergreen dedup
def test_evergreen_topic_rejects_a_reworded_repeat(monkeypatch):
    """Exact lowercase equality was the only dedup, while the signal engine already
    carries _too_similar for precisely this — a re-worded topic is the same video."""
    monkeypatch.setattr(ap, "_read_json",
                        lambda p, d: ["How Do Large Language Models Actually Work"]
                        if p == ap.USED_TOPICS else d)
    monkeypatch.setattr(ap, "too_many_failures", lambda t: False)
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: {"topics": [
        {"title_idea": "How Large Language Models Actually Work", "search_question": "q"},
        {"title_idea": "Why AI Chips Cost So Much", "search_question": "q"}]})
    t = ap.pick_evergreen_topic([])
    assert t["title_idea"] == "Why AI Chips Cost So Much"


# --------------------------------------------------------------- veto window truth
def test_notify_review_does_not_claim_a_window_it_never_opened(monkeypatch):
    """requests.post does not raise on 401/404. The log said 'veto window active'
    while no issue existed and the video published unattended anyway."""
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")

    class _R:
        status_code = 404
        text = "Not Found"

    monkeypatch.setattr(ap.requests, "post", lambda *a, **k: _R())
    out = []
    monkeypatch.setattr("builtins.print", lambda *a, **k: out.append(" ".join(str(x) for x in a)))
    ap._notify_review({"title": "T"}, None, "https://y.test/v", "2026-08-23T16:45:00Z",
                      {"score": 0.7, "components": {}})
    joined = "\n".join(out)
    assert "veto window active" not in joined
    assert "404" in joined and "REVIEW WINDOW" in joined, "it must fall back to the log"


# --------------------------------------------------------------- ledger cannot raise
def test_record_run_survives_a_value_json_cannot_serialize(tmp_path, monkeypatch):
    """record_run caught OSError only. It is the LAST statement of the publish
    window C.1 closed: if it raises, the video is live with no PUBLISHED row and
    the 14:53 retry cron publishes a second one into the same slot."""
    log = tmp_path / "runs.jsonl"
    monkeypatch.setattr(ap, "RUNS_LOG", log)
    ap.record_run(status="PUBLISHED", format="news", title="T",
                  publish_at=Path("x"), odd={1, 2})
    row = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert row["status"] == "PUBLISHED" and row["title"] == "T"


# --------------------------------------------------------------- thin grounding
def test_news_refuses_a_story_it_cannot_fact_check(monkeypatch):
    """With empty grounding every accuracy gate passes for free: verbatim_overlap
    scores 0.0, fact_check skips below 200 chars, verify_synthesis has nothing to
    compare, and the confidence 'facts' component reads 1.0 — identical to a fully
    verified script. If the fact-checker cannot run, the lane must not write."""
    called = []
    monkeypatch.setattr(ap.llm, "generate_json", _capture(called, {"scenes": []}))
    monkeypatch.setattr(ap, "fetch_text", lambda u, limit=4000: "")
    assert ap.script_news({"title": "T", "source": "s", "url": "https://x.test/a"}) is None
    monkeypatch.setattr(ap, "fetch_text", lambda u, limit=4000: "x" * 199)
    assert ap.script_news({"title": "T", "source": "s", "url": "https://x.test/a"}) is None
    assert not called, "no LLM call is worth making against an unsourced headline"
    monkeypatch.setattr(ap, "fetch_text", lambda u, limit=4000: "real reporting. " * 40)
    ap.script_news({"title": "T", "source": "s", "url": "https://x.test/a"})
    assert called, "a properly grounded story must still be written"


def test_evergreen_stays_ungrounded_by_design(monkeypatch):
    """The floor applies to the lanes that CLAIM a source. An evergreen explainer
    has no source URL and gates.fact_check's skip note names it explicitly."""
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: {
        "title": "E", "scenes": [{"narration": f"s {i}", "visual_query": "v"} for i in range(6)]})
    s = ap.script_evergreen({"title_idea": "How AI chips work"})
    assert s and s["format"] == "evergreen" and s["grounding"] == ""


def test_roundup_refuses_an_unsourced_countdown(monkeypatch):
    """Five stories that all failed to fetch produce five '(none)' excerpts — a
    countdown written entirely from headlines, gated by nothing."""
    called = []
    monkeypatch.setattr(ap.llm, "generate_json", _capture(called, None))
    monkeypatch.setattr(ap, "fetch_text", lambda u, limit=4000: "")
    assert ap.script_roundup([c for c in _mixed_ranked() if c["kind"] == "news"]) is None
    assert not called


def test_roundup_failure_does_not_cost_the_sunday(monkeypatch):
    """Sunday is the only roundup slot; a dead fetch must not mean no video.
    Same fallback shape the tool lane already uses, and the script labels itself
    so run() re-binds fmt and the ledger stays honest."""
    monkeypatch.setattr(ap, "script_roundup", lambda items: None)
    monkeypatch.setattr(ap, "pick_evergreen_topic", lambda r: {"title_idea": "how x works"})
    monkeypatch.setattr(ap, "script_evergreen",
                        lambda t: {"format": "evergreen", "title": "E", "scenes": []})
    out = ap.build_script("roundup", _mixed_ranked())
    assert out and out["format"] == "evergreen"


def test_evergreen_dedup_separates_a_reword_from_a_new_subject(monkeypatch):
    """0.5 (the signal engine's headline default) blocks the lane's own title
    template — the evergreen prompt literally asks for 'how does X actually work'.
    0.7 still catches the re-word."""
    from factverse.intelligence import signal_engine as se
    used = {se._norm("How Diffusion Models Actually Work")}
    assert se._is_used("How Transformers Actually Work", used)                    # 0.5: blocked
    assert not se._is_used("How Transformers Actually Work", used,
                           threshold=ap.EVERGREEN_DUP_OVERLAP)
    reword = {se._norm("How Do Large Language Models Actually Work")}
    assert se._is_used("How Large Language Models Actually Work", reword,
                       threshold=ap.EVERGREEN_DUP_OVERLAP)

    monkeypatch.setattr(ap, "_read_json",
                        lambda p, d: ["How Diffusion Models Actually Work"]
                        if p == ap.USED_TOPICS else d)
    monkeypatch.setattr(ap, "too_many_failures", lambda t: False)
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: {"topics": [
        {"title_idea": "How Transformers Actually Work", "search_question": "q"}]})
    assert ap.pick_evergreen_topic([])["title_idea"] == "How Transformers Actually Work"


def test_roundup_does_not_stack_one_outlet(monkeypatch):
    """Curation is the roundup's whole added value — and its policy defence. The
    dedup only skipped a repeat once THREE distinct sources were already banked,
    so on a feed where one outlet dominates it never fired: the live signals of
    2026-08-23 produced a five-story countdown of five TechCrunch stories."""
    items = ([{"title": f"TC story {i}", "url": f"https://tc.test/{i}",
               "source": "news/techcrunch", "kind": "news"} for i in range(5)]
             + [{"title": "HF post", "url": "https://hf.test/1",
                 "source": "blog/huggingface", "kind": "news"},
                {"title": "OpenAI post", "url": "https://oa.test/1",
                 "source": "blog/openai", "kind": "news"}])
    monkeypatch.setattr(ap, "fetch_text", lambda u, limit=4000: "body text " * 60)
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: {
        "title": "This Week in AI",
        "scenes": [{"narration": f"scene {i} text", "visual_query": "v"} for i in range(6)]})
    s = ap.script_roundup(items)
    hosts = {it["url"].split("/")[2] for it in s["roundup_items"]}
    assert len(s["roundup_items"]) == 5, "the countdown must still be full"
    assert hosts == {"tc.test", "hf.test", "oa.test"}, f"one outlet dominated: {hosts}"


# --------------------------------------------------------------- v3-C.3 render surfaces
def test_count_seq_final_frame_is_the_stat_verbatim():
    """The count-up formatter is not an identity function at its own end point.
    The frame held longest on screen was re-rendering the number through a
    format spec: "120.5 billion" became "120 billion" and "154.7%" became
    "155%" — the card contradicting the narration on a fact-checked channel."""
    from factverse import infographics as ig
    for stat in ("54%", "154.7%", "120.5 billion", "1500x", "$2 billion",
                 "12.5%", "99.9%", "2,400 percent", "3.7 million"):
        assert ig._count_seq(stat, 1.0) == stat, f"final frame rewrote {stat!r}"
    # the intermediate frames must still animate
    assert ig._count_seq("54%", 0.0) == "0%"
    assert ig._count_seq("54%", 0.3) != "54%"


def test_card_duration_matches_the_slot_step5_build_will_give_it():
    """step5_build splits a scene's time equally between its clips, so a card
    stacked onto a 2-clip scene gets sdur/3 — not the fixed 4.0s it was rendered
    at. Long slot: -stream_loop replays the count-up mid-scene. Short slot: the
    clip is cut before the count finishes and the last frame shows a number that
    is not the one the script says (measured: 43% for a true 54%)."""
    from factverse import infographics as ig
    # a 20s scene with 2 stock clips: the card's real share is 20/3
    assert ig.card_slot_dur(20.0, 2) == 20.0 / 3
    # a scene with no stock clips still gets the whole scene
    assert ig.card_slot_dur(6.0, 0) == 6.0
    # missing/degenerate duration falls back to the module default, never 0
    assert ig.card_slot_dur(None, 2) == ig.CARD_DUR
    assert ig.card_slot_dur(0.0, 2) == ig.CARD_DUR


def test_inject_cards_renders_each_card_at_its_own_scene_share(monkeypatch):
    """The card must be rendered to the slot, not looped or cut to fit it."""
    from factverse import infographics as ig
    seen = []

    def _fake_card(stat, label, out, source="", dur=4.0, size=(1280, 720)):
        seen.append((stat, round(dur, 3)))
        return out

    monkeypatch.setattr(ig, "plan_cards", lambda s, max_cards=4: [
        {"n": 1, "stat": "54%", "label": "l1"}, {"n": 2, "stat": "9x", "label": "l2"}])
    monkeypatch.setattr(ig, "make_card_clip", _fake_card)
    clips = [["a.mp4", "b.mp4"], ["c.mp4"]]
    ig.inject_cards({}, clips, source_domain="x.test", scene_durs=[30.0, 8.0])
    assert seen == [("54%", 10.0), ("9x", 4.0)], seen
    # and the card really is the scene's lead visual
    assert "statcard" in clips[0][0] or clips[0][0].endswith(".mp4")
    assert len(clips[0]) == 3 and len(clips[1]) == 2


def test_fit_font_shrinks_until_the_text_measures_inside_the_budget():
    """The one shrink loop, shared by every surface that draws text on a frame.
    make_tool_thumb already had it inline; compose, _text_block and the stat card
    picked a size off a character-count ladder and drew it unmeasured."""
    from PIL import Image, ImageDraw
    from factverse import branding as br
    d = ImageDraw.Draw(Image.new("RGB", (1280, 720)))
    lines = ["OPENAI QUIETLY SHIPPED", "A NEW REASONING MODEL"]
    size, font = br.fit_font(br._font, lines, 150, 1280 - 2 * 56)
    assert size <= 150
    assert max(d.textlength(l, font=font) for l in lines) <= 1280 - 2 * 56
    # a floor is honoured when the caller prefers overflow to illegibility
    size2, _ = br.fit_font(br._font, ["A VERY LONG HEADLINE INDEED"], 130, 50, floor=72)
    assert size2 == 72


def test_stat_is_never_cut_mid_word_and_is_drawn_inside_the_card():
    """plan_cards capped the stat at 12 characters, so "120.5 billion" reached
    the screen as "120.5 billio" — and even capped, "2,400 percen" measures
    1304px on a 1280px card and is clipped at both edges."""
    from PIL import Image, ImageDraw
    from factverse import infographics as ig
    from factverse import branding as br
    assert ig._cap_stat("120.5 billion") == "120.5 billion"
    assert ig._cap_stat("2,400 percent") == "2,400 percent"
    assert ig._cap_stat("54%") == "54%"
    # an LLM answering with a sentence is still bounded, but on a word boundary
    long = ig._cap_stat("54 percent of all enterprise deployments surveyed")
    assert not long.endswith(" ") and " " in long and len(long) <= 24
    assert long in "54 percent of all enterprise deployments surveyed"
    d = ImageDraw.Draw(Image.new("RGB", (1280, 720)))
    size, font = br.fit_font(br._font, ["2,400 percent"], int(720 * 0.30), 1280)
    assert d.textlength("2,400 percent", font=font) <= 1280
