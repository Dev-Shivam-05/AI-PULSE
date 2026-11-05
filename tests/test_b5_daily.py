"""v3-B.5: the daily-video fixes (docs/spec/ai-pulse-v3b5.md).

1. The tool video's screen recording no longer loops: it browses several pages
   without scrolling back up, and is recut AFTER the narration timings exist.
2. The daily lane mix (behind "lane_mix_v2").
3. The evergreen subject-family screen.

Tests never run ffmpeg, the browser, the network or the LLM. Helpers are prefixed
`_b5_` (the shared-module helper-name trap)."""
import datetime as dt
import inspect
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factverse import ai_pipeline as ap   # noqa: E402
from factverse import screencap as sc     # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


# =============================================================== 1. screen recording
def test_b5_locked_recording_values():
    assert sc.WPS == 2.0 and sc.REC_MAX == 480.0 and sc.REC_MIN == 60.0
    assert sc.MAX_SLOW == 1.35
    est = sc.estimate_video_seconds({"scenes": [{"narration": " ".join(["w"] * 761)}]})
    assert est == 761 / 2.0                      # the median script is now fully recorded


def test_b5_browse_plan_github_repo_visits_four_pages_in_order():
    base = "https://github.com/omlahore/removemacai"
    want = [base, base + "/releases", base + "/issues", base + "/commits"]
    assert sc.browse_plan(base) == want
    assert sc.browse_plan(base + "/") == want
    assert sc.browse_plan(base + ".git") == want
    assert sc.browse_plan(base + "/tree/main/docs") == want     # README first, always


def test_b5_browse_plan_hf_model_and_other_urls():
    m = "https://huggingface.co/nvidia/parakeet"
    assert sc.browse_plan(m) == [m, m + "/tree/main", m + "/discussions"]
    ds = "https://huggingface.co/datasets/org/thing"
    assert sc.browse_plan(ds) == [ds]                           # a dataset is not a model
    assert sc.browse_plan("https://github.com/topics/llm") == ["https://github.com/topics/llm"]
    assert sc.browse_plan("https://example.test/tool") == ["https://example.test/tool"]
    assert sc.browse_plan("") == [] and sc.browse_plan("javascript:alert(1)") == []


def test_b5_redirected_subpage_is_not_recorded():
    base = "https://github.com/o/r"
    assert sc.landed_on(base + "/commits", base + "/commits/main")
    assert sc.landed_on(base + "/releases", base + "/releases/")
    assert not sc.landed_on(base + "/issues", base)              # Issues disabled -> README again
    assert not sc.landed_on(base + "/issues", base + "/issues-archive")
    assert not sc.landed_on(base + "/issues", "https://evil.test/o/r/issues")


def test_b5_page_budget_hands_unused_time_on():
    assert sc.page_budget(400, 4) == 100
    assert sc.page_budget(370, 3) == 370 / 3      # README ended early: 30 s more each
    assert sc.page_budget(-5, 2) == 0.0 and sc.page_budget(10, 0) == 10


class _B5Page:
    """A fake Playwright page: bottom reached on the Nth check."""
    def __init__(self, bottom_after):
        self.checks, self.bottom_after, self.wheels, self.js = 0, bottom_after, [], []
        self.mouse = self

    def evaluate(self, js):
        self.js.append(js)
        self.checks += 1
        return self.checks > self.bottom_after

    def wheel(self, dx, dy):
        self.wheels.append(dy)

    def wait_for_timeout(self, ms):
        pass


def test_b5_browse_never_scrolls_back_up():
    page = _B5Page(bottom_after=5)
    sc._browse(page, 60.0)
    assert len(page.wheels) == 5 and all(dy > 0 for dy in page.wheels)
    assert not any("scrollTo" in js for js in page.js)          # the old loop is gone
    assert "scrollTo" not in inspect.getsource(sc._browse)


def _b5_clips(n=6, card_scene=2):
    clips = [[f"/t/screencap/chunk_{i:03d}.mp4"] for i in range(n)]
    clips[card_scene].insert(0, "/t/statcard_03.mp4")
    return clips


def test_b5_recut_plan_is_sequential_and_sized_to_the_step5_share():
    clips = _b5_clips()
    durs = [40.0, 65.0, 55.0, 70.0, 50.0, 50.0]
    prov = {c for cs in clips for c in cs if "chunk_" in c}
    plan = sc.recut_plan(clips, durs, prov, rec_seconds=400.0)
    assert len(plan) == 6                                        # the stat card is not touched
    assert [p["scene"] for p in plan] == list(range(6))
    assert plan[2]["slot"] == 1 and plan[2]["share"] == 27.5     # 55 s shared with the card
    for p, d, cs in zip(plan, durs, clips):
        assert abs(p["share"] - d / len(cs)) < 1e-6
        assert p["slow"] == 1.0 and p["src"] == p["share"]       # long enough: real time
        assert p["out"] == round(p["share"] + sc.TAIL_PAD, 3)
    for a, b in zip(plan, plan[1:]):
        assert abs(b["start"] - (a["start"] + a["src"])) < 0.01  # back to back, no overlap


def test_b5_recut_plan_short_recording_slows_then_holds():
    clips = [[f"/t/screencap/chunk_{i:03d}.mp4"] for i in range(6)]
    prov = {c[0] for c in clips}
    durs = [55.0] * 6                                            # 330 s needed
    # 280 s recorded: 330/280 = 1.18 <= 1.35, pure slow-down, no extra hold
    plan = sc.recut_plan(clips, durs, prov, rec_seconds=280.0)
    assert plan[0]["slow"] == round(330 / 280, 4)
    assert all(abs(p["hold"] - sc.TAIL_PAD) < 0.01 for p in plan)
    assert abs(sum(p["src"] for p in plan) - 280.0) < 0.05      # the WHOLE recording, once
    # 150 s recorded: capped at 1.35, the rest is a held last frame per piece
    plan = sc.recut_plan(clips, durs, prov, rec_seconds=150.0)
    assert plan[0]["slow"] == sc.MAX_SLOW
    for p in plan:
        played = p["src"] * p["slow"]
        assert abs(played + p["hold"] - sc.TAIL_PAD - p["share"]) < 0.01
        assert p["hold"] > sc.TAIL_PAD
    assert abs(plan[-1]["start"] + plan[-1]["src"] - 150.0) < 0.05


def test_b5_recut_pieces_never_trigger_stream_loop():
    """The acceptance pin: step5_build's loop count for every recut piece is 0,
    even when the encoded piece probes one frame short of its planned length."""
    clips = _b5_clips()
    durs = [40.0, 65.0, 55.0, 70.0, 50.0, 50.0]
    prov = {c for cs in clips for c in cs if "chunk_" in c}
    for rec in (400.0, 300.0, 120.0, 30.0):
        for p in sc.recut_plan(clips, durs, prov, rec):
            assert sc.stream_loops(p["share"], p["out"] - 1 / sc.FPS) == 0, (rec, p)
    # the bug it replaces: 6 equal pre-narration chunks of a 300 s recording
    old = [sc.stream_loops(d, 300.0 / 6) for d in durs]
    assert max(old) >= 1                                         # 65 s and 70 s slots looped


def test_b5_stream_loops_mirrors_step5_build():
    import factverse_engine as eng
    src = inspect.getsource(eng.step5_build)
    assert src.count("int(math.ceil(sdur/cd)) - 1") == 1
    assert src.count("int(math.ceil(each_dur/cd)) - 1") == 1
    assert sc.stream_loops(10.0, 10.0) == 0 and sc.stream_loops(10.0, 9.9) == 1


def test_b5_recut_plan_refuses_unsafe_inputs():
    clips = [["/t/screencap/chunk_000.mp4"], ["/t/screencap/chunk_001.mp4"]]
    prov = {c[0] for c in clips}
    assert sc.recut_plan(clips, [10.0], prov, 100.0) == []      # durs do not match scenes
    assert sc.recut_plan(clips, [10.0, 10.0], set(), 100.0) == []
    assert sc.recut_plan(clips, [10.0, 10.0], prov, 0.0) == []
    assert sc.recut_plan([], [], prov, 100.0) == []


def test_b5_piece_args_slow_then_hold_never_loop():
    p = {"start": 12.5, "src": 20.0, "slow": 1.2, "hold": 3.5, "out": 27.5}
    a = sc._piece_args("rec.mp4", "piece.mp4", p)
    assert "-stream_loop" not in a
    i = a.index("-i")
    assert a[a.index("-ss") + 1] == "12.5" and a.index("-ss") < i
    assert a[a.index("-t") + 1] == "20.0" and a.index("-t") < i          # read span
    assert a[len(a) - 1 - a[::-1].index("-t") + 1] == "27.5"             # output length
    vf = a[a.index("-vf") + 1]
    assert vf.startswith("setpts=1.2*(PTS-STARTPTS)")
    assert "tpad=stop_mode=clone:stop_duration=3.5" in vf


def test_b5_join_args_trims_each_pages_own_blank():
    a = sc._join_args([("a.webm", 2.5), ("b.webm", 3.9), ("c.webm", 2.5)], "rec.mp4")
    assert [a[k + 1] for k, x in enumerate(a) if x == "-ss"] == ["2.5", "3.9", "2.5"]
    assert [a[k + 1] for k, x in enumerate(a) if x == "-i"] == ["a.webm", "b.webm", "c.webm"]
    assert "concat=n=3:v=1:a=0[v]" in a[a.index("-filter_complex") + 1]
    assert a[-1] == "rec.mp4"


def _b5_fake_ffmpeg(seen, fail_on=None):
    def run(args, timeout=600):
        seen.append(args)
        if fail_on and fail_on in args[-1]:
            return False
        Path(args[-1]).write_bytes(b"0" * 2000)
        return True
    return run


def test_b5_capture_returns_the_recording_and_browses_the_plan(monkeypatch, tmp_path):
    monkeypatch.setattr(sc.fv, "TEMP", tmp_path)
    asked = []

    def rec(urls, out, t):
        asked.append((list(urls), t))
        return [(str(Path(out) / "a.webm"), 2.5), (str(Path(out) / "b.webm"), 3.0)], "shot.png"
    monkeypatch.setattr(sc, "_record_pages", rec)
    seen = []
    monkeypatch.setattr(sc, "_ffmpeg", _b5_fake_ffmpeg(seen))
    monkeypatch.setattr(sc, "_probe_duration", lambda p: 200.0)
    s = {"scenes": [{"narration": "w " * 100}] * 6, "source_url": "https://github.com/o/r"}
    out = sc.capture(s)
    assert asked[0][0] == sc.browse_plan("https://github.com/o/r")
    assert out["recording"].endswith("recording.mp4") and out["rec_seconds"] == 200.0
    assert out["screenshot"] == "shot.png" and out["pages"] == 2
    assert set(out["provisional"]) == {c for cs in out["scene_clips"] for c in cs}
    assert "concat=n=2" in seen[0][seen[0].index("-filter_complex") + 1]


def test_b5_recut_replaces_only_recording_clips_in_place(monkeypatch, tmp_path):
    rec = tmp_path / "recording.mp4"
    rec.write_bytes(b"0" * 2000)
    clips = [[str(tmp_path / f"chunk_{i:03d}.mp4")] for i in range(3)]
    clips[1].insert(0, "statcard_02.mp4")
    cap = {"recording": str(rec), "rec_seconds": 100.0,
           "provisional": [c for cs in clips for c in cs if "chunk_" in c]}
    seen = []
    monkeypatch.setattr(sc, "_ffmpeg", _b5_fake_ffmpeg(seen))
    assert sc.recut(cap, clips, [30.0, 40.0, 30.0]) == 3
    assert clips[1][0] == "statcard_02.mp4"
    assert [Path(c[-1]).name for c in clips] == ["piece_000_0.mp4", "piece_001_1.mp4",
                                                 "piece_002_0.mp4"]
    assert all("-stream_loop" not in a for a in seen)


def test_b5_recut_is_all_or_nothing(monkeypatch, tmp_path):
    rec = tmp_path / "recording.mp4"
    rec.write_bytes(b"0" * 2000)
    clips = [[str(tmp_path / f"chunk_{i:03d}.mp4")] for i in range(3)]
    before = [list(c) for c in clips]
    cap = {"recording": str(rec), "rec_seconds": 100.0, "provisional": [c[0] for c in clips]}
    monkeypatch.setattr(sc, "_ffmpeg", _b5_fake_ffmpeg([], fail_on="piece_001"))
    assert sc.recut(cap, clips, [30.0, 40.0, 30.0]) is None      # says it failed
    assert clips == before                                       # nothing half-replaced
    assert sc.recut(None, clips, [1.0] * 3) is None
    assert sc.recut({"recording": str(rec)}, clips, "not-a-list") is None


def test_b5_run_recuts_after_every_inject_and_before_step5():
    # v3-P.2 moved run()'s render block, unchanged in order, into _render_longform
    src = inspect.getsource(ap._render_longform)
    cut = src.index("screencap.recut(")
    for earlier in ("infographics.inject_cards(", "screencap.inject_code_card(",
                    "receipts.inject_receipt_clip(", "scene_durations("):
        assert src.index(earlier) < cut, earlier
    assert cut < src.index("eng.step5_build(")


# =============================================================== 2. lane mix
MON, TUE, WED, THU, FRI, SAT, SUN = (dt.date(2026, 11, d) for d in range(2, 9))


def _b5_sig(kind):
    return {"title": f"a {kind} signal", "url": "https://x.test/a", "source": "s",
            "kind": kind, "fit_score": 50.0}


def _b5_lane(monkeypatch, viral=None, rows=(), seats=3, **flags):
    on = {"lane_mix_v2": True, "tool_format": True, "debate_format": True}
    on.update(flags)
    monkeypatch.setattr(ap.fv, "flag", lambda name, default=False: on.get(name, default))
    calls = []

    def vp(r):
        calls.append(1)
        return (r[0], viral, "a", "h") if viral is not None else None
    monkeypatch.setattr(ap, "viral_pick", vp)
    monkeypatch.setattr(ap.debate, "panel", lambda: [{}] * seats)
    monkeypatch.setattr(ap.learn, "read_runs", lambda path=None: list(rows))
    return calls


def test_b5_lane_mix_week(monkeypatch):
    _b5_lane(monkeypatch, viral=9.0)
    both = [_b5_sig("tool"), _b5_sig("news")]
    got = {d.strftime("%a"): ap.decide_format(None, both, today=d)[0]
           for d in (MON, TUE, WED, THU, FRI, SAT, SUN)}
    assert got == {"Mon": "tool", "Tue": "tool", "Wed": "debate", "Thu": "tool",
                   "Fri": "tool", "Sat": "evergreen", "Sun": "roundup"}
    news_only = [_b5_sig("news")]
    for d in (MON, TUE, THU, FRI):
        assert ap.decide_format(None, news_only, today=d)[0] == "evergreen"


def test_b5_wednesday_falls_through_to_the_tool_rule(monkeypatch):
    _b5_lane(monkeypatch, seats=2)
    assert ap.decide_format(None, [_b5_sig("tool")], today=WED)[0] == "tool"
    assert ap.decide_format(None, [_b5_sig("news")], today=WED)[0] == "evergreen"
    _b5_lane(monkeypatch, debate_format=False)
    assert ap.decide_format(None, [_b5_sig("tool")], today=WED)[0] == "tool"


def test_b5_hot_story_takes_any_slot_once_per_iso_week(monkeypatch):
    sigs = [_b5_sig("news"), _b5_sig("tool")]
    _b5_lane(monkeypatch, viral=10.0)
    for d in (MON, WED, SAT):
        fmt, hint = ap.decide_format(None, sigs, today=d)
        assert fmt == "news" and hint[1] == 10.0
    assert ap.decide_format(None, sigs, today=SUN)[0] == "roundup"      # Sunday is untouchable
    week_news = [{"status": "PUBLISHED", "format": "news", "timestamp": "2026-11-03T12:30:00"}]
    calls = _b5_lane(monkeypatch, viral=10.0, rows=week_news)
    assert ap.decide_format(None, sigs, today=THU)[0] == "tool"
    assert ap.decide_format(None, sigs, today=SAT)[0] == "evergreen"
    assert not calls                                                    # no judge call spent


def test_b5_news_week_reads_published_news_rows_only():
    def row(status="PUBLISHED", fmt="news", ts="2026-11-03T12:30:00"):
        return {"status": status, "format": fmt, "timestamp": ts}
    assert ap.news_published_this_week(THU, [row()])
    assert not ap.news_published_this_week(THU, [row(ts="2026-11-01T12:30:00")])  # ISO wk 44
    assert not ap.news_published_this_week(THU, [row(status="FACTCHECK_BLOCKED")])
    assert not ap.news_published_this_week(THU, [row(fmt="evergreen")])
    assert not ap.news_published_this_week(THU, [row(ts="garbage"), "not a dict", None])
    assert not ap.news_published_this_week(THU, [])


def test_b5_lane_mix_off_is_todays_behaviour(monkeypatch):
    week_news = [{"status": "PUBLISHED", "format": "news", "timestamp": "2026-11-03T12:30:00"}]
    _b5_lane(monkeypatch, viral=10.0, rows=week_news, lane_mix_v2=False)
    assert ap.decide_format(None, [_b5_sig("tool")], today=THU)[0] == "news"   # no weekly cap
    _b5_lane(monkeypatch, viral=None, lane_mix_v2=False)
    assert ap.decide_format(None, [_b5_sig("tool")], today=SAT)[0] == "tool"   # no Saturday rule


def test_b5_forced_formats_are_unchanged(monkeypatch):
    _b5_lane(monkeypatch, viral=10.0)
    for f in ("news", "evergreen", "roundup", "tool", "debate"):
        assert ap.decide_format(f, [_b5_sig("tool")], today=SAT)[0] == f


def test_b5_kill_switch_is_in_both_configs():
    for name in ("config.json", "config.example.json"):
        cfg = json.loads((ROOT / name).read_text(encoding="utf-8"))
        assert cfg.get("lane_mix_v2") is True, name
    assert ap.MAX_DAY_ATTEMPTS == 3                      # the fallback chain is untouched


# =============================================================== 3. evergreen subjects
LLM_TITLES = [  # (date, title) — the real ledger, 2026-09-24 .. 2026-10-30
    ("2026-09-24", "LLMs: How Billion Parameters Understand You"),
    ("2026-09-27", "LLMs: How AI Truly Thinks"),
    ("2026-10-08", "LLM Inner Workings: How Trillion Parameters Learn"),
    ("2026-10-17", "LLM Explained: Your AI Brain Decoded"),
    ("2026-10-19", "LLMs Explained: How AI 'Thinks' With Data"),
    ("2026-10-22", "LLM Mechanics: How AI Learns to Think"),
    ("2026-10-30", "LLM Thinking: Transformers Explained"),
]
HW_TITLES = [
    ("2026-10-10", "AI Hardware: Why CPUs Fail at AI"),
    ("2026-10-21", "Beyond CPUs: Specialized AI Hardware Explained"),
    ("2026-10-26", "The Chip Revolution: Making AI Think Faster"),
]
OTHER_TITLES = [
    ("2026-10-09", "AI vs. Human Creativity: The Real Winner"),
    ("2026-10-15", "AI Art vs. Human Art: Understand the Creative Engines"),
    ("2026-10-28", "Voice AI: How Assistants Hear You"),
]


def _b5_rows(pairs, fmt="evergreen"):
    return [{"status": "PUBLISHED", "format": fmt, "title": t, "timestamp": d + "T12:00:00"}
            for d, t in pairs]


def test_b5_subject_terms_strip_the_generic_words():
    assert ap.subject_terms("LLMs Explained: How AI 'Thinks' With Data") == {"llm", "data"}
    assert ap.subject_terms("LLM Mechanics: How AI Learns to Think") == {"llm"}
    assert ap.subject_terms("How Large Language Models Actually Think") == {"llm"}
    assert ap.subject_terms("The Chip Revolution: Making AI Think Faster") == {"hardware"}
    assert "hardware" in ap.subject_terms("Beyond CPUs: Specialized AI Hardware Explained")
    assert ap.subject_terms("LLM Thinking: Transformers Explained") == {"llm"}
    assert ap._eg_stem("industries") == "industry" and ap._eg_stem("autonomous") == "autonomous"
    assert ap._eg_stem("gpus") == "gpu" and ap._eg_stem("class") == "class"


def test_b5_the_repeated_subjects_are_caught_against_earlier_ones():
    """The measured failure: every LLM / hardware evergreen after a family's first
    appearance is caught by an earlier one published inside 30 days."""
    for fam in (LLM_TITLES, HW_TITLES):
        for k, (d, title) in enumerate(fam[1:], start=1):
            day = dt.date.fromisoformat(d)
            recent = ap.recent_evergreen_titles(_b5_rows(fam[:k]), day)
            assert ap.subject_clash(title, recent), title


def test_b5_other_subjects_still_pass():
    every = _b5_rows(LLM_TITLES + HW_TITLES)
    for d, title in OTHER_TITLES:
        recent = ap.recent_evergreen_titles(every, dt.date.fromisoformat(d))
        assert ap.subject_clash(title, recent) is None, title


def test_b5_window_is_30_days_of_published_evergreens():
    rows = (_b5_rows([("2026-10-01", "LLMs: How AI Truly Thinks")])
            + _b5_rows([("2026-10-20", "LLM news row")], fmt="news")
            + [{"status": "FACTCHECK_BLOCKED", "format": "evergreen", "title": "LLM x",
                "timestamp": "2026-10-25T12:00:00"}])
    assert ap.recent_evergreen_titles(rows, dt.date(2026, 10, 31)) == ["LLMs: How AI Truly Thinks"]
    assert ap.recent_evergreen_titles(rows, dt.date(2026, 11, 1)) == []    # 31 days ago
    assert ap.EVERGREEN_SUBJECT_DAYS == 30


def test_b5_pick_evergreen_topic_skips_a_repeated_subject(monkeypatch):
    prompts = []

    def gen(prompt, **k):
        prompts.append(prompt)
        return {"topics": ["not a dict",
                           {"title_idea": "Transformers: How LLMs Really Work"},
                           {"title_idea": "GPUs vs NPUs: Which Chip Runs AI?"},
                           {"title_idea": "How Recommendation Algorithms Pick Your Feed"}]}
    monkeypatch.setattr(ap.llm, "generate_json", gen)
    monkeypatch.setattr(ap, "_read_json", lambda path, default: [])
    monkeypatch.setattr(ap, "too_many_failures", lambda t: False)
    today = dt.date.today()
    rows = _b5_rows([((today - dt.timedelta(days=3)).isoformat(), "LLM Thinking: Transformers Explained"),
                     ((today - dt.timedelta(days=6)).isoformat(), "The Chip Revolution: Making AI Think Faster")])
    monkeypatch.setattr(ap.learn, "read_runs", lambda path=None: rows)
    t = ap.pick_evergreen_topic([])
    assert t["title_idea"] == "How Recommendation Algorithms Pick Your Feed"
    assert "RECENT SUBJECTS" in prompts[0] and "LLM Thinking" in prompts[0]


def test_b5_pick_evergreen_topic_survives_a_missing_ledger(monkeypatch):
    monkeypatch.setattr(ap.llm, "generate_json",
                        lambda p, **k: {"topics": [{"title_idea": "LLMs: How They Work"}]})
    monkeypatch.setattr(ap, "_read_json", lambda path, default: [])
    monkeypatch.setattr(ap, "too_many_failures", lambda t: False)

    def boom(path=None):
        raise FileNotFoundError(path)
    monkeypatch.setattr(ap.learn, "read_runs", boom)
    assert ap.pick_evergreen_topic([])["title_idea"] == "LLMs: How They Work"
