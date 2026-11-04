"""v3-P.2: opening contract, Pilot A, query-map packaging (docs/spec/ai-pulse-v3p2.md).

Network, ffmpeg, the browser and the LLM are never touched: the encoded-file gate
is exercised with PIL frames written to tmp_path and its ffmpeg seams stubbed as
the consumer sees them (op.scan, op._probe, op.encoded_words). tests/conftest.py
turns PILOT_A / QUERY_MAP / PILOT_RETENTION off; each test turns on what it needs.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factverse import ai_pipeline as ap
from factverse import evidence as ev
from factverse import opening as op
from factverse import pilot
from factverse import querymap as qm
from factverse import state_merge

_P2_GH = "https://github.com/acme/demo-tool"
_ROOT = Path(__file__).resolve().parent.parent


def _p2_on(monkeypatch, pilot_a=True, query=True, retention=False):
    monkeypatch.setenv("EVIDENCE_ENGINE", "1")
    monkeypatch.setenv("EVIDENCE_REQUIRED", "1")
    monkeypatch.setenv("CLAIM_SUBSTANTIATION", "1")
    monkeypatch.setenv("PILOT_A", "1" if pilot_a else "0")
    monkeypatch.setenv("QUERY_MAP", "1" if query else "0")
    monkeypatch.setenv("PILOT_RETENTION", "1" if retention else "0")


def _p2_author_ev(tmp_path, **over):
    clip = tmp_path / "evidence_author.mp4"
    clip.write_bytes(b"\0" * 2000)
    e = ev.empty()
    e.update({"source": "author", "status": "NOT_RUN", "label": "Author demo",
              "wording": ev.wording("NOT_RUN"), "clip": str(clip), "clip_seconds": 12.0,
              "url": f"{_P2_GH}/blob/{'a' * 40}/docs/demo.gif",
              "observed": 'The README presents this demo as "sorting files".',
              "rights": {"path": "docs/demo.gif", "commit": "a" * 40, "license": "MIT",
                         "copyright": "Copyright (c) 2026 Acme", "notice": "",
                         "modified": "Modified by ToolDojo: scaled and re-encoded."}})
    e.update(over)
    return e


def _p2_hosted_ev(tmp_path, **over):
    clip = tmp_path / "evidence_hosted.mp4"
    clip.write_bytes(b"\0" * 2000)
    e = ev.empty()
    obs = "In our hosted-demo run, this input produced image output in about 2 seconds."
    e.update({"source": "hosted", "status": "PASSED_FIXED_TEST", "label": "Hosted test",
              "wording": ev.wording("PASSED_FIXED_TEST"), "clip": str(clip), "clip_seconds": 9.0,
              "url": "https://acme-demo.hf.space", "input": "the Space's second example: lion.jpg",
              "captured_at": "2026-11-04", "observed": obs, "supported_claims": [obs]})
    e.update(over)
    return e


def _p2_scenes(arm="proof", author=True, filler=60):
    s1 = ("The author's demo shows a messy folder sorted into four labelled groups."
          if author else "In our hosted-demo run, this lion photo came back rotated.")
    if arm == "proof":
        texts = [s1, "It suits people with big download folders. It requires Python 3.10 or newer.",
                 "Start with the documented command from the README, which installs the tool "
                 "and its one dependency in a single line on your machine today."]
    else:
        texts = ["You want a cluttered downloads folder sorted without doing it by hand. "
                 "This suits anyone on a laptop, but it requires Python 3.10 and a terminal "
                 "you are comfortable typing commands into today.", s1,
                 "Start with the documented command from the README, which installs the tool "
                 "and its one dependency in a single line on your machine today."]
    texts += ["word " * filler, "word " * filler,
              "It does not handle network drives yet, which is a real limitation. " + "word " * 40,
              "Decide whether it fits your folder. The exact command is in the description."]
    return [{"scene_num": i + 1, "narration": t.strip(), "visual_query": "laptop"}
            for i, t in enumerate(texts)]


def _p2_script(tmp_path, arm="proof", author=True, evd=None, **over):
    e = evd or (_p2_author_ev(tmp_path) if author else _p2_hosted_ev(tmp_path))
    s = {"title": "Demo Tool Sorts Files", "titles": ["Demo Tool Sorts Files"], "thumb_text": "FREE",
         "description": "Hook line.\n\nBody.", "tags": ["ai"], "task": "Sort Files",
         "scenes": _p2_scenes(arm, author)}
    s = ap._validate_script(s, s["title"], _P2_GH)
    s.update(format="tool", grounding="pip install demo-tool",
             deliverable={"kind": "command", "text": "pip install demo-tool", "url": _P2_GH},
             evidence=e, task="Sort Files",
             pilot={"experiment": "pilot_a", "pair_id": "B1P1", "arm": arm, "slot": 1,
                    "stratum": f"{e['source']}|x", "intent": "install-and-run", "source": e["source"],
                    "partner_seconds": None})
    s.update(over)
    return s


# ================================================================ Pilot A design + assignment
def test_p2_design_is_seeded_six_pairs_and_recorded():
    a, b = pilot.new_design(seed=7), pilot.new_design(seed=7)
    assert a["pairs"] == b["pairs"] and len(a["pairs"]) == 6 and a["seed"] == 7
    assert all(p["first_arm"] in ("proof", "context") for p in a["pairs"])
    assert a["members"] == [] and a["experiment"] == "pilot_a"


def test_p2_frozen_state_file_is_valid_and_has_the_baseline():
    d = pilot.load(_ROOT / "state" / "pilot_a.json")
    assert d and len(d["pairs"]) == 6 and isinstance(d["seed"], int)
    base = d["avd_baseline"]
    assert base["status"] in ("frozen", "unverified")
    if base["status"] == "frozen":
        assert base["value_s"] > 0 and base["n"] == len(base["videos"])


def test_p2_intent_types():
    assert pilot.intent_of({"source": "hosted"}) == "use-a-hosted-demo"
    assert pilot.intent_of({"source": "author"}, "pip install x") == "install-and-run"
    assert pilot.intent_of({"source": "author"}, "Needs an NVIDIA GPU with 24GB VRAM") == \
        "decide-before-installing"
    assert pilot.intent_of({"source": "none"}) == "" and pilot.intent_of(None) == ""


def test_p2_assignment_by_arrival_closes_matching_pair_then_opens_next():
    d = pilot.new_design(seed=3)
    first = d["pairs"][0]
    a = pilot.assign({"source": "author"}, "pip install x", d, [])
    assert a["pair_id"] == first["pair_id"] and a["arm"] == first["first_arm"] and a["slot"] == 1
    d["members"].append({"pair_id": a["pair_id"], "arm": a["arm"], "stratum": a["stratum"],
                         "duration_s": 180.0})
    h = pilot.assign({"source": "hosted"}, "", d, [])           # other stratum: next pair
    assert h["pair_id"] == d["pairs"][1]["pair_id"] and h["slot"] == 1
    b = pilot.assign({"source": "author"}, "pip install y", d, [])   # same stratum: closes pair 1
    assert b["pair_id"] == first["pair_id"] and b["slot"] == 2
    assert {a["arm"], b["arm"]} == {"proof", "context"} and b["partner_seconds"] == 180.0


def test_p2_assignment_reads_published_ledger_rows_and_stops_when_full():
    d = pilot.new_design(seed=5)
    runs = [{"status": "PUBLISHED", "experiment": "pilot_a", "pair_id": p["pair_id"], "arm": arm,
             "pilot_stratum": "author|install-and-run", "youtube_url": "https://youtube.com/watch?v=abcdefghijk"}
            for p in d["pairs"] for arm in ("proof", "context")]
    assert pilot.assign({"source": "author"}, "", d, runs) is None
    blocked = [dict(r, status="OPENING_BLOCKED") for r in runs]       # never published: not a member
    assert pilot.assign({"source": "author"}, "", d, blocked)["slot"] == 1
    assert pilot.assign({"source": "none"}, "", d, []) is None
    assert pilot.assign({"source": "author"}, "", None, []) is None


def test_p2_members_union_first_record_wins():
    d = {"pairs": [], "members": [{"pair_id": "P", "arm": "proof", "video_id": "first"}]}
    runs = [{"status": "PUBLISHED", "experiment": "pilot_a", "pair_id": "P", "arm": "proof",
             "youtube_url": "https://youtube.com/watch?v=secondvideo"}]
    m = pilot.members(d, runs)
    assert len(m) == 1 and m[0]["video_id"] == "first"


def test_p2_ledger_fields_are_coerced_and_none_off_pilot():
    assert pilot.ledger_fields({}) == {"experiment": None, "pair_id": None, "arm": None, "slot": None}
    f = pilot.ledger_fields({"pilot": {"experiment": "pilot_a", "pair_id": 3, "arm": "evil", "slot": "9"}})
    assert f["experiment"] == "pilot_a" and f["pair_id"] == "3" and f["arm"] is None and f["slot"] is None


def test_p2_record_member_appends_and_never_raises(tmp_path):
    path = tmp_path / "pilot_a.json"
    pilot.save(pilot.new_design(seed=1), path)
    s = {"title": "T", "pilot": {"pair_id": "B1P1", "arm": "proof", "slot": 1, "stratum": "a|b"},
         "query_map": {"task": "Sort Files"}}
    assert pilot.record_member(s, "abcdefghijk", "2026-11-05T16:45:00Z", 181.2, path)
    m = json.loads(path.read_text(encoding="utf-8"))["members"][0]
    assert m["video_id"] == "abcdefghijk" and m["duration_s"] == 181.2 and m["task"] == "Sort Files"
    assert pilot.record_member({"pilot": "junk"}, "x", None, None, path) is False
    assert pilot.record_member(s, "x", None, None, tmp_path / "missing.json") is False


# ================================================================ AVD baseline (A2)
def _p2_snap(day, rows):
    return {"collected": f"{day}T19:00:00",
            "ledger_headers": ["video", "views", "estimatedMinutesWatched", "averageViewDuration",
                               "averageViewPercentage"], "ledger_videos": rows}


def test_p2_avd_baseline_uses_the_age_7_snapshot_never_lifetime():
    runs = [{"status": "PUBLISHED", "format": "tool", "publish_at": "2026-10-01T16:45:00Z",
             "youtube_url": "https://youtube.com/watch?v=aaaaaaaaaaa"},
            {"status": "PUBLISHED", "format": "tool", "publish_at": "2026-10-02T16:45:00Z",
             "youtube_url": "https://youtube.com/watch?v=bbbbbbbbbbb"},
            {"status": "PUBLISHED", "format": "tool", "publish_at": "2026-10-03T16:45:00Z",
             "youtube_url": "https://youtube.com/watch?v=ccccccccccc"},
            {"status": "PUBLISHED", "format": "news", "publish_at": "2026-10-03T16:45:00Z",
             "youtube_url": "https://youtube.com/watch?v=ddddddddddd"}]
    snaps = [_p2_snap("2026-10-08", [["aaaaaaaaaaa", 10, 5, 60, 30]]),
             _p2_snap("2026-10-08", [["aaaaaaaaaaa", 12, 6, 70, 30]]),        # later that day wins
             _p2_snap("2026-10-09", [["bbbbbbbbbbb", 5, 2, 40, 20]]),
             _p2_snap("2026-10-30", [["aaaaaaaaaaa", 99, 99, 999, 9]]),       # lifetime: ignored
             _p2_snap("2026-10-10", [["ccccccccccc", 3, 0, 0, 0]])]           # AVD 0: excluded
    b = pilot.avd_baseline(runs, snaps, before=dt.date(2026, 11, 4))
    assert b["status"] == "frozen" and b["n"] == 2 and b["value_s"] == 55.0
    assert [e["video"] for e in b["excluded"]] == ["ccccccccccc"]
    assert pilot.avd_baseline([], [])["status"] == "unverified"


# ================================================================ Analytics reads + readout
def test_p2_retention_query_shape_matches_the_documented_report():
    a = pilot.retention_args("abcdefghijk", dt.date(2026, 11, 5), dt.date(2026, 11, 12))
    assert a["dimensions"] == "elapsedVideoTimeRatio"
    assert a["metrics"].split(",")[0] == "audienceWatchRatio"
    assert a["filters"] == "video==abcdefghijk" and "," not in a["filters"]   # ONE id only
    assert (a["startDate"], a["endDate"]) == ("2026-11-05", "2026-11-12")


def test_p2_due_reads_wait_for_processing_and_stop_once_usable():
    mem = [{"video_id": "v1", "published_at": "2026-11-01T16:45:00Z"}]
    assert pilot.due_reads(mem, {}, dt.date(2026, 11, 9)) == []                # day 8: lag
    due = pilot.due_reads(mem, {}, dt.date(2026, 11, 10))
    assert [(v, a) for v, a, _s, _e in due] == [("v1", 7)]
    good = {("v1", 7): {"curve": [[0.01 * i, 0.5] for i in range(1, 101)]}}
    assert pilot.due_reads(mem, good, dt.date(2026, 11, 10)) == []
    assert pilot.due_reads(mem, {}, dt.date(2026, 12, 30)) == []               # gave up


def test_p2_sample_stores_the_actual_sampled_time():
    curve = [[round(0.01 * i, 2), 1.0 - 0.004 * i] for i in range(1, 101)]
    pct, t = pilot.sample(curve, 180.0, 7)
    assert t == 7.2 and pct == pytest.approx(98.4)       # 0.04 x 180 = 7.2 s, not "0:07"


def _p2_row(pid, adv, proof7=70.0, p30=50.0, p60=40.0, views=(50, 50)):
    return {"pair_id": pid, "evaluable": True, "advantage": adv,
            "proof": {"points": {7: (proof7, 7.2), 30: (p30, 30.6), 60: (p60, 59.4)}, "views": views[0]},
            "context": {"points": {7: (proof7 - adv, 7.2)}, "views": views[1]}}


def test_p2_decision_rules():
    six = lambda advs, **k: [_p2_row(f"P{i}", a, **k) for i, a in enumerate(advs)]
    avd6 = [80] * 6
    assert pilot.decide(six([9, 10, 8, 12, 9, -1]), 72, avd6)["decision"] == "promising"
    assert pilot.decide(six([9, 10, 8, 12, 9, -1], p30=40), 72, avd6)["decision"] == "revise delivery"
    assert pilot.decide(six([9, 10, 8, 12, 9, -1]), 72, [60] * 6)["decision"] == "revise delivery"
    assert pilot.decide(six([-6, -5, -7, -9, -5, -6]), 72, avd6)["decision"] == "stop"
    assert pilot.decide(six([3, 2, 4, -1, 5, 1]), 72, avd6)["decision"] == "revise hypothesis"
    assert pilot.decide(six([1, -2, 0, -1, -3, 2]), 72, avd6)["decision"] == "flat"
    assert pilot.decide(six([1, -2, 0, -1, -3, 2]), 72, avd6, batch=2)["decision"] == "stop"
    r = pilot.decide(six([9, 10, 8, 12, 9])
                     + [{"pair_id": "P5", "evaluable": False}], 72, avd6)
    assert r["decision"] == "unresolved" and r["missing"] == ["P5"]
    assert pilot.decide(six([9] * 6), None, avd6)["avd_guardrail"] == "unverified"


def test_p2_readout_over_fixture_reads_is_outlier_checked(tmp_path):
    d = pilot.new_design(seed=11)
    mem, snaps = [], []
    advs = [30, 1, 1, -2, 1, 1]      # one big winner carries the median
    for k, p in enumerate(d["pairs"]):
        for arm in ("proof", "context"):
            vid = f"{p['pair_id']}{arm}"
            mem.append({"pair_id": p["pair_id"], "arm": arm, "stratum": "author|install-and-run",
                        "video_id": vid, "published_at": "2026-11-05", "duration_s": 180.0})
            base = 0.60 + (advs[k] / 100.0 if arm == "proof" else 0)
            curve = [[round(0.01 * i, 2), base] for i in range(1, 101)]
            snaps.append({"pilot_reads": [{"video": vid, "age": 7, "curve": curve,
                                           "totals": [100, 150, 90], "traffic": [["YT_SEARCH", 80]]}]})
    d["members"] = mem
    res = pilot.readout(d, [], snaps)
    assert res["evaluable"] == 6 and res["median_advantage"] == 1.0
    assert res["without_largest_winner"]["pair"] == d["pairs"][0]["pair_id"]
    assert len(res["pairs"]) == 6 and res["pairs"][0]["age"] == 7
    text = pilot.format_readout(res)
    assert "Pilot A readout" in text and "7.2" in text
    assert res["outlier_dependent"] is False
    assert pilot.readout({}, [], [])["error"]


# ================================================================ opening: timeline + lint
def test_p2_timeline_proof_and_step_spill():
    tl = op.timeline("proof", [6.0, 8.0, 4.0, 20.0, 30.0])
    assert tl["scenes"][0] == [("result", 6.0)] and tl["step_at"] == 14.0
    assert tl["scenes"][3][0] == ("step", 1.5) and tl["step_seconds"] == 5.5
    assert 1 not in tl["scenes"]                     # the limitation scene keeps its visuals


@pytest.mark.parametrize("d0,result_at,s0,s1", [
    (15.4, 15.4, [("context", 15.4)], [("result", 7.0)]),
    (12.0, 15.0, [("context", 12.0)], [("context", 3.0), ("result", 4.0)]),
    (17.0, 15.0, [("context", 15.0), ("result", 2.0)], [("result", 7.0)]),
])
def test_p2_timeline_context_puts_the_result_in_its_window(d0, result_at, s0, s1):
    tl = op.timeline("context", [d0, 7.0, 6.0, 20.0, 30.0])
    assert tl["result_at"] == result_at and tl["scenes"][0] == s0 and tl["scenes"][1] == s1
    assert op.CONTEXT_RESULT_FROM <= tl["result_at"] <= op.CONTEXT_RESULT_TO


def test_p2_timeline_context_keeps_the_result_up_when_scenes_end_early():
    # measured on the repaired context render: scenes 1+2 ended before 0:15, and the
    # first timeline refused the opening outright ("placement")
    tl = op.timeline("context", [10.0, 3.0, 6.0, 20.0, 30.0])
    assert tl["result_at"] == 15.0 and tl["step_at"] == 18.0
    assert tl["scenes"][1] == [("context", 3.0)]
    assert tl["scenes"][2] == [("context", 2.0), ("result", 3.0), ("step", 1.0)]
    assert tl["step_seconds"] >= op.STEP_MIN_SECONDS and tl["sequence_at"] == 23.5


def test_p2_timeline_refuses_what_cannot_carry_it():
    assert op.timeline("context", [10.0, 1.0, 1.0, 2.0, 30.0]) is None
    assert op.timeline("proof", [6.0, 8.0]) is None and op.timeline("x", [1] * 6) is None


def test_p2_lint_codes(tmp_path):
    assert op.lint(_p2_script(tmp_path, "proof"), "proof") == ["length"]       # fixture is short
    s = _p2_script(tmp_path, "proof")
    s["scenes"][0]["narration"] = "This tool is great and you will love it. " + s["scenes"][0]["narration"]
    assert "first_sentence_content" in op.lint(s, "proof")
    s = _p2_script(tmp_path, "proof")
    s["scenes"][1]["narration"] = "It is for people with folders. Not independently tested."
    assert "limitation_missing" in op.lint(s, "proof")     # the status is not a limitation
    s = _p2_script(tmp_path, "proof")
    s["scenes"][0]["narration"] = ("The author's demo shows " + "very " * 14 + "sorted files.")
    assert "first_sentence_long" in op.lint(s, "proof")
    h = _p2_script(tmp_path, "proof", author=False)
    assert "first_sentence_content" not in op.lint(h, "proof")
    c = _p2_script(tmp_path, "context")
    assert "context_length" not in op.lint(c, "context") and "limitation_missing" not in op.lint(c, "context")


def test_p2_fix_prompt_names_the_rules_and_keeps_the_schema(tmp_path):
    s = _p2_script(tmp_path, "proof")
    p = op.fix_prompt(s, ["first_sentence_long", "step_late"], "proof")
    assert "at most 13 words" in p and "first step" in p and '"scenes"' in p
    assert op.repair_kind(["frame0"]) == "render" and op.repair_kind(["step_late", "frame0"]) == "script"


def test_p2_writer_block_per_arm_and_source(tmp_path):
    h = op.writer_block("proof", _p2_hosted_ev(tmp_path))
    assert "In our hosted-demo run" in h and "never an install command" in h and '"task"' in h
    c = op.writer_block("context", _p2_author_ev(tmp_path))
    assert "TASK + SUITABILITY" in c and "The author's demo shows" in c and "Do NOT reveal" in c


# ================================================================ opening: visuals (PIL only)
def test_p2_region_plan_reaches_40_percent_for_tall_and_wide_changes():
    from PIL import Image, ImageDraw
    for box in ((900, 50, 1020, 1030), (100, 480, 1820, 600), (860, 500, 1060, 580)):
        a = Image.new("RGB", (1920, 1080), (13, 17, 23))
        b = a.copy()
        ImageDraw.Draw(b).rectangle(box, fill=(240, 240, 240))
        plan = op.region_plan(a, b)
        assert plan["coverage"] >= op.RESULT_AREA_MIN, (box, plan)
        assert plan["scale"] <= op.SCALE_MAX
    a = Image.new("RGB", (1920, 1080), (13, 17, 23))
    assert op.region_plan(a, a.copy()) is None


def test_p2_step_card_hosted_is_the_demo_action_never_an_install_command(tmp_path):
    s = _p2_script(tmp_path, "proof", author=False)
    lines, cmd = op.step_lines(s)
    assert cmd == "acme-demo.hf.space" and "pip" not in " ".join(lines) + cmd
    meta = op.render_step_card(s, str(tmp_path / "step.png"))
    assert meta and meta["text_px"] >= op.TEXT_MIN_PX
    a = _p2_script(tmp_path, "proof")
    assert op.step_lines(a)[1] == "pip install demo-tool"
    long = dict(a, deliverable={"kind": "command", "text": "pip install " + "x" * 400})
    meta = op.render_step_card(long, str(tmp_path / "step2.png"))
    assert meta["shed"] and meta["text_px"] >= op.TEXT_MIN_PX


def test_p2_context_card_text_is_at_least_48px(tmp_path):
    png = ev.render_label_png("Author demo · acme/demo-tool", str(tmp_path / "l.png"))
    meta = op.render_context_card("You want a cluttered downloads folder sorted by hand.",
                                  "demo-tool · acme/demo-tool", png, str(tmp_path / "c.png"))
    assert meta and meta["text_px"] >= op.TEXT_MIN_PX and meta["label_box"][0] == 48
    assert op._label_px("Author demo · acme/demo-tool") >= op.LABEL_MIN_PX


# ================================================================ opening: the gate
def test_p2_runs_of_and_token_alignment():
    assert op.runs_of([(0, True), (0.5, True), (1.0, False), (1.5, True)], 0.5) == [(0, 1.0), (1.5, 2.0)]
    words = [(0.1, 0.4, "the"), (0.4, 0.8, "authors"), (0.8, 1.1, "demo"), (1.1, 1.5, "shows"),
             (1.5, 1.9, "x")]
    assert op.token_end(words, ["The", "author's", "demo", "shows", "x"], 3) == 1.5


def _p2_gate_setup(monkeypatch, tmp_path, arm, frames_at):
    """frames_at(t) -> which reference the encoded frame at t shows."""
    from PIL import Image, ImageDraw
    refs = {}
    for k, col in (("result", (200, 30, 30)), ("step", (30, 200, 30)), ("context", (30, 30, 200))):
        p = tmp_path / f"ref_{k}.png"
        img = Image.new("RGB", (480, 270), col)
        ImageDraw.Draw(img).rectangle((60, 40, 300, 150), fill=(250, 250, 250))   # not blank
        img.save(p)
        refs[k] = str(p)
    frames = [(i / op.SCAN_FPS, refs[frames_at(i / op.SCAN_FPS)])
              for i in range(int(op.SCAN_SECONDS * op.SCAN_FPS))]
    monkeypatch.setattr(op, "scan", lambda v, out, **k: frames)
    monkeypatch.setattr(op, "_probe", lambda v: 180.0)
    monkeypatch.setattr(op, "encoded_words", lambda v, n: None)
    meta = {"arm": arm, "refs": refs, "coverage": 0.5, "label_px": 40, "text_px": [52],
            "branding": "skipped"}
    return meta


def _p2_words(script, wps=2.5, start=0.2):
    out, t = [], start
    for sc in script["scenes"]:
        for w in sc["narration"].split():
            out.append((round(t, 3), round(t + 1 / wps, 3), w))
            t += 1 / wps
    return out


def test_p2_gate_passes_a_good_proof_first_render(monkeypatch, tmp_path):
    s = _p2_script(tmp_path, "proof")
    meta = _p2_gate_setup(monkeypatch, tmp_path, "proof",
                          lambda t: "result" if t < 6 else ("step" if 14 <= t < 20 else "context"))
    g = op.measure("v.mp4", meta, s, _p2_words(s), 180.0)
    assert g["passed"], g["failures"]
    assert g["frame0_diff"] == 0 and g["step_at"] == 14.0 and g["step_seconds"] >= 5.0
    assert g["first_speech_at"] == 0.2 and g["first_sentence_end"] <= op.FIRST_SENTENCE_BY
    assert g["timing_source"] == "narration_words"


def test_p2_gate_catches_late_step_slow_speech_and_wrong_duration(monkeypatch, tmp_path):
    s = _p2_script(tmp_path, "proof")
    meta = _p2_gate_setup(monkeypatch, tmp_path, "proof",
                          lambda t: "step" if t >= 26 else "result")
    monkeypatch.setattr(op, "_probe", lambda v: 230.0)
    g = op.measure("v.mp4", meta, s, _p2_words(s, wps=1.5, start=0.9), 230.0, partner_seconds=180.0)
    for f in ("step_late", "first_speech", "first_sentence_end", "limitation_late", "duration",
              "pair_duration"):
        assert f in g["failures"], f
    assert not g["passed"] and op.repair_kind(g["failures"]) == "script"


def test_p2_gate_context_first_result_window_and_no_early_reveal(monkeypatch, tmp_path):
    s = _p2_script(tmp_path, "context")
    good = _p2_gate_setup(monkeypatch, tmp_path, "context",
                          lambda t: "context" if t < 15.25 else ("result" if t < 21 else "step"))
    g = op.measure("v.mp4", good, s, _p2_words(s), 180.0)
    assert "result_window" not in g["failures"] and g["result_at"] == 15.25 and "frame0" not in g["failures"]
    early = _p2_gate_setup(monkeypatch, tmp_path, "context",
                           lambda t: "result" if 3 <= t < 4 or 15 <= t < 21 else "context")
    assert "result_window" in op.measure("v.mp4", early, s, _p2_words(s), 180.0)["failures"]


def test_p2_gate_flags_a_sting_and_a_blank_frame_zero(monkeypatch, tmp_path):
    s = _p2_script(tmp_path, "proof")
    meta = _p2_gate_setup(monkeypatch, tmp_path, "proof", lambda t: "context")
    meta["branding"] = "added"
    g = op.measure("v.mp4", meta, s, _p2_words(s), 180.0)
    assert {"sting", "frame0", "result_area"} <= set(g["failures"])
    view = op.ledger_view(g)
    assert view["passed"] is False and all(isinstance(x, str) for x in view["failures"])


def test_p2_measure_never_raises_on_junk(monkeypatch):
    monkeypatch.setattr(op, "_probe", lambda v: 0.0)
    monkeypatch.setattr(op, "scan", lambda v, out, **k: [])
    monkeypatch.setattr(op, "encoded_words", lambda v, n: None)
    g = op.measure("missing.mp4", {"arm": "proof", "refs": {}}, {"scenes": []}, [], 0.0)
    assert g["passed"] is False and g["failures"]


# ================================================================ query-map packaging
def test_p2_query_titles_and_first_sentence(tmp_path):
    h = _p2_script(tmp_path, author=False)
    assert qm.query_title(h) == "demo-tool — Sort Files: Hosted Demo and Limits"
    assert qm.first_sentence(h) == ("demo-tool (acme/demo-tool) for sort files, shown in our "
                                    "hosted-demo run of 2026-11-04: passed this specific test.")
    a = _p2_script(tmp_path)
    assert qm.query_title(a) == "demo-tool Demo Explained: Requirements and Limits"
    assert qm.first_sentence(a).endswith("the author's own demo: not independently tested.")
    assert qm.clean_task("Make it 3x Faster") == "" and qm.clean_task("rotate images") == "Rotate Images"
    assert qm.clean_task("a b c d e f") == "" and qm.query_title({"title": "x"}) == ""


def test_p2_description_first_sentence_then_the_command_block(monkeypatch, tmp_path):
    _p2_on(monkeypatch)
    s = _p2_script(tmp_path)
    assert qm.apply(s) and s["titles"][1] == "Demo Tool Sorts Files"
    assert s["tags"][:2] == ["acme/demo-tool", "demo-tool"] or "demo-tool" in s["tags"]
    ap.place_description_blocks(s)
    ap.place_description_blocks(s)                                      # idempotent
    paras = s["description"].split("\n\n")
    assert paras[0] == qm.first_sentence(s)
    assert paras[1].startswith(ap._DL_MARK)
    assert s["description"].count(qm.first_sentence(s)) == 1
    s["description"] = "demo-tool (acme/demo-tool) mangled by a rewrite.\n\n" + s["description"]
    ap.place_description_blocks(s)
    assert s["description"].count("demo-tool (acme/demo-tool)") == 1


def test_p2_chapters_descriptive_ten_seconds_three_minimum(tmp_path):
    s = _p2_script(tmp_path, "proof")
    starts = [0.0, 6.0, 14.0, 18.0, 45.0, 70.0, 100.0]
    meta = {"arm": "proof", "timeline": op.timeline("proof", [6, 8, 4, 27, 25, 30, 20])}
    ch = qm.chapters(op.chapter_candidates(s, starts, meta))
    lines = ch.splitlines()[1:]
    assert lines[0] == "00:00 Observed result" and len(lines) >= 3
    secs = [int(l[:2]) * 60 + int(l[3:5]) for l in lines]
    assert all(b - a >= 10 for a, b in zip(secs, secs[1:]))
    assert "00:14 Starting step" in lines and "01:10 Limitations" in lines
    assert qm.chapters([(0, "A"), (5, "B")]) == ""


def test_p2_first_seen_earliest_wins_and_timestamps(tmp_path):
    p = tmp_path / "fs.json"
    qm.note_seen([_P2_GH], "signal", p, when="2026-11-03T10:00:00Z")
    qm.note_seen([_P2_GH, "not-a-url"], "signal", p, when="2026-11-04T10:00:00Z")
    qm.note_seen([_P2_GH], "evidence", p, when="2026-11-04T11:00:00Z")
    t = qm.timestamps({"source_url": _P2_GH}, "2026-11-05T16:45:00Z", p)
    assert t == {"t_signal": "2026-11-03T10:00:00Z", "t_evidence": "2026-11-04T11:00:00Z",
                 "t_publication": "2026-11-05T16:45:00Z"}
    p.write_text("[broken", encoding="utf-8")
    assert qm.timestamps({"source_url": _P2_GH}, None, p)["t_signal"] == ""


# ================================================================ state + config
def test_p2_state_files_get_both_halves():
    assert "state/pilot_a.json" in state_merge.FILES and "state/first_seen.json" in state_merge.FILES
    wf = (_ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    assert "state/pilot_a.json" in wf and "state/first_seen.json" in wf
    main = {"pairs": [{"pair_id": "B1P1", "first_arm": "proof"}], "seed": 1,
            "members": [{"pair_id": "B1P1", "arm": "proof", "video_id": "a"}]}
    ours = {"pairs": [{"pair_id": "B1P1", "first_arm": "context"}], "seed": 2,
            "members": [{"pair_id": "B1P1", "arm": "proof", "video_id": "z"},
                        {"pair_id": "B1P1", "arm": "context", "video_id": "b"}]}
    m = json.loads(state_merge.merge_file("state/pilot_a.json", json.dumps(ours), json.dumps(main)))
    assert m["seed"] == 1 and m["pairs"][0]["first_arm"] == "proof"
    assert [x["video_id"] for x in m["members"]] == ["a", "b"]
    fs = json.loads(state_merge.merge_file("state/first_seen.json",
                                           json.dumps({"u": {"signal": "2026-11-02"}}),
                                           json.dumps({"u": {"signal": "2026-11-03", "evidence": "e"}})))
    assert fs == {"u": {"signal": "2026-11-02", "evidence": "e"}}
    assert state_merge.merge_file("state/pilot_a.json", "[1]", "5") is not None   # never raises


def test_p2_kill_switches_in_both_configs():
    for name in ("config.json", "config.example.json"):
        c = json.loads((_ROOT / name).read_text(encoding="utf-8"))
        for k in ("pilot_a", "query_map", "pilot_retention"):
            assert k in c, (name, k)


def test_p2_planted_keys_are_popped_and_carried():
    s = {"scenes": _p2_scenes(), "pilot": {"arm": "proof"}, "query_map": {"task": "x"}, "task": "Sort"}
    v = ap._validate_script(s, "t")
    assert "pilot" not in v and "query_map" not in v and v["task"] == "Sort"
    for k in ("pilot", "query_map", "task"):
        assert k in ap._CARRY


# ================================================================ script_tool + run()
def test_p2_script_tool_draws_a_slot_and_writes_the_pilot_structure(monkeypatch, tmp_path):
    _p2_on(monkeypatch)
    e = _p2_author_ev(tmp_path)
    d = pilot.new_design(seed=2)
    monkeypatch.setattr(ap.pilot, "load", lambda path=None: d)
    monkeypatch.setattr(ap, "_ledger_rows", lambda: [])
    monkeypatch.setattr(ap.querymap, "note_seen", lambda *a, **k: None)
    monkeypatch.setattr(ap.evidence, "gather", lambda item, probe_result=None: e)
    monkeypatch.setattr(ap, "fetch_text", lambda u, limit=4000: "README pip install demo-tool " * 80)
    monkeypatch.setattr(ap, "_verified_facts", lambda u: {})
    monkeypatch.setattr(ap, "_top_issues", lambda u: [])
    seen = {}

    def fake(prompt, **k):
        seen["p"] = prompt
        return {"title": "t", "description": "d", "task": "Sort Files", "scenes": _p2_scenes(),
                "deliverable": {"kind": "command", "text": "pip install demo-tool", "url": _P2_GH}}
    monkeypatch.setattr(ap.llm, "generate_json", fake)
    s = ap.script_tool({"title": "acme/demo-tool", "source": "github", "url": _P2_GH})
    arm = d["pairs"][0]["first_arm"]
    assert s["pilot"]["arm"] == arm and s["pilot"]["pair_id"] == d["pairs"][0]["pair_id"]
    assert f"Pilot A, {arm}-first" in seen["p"] and "7-9 scenes" in seen["p"] and '"task"' in seen["p"]
    if arm == "context":
        assert "Scene 2 (the result scene) must begin with" in seen["p"]


def _p2_run(monkeypatch, tmp_path, script, gates_seq):
    rows, calls = [], {"render": 0, "l2": [], "brand": 0, "member": 0, "fix": 0}
    monkeypatch.setattr(ap.fv, "TEMP", tmp_path)
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: None)
    monkeypatch.setattr(ap.signal_engine, "rank", lambda limit=20: [])
    monkeypatch.setattr(ap.querymap, "note_seen", lambda *a, **k: None)
    monkeypatch.setattr(ap, "decide_format", lambda f, r: ("tool", None))
    monkeypatch.setattr(ap, "build_script", lambda f, r, v: script)
    monkeypatch.setattr(ap, "too_many_failures", lambda t: False)
    monkeypatch.setattr(ap.screencap, "capture", lambda s: None)
    monkeypatch.setattr(ap.screencap, "inject_code_card", lambda *a, **k: pytest.fail("code card"))
    monkeypatch.setattr(ap.receipts, "install_scene_idx", lambda s: pytest.fail("receipts"))
    monkeypatch.setattr(ap.eng, "step3_download", lambda s: [["stock.mp4"] for _ in s["scenes"]])
    monkeypatch.setattr(ap, "synthesize_voice", lambda n, s: ("a.mp3", [(0.1, 0.5, "w")] * 30))
    monkeypatch.setattr(ap.captions, "transcribe_words", lambda a: [(0.1, 0.5, "w")] * 30)
    monkeypatch.setattr(ap.captions, "correct_words", lambda w, n: w)
    monkeypatch.setattr(ap.eng, "dur", lambda p: 180.0)
    monkeypatch.setattr(ap, "scene_durations", lambda s, w, d: [20.0] * len(s["scenes"]))
    monkeypatch.setattr(ap.infographics, "inject_cards", lambda *a, **k: None)
    monkeypatch.setattr(ap.opening, "place_opening",
                        lambda s, c, d, arm: calls.__setitem__("render", calls["render"] + 1)
                        or {"arm": arm, "timeline": op.timeline(arm, d)})
    monkeypatch.setattr(ap.opening, "measure", lambda *a, **k: dict(gates_seq.pop(0)))
    monkeypatch.setattr(ap.eng, "step5_build", lambda s, clips, *a, **k: str(tmp_path / "v.mp4"))
    monkeypatch.setattr(ap.thumbnail, "make", lambda *a, **k: "t.jpg")
    monkeypatch.setattr(ap.shorts_mod, "make_shorts", lambda *a, **k: [])
    monkeypatch.setattr(ap.captions, "build_ass", lambda *a, **k: "c.ass")
    monkeypatch.setattr(ap.captions, "burn_ass", lambda v, a, **k: v)
    monkeypatch.setattr(ap.branding, "add_intro_outro",
                        lambda v, **k: calls.__setitem__("brand", 1) or v)
    monkeypatch.setattr(ap.l2, "inject", lambda v, at, **k: calls["l2"].append(k) or (v, {}))
    monkeypatch.setattr(ap, "qa_video", lambda v, d: True)
    monkeypatch.setattr(ap.eng, "step8_meta", lambda s, n: [])
    monkeypatch.setattr(ap, "mark_used", lambda *a, **k: None)
    monkeypatch.setattr(ap, "mark_failed", lambda *a, **k: None)
    monkeypatch.setattr(ap, "_save_asset_record", lambda *a, **k: None)
    monkeypatch.setattr(ap.eng, "save_report", lambda *a, **k: {"status": "RENDER_ONLY"})
    monkeypatch.setattr(ap.eng, "cleanup", lambda: None)
    monkeypatch.setattr(ap.eng, "_rel", lambda v: v)
    monkeypatch.setattr(ap.deliverable, "sheet_for", lambda s: {})
    monkeypatch.setattr(ap.deliverable, "make_cheat_sheet", lambda *a, **k: None)
    monkeypatch.setattr(ap.site, "publish_page", lambda *a, **k: None)
    monkeypatch.setattr(ap, "record_run", lambda **kw: rows.append(kw))
    monkeypatch.setattr(ap, "_fall_back", lambda *a, **k: rows.append({"status": "FELL_BACK"}))
    monkeypatch.setattr(ap.gates, "fact_check", lambda *a, **k: {"passed": True})
    monkeypatch.setattr(ap.gates, "verify_synthesis", lambda *a, **k: {"present": True})
    monkeypatch.setattr(ap.gates, "replication_test", lambda *a, **k: {"passed": True})
    monkeypatch.setattr(ap, "_pilot_lint", lambda s, arm: (s, []))
    monkeypatch.setattr(ap, "_pilot_fix", lambda s, f, arm: calls.__setitem__("fix", calls["fix"] + 1) or s)
    monkeypatch.setattr(ap, "_recheck_fixed", lambda s: "")
    monkeypatch.setattr(ap.querymap, "timestamps",
                        lambda s, p: {"t_signal": "S", "t_evidence": "E", "t_publication": ""})
    ap.run(publish=False)
    return rows, calls


_P2_PASS = {"passed": True, "failures": [], "duration_s": 181.0}


def test_p2_run_pilot_path_no_sting_no_cold_open_and_ledger_fields(monkeypatch, tmp_path):
    _p2_on(monkeypatch)
    s = _p2_script(tmp_path, "context")
    rows, calls = _p2_run(monkeypatch, tmp_path, s, [_P2_PASS])
    row = rows[-1]
    assert row["status"] == "RENDER_ONLY" and calls["brand"] == 0 and calls["l2"] == [{"cold_open": False}]
    assert (row["experiment"], row["pair_id"], row["arm"], row["slot"]) == ("pilot_a", "B1P1", "context", 1)
    assert row["opening"]["passed"] is True and row["duration_s"] == 181.0
    assert row["title"] == "demo-tool Demo Explained: Requirements and Limits"
    assert (row["t_signal"], row["t_evidence"]) == ("S", "E") and row["pilot_task"] == "Sort Files"


def test_p2_run_one_repair_then_skip(monkeypatch, tmp_path):
    _p2_on(monkeypatch)
    fail = {"passed": False, "failures": ["step_late"]}
    rows, calls = _p2_run(monkeypatch, tmp_path, _p2_script(tmp_path), [fail, dict(fail)])
    assert calls["render"] == 2 and calls["fix"] == 1
    assert [r["status"] for r in rows[-2:]] == ["OPENING_BLOCKED", "FELL_BACK"]
    assert rows[-2]["experiment"] == "pilot_a"


def test_p2_run_render_repair_passes_on_the_second_render(monkeypatch, tmp_path):
    _p2_on(monkeypatch)
    rows, calls = _p2_run(monkeypatch, tmp_path, _p2_script(tmp_path),
                          [{"passed": False, "failures": ["frame0"]}, _P2_PASS])
    assert calls["render"] == 2 and calls["fix"] == 0 and rows[-1]["status"] == "RENDER_ONLY"
    assert rows[-1]["opening"]["attempts"] == 2


def test_p2_pilot_off_keeps_the_p1_path(monkeypatch, tmp_path):
    _p2_on(monkeypatch, pilot_a=False, query=False)
    s = _p2_script(tmp_path)
    assert ap._pilot_arm(s) is None
    monkeypatch.setenv("PILOT_A", "1")
    assert ap._pilot_arm(s) == "proof"
    assert ap._pilot_arm(dict(s, evidence=None)) is None
