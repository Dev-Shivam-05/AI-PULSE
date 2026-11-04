"""v3-S.1: native concept Short + Pilot B + Reels source (docs/spec/ai-pulse-v3s1.md).

Tests never run ffmpeg, Chromium, the network or the LLM: every seam is stubbed
as its consumer sees it. Helpers are prefixed `_s1_` (the shared-module helper
name trap)."""
import ast
import datetime as dt
import json
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factverse import ai_pipeline as ap    # noqa: E402
from factverse import learn                # noqa: E402
from factverse import native_short as ns   # noqa: E402
from factverse import pilot_b as pb        # noqa: E402
from factverse import reels                # noqa: E402
from factverse import scheduling           # noqa: E402
from factverse import state_merge as sm    # noqa: E402
from factverse import storyboard as sbd    # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

_S1_SENTENCES = ["AI runs on GPUs because they do thousands of small sums at once.",
                 "A CPU has a few strong cores that work one task after another.",
                 "A GPU has thousands of simple cores working at the same time.",
                 "But for branching everyday code, the CPU is still faster.",
                 "So parallel math goes to the GPU, and decisions stay on the CPU."]
_S1_SOURCE = "A CPU has a few powerful cores. A GPU has thousands of simpler cores."


def _s1_answer(**over):
    a = {"question": "Why does AI run on GPUs?", "headline": "GPUs vs CPUs for AI",
         "sentences": list(_S1_SENTENCES), "answer": 1, "qualification": 4,
         "diagram": {"template": "compare", "slots": {
             "left": [{"text": "CPU cores", "cue": "CPU has"},
                      {"text": "few strong cores", "cue": "strong cores"}],
             "right": [{"text": "GPU cores", "cue": "GPU has"},
                       {"text": "thousands of cores", "cue": "simple cores"}]}},
         "title": "Why AI runs on GPUs"}
    a.update(over)
    return a


def _s1_spec(**over):
    spec, f = ns.validate(_s1_answer(**over), _S1_SOURCE)
    assert spec, f
    return spec


def _s1_words(sentences=_S1_SENTENCES, start=0.15, step=0.36):
    out, t = [], start
    for w in " ".join(sentences).split():
        out.append((round(t, 3), round(t + 0.3, 3), w.strip(".,")))
        t += step
    return out


def _s1_good_measure(**over):
    m = {"duration": 24.5, "source": "asr", "first_speech": 0.18, "script_words": 61,
         "sentence_ends": [3.64, 7.92, 12.18, 16.24, 21.0]}
    m.update(over)
    return m


def _s1_meta(**over):
    m = {"unfit": [], "min_px": 60, "shown": {"0.0": {"shown": 7, "total": 7},
                                              "2.0": {"shown": 7, "total": 7}}}
    m.update(over)
    return m


# =============================================================== locked values
def test_s1_locked_round3_values():
    assert ns.HEADLINE_WORDS == 8 and ns.FIRST_SPEECH_S == 0.30
    assert ns.FIRST_SENTENCE_WORDS == 14 and ns.FIRST_SENTENCE_END_S == 5.00
    assert ns.ANSWER_BY_S == 7.0 and (ns.MIN_LEN_S, ns.MAX_LEN_S) == (20.0, 28.0)
    assert ns.MAX_WORDS == 65 and ns.END_MARGIN_S == 2.0 and ns.NO_REVEAL_S == 2.0
    assert ns.MIN_TEXT_PX == 60 and ns.REPAIRS == 1 and (ns.W, ns.H) == (1080, 1920)
    # delegated margins stay INSIDE the round-3 limits
    assert ns.LEAD_S < ns.FIRST_SPEECH_S and ns.HOLD_S > ns.END_MARGIN_S
    assert pb.SLOTS == ("18:45", "01:30") and pb.PAIRS_PER_BATCH == 6
    assert (pb.BASELINE_CROP_MEDIAN, pb.BASELINE_N, pb.FLOOR_IMPRESSIONS) == (16.9, 18, 100)
    assert (pb.PROMISING_MEDIAN, pb.PROMISING_ADV, pb.PROMISING_WINS) == (22.0, 5.0, 5)
    assert (pb.STOP_WINS, pb.STOP_DISADV) == (1, 5.0)
    assert (pb.SECOND_BATCH_PAIRS, pb.SECOND_BATCH_MAX_WINS, pb.GUARDRAIL_DECLINE) == (12, 6, 0.10)


# =============================================================== script validation
def test_s1_validate_accepts_a_good_answer_and_coerces_it():
    spec = _s1_spec()
    assert spec["headline"] == "GPUs vs CPUs for AI" and len(spec["sentences"]) == 5
    assert spec["template"] == "compare" and spec["qualification"] == 4 and spec["answer"] == 1
    assert spec["title"] == "Why AI runs on GPUs #Shorts"
    # a single string of sentences, a missing full stop, a junk answer index, a URL
    s2 = _s1_spec(sentences="AI runs on GPUs because they do sums at once. A CPU has strong cores",
                  answer="banana", qualification=True)
    assert s2["sentences"][-1].endswith(".") and s2["answer"] == 1
    s3 = _s1_spec(sentences=["AI runs on GPUs https://evil.test/x because they do sums.", None,
                             {"x": 1}, "A CPU has strong cores."])
    assert "http" not in " ".join(s3["sentences"]) and len(s3["sentences"]) == 2


@pytest.mark.parametrize("over, needle", [
    ({"headline": "one two three four five six seven eight nine"}, "headline must be"),
    ({"headline": ""}, "headline must be"),
    ({"headline": "SHOCKING GPUs secret"}, "hype"),
    ({"sentences": ["AI runs on GPUs because they do thousands and thousands of small sums at once."]
      + _S1_SENTENCES[1:]}, "sentence 1 has"),
    ({"sentences": _S1_SENTENCES + ["A GPU has many cores and they all run the same sums at once again."]},
     "spoken words"),
    ({"sentences": _S1_SENTENCES[:4] + ["Subscribe for more GPU cores."]}, "call to action"),
    ({"sentences": ["AI runs on GPUs because they do 4096 sums at once."] + _S1_SENTENCES[1:]},
     "numbers not in the source"),
    ({"diagram": {"template": "compare", "slots": {"left": [{"text": "CPU cores", "cue": ""}],
                                                    "right": [{"text": "GPU cores", "cue": ""}]}}},
     "diagram must be"),
    ({"diagram": {"template": "bars", "slots": {}}}, "diagram must be"),
    ({"diagram": "steps"}, "diagram must be"),
    ({"diagram": {"template": "steps", "slots": {"steps": [{"text": "banana pudding", "cue": ""},
                                                           {"text": "GPU cores", "cue": ""},
                                                           {"text": "CPU cores", "cue": ""}]}}},
     "shares no spoken word"),
    ({"qualification": 5}, "qualification is the last sentence"),
])
def test_s1_validate_rejects_each_broken_rule(over, needle):
    spec, f = ns.validate(_s1_answer(**over), _S1_SOURCE)
    assert spec is None and any(needle in x for x in f), f


def test_s1_validate_survives_hostile_model_output():
    for raw in (None, "json", 42, [], [{"headline": "x"}], {"sentences": None},
                {"sentences": [None]}, {"headline": {"a": 1}, "sentences": ["x."]},
                {"diagram": {"template": "<script>", "slots": []}, "sentences": ["Hi there."]}):
        spec, f = ns.validate(raw, "")
        assert spec is None and f


def test_s1_steps_diagram_is_a_causal_chain():
    steps = {"template": "steps", "slots": {"steps": [{"text": "small sums", "cue": "small sums"},
                                                     {"text": "simple cores", "cue": "simple cores"},
                                                     {"text": "same time", "cue": "same time"}]}}
    spec = _s1_spec(diagram=steps)
    assert spec["template"] == "steps" and [e["role"] for e in spec["els"]] == ["step"] * 3


def test_s1_match_level_uses_the_storyboard_gate_on_the_crop_excerpt():
    spec = _s1_spec()
    assert ns.match_level(spec, "A CPU has strong cores. A GPU has thousands of cores.") == "same_question"
    assert ns.match_level(spec, "Something about batteries entirely.") == "concept_family"
    assert ns.match_level(spec, "") == "concept_family"


# =============================================================== board (frame 0, no reveal)
def test_s1_board_is_complete_at_frame_zero_and_still_for_two_seconds():
    spec = _s1_spec()
    words = _s1_words()
    b = ns.board(spec, words, 24.5)
    beat = b["beats"][0]
    assert len(b["beats"]) == 1 and beat["start"] == 0.0 and beat["end"] == 24.5
    assert b["floor"] == 60 and beat["stack"] is True
    assert beat["head"]["text"] == "GPUs vs CPUs for AI" and beat["head"]["t"] < 0
    assert all(e["t"] < 0 for e in beat["els"])                     # fully drawn at 0.00 s
    hls = [h for e in beat["els"] for h in e["hl"]]
    assert hls and all(ns.NO_REVEAL_S <= h <= 24.5 - ns.END_MARGIN_S - sbd.HIGHLIGHT_S for h in hls)
    assert all(a >= ns.NO_REVEAL_S for a, _ in b["intervals"])      # nothing moves before 2 s
    # a cue spoken in the first 2 s is NOT pointed at
    early = ns.board(_s1_spec(), [(0.1, 0.4, "CPU"), (0.5, 0.8, "has")] + words, 24.5)
    assert all(h >= 2.0 for e in early["beats"][0]["els"] for h in e["hl"])


def test_s1_plan_length_trims_the_lead_and_holds_the_end():
    shift, length = ns.plan_length([(0.62, 0.9, "a"), (10.0, 10.4, "b")])
    assert shift == round(0.62 - ns.LEAD_S, 3)
    assert length == 20.0                                   # padded up to the 20 s floor
    shift, length = ns.plan_length([(0.1, 0.3, "a"), (21.0, 21.37, "b")])
    assert shift == 0.0 and length >= 21.37 + ns.HOLD_S
    assert abs(length * 30 - round(length * 30)) < 1e-6     # a whole frame
    assert ns.plan_length([(0.1, 0.3, "a"), (25.7, 26.0, "b")]) is None   # cannot fit 28 s
    assert ns.plan_length([]) is None


# =============================================================== measuring the encoded file
def test_s1_sentence_ends_align_conservatively():
    sents = ["GPT-5 is fast.", "It runs on GPUs.", "That is why."]
    asr = [(0.1, 0.4, "GPT"), (0.4, 0.6, "5"), (0.6, 0.8, "is"), (0.8, 1.2, "fast"),
           (1.5, 1.7, "It"), (1.7, 1.9, "runs"), (1.9, 2.0, "on"), (2.0, 2.5, "GPUs"),
           (2.9, 3.1, "That"), (3.1, 3.2, "is"), (3.2, 3.6, "why")]
    assert ns.sentence_ends(asr, sents) == [1.2, 2.5, 3.6]
    # an unaligned word at a boundary is counted with the EARLIER sentence
    asr2 = asr[:4] + [(1.3, 1.45, "um")] + asr[4:]
    assert ns.sentence_ends(asr2, sents)[0] == 1.45
    assert ns.sentence_ends([], sents) == [] and ns.sentence_ends(asr, []) == []


def test_s1_silencedetect_parsing():
    err = ("[silencedetect] silence_start: 0\n[silencedetect] silence_end: 0.182 | silence_duration: 0.182\n"
           "[silencedetect] silence_start: 3.72\n[silencedetect] silence_end: 4.62 | silence_duration: 0.9\n"
           "[silencedetect] silence_start: 21.08\n[silencedetect] silence_end: 24.5 | silence_duration: 3.42\n")
    assert ns.parse_onset(err) == 0.182
    assert ns.parse_offset(err, 24.5) == 21.08
    assert ns.parse_onset("silence_start: 1.0\nsilence_end: 2.0") == 0.0      # sound from sample 0
    assert ns.parse_onset("silence_start: 0") is None                         # silent file
    assert ns.parse_offset("silence_start: 3\nsilence_end: 4", 24.5) == 24.5  # sound to the end
    assert ns.parse_offset("", 0) is None and ns.parse_silences(None) == []


def test_s1_measure_takes_the_later_of_whisper_and_the_energy_onset(monkeypatch, tmp_path):
    from factverse import shorts as sh
    monkeypatch.setattr(ns.fv, "TEMP", tmp_path)
    monkeypatch.setattr(sh.eng, "dur", lambda p: 24.5)

    class _R:
        returncode = 0
        stderr = "silence_start: 0\nsilence_end: 0.21\nsilence_start: 21.3\nsilence_end: 24.5\n"

    def fake_run(args, **k):
        if "-ar" in args:
            Path(args[-1]).write_bytes(b"wav")
        return _R()
    monkeypatch.setattr(ns.subprocess, "run", fake_run)
    words = _s1_words(start=0.0)
    monkeypatch.setattr(ns.cap, "transcribe_words", lambda p: words)
    m = ns.measure("x.mp4", _S1_SENTENCES)
    assert m["source"] == "asr" and m["asr_first"] == 0.0 and m["onset"] == 0.21
    assert m["first_speech"] == 0.21                         # whisper's 0.00 clamp is not trusted
    assert m["sentence_ends"][-1] >= 21.3 and m["asr_words"] == len(words)
    # no whisper: the planned timings re-anchored on the measured onset
    monkeypatch.setattr(ns.cap, "transcribe_words", lambda p: [])
    m = ns.measure("x.mp4", _S1_SENTENCES, planned=_s1_words(start=0.15))
    assert m["source"] == "tts+silencedetect" and m["first_speech"] == 0.21
    # nothing measurable -> the gate refuses
    monkeypatch.setattr(ns.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    m = ns.measure("x.mp4", _S1_SENTENCES)
    assert m["source"] == "none" and ns.gate(m, _s1_spec(), None)


# =============================================================== the gate
def test_s1_gate_passes_the_rendered_sample():
    assert ns.gate(_s1_good_measure(), _s1_spec(), _s1_meta()) == []


@pytest.mark.parametrize("over, meta, needle", [
    ({"first_speech": 0.31}, {}, "speech starts"),
    ({"sentence_ends": [5.01, 7.0, 12.0, 16.0, 21.0]}, {}, "sentence 1 ends"),
    ({"duration": 19.9}, {}, "duration"),
    ({"duration": 28.1, "sentence_ends": [3.0, 6.0, 12.0, 16.0, 21.0]}, {}, "duration"),
    ({"script_words": 66}, {}, "spoken words"),
    ({"sentence_ends": [3.0, 6.0, 12.0, 16.0, 22.6]}, {}, "takeaway"),
    ({"sentence_ends": [3.0, 6.0, 12.0, 23.0, 23.0], "duration": 24.5}, {}, "qualification"),
    ({}, {"min_px": 56}, "smallest on-screen text"),
    ({}, {"min_px": None}, "smallest on-screen text"),
    ({}, {"unfit": [0]}, "does not fit"),
    ({}, {"shown": {"0.0": {"shown": 6, "total": 7}, "2.0": {"shown": 7, "total": 7}}}, "at 0.0s"),
    ({}, {"shown": {"0.0": {"shown": 7, "total": 7}, "2.0": {"shown": 5, "total": 7}}}, "at 2.0s"),
    ({}, {"shown": {}}, "fully drawn"),
])
def test_s1_gate_fails_each_rule(over, meta, needle):
    f = ns.gate(_s1_good_measure(**over), _s1_spec(), _s1_meta(**meta))
    assert any(needle in x for x in f), f


def test_s1_answer_in_sentence_two_is_checked_at_seven_seconds():
    spec = _s1_spec(answer=2)
    assert ns.gate(_s1_good_measure(sentence_ends=[3.6, 6.9, 12.0, 16.0, 21.0]), spec, _s1_meta()) == []
    assert ns.gate(_s1_good_measure(), spec, _s1_meta())       # 7.92 > 7.0


# =============================================================== render args (no ffmpeg)
def test_s1_mux_has_no_cta_no_sting_and_trims_the_lead():
    args = ns.mux_args("v.mp4", "a.mp3", 0.47, 24.5, "ToolDojo", "o.mp4")
    joined = " ".join(args)
    assert args[args.index("-ss") + 1] == "0.470" and args.index("-ss") < args.index("a.mp3")
    assert args[args.index("-t") + 1] == "24.500" and "atrim=0:24.500" in joined
    assert "ToolDojo" in joined and "fontsize=42" in joined                 # the control's watermark
    for cta in ("Full video", "SUBSCRIBE", "yellow", "intro_v", "outro_v", "enable="):
        assert cta not in joined
    cargs = ns.caption_args("raw.mp4", "nv.ass", "out.mp4")
    assert "ass=nv.ass" in cargs and cargs[-1] == "out.mp4"
    assert ns.extract_args("x.mp4", "x.wav")[-1] == "x.wav"
    assert "silencedetect=noise=-45dB:d=0.1" in " ".join(ns.silence_args("x.mp4"))


def test_s1_heavy_imports_stay_inside_functions():
    for mod in ("native_short.py", "pilot_b.py"):
        tree = ast.parse((ROOT / "factverse" / mod).read_text(encoding="utf-8"))
        top = [ast.dump(n) for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        for heavy in ("playwright", "faster_whisper", "kokoro", "cv2"):
            assert not any(heavy in t for t in top), (mod, heavy)


# =============================================================== make(): one call, one repair
def test_s1_make_repairs_once_then_skips(monkeypatch):
    prompts = []

    def fake_llm(p, **k):
        prompts.append(p)
        return {"headline": "x"} if len(prompts) == 1 else _s1_answer()
    monkeypatch.setattr(ns.llm, "generate_json", fake_llm)
    built = []
    monkeypatch.setattr(ns, "build", lambda spec, tag="": (built.append(spec) or
                        ({"path": "short_nv_1.mp4", "measured": _s1_good_measure()}, [])))
    res = ns.make({"title": "T", "scenes": []}, hook="h", excerpt="A CPU has strong cores.")
    assert res and len(prompts) == 2 and res["attempts"] == 2
    assert "FAILED THESE CHECKS" in prompts[1] and "no sentences" in prompts[1]
    assert res["match"] == "same_question" and ns.last_skip == ""
    # a timeline that fails twice is skipped after exactly 1 + REPAIRS model calls
    prompts.clear()
    monkeypatch.setattr(ns.llm, "generate_json", lambda p, **k: prompts.append(p) or _s1_answer())
    monkeypatch.setattr(ns, "build", lambda spec, tag="": (None, ["sentence 1 ends at 5.40s"]))
    assert ns.make({"title": "T", "scenes": []}) is None
    assert len(prompts) == 1 + ns.REPAIRS and "5.40" in ns.last_skip


def test_s1_make_never_raises(monkeypatch):
    monkeypatch.setattr(ns.llm, "generate_json", lambda p, **k: 1 / 0)
    assert ns.make({"title": "T"}) is None and "ZeroDivisionError" in ns.last_skip
    monkeypatch.setattr(ns.llm, "generate_json", lambda p, **k: _s1_answer())
    monkeypatch.setattr(ns, "build", lambda spec, tag="": (_ for _ in ()).throw(RuntimeError("boom")))
    assert ns.make(None) is None and ns.last_skip


def test_s1_a_short_that_fails_the_encoded_check_is_deleted(monkeypatch, tmp_path):
    """A failed file left in output/shorts could be picked up by Reels."""
    from factverse import shorts as sh
    monkeypatch.setattr(ns.fv, "TEMP", tmp_path)
    monkeypatch.setattr(ns.fv, "SHORTS", tmp_path)
    monkeypatch.setattr(ns, "voice", lambda text: ("a.mp3", _s1_words()))
    monkeypatch.setattr(ns.cap, "correct_words", lambda w, t: w)
    vis = tmp_path / "vis.mp4"
    vis.write_bytes(b"0" * 20000)
    monkeypatch.setattr(ns.sb, "render_meta", lambda *a, **k: (str(vis), _s1_meta()))
    monkeypatch.setattr(sh, "_ensure_font", lambda: tmp_path)
    monkeypatch.setattr(ns.cap, "build_ass", lambda *a, **k: str(tmp_path / "nv.ass"))

    class _R:
        returncode, stderr = 0, ""
    monkeypatch.setattr(ns.subprocess, "run",
                        lambda args, **k: (Path(args[-1]).write_bytes(b"0" * 20000), _R())[1])
    monkeypatch.setattr(ns, "measure", lambda *a, **k: _s1_good_measure(first_speech=0.9))
    res, f = ns.build(_s1_spec())
    assert res is None and any("speech starts" in x for x in f)
    assert not list(tmp_path.glob("short*_nv_*.mp4"))
    monkeypatch.setattr(ns, "measure", lambda *a, **k: _s1_good_measure())
    res, f = ns.build(_s1_spec())
    assert f == [] and "_nv_" in res["path"] and Path(res["path"]).exists()
    assert sbd.engine_of(res["path"]) == "native"


def test_s1_unfit_text_is_a_repairable_failure_not_a_demotion(monkeypatch, tmp_path):
    monkeypatch.setattr(ns.fv, "TEMP", tmp_path)
    monkeypatch.setattr(ns, "voice", lambda text: ("a.mp3", _s1_words()))
    monkeypatch.setattr(ns.cap, "correct_words", lambda w, t: w)
    seen = {}

    def fake_render(board, out, words, demote_unfit=True, probes=()):
        seen.update(demote=demote_unfit, probes=probes, floor=board["floor"])
        return None, _s1_meta(unfit=[0])
    monkeypatch.setattr(ns.sb, "render_meta", fake_render)
    res, f = ns.build(_s1_spec())
    assert res is None and any("does not fit at 60px" in x for x in f)
    assert seen == {"demote": False, "probes": (0.0, 2.0), "floor": 60}


# =============================================================== storyboard + page
def test_s1_engine_label_and_page():
    assert sbd.engine_of("C:\\out\\short_nv_20261105_1200.mp4") == "native"
    assert sbd.engine_of("/tmp/out/short_1_sb_20261105_1200.mp4") == "storyboard"
    assert sbd.engine_of("/tmp/out/short_2_20261105_1200.mp4") == "crop"
    page = (ROOT / "assets" / "storyboard" / "storyboard.html").read_text(encoding="utf-8")
    assert "innerHTML" not in page and "http://" not in page and "https://" not in page
    for api in ("window.__minSize", "window.__shown", "function floor()", "HEAD_TOP = 192",
                "STAGE_BOTTOM = 1150", ".beat.stack .cols"):
        assert api in page, api
    # the storyboard trap: a hidden beat's headline is hidden with display, never visibility
    assert "root._head.style.display" in page and "_head.style.visibility" not in page


# =============================================================== scheduling
def test_s1_pilot_slots_are_exactly_1845_and_0130():
    now = dt.datetime(2026, 11, 5, 12, 23, tzinfo=dt.timezone.utc)
    assert scheduling.pilot_b_slots("2026-11-05T16:45:00Z", now=now) == [
        "2026-11-05T18:45:00Z", "2026-11-06T01:30:00Z"]
    # a moved long-form slot cannot move the pilot
    assert scheduling.pilot_b_slots("2026-11-05T15:00:00Z", now=now)[0] == "2026-11-05T18:45:00Z"
    # today's grid already gives the same two with the default 16:45 slot
    assert scheduling.shorts_slots_after_long(2, "2026-11-05T16:45:00Z") == [
        "2026-11-05T18:45:00Z", "2026-11-06T01:30:00Z"]
    late = dt.datetime(2026, 11, 5, 18, 30, tzinfo=dt.timezone.utc)
    assert scheduling.pilot_b_slots("2026-11-05T16:45:00Z", now=late) is None
    assert scheduling.pilot_b_slots("garbage") is None and scheduling.pilot_b_slots(None) is None
    assert scheduling.slot_label("2026-11-05T18:45:00Z") == "18:45"
    assert scheduling.slot_label(None) is None and scheduling.slot_label("x") is None


# =============================================================== assignment
def test_s1_assignment_alternates_and_balances_slots():
    st = pb.empty_state()
    got = []
    for k in range(7):
        day = (dt.date(2026, 11, 5) + dt.timedelta(days=k)).isoformat()
        a = pb.assign(st, day, 1, rng=random.Random(7))
        if a:
            st["days"][day] = dict(a)
        got.append(a)
    assert got[-1] is None                                          # batch 1 complete
    six = got[:6]
    assert [a["pair_id"] for a in six] == [f"B1-0{i}" for i in range(1, 7)]
    assert all(a["native_slot"] != b["native_slot"] for a, b in zip(six, six[1:]))   # daily alternation
    for slot in pb.SLOTS:
        assert sum(a["native_slot"] == slot for a in six) == 3      # each format, each slot, 3 times
        assert sum(a["crop_slot"] == slot for a in six) == 3
    b1 = st["batches"]["1"]
    assert b1["first_native_slot"] == six[0]["native_slot"] and "SystemRandom" in b1["method"]
    # a retry run on a recorded day gets ITS assignment back, not the next one
    assert pb.assign(st, "2026-11-07", 1)["pair_id"] == "B1-03"
    # batch 2 only when the owner allows it, with its own draw
    a = pb.assign(st, "2026-11-20", 2, rng=random.Random(1))
    assert a["pair_id"] == "B2-01" and "2" in st["batches"]
    # the default draw really is random over both slots
    firsts = {pb.assign(pb.empty_state(), "2026-11-05", 1)["native_slot"] for _ in range(60)}
    assert firsts == set(pb.SLOTS)


def test_s1_schedule_print_is_balanced():
    rows = pb.schedule("01:30", dt.date(2026, 11, 5))
    assert len(rows) == 6 and rows[0]["01:30"].endswith("native") and rows[1]["18:45"].endswith("native")
    assert sum(r["18:45"].endswith("native") for r in rows) == 3


# =============================================================== composition + ledger
def test_s1_compose_puts_each_format_in_its_slot():
    nat = {"path": "out/short_nv_1.mp4", "spec": {"headline": "GPUs vs CPUs"}}
    c = pb.compose(["c1.mp4", "c2.mp4"], ["hook1", "hook2"], nat, 0)
    assert c == {"shorts": ["out/short_nv_1.mp4", "c1.mp4"], "hooks": ["GPUs vs CPUs", "hook1"]}
    c = pb.compose(["c1.mp4", "c2.mp4"], ["hook1", "hook2"], nat, 1)
    assert c["shorts"] == ["c1.mp4", "out/short_nv_1.mp4"]
    # native skipped: the spare crop fills the native slot, the control keeps its own
    assert pb.compose(["c1.mp4", "c2.mp4"], ["h1", "h2"], None, 0)["shorts"] == ["c2.mp4", "c1.mp4"]
    assert pb.compose(["c1.mp4", "c2.mp4"], ["h1", "h2"], None, 1)["shorts"] == ["c1.mp4", "c2.mp4"]
    assert pb.compose(["c1.mp4"], ["h1"], None, 0)["shorts"] == ["c1.mp4"]
    assert pb.compose([], [], nat, 1)["shorts"] == ["out/short_nv_1.mp4"]
    assert pb.compose(["c1.mp4", "c2.mp4"], None, None, 0)["hooks"] == ["", ""]


def test_s1_plan_and_ledger_fields(tmp_path):
    st = pb.empty_state()
    nat = {"path": "short_nv_1.mp4", "spec": {"headline": "H", "title": "H #Shorts"}, "match": "same_question",
           "measured": _s1_good_measure(), "attempts": 1}
    plan = pb.plan_day("2026-11-05", ["c1.mp4", "c2.mp4"], ["h1", "h2"], nat, state=st, pilot=True)
    a = plan["assignment"]
    assert plan["shorts"][plan["native_index"]] == "short_nv_1.mp4"
    assert pb.ledger_fields(plan) == {"experiment": "pilot_b", "pair_id": "B1-01",
                                      "arm": f"native@{a['native_slot']}", "slot": a["native_slot"]}
    skipped = pb.plan_day("2026-11-06", ["c1.mp4", "c2.mp4"], ["h1", "h2"], None, "sentence 1 too long",
                          state=st, pilot=True)
    assert pb.ledger_fields(skipped)["arm"].startswith("native_skipped@")
    off = pb.plan_day("2026-11-05", ["c1.mp4", "c2.mp4"], ["h1", "h2"], nat, state=pb.empty_state(),
                      pilot=False, parity_index=1)
    assert off["assignment"] is None and pb.ledger_fields(off) == {} and off["native_index"] == 1
    assert pb.ledger_fields(None) == {} and pb.ledger_fields({"assignment": {}}) == {}
    # never raises, whatever it is handed
    bad = pb.plan_day("2026-11-05", 42, None, {"path": 1}, state={"days": 5})
    assert isinstance(bad, dict) and "shorts" in bad


def test_s1_record_writes_every_assigned_day_and_never_raises(tmp_path):
    p = tmp_path / "pilot_b.json"
    st = pb.empty_state()
    nat = {"path": "short_nv_1.mp4", "spec": {"headline": "H"}, "match": "same_question",
           "measured": _s1_good_measure(), "attempts": 1}
    plan = pb.plan_day("2026-11-05", ["c1.mp4", "c2.mp4"], ["h1", "h2"], nat, state=st, pilot=True)
    a = plan["assignment"]
    rows = [{"url": "https://youtube.com/shorts/NNNNNNNNNNN", "engine": "native", "slot": a["native_slot"]},
            {"url": "https://youtube.com/shorts/CCCCCCCCCCC", "engine": "crop", "slot": a["crop_slot"]}]
    assert pb.record(plan, rows, "https://youtube.com/watch?v=LLLLLLLLLLL", True, path=p)
    d = pb.load_state(p)["days"]["2026-11-05"]
    assert d["evaluable_by_design"] and d["native"]["status"] == "published" and d["match"] == "same_question"
    assert d["native"]["first_speech"] == 0.18 and d["crop"]["hook"] == "h1"
    assert pb.load_state(p)["batches"]["1"]["first_native_slot"] in pb.SLOTS     # the draw is recorded
    # a skipped native is recorded too, as unevaluable — never silently dropped
    st2 = pb.load_state(p)
    plan2 = pb.plan_day("2026-11-06", ["c1.mp4", "c2.mp4"], ["h1", "h2"], None, "the answer ends after 7.0s",
                        state=st2, pilot=True)
    assert pb.record(plan2, rows[1:], "u", True, path=p)
    d2 = pb.load_state(p)["days"]["2026-11-06"]
    assert not d2["evaluable_by_design"] and "7.0s" in d2["unevaluable_reason"]
    assert d2["native"]["status"] == "skipped" and d2["index"] == 1
    # off-slot and no-assignment and junk
    plan3 = pb.plan_day("2026-11-07", ["c1.mp4"], ["h1"], nat, state=pb.load_state(p), pilot=True)
    assert pb.record(plan3, rows, "u", False, path=p)
    assert "normal grid" in pb.load_state(p)["days"]["2026-11-07"]["unevaluable_reason"]
    assert pb.record(None, rows, "u", True, path=p) is False
    assert pb.record({"assignment": {"x": 1}, "state": {}}, "junk", None, True, path=p) is False


# =============================================================== state file (both halves)
def test_s1_state_file_has_the_both_halves_treatment():
    wf = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    assert "state/pilot_b.json" in sm.FILES and "state/pilot_b.json" in wf
    assert "state/pilot_b.json" in ap.pilot_b.STATE_FILE.as_posix()
    # basenames must stay unique: main() reads the incoming copy by basename
    names = [Path(f).name for f in sm.FILES]
    assert len(names) == len(set(names))


def test_s1_state_merge_keeps_the_first_draw_and_unions_days():
    theirs = {"experiment": "pilot_b", "batches": {"1": {"first_native_slot": "18:45", "drawn_at": "a"}},
              "days": {"2026-11-05": {"pair_id": "B1-01", "recorded_at": "2026-11-05T12:40:00+00:00"}}}
    ours = {"experiment": "pilot_b", "batches": {"1": {"first_native_slot": "01:30", "drawn_at": "b"}},
            "days": {"2026-11-05": {"pair_id": "B1-01", "recorded_at": "2026-11-05T15:10:00+00:00", "x": 1},
                     "2026-11-06": {"pair_id": "B1-02", "recorded_at": "2026-11-06T12:40:00+00:00"}}}
    merged = json.loads(sm.merge_file("state/pilot_b.json", json.dumps(ours), json.dumps(theirs)))
    assert merged["batches"]["1"]["first_native_slot"] == "18:45"          # origin/main's draw
    assert merged["days"]["2026-11-05"]["x"] == 1                           # later recorded_at
    assert set(merged["days"]) == {"2026-11-05", "2026-11-06"}
    # a corrupt or mis-shaped side never raises (the CI state-save has no `|| true`)
    for junk in ("[1, 2]", '"x"', "42", '{"batches": [1], "days": "x"}'):
        out = json.loads(sm.merge_file("state/pilot_b.json", junk, json.dumps(theirs)))
        assert out["batches"]["1"]["first_native_slot"] == "18:45"
    assert json.loads(sm.merge_file("state/pilot_b.json", json.dumps(ours), None))["days"]


def test_s1_load_state_survives_a_corrupt_file(tmp_path):
    p = tmp_path / "s.json"
    for body in ("{not json", "[]", '{"days": [1], "batches": 3}', '{"days": {"d": 5}}'):
        p.write_text(body, encoding="utf-8")
        assert pb.load_state(p) == pb.empty_state()
    assert pb.load_state(tmp_path / "missing.json") == pb.empty_state()


# =============================================================== readout
def _s1_csv(path, rows, stayed=True):
    head = ["Content", "Video title", "Video publish time", "Shown in feed"]
    head += ["Stayed to watch (%)"] if stayed else ["Engaged views"]
    lines = [",".join(head), "Total,,,99999," + ("12.0" if stayed else "5000")]
    for vid, shown, val in rows:
        lines.append(f'{vid},"A, title",Nov 5 2026,"{shown:,}",{val}')
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def _s1_state_with(n=6, skipped=()):
    st = pb.empty_state()
    for k in range(n):
        day = (dt.date(2026, 11, 5) + dt.timedelta(days=k)).isoformat()
        st["days"][day] = {"pair_id": f"B1-0{k + 1}", "batch": 1, "index": k,
                           "native_slot": pb.SLOTS[k % 2], "crop_slot": pb.SLOTS[(k + 1) % 2],
                           "native": {"url": f"https://youtube.com/shorts/NATIVE{k:05d}"},
                           "crop": {"url": f"https://youtube.com/shorts/CROPXX{k:05d}"},
                           "match": "same_question", "evaluable_by_design": k not in skipped,
                           "unevaluable_reason": "native skipped: x" if k in skipped else ""}
    return st


def test_s1_parse_studio_csv(tmp_path):
    p = tmp_path / "t.csv"
    _s1_csv(p, [("NATIVE00000", 1234, "25.5%"), ("CROPXX00000", 99, "16.0")])
    d = pb.parse_studio_csv(p)
    assert d["NATIVE00000"] == {"shown": 1234.0, "stayed": 25.5, "engaged": None, "watch_h": None}
    assert "Total" not in d and d["CROPXX00000"]["shown"] == 99.0
    # no stayed column: Studio's own definition, engaged views / shown in feed
    _s1_csv(p, [("NATIVE00000", 200, 50)], stayed=False)
    assert pb.parse_studio_csv(p)["NATIVE00000"]["stayed"] == 25.0
    p.write_text("", encoding="utf-8")
    assert pb.parse_studio_csv(p) == {}


def _s1_readout(tmp_path, pairs, skipped=(), as_of=dt.date(2026, 12, 1), feed=None):
    st = _s1_state_with(len(pairs), skipped)
    for k, (n, c, ns_, cs_) in enumerate(pairs):
        _s1_csv(tmp_path / f"B1-0{k + 1}.csv", [(f"NATIVE{k:05d}", ns_, n), (f"CROPXX{k:05d}", cs_, c)])
        if feed:
            fn, fc = feed[k]
            (tmp_path / f"B1-0{k + 1}_feed.csv").write_text(
                "Content,Shown in feed,Watch time (hours)\n"
                f"NATIVE{k:05d},{ns_},{fn}\nCROPXX{k:05d},{cs_},{fc}\n", encoding="utf-8")
    return pb.collect(st, tmp_path, as_of)


def test_s1_readout_promising(tmp_path):
    pairs = [(30, 20, 300, 300), (25, 18, 200, 250), (28, 22, 150, 400), (24, 26, 500, 500),
             (23, 15, 120, 130), (27, 19, 260, 210)]
    rows = _s1_readout(tmp_path, pairs)
    s = pb.summarize(rows)
    assert s["evaluable"] == 6 and s["wins"] == 5
    assert s["native_median"] == 26.0 and s["median_adv"] == 7.5
    assert round(s["native_agg"], 3) == round(sum(n * a for n, _, a, _ in pairs) / sum(p[2] for p in pairs), 3)
    assert s["largest_winner"] == "B1-01" and not s["outlier_dependent"]
    assert pb.verdict(s) == "promising: repeat"
    text = pb.format_readout(rows, dt.date(2026, 12, 1))
    assert "B1-06" in text and "promising: repeat" in text and "not available" in text


def test_s1_readout_unresolved_stop_revise_and_outliers(tmp_path):
    # one Short under the 100-impression floor: reported, not zeroed -> unresolved
    rows = _s1_readout(tmp_path, [(30, 20, 300, 300)] * 5 + [(30, 20, 99, 300)])
    assert pb.summarize(rows)["evaluable"] == 5
    assert "below 100 feed impressions" in rows[-1]["why"] and rows[-1]["native"] == 30
    assert pb.verdict(pb.summarize(rows)).startswith("audience effect unresolved")
    # stop: native wins <= 1 of 6 with a median disadvantage >= 5 pts
    (tmp_path / "s").mkdir()
    stop = _s1_readout(tmp_path / "s", [(10, 20, 300, 300)] * 5 + [(25, 20, 300, 300)])
    assert pb.verdict(pb.summarize(stop)).startswith("stop this native package")
    # revise: positive but below the bar
    (tmp_path / "r").mkdir()
    rev = _s1_readout(tmp_path / "r", [(19, 17, 300, 300)] * 6)
    assert pb.verdict(pb.summarize(rev)) == "revise"
    # outlier-dependent: one big winner carries the weighted aggregate
    (tmp_path / "o").mkdir()
    out = _s1_readout(tmp_path / "o", [(60, 10, 5000, 5000)] + [(16, 17, 200, 200)] * 5)
    s = pb.summarize(out)
    assert s["agg_adv"] > 0 and s["agg_adv_wo"] < 0 and s["outlier_dependent"]
    assert "OUTLIER-DEPENDENT" in pb.format_readout(out, dt.date(2026, 12, 1))


def test_s1_readout_skips_nothing_silently(tmp_path):
    rows = _s1_readout(tmp_path, [(30, 20, 300, 300)] * 6, skipped=(2,))
    assert len(rows) == 6 and not rows[2]["evaluable"] and "native skipped" in rows[2]["why"]
    # the observation window: D + 1 + 7 days
    early = _s1_readout(tmp_path, [(30, 20, 300, 300)] * 6, as_of=dt.date(2026, 11, 12))
    assert "observation window open" in early[0]["why"]
    assert not _s1_readout(tmp_path, [(30, 20, 300, 300)] * 6, as_of=dt.date(2026, 11, 13))[0]["why"]


def test_s1_watch_time_guardrail_turns_promising_into_revise(tmp_path):
    pairs = [(30, 20, 300, 300)] * 6
    rows = _s1_readout(tmp_path, pairs, feed=[(0.5, 1.0)] * 6)
    s = pb.summarize(rows)
    assert s["guardrail"]["change"] == -0.5 and pb.verdict(s).startswith("revise, not scale")
    (tmp_path / "ok").mkdir()
    rows = _s1_readout(tmp_path / "ok", pairs, feed=[(0.95, 1.0)] * 6)
    assert pb.verdict(pb.summarize(rows)) == "promising: repeat"         # -5% is inside the 10%


def test_s1_second_batch_rule():
    flat = [{"evaluable": True, "native": 17, "crop": 17, "adv": 0.0, "native_shown": 200,
             "crop_shown": 200, "pair_id": f"B{k // 6 + 1}-0{k % 6 + 1}", "batch": k // 6 + 1}
            for k in range(12)]
    assert pb.overall_verdict(pb.summarize(flat)) == "stop scaling this native implementation"
    assert "not reached" in pb.overall_verdict(pb.summarize(flat[:11]))


def test_s1_readout_cli_prints(tmp_path, capsys):
    st = _s1_state_with(1)
    sp = tmp_path / "state.json"
    sp.write_text(json.dumps(st), encoding="utf-8")
    _s1_csv(tmp_path / "B1-01.csv", [("NATIVE00000", 300, 30), ("CROPXX00000", 300, 20)])
    assert pb.main(["readout", str(tmp_path), "--state", str(sp), "--as-of", "2026-12-01"]) == 0
    assert "B1-01" in capsys.readouterr().out
    assert pb.main(["schedule", "--start", "2026-11-05", "--first", "18:45", "--state", str(sp)]) == 0
    assert "B1-06" in capsys.readouterr().out


# =============================================================== Reels
def _s1_log_row(**over):
    r = {"status": "PUBLISHED", "format": "news", "title": "T",
         "youtube_url": "https://youtube.com/watch?v=ABCDEFGHIJK",
         "shorts": ["output/shorts/short_1_20261105.mp4", "output/shorts/short_nv_20261105.mp4"]}
    r.update(over)
    return r


def _s1_file(tmp_path, rel):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\0" * 1024)
    return p


def test_s1_reels_carry_the_native_short_only(tmp_path, monkeypatch):
    _s1_file(tmp_path, "output/shorts/short_1_20261105.mp4")
    _s1_file(tmp_path, "output/shorts/short_nv_20261105.mp4")
    assert reels.native_only() is True                       # the shipped default
    assert reels.pick_entry([_s1_log_row()], [], tmp_path)[1].name == "short_nv_20261105.mp4"
    # no native that day -> nothing, never the crop
    row = _s1_log_row(shorts=["output/shorts/short_1_20261105.mp4", "output/shorts/short_2_20261105.mp4"])
    assert reels.pick_entry([row], [], tmp_path) is None
    # a native whose file is gone -> nothing, never the crop
    assert reels.pick_entry([_s1_log_row(shorts=["output/shorts/short_1_20261105.mp4",
                                                 "output/shorts/short_nv_gone.mp4"])], [], tmp_path) is None
    # Windows-authored separators still resolve
    assert reels.pick_entry([_s1_log_row(shorts=["output\\shorts\\short_nv_20261105.mp4"])], [], tmp_path)
    # kill switch off -> the pre-S.1 rule (the first Short)
    monkeypatch.setattr(reels, "native_only", lambda: False)
    assert reels.pick_entry([_s1_log_row()], [], tmp_path)[1].name == "short_1_20261105.mp4"


# =============================================================== learn
def test_s1_learn_collects_native_shorts():
    rows = [{"status": "PUBLISHED", "timestamp": "2026-11-05T12:30:00", "publish_at": "2026-11-05T16:45:00Z",
             "youtube_url": "https://youtube.com/watch?v=LLLLLLLLLLL",
             "shorts": [{"url": "https://youtube.com/shorts/NNNNNNNNNNN", "engine": "native", "slot": "18:45"},
                        {"url": "https://youtube.com/shorts/CCCCCCCCCCC", "engine": "crop", "slot": "01:30"}]}]
    assert {s["engine"] for s in learn.ledger_shorts(rows)} == {"native", "crop"}
    assert "NNNNNNNNNNN" in learn.ledger_ids(rows)
    ab = learn.shorts_ab(rows, {}, dt.date(2026, 11, 9))
    assert ab["short:native"]["videos"] == 1 and ab["pairs"] == 0


# =============================================================== config
def test_s1_kill_switches_in_both_config_files():
    for name in ("config.json", "config.example.json"):
        cfg = json.loads((ROOT / name).read_text(encoding="utf-8"))
        assert cfg["native_shorts"] is True and cfg["pilot_b"] is True
        assert cfg["pilot_b_batches"] == 1 and cfg["reels_native_only"] is True
        assert cfg["storyboard_shorts"] is True                 # the fallback engine stays switchable


# =============================================================== make_shorts
def test_s1_make_shorts_storyboard_off_and_windows(monkeypatch, tmp_path):
    from factverse import shorts as sh
    monkeypatch.setattr(sh.eng, "dur", lambda v: 60.0)
    monkeypatch.setattr(sh.eng, "find_best_moments", lambda s: [{"scene_num": 1, "hook_text": "Hook one"},
                                                                {"scene_num": 1, "hook_text": "Hook two"}])
    monkeypatch.setattr(sh, "_ensure_font", lambda: tmp_path)
    monkeypatch.setattr(sh.fv, "SHORTS", tmp_path)
    monkeypatch.setattr(sh.fv, "TEMP", tmp_path)
    monkeypatch.setattr(sh.fv, "flag", lambda name, default=False: True)     # storyboard flag ON
    monkeypatch.setattr(sh.cap, "build_ass", lambda *a, **k: str(tmp_path / "x.ass"))
    monkeypatch.setattr(sh.sb, "plan", lambda *a: (_ for _ in ()).throw(AssertionError("no storyboard")))

    class _R:
        returncode, stderr = 0, ""
    monkeypatch.setattr(sh.subprocess, "run",
                        lambda args, **k: (Path(args[-1]).write_bytes(b"0" * 20000), _R())[1])
    words = [(i * 0.4, i * 0.4 + 0.3, f"w{i}") for i in range(100)]
    out = sh.make_shorts("c.mp4", {"scenes": [{"narration": "x"}]}, words, scene_starts=[0.0],
                         max_count=2, storyboard=False)
    assert len(out) == 2 and all(sbd.engine_of(p) == "crop" for p in out)
    assert sh.last_hooks == ["Hook one", "Hook two"] and sh.last_windows[0].startswith("w0 w1")


# =============================================================== run(): the publish path
def _s1_run(monkeypatch, tmp_path, native, crops=2, flags=None):
    """run(publish=True) with every render/network seam stubbed. Returns
    (record_run kwargs, uploads [(path, publish_at)], pilot state path)."""
    script = {"title": "GPUs vs CPUs", "description": "How it works.", "tags": ["ai"], "format": "evergreen",
              "grounding": "", "scenes": [{"scene_num": i, "narration": "a calm explainer " * 10,
                                           "visual_query": "x"} for i in range(1, 9)]}
    rows, uploads = [], []
    state = tmp_path / "pilot_b.json"
    flags = {"native_shorts": True, "pilot_b": True, "auto_upload_youtube": True, **(flags or {})}
    real_flag = ap.fv.flag
    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ap.fv, "flag",
                        lambda n, default=False: flags[n] if n in flags else real_flag(n, default))
    monkeypatch.setattr(ap.pilot_b, "STATE_FILE", state)
    monkeypatch.setattr(ap.fv, "TEMP", tmp_path)
    monkeypatch.setattr(ap, "already_published_today", lambda: False)
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: None)
    monkeypatch.setattr(ap.signal_engine, "rank", lambda limit=20: [])
    monkeypatch.setattr(ap, "decide_format", lambda f, r: ("evergreen", None))
    monkeypatch.setattr(ap, "build_script", lambda f, r, v: script)
    monkeypatch.setattr(ap, "too_many_failures", lambda t: False)
    monkeypatch.setattr(ap.gates, "fact_check", lambda *a, **k: {"passed": True})
    monkeypatch.setattr(ap.gates, "confidence", lambda d: {"score": 0.9, "routing": "auto"})
    monkeypatch.setattr(ap.eng, "step3_download", lambda s: [[] for _ in s["scenes"]])
    monkeypatch.setattr(ap, "synthesize_voice", lambda n, s: ("a.mp3", [(0.0, 0.5, "w")]))
    monkeypatch.setattr(ap.captions, "transcribe_words", lambda a: [(0.0, 0.5, "w")])
    monkeypatch.setattr(ap.captions, "correct_words", lambda w, n: w)
    monkeypatch.setattr(ap.eng, "dur", lambda p: 300.0)
    monkeypatch.setattr(ap, "scene_durations", lambda s, w, d: None)
    monkeypatch.setattr(ap.infographics, "inject_cards", lambda *a, **k: None)
    monkeypatch.setattr(ap.eng, "step5_build", lambda *a, **k: "v.mp4")
    monkeypatch.setattr(ap.thumbnail, "make", lambda *a, **k: "t.jpg")

    def fake_make_shorts(*a, **k):
        assert k.get("storyboard") is False                    # the native takes that slot
        ap.shorts_mod.last_hooks[:] = [f"crop hook {i}" for i in range(crops)]
        ap.shorts_mod.last_windows[:] = ["A CPU has strong cores."] * crops
        return [f"out/short_{i + 1}_x.mp4" for i in range(crops)]
    monkeypatch.setattr(ap.shorts_mod, "make_shorts", fake_make_shorts)
    monkeypatch.setattr(ap.native_short, "make", native)
    monkeypatch.setattr(ap.scheduling, "long_slot", lambda: "2026-11-05T16:45:00Z")
    real_slots = scheduling.pilot_b_slots
    monkeypatch.setattr(ap.scheduling, "pilot_b_slots",
                        lambda lp: real_slots(lp, now=dt.datetime(2026, 11, 5, 12, 30, tzinfo=dt.timezone.utc)))
    monkeypatch.setattr(ap.captions, "build_ass", lambda *a, **k: "c.ass")
    monkeypatch.setattr(ap.captions, "burn_ass", lambda v, a, **k: v)
    monkeypatch.setattr(ap.branding, "add_intro_outro", lambda v, **k: v)
    monkeypatch.setattr(ap.l2, "inject", lambda v, at: (v, {}))
    monkeypatch.setattr(ap, "qa_video", lambda v, d: True)
    monkeypatch.setattr(ap.eng, "step8_meta", lambda s, n: [{"title": f"Meta {i} #Shorts"} for i in range(n)])
    monkeypatch.setattr(ap, "_last_published_url", lambda: "")
    n = {"i": 0}

    def fake_upload(path, title, desc, tags, thumb=None, is_short=False, publish_at=None):
        n["i"] += 1
        uploads.append((path, publish_at, title))
        return (f"https://youtube.com/shorts/SHORT{n['i']:06d}" if is_short
                else "https://youtube.com/watch?v=LONGFORM001")
    monkeypatch.setattr(ap.eng, "yt_upload", fake_upload)
    monkeypatch.setattr(ap.eng, "yt_playlist_add", lambda *a, **k: None)
    monkeypatch.setattr(ap.eng, "yt_comment", lambda *a, **k: None)
    monkeypatch.setattr(ap, "mark_used", lambda *a, **k: None)
    monkeypatch.setattr(ap, "_save_asset_record", lambda *a, **k: None)
    monkeypatch.setattr(ap.eng, "save_report", lambda *a, **k: {"status": "PUBLISHED"})
    monkeypatch.setattr(ap.eng, "cleanup", lambda: None)
    monkeypatch.setattr(ap.eng, "_rel", lambda v: v)
    monkeypatch.setattr(ap, "record_run", lambda **kw: rows.append(kw))
    ap.run(publish=True)
    return rows, uploads, state


def _s1_native_ok(script, hook="", excerpt=""):
    return {"path": "out/short_nv_x.mp4", "match": "same_question", "attempts": 1,
            "measured": _s1_good_measure(), "min_px": 60,
            "spec": {"headline": "GPUs vs CPUs", "title": "Why AI runs on GPUs #Shorts", "question": "q"}}


def test_s1_run_publishes_the_pair_on_the_pilot_slots(monkeypatch, tmp_path):
    rows, uploads, state = _s1_run(monkeypatch, tmp_path, _s1_native_ok)
    row = rows[-1]
    assert row["status"] == "PUBLISHED"
    st = pb.load_state(state)
    a = st["days"]["2026-11-05"]
    assert row["experiment"] == "pilot_b" and row["pair_id"] == "B1-01"
    assert row["arm"] == f"native@{a['native_slot']}" and row["slot"] == a["native_slot"]
    shorts = [u for u in uploads if "short" in u[0]]
    assert [u[1] for u in shorts] == ["2026-11-05T18:45:00Z", "2026-11-06T01:30:00Z"]
    nat_i = 0 if a["native_slot"] == "18:45" else 1
    assert "_nv_" in shorts[nat_i][0] and shorts[nat_i][2] == "Why AI runs on GPUs #Shorts"
    assert "_nv_" not in shorts[1 - nat_i][0]
    assert {(r["engine"], r["slot"]) for r in row["shorts"]} == {("native", a["native_slot"]),
                                                                ("crop", a["crop_slot"])}
    assert a["evaluable_by_design"] and a["native"]["url"] and a["crop"]["url"]


def test_s1_run_with_a_skipped_native_still_publishes_and_records(monkeypatch, tmp_path):
    def skipped(script, hook="", excerpt=""):
        ns.last_skip = "sentence 1 ends at 5.40s"
        return None
    rows, uploads, state = _s1_run(monkeypatch, tmp_path, skipped)
    row = rows[-1]
    assert row["status"] == "PUBLISHED" and row["arm"].startswith("native_skipped@")
    assert all(r["engine"] == "crop" for r in row["shorts"]) and len(row["shorts"]) == 2
    d = pb.load_state(state)["days"]["2026-11-05"]
    assert not d["evaluable_by_design"] and "5.40s" in d["unevaluable_reason"]


def test_s1_run_survives_a_raising_native_and_the_pilot_off(monkeypatch, tmp_path):
    rows, uploads, _ = _s1_run(monkeypatch, tmp_path, lambda *a, **k: 1 / 0)
    assert rows[-1]["status"] == "PUBLISHED" and len(rows[-1]["shorts"]) == 2
    rows, uploads, state = _s1_run(monkeypatch, tmp_path / "off", _s1_native_ok, flags={"pilot_b": False})
    assert rows[-1]["status"] == "PUBLISHED" and "experiment" not in rows[-1]
    assert any(r["engine"] == "native" for r in rows[-1]["shorts"]) and not state.exists()
