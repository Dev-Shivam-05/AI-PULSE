"""v3-T.1 ToolDojo Live Trials (docs/spec/ai-pulse-v3t1.md).

No network, no ffmpeg, no browser, no LLM: every seam is stubbed as the consumer
sees it. Helpers are prefixed `_t1_` (one shared namespace rule, CLAUDE.md).
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from factverse import trials as tr  # noqa: E402


def _t1_set(i=0):
    return tr.load_sets()[i]


def _t1_plan(i=0, tool="sherpa-onnx", hardware="cpu-basic"):
    s = _t1_set(i)
    return {"id": f"2026-11-07-{tr.slug(tool)}", "date": "2026-11-07", "slot": "2026-11-07T18:45:00Z",
            "tool": tool, "maker": "k2-fsa", "space": "k2-fsa/automatic-speech-recognition",
            "host": "https://k2-fsa-automatic-speech-recognition.hf.space", "sha": "d9d0c7b",
            "hardware": hardware, "fixture_set": s["id"], "set": s,
            "question": s["question"].format(tool=tool), "question_short": s["question_short"],
            "pins": ["English"], "settings": [], "upload": {}}


def _t1_result(branch="PASS", clip=None, text=None):
    clip = clip or _t1_set()["clips"][0]
    text = clip["text"] if text is None else text
    checks = tr.checks_for(clip, text) if branch in ("PASS", "PARTIAL_FAIL") else [
        {"id": "terms", "label": "Key words heard", "value": "not run", "ok": None},
        {"id": "errors", "label": "Word errors", "value": "not run", "ok": None}]
    return {"clip": clip["id"], "branch": branch, "why": "", "status": tr.EVIDENCE_STATUS[branch], "transcript": text if branch in
            ("PASS", "PARTIAL_FAIL") else "", "checks": checks, "ran_at": "2026-11-07T18:46:05+00:00",
            "recording": "", "cut": None, "settings": {}, "seconds": 3.0, "label": "Test"}


# ------------------------------------------------------------------ checks
def test_t1_normalize_reads_numbers_and_times_as_words():
    assert tr.normalize("Call Maria at 9:15, room 4.") == "call maria at nine fifteen room four".split()
    assert tr.normalize("9:05 and 9:00") == "nine oh five and nine".split()
    assert tr.normalize("the 4th of 2,450 items") == "the fourth of two thousand four hundred fifty items".split()
    assert tr.normalize("Don't STOP!") == ["dont", "stop"]
    assert tr.normalize(None) == []


def test_t1_word_errors_count_sub_ins_del():
    ref = tr.normalize("send the final report")
    errs, marks = tr.align(ref, tr.normalize("send the report now"))
    assert errs == 2                      # "final" deleted, "now" inserted
    assert ("now", "ins") in marks
    errs, marks = tr.align(ref, tr.normalize("send a final report"))
    assert errs == 1 and ("a", "sub") in marks


def test_t1_allowance_is_floored_from_the_threshold():
    assert tr.WER_MAX == 0.15
    assert tr.allowed_errors(12) == 1 and tr.allowed_errors(13) == 1 and tr.allowed_errors(14) == 2
    assert tr.allowed_errors(0) == 0


def test_t1_key_word_check_catches_a_homophone():
    clip = _t1_set()["clips"][1]          # "... move the budget meeting to room four."
    ok = tr.checks_for(clip, "Call Maria at 9:15 and move the budget meeting to room 4.")
    assert [c["ok"] for c in ok] == [True, True]
    bad = tr.checks_for(clip, "Call Maria at nine fifteen and move the budget meeting to room for.")
    assert bad[0]["ok"] is False and bad[0]["missing"] == ["four"]


def test_t1_a_broken_checker_is_never_a_pass(monkeypatch):
    clip = _t1_set()["clips"][0]
    monkeypatch.setattr(tr, "align", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    checks = tr.checks_for(clip, clip["text"])
    assert checks[1]["ok"] is None
    assert tr.test_status({"done": True}, checks)[0] == "INCONCLUSIVE"


def test_t1_status_order_execution_failures_are_never_scored():
    ok = tr.checks_for(_t1_set()["clips"][0], _t1_set()["clips"][0]["text"])
    assert tr.test_status({"error": "You have exceeded your GPU quota"}, ok)[0] == "INCONCLUSIVE"
    assert tr.test_status({"unavailable": True}, ok)[0] == "INCONCLUSIVE"
    assert tr.test_status({"deadline": True, "submitted": True}, [])[0] == "TIMEOUT"
    assert tr.test_status({"deadline": True}, [])[0] == "INCONCLUSIVE"
    assert tr.test_status({"error": "ValueError: bad audio"}, [])[0] == "PARTIAL_FAIL"
    assert tr.test_status({"inconclusive": "TimeoutError"}, [])[0] == "INCONCLUSIVE"
    assert tr.test_status({"done": True}, ok)[0] == "PASS"
    assert tr.test_status({"done": True}, [])[0] == "INCONCLUSIVE"


def test_t1_verdict_tally_and_the_incomplete_rule():
    P, F, T, I = (_t1_result(b) for b in ("PASS", "PARTIAL_FAIL", "TIMEOUT", "INCONCLUSIVE"))
    assert tr.verdict([P, P, P, P]) == "PASS"
    assert tr.verdict([P, P, P]) != "PASS"           # a missing test is never a pass
    assert tr.verdict([P, T, F, P]) == "PARTIAL_FAIL"
    assert tr.verdict([P, T, I, P]) == "TIMEOUT"
    assert tr.verdict([P, I, P, P]) == "INCONCLUSIVE"
    assert tr.incomplete([P, T, I]) and not tr.incomplete([T, P, I])
    t = tr.tally([P, P, T, P])
    assert t == {"passed": 6, "declared": 8, "timed_out": 1, "unverified": 0}
    assert tr.tally_text(t) == "6/8 checks passed; one timed out"
    assert "%" not in tr.tally_text(t)


def test_t1_repeat_is_first_failure_else_control():
    P, F = _t1_result("PASS"), _t1_result("PARTIAL_FAIL", text="nothing like it")
    assert tr.repeat_choice([P, P, F, F]) == (2, "failed")
    assert tr.repeat_choice([P, P, P, P]) == (0, "control")
    assert tr.repeat_choice([P, _t1_result("TIMEOUT"), P, P]) == (0, "control")


# ------------------------------------------------------------------ fixtures
def test_t1_committed_fixtures_match_their_manifest():
    sets = tr.load_sets()
    assert [s["id"] for s in sets] == ["voice-notes", "dev-commands"]
    for s in sets:
        assert [c["role"] for c in s["clips"]] == ["control", "ordinary", "complication", "boundary"]
        for c in s["clips"]:
            assert tr.fixture_ok(c), c["file"]
            assert len(c["terms"]) == 2
            ref = tr.normalize(c["text"])
            assert all(tr.term_heard(t, ref) for t in c["terms"])
            assert 2.0 < c["seconds"] < 30.0     # onnx-asr's simple tab caps at 30 s


def test_t1_pick_set_never_repeats_inputs():
    sets = tr.load_sets()
    assert tr.pick_set([], sets)["id"] == "voice-notes"
    assert tr.pick_set([{"fixture_set": "voice-notes"}], sets)["id"] == "dev-commands"
    assert tr.pick_set([{"fixture_set": "voice-notes"}, {"fixture_set": "dev-commands"}], sets) is None


# ------------------------------------------------------------------ planning
def _t1_cfg(button="Transcribe", audio_sources=("upload", "microphone"), out_type="textbox"):
    return {"version": "6.20.0", "components": [
        {"id": 7, "type": "audio", "props": {"label": "Speech", "sources": list(audio_sources)}},
        {"id": 8, "type": "button", "props": {"value": button, "variant": "primary"}},
        {"id": 10, "type": out_type, "props": {"label": "Transcript"}},
        {"id": 5, "type": "button", "props": {"value": "Recognize (ru)"}},
        {"id": 6, "type": "button", "props": {"value": "Recognize (en)"}}],
        "dependencies": [
            {"targets": [[5, "click"]], "inputs": [7], "outputs": [10], "api_name": "ru"},
            {"targets": [[8, "click"]], "inputs": [7], "outputs": [10], "api_name": "transcribe"},
            {"targets": [[6, "click"]], "inputs": [7], "outputs": [10], "api_name": "en"}]}


def test_t1_upload_plan_prefers_english_and_needs_text_out():
    p = tr.upload_plan(_t1_cfg())
    assert p["button_text"] == "Recognize (en)" and p["audio_label"] == "Speech"
    assert p["outputs"] == ["#component-10"] and p["output_types"] == ["textbox"]
    assert tr.upload_plan(_t1_cfg(), prefer="Transcribe")["button_text"] == "Transcribe"
    assert tr.upload_plan(_t1_cfg(out_type="dataframe")) is None
    assert tr.upload_plan(_t1_cfg(audio_sources=("microphone",))) is None
    assert tr.upload_plan(None) is None and tr.upload_plan({"components": "x"}) is None


def test_t1_hard_gates():
    plan = {"button": "#b"}
    facts = {"hardware": "cpu-basic", "stage": "RUNNING", "sdk": "gradio", "host": "https://x.hf.space"}
    c = {"family": tr.FAMILY}
    assert tr.gate(c, facts, plan) == []
    assert any("not free CPU" in w for w in tr.gate(c, dict(facts, hardware="zero-a10g"), plan))
    assert any("SLEEPING" in w for w in tr.gate(c, dict(facts, stage="SLEEPING"), plan))
    assert any("Gradio" in w for w in tr.gate(c, dict(facts, sdk="docker"), plan))
    assert any("upload" in w for w in tr.gate(c, facts, None))
    assert any("checker" in w for w in tr.gate({"family": "ocr"}, facts, plan))
    assert tr.gate(c, None, plan)


def test_t1_rank_search_then_release_then_stars_and_missing_is_not_zero():
    a = {"search_delta": 5, "release_days": None, "stars_delta": None, "order": 2}
    b = {"search_delta": None, "release_days": 9, "stars_delta": 1, "order": 0}
    c = {"search_delta": None, "release_days": 60, "stars_delta": 40, "order": 1}
    d = {"search_delta": None, "release_days": None, "stars_delta": None, "order": 3}
    assert sorted([d, c, b, a], key=tr.rank_key) == [a, b, c, d]
    e = {"search_delta": 0, "order": 9}
    assert sorted([b, e], key=tr.rank_key)[0] is e   # a measured 0 still beats no data


def test_t1_search_movement_from_two_windows():
    snaps = [{"search_terms": {"start": "a", "end": "b", "videos": {"v": [["Sherpa-ONNX", 2]]}}},
             {"search_terms": {"start": "c", "end": "d", "videos": {"v": [["sherpa onnx", 7], ["x", 9]]}}}]
    assert tr.search_movement("sherpa-onnx", snaps) == 5
    assert tr.search_movement("sherpa-onnx", snaps[:1]) is None
    assert tr.search_movement("x", [{"search_terms": "junk"}]) is None


def test_t1_plan_episodes_refuses_without_network(monkeypatch):
    monkeypatch.setattr(tr, "space_facts", lambda s: None)
    monkeypatch.setattr(tr.evidence, "_json", lambda *a, **k: None)
    plans, log = tr.plan_episodes(today=dt.date(2026, 11, 7), history=[], feed=[], signals=False)
    assert plans == [] and all("refused" in line for line in log)


def test_t1_plan_episodes_builds_a_plan_and_skips_a_used_pair(monkeypatch):
    facts = {"space": "s", "host": "https://x.hf.space", "sdk": "gradio", "stage": "RUNNING",
             "hardware": "cpu-basic", "sha": "abc", "likes": 1, "license": "mit", "last_modified": ""}
    monkeypatch.setattr(tr, "space_facts", lambda s: dict(facts, space=s))
    monkeypatch.setattr(tr.evidence, "_json", lambda *a, **k: _t1_cfg())
    plans, _ = tr.plan_episodes(today=dt.date(2026, 11, 7), history=[], feed=[], signals=False)
    assert [p["tool"] for p in plans] == ["VibeVoice-ASR-BitNet", "sherpa-onnx", "onnx-asr"]
    p = plans[1]
    assert p["fixture_set"] == "voice-notes" and p["question"].startswith("Can sherpa-onnx")
    assert p["signals"]["demand"].startswith("exploratory")
    plans2, _ = tr.plan_episodes(today=dt.date(2026, 11, 14),
                                 history=[{"id": "e1", "tool": "sherpa-onnx", "fixture_set": "voice-notes"}],
                                 feed=[], signals=False)
    assert all(p["fixture_set"] == "dev-commands" for p in plans2)


def test_t1_episode_b_needs_the_same_inputs():
    a, b = _t1_plan(0, "sherpa-onnx"), _t1_plan(0, "VibeVoice-ASR-BitNet")
    assert tr.comparison_honest(a, b)[0]
    assert not tr.comparison_honest(a, _t1_plan(1, "VibeVoice-ASR-BitNet"))[0]
    assert not tr.comparison_honest(a, a)[0]
    assert not tr.comparison_honest(a, _t1_plan(0, "x", hardware="zero-a10g"))[0]


# ------------------------------------------------------------------ narration
def test_t1_template_writes_all_four_branches_inside_their_budgets():
    n = tr.template_narration(_t1_plan())
    for w in ("result1", "result2", "result3", "result4", "repeat_result", "verdict", "limits"):
        assert set(n[w]) == set(tr.BRANCHES), w
    assert set(n["repeat_intro"]) == {"control", "1", "2", "3", "4"}
    assert set(n["files"]) == {"published", "unpublished"}
    for key, text in tr._flat(n):
        assert len(text.split()) <= tr._budget(key.split(".")[0]), key
        assert "%" not in text
    assert "not today's result" in n["open"]       # R2: never present preflight as the run


def test_t1_branch_lines_are_prepared_before_any_result():
    # the template is a pure function of the plan: no result can leak into a branch
    p = _t1_plan()
    assert tr.template_narration(p) == tr.template_narration(json.loads(json.dumps(p)))


def test_t1_materially_varied_refuses_a_name_swap_and_a_reused_set():
    a = _t1_plan(0, "sherpa-onnx")
    na = tr.template_narration(a)
    hist = [{"id": "e1", "question": a["question"], "fixture_set": a["fixture_set"],
             "narration_text": tr.investigation_text(na)}]
    b_swap = _t1_plan(0, "VibeVoice-ASR-BitNet")
    ok, why = tr.materially_varied(b_swap, tr.template_narration(b_swap), hist)
    assert not ok and any("fixture set" in w for w in why) and any("overlaps" in w for w in why)
    b = _t1_plan(1, "VibeVoice-ASR-BitNet")
    ok, why = tr.materially_varied(b, tr.template_narration(b), hist)
    assert ok, why
    assert tr.overlap(tr.investigation_text(na), tr.investigation_text(tr.template_narration(b))) < tr.VARIED_MAX_OVERLAP


def test_t1_llm_line_gate():
    g = "sherpa-onnx four clips 60"
    assert tr.text_ok("open", "Live trial: sherpa-onnx. The rerun of clip one starts now.", g)
    assert not tr.text_ok("open", "This shocking tool is mind-blowing for everyone here today.", g)
    assert not tr.text_ok("open", "It works offline on any machine and the rerun starts now.", g)
    assert not tr.text_ok("open", "It is 10 times faster than anything and the rerun starts now.", g)
    assert not tr.text_ok("open", "Short.", g)


def test_t1_llm_narration_keeps_the_template_line_that_fails(monkeypatch):
    p = _t1_plan()
    tm = tr.template_narration(p)
    monkeypatch.setattr(tr.fv, "GEMINI_KEY", "")
    assert tr.llm_narration(p, tm) == (tm, 0)
    monkeypatch.setattr(tr.fv, "GEMINI_KEY", "k")
    from factverse import llm
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: {
        "open": "Live trial: sherpa-onnx. Our preflight is on screen; the live rerun starts now.",
        "verdict.PASS": "It is 100 times better than every rival.",
        "rules": ["not", "a", "string"]})
    out, wrote = tr.llm_narration(p, tm)
    assert wrote == 1 and out["open"].startswith("Live trial: sherpa-onnx. Our")
    assert out["verdict"]["PASS"] == tm["verdict"]["PASS"] and out["rules"] == tm["rules"]
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    assert tr.llm_narration(p, tm) == (tm, 0)


# ------------------------------------------------------------------ pipeline hooks
def test_t1_live_day_drops_only_the_1845_short(monkeypatch):
    monkeypatch.setenv("TRIALS_LIVE", "1")
    assert tr.skip_short_slot("2026-11-07T18:45:00Z")          # Saturday
    assert not tr.skip_short_slot("2026-11-08T01:30:00Z")      # the retained Short
    assert not tr.skip_short_slot("2026-11-06T18:45:00Z")      # Friday
    assert not tr.skip_short_slot(None) and not tr.skip_short_slot({"x": 1})
    monkeypatch.setenv("TRIALS_LIVE", "0")
    assert not tr.skip_short_slot("2026-11-07T18:45:00Z")


def test_t1_pipeline_seams_never_raise(monkeypatch):
    from factverse import ai_pipeline as ap
    monkeypatch.setattr(tr, "skip_short_slot", lambda s: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(tr, "recap_blocked", lambda i: (_ for _ in ()).throw(RuntimeError()))
    assert ap._trials_skip_short("2026-11-07T18:45:00Z") is False
    assert ap._trials_recap_blocked({"title": "x"}) is False


def test_t1_recap_window_is_72_hours():
    ep = {"tool": "sherpa-onnx", "repo": "k2-fsa/sherpa-onnx", "space": "k2-fsa/automatic-speech-recognition",
          "recap_not_before": tr.recap_not_before("2026-11-07T18:45:00+00:00")}
    assert ep["recap_not_before"].startswith("2026-11-10T18:45")
    at = dt.datetime(2026, 11, 9, 12, tzinfo=dt.timezone.utc)
    assert tr.recap_blocked({"url": "https://github.com/k2-fsa/sherpa-onnx", "title": "x"}, at, [ep])
    assert tr.recap_blocked({"url": "https://example.com", "title": "Sherpa-ONNX 2.0 is out"}, at, [ep])
    assert not tr.recap_blocked({"url": "https://github.com/other/repo", "title": "other"}, at, [ep])
    later = dt.datetime(2026, 11, 10, 19, tzinfo=dt.timezone.utc)
    assert not tr.recap_blocked({"url": "https://github.com/k2-fsa/sherpa-onnx"}, later, [ep])
    assert not tr.recap_blocked({"url": "x"}, at, [{"recap_not_before": "garbage"}, "junk"])
    assert not tr.recap_blocked(None, at, [ep])


def test_t1_fourteen_day_readout():
    assert tr.fourteen_day_readout([{"avd_s": 40, "views": 30}, {"avd_s": 44, "views": 25}]) == "stop"
    assert tr.fourteen_day_readout([{"avd_s": 40, "views": 30}, {"avd_s": 44, "views": 24}]) == "inconclusive"
    assert tr.fourteen_day_readout([{"avd_s": 70, "views": 3}, {"avd_s": 63, "views": 9}]) == "better"
    assert tr.fourteen_day_readout([{"avd_s": 130, "views": 3}, {"avd_s": 121, "views": 9}]) == "stretch"
    assert tr.fourteen_day_readout([{"avd_s": float("inf"), "views": 3}, {"avd_s": 70, "views": 1}]) == "insufficient"
    assert tr.fourteen_day_readout([]) == "insufficient"


# ------------------------------------------------------------------ sheet + record
def _t1_episode():
    p = _t1_plan()
    clips = p["set"]["clips"]
    tests = [_t1_result("PASS", clips[0]),
             _t1_result("PARTIAL_FAIL", clips[1], "<script>alert(1)</script> room for"),
             _t1_result("TIMEOUT", clips[2]), _t1_result("PASS", clips[3])]
    return dict(p, repo="k2-fsa/sherpa-onnx", tests=tests, repeat=_t1_result("PASS", clips[1]), verdict=tr.verdict(tests),
                tally=tr.tally(tests), branch_why="why", signals={"demand": "exploratory"},
                narration_text="secret narration", started_at="2026-11-07T18:45:00+00:00")


def test_t1_sheet_is_escaped_and_links_are_checked(monkeypatch):
    ep = _t1_episode()
    ep["space"] = "javascript:alert(1)//"
    ep["tool"] = "<b>sherpa</b>"
    ep["tests"][2]["transcript"] = "<script>alert(1)</script>"   # no marks: shown raw
    page = tr.render_sheet(ep)
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "<b>sherpa" not in page and "&lt;b&gt;sherpa" in page
    assert 'href="javascript:' not in page
    assert tr.DISCLOSURE in page and "Hosted test" in page
    assert tr.tally_text(tr.tally(ep["tests"])) + "." in page and "one timed out" in page
    assert "/raw/main/assets/trials/fixtures/speech-to-text/voice-notes/c1-control.wav" in page
    assert page.startswith("<!doctype html>")


def test_t1_sheet_name_and_url():
    ep = {"date": "2026-11-07", "tool": "Sherpa ONNX/../x", "fixture_set": "voice-notes"}
    name = tr.sheet_name(ep)
    assert name == "2026-11-07-sherpa-onnx-x-voice-notes.html" and "/" not in name
    assert tr.sheet_url(ep).endswith("/trials/" + name)


def test_t1_public_record_drops_narration_and_local_paths():
    ep = _t1_episode()
    ep["tests"][0]["recording"] = "C:\\temp\\rec.webm"
    pub = tr.public_record(ep)
    assert "narration_text" not in pub and "set" not in pub
    assert all("recording" not in t for t in pub["tests"])
    assert "repo" in pub and "tool" in pub


def test_t1_publish_needs_a_token(monkeypatch):
    monkeypatch.delenv("TRIALS_GITHUB_TOKEN", raising=False)
    assert tr.publish_files({"docs/trials/x.html": "x"}, "m") is None


def test_t1_evidence_record_uses_the_shared_interface():
    from factverse import evidence
    p = _t1_plan()
    ev = tr.evidence_record(p, p["set"]["clips"][0], _t1_result("PASS"))
    assert set(evidence.empty()) <= set(ev)
    assert ev["source"] == "hosted" and ev["status"] == "PASSED_FIXED_TEST" and ev["label"] == "Hosted test"


# ------------------------------------------------------------------ the live script (pure)
def test_t1_grid_is_exactly_twelve_minutes_of_even_segments():
    import trials_live as tl
    assert sum(n for _w, n in tl.GRID) == 720
    assert all(n % 2 == 0 for _w, n in tl.GRID)
    assert tl.STARTS["run2"] == 90 and tl.STARTS["repeat"] == 450 and tl.STARTS["limits"] == 660


def test_t1_runs_start_at_most_the_lead_before_their_window():
    import trials_live as tl
    assert tl.run_at(0) == 0 and tl.run_at(1) == 0
    assert tl.run_at(2) == 210 - tr.RUN_LEAD_SECONDS and tl.run_at(4) == 450 - tr.RUN_LEAD_SECONDS


def test_t1_incomplete_ending_drops_the_remaining_test_windows():
    import trials_live as tl
    P, T, I = (_t1_result(b) for b in ("PASS", "TIMEOUT", "INCONCLUSIVE"))
    assert tl.skipped_windows({0: P, 1: T, 2: I}) == {"run4", "result4", "repeat"}
    assert tl.skipped_windows({0: P, 1: T, 2: P}) == set()


def test_t1_window_specs():
    import trials_live as tl
    p = _t1_plan()
    pre = _t1_result("PASS")
    s = tl.spec_open(p, pre)
    assert s["out"]["header"].startswith("PREFLIGHT RESULT") and "BEFORE THE STREAM" in s["out"]["header"]
    assert s["disclosure"] == tr.DISCLOSURE and s["ev"]["badge"] == "HOSTED TEST"
    r = _t1_result("PARTIAL_FAIL", p["set"]["clips"][1], "Call Maria at 9:15 in room for")
    rs = tl.spec_result(p, 1, r, [pre, r], "result2")
    assert rs["score"]["big"] == "PARTIAL / FAIL" and rs["score"]["sub"] == "TEST 2 · 2/4 SO FAR"
    assert [x["state"] for x in rs["score"]["rows"]] == ["fail", "fail"]
    assert ["for", "sub"] in rs["out"]["tokens"] and ["9:15", "ok"] in rs["out"]["tokens"]
    t = tl.spec_result(p, 2, _t1_result("TIMEOUT"), [pre, r, _t1_result("TIMEOUT")], "result3")
    assert t["out"]["lines"][0]["text"] == "NO RESULT IN 60 S" and "capture" not in t
    f = tl.spec_files(p, [pre], "https://dev-shivam-05.github.io/AI-PULSE/trials/a.html", "PASS")
    assert [x["text"] for x in f["ev"]["lines"]] == ["dev-shivam-05.github.io", "/AI-PULSE/trials/", "a.html"]
    assert tl.spec_files(p, [pre], None, "PASS")["ev"]["header"] == "NOT PUBLISHED"
    v = tl.spec_verdict(p, [pre, r], None, "PARTIAL_FAIL")
    assert v["score"]["big"] == "2/8 CHECKS"


def test_t1_replay_fits_its_room_and_keeps_the_result(tmp_path):
    import trials_live as tl
    rec = tmp_path / "r.webm"
    rec.write_bytes(b"x")
    r = {"recording": str(rec), "cut": {"start": 2.0, "length": 40.0, "speed": 2.0, "seconds": 20.0}}
    cut, at, shown = tl.replay_window(r, 5.0, 8.0)
    assert shown <= 8.0 and cut["speed"] <= 4.0
    assert abs(cut["start"] + cut["length"] - 42.0) < 1e-6         # the END is kept
    assert tl.replay_window({"recording": "", "cut": None}, 0, 9) == (None, 0, 0.0)


def test_t1_segment_args_overlay_keeps_the_radar_encoder():
    import radar_live as rl
    import trials_live as tl
    cap = {"path": "rec.webm", "cut": {"start": 1.0, "length": 9.0, "speed": 1.0}, "at": 3.0, "shown": 9.0}
    a = tl.segment_args("l.txt", "v.mp3", 30, "o.ts", "m.ffconcat", 0.0, 1.0, cap)
    fc = a[a.index("-filter_complex") + 1]
    assert f"overlay=x={tl.CAP_X}:y={tl.CAP_Y}" in fc and "between(t,3.000,12.000)" in fc
    assert "[3:a]volume=1.0" in fc and "scale=720" not in fc
    assert a[a.index("-frames:v") + 1] == str(30 * rl.FPS) and a[a.index("-bf") + 1] == "0"
    assert a[a.index("-g") + 1] == str(rl.FPS * rl.lp.KEYFRAME_S)
    assert a[a.index("-maxrate") + 1] == f"{rl.PROFILE['kbps']}k"
    b = tl.segment_args("l.txt", None, 30, "o.ts", "m.mp3", 5.0, 0.07, None)
    fb = b[b.index("-filter_complex") + 1]
    assert "overlay" not in fb and "[2:a]volume=0.07" in fb and "anullsrc" in " ".join(b)


def test_t1_stream_profile_scales_to_720p_from_the_node_env():
    import radar_live as rl
    import trials_live as tl
    assert tl.out_profile({})["w"] == 1080 and tl.out_profile({})["h"] == 1920
    p = tl.out_profile({"TOOLDOJO_STREAM_PROFILE": "720p30"})
    assert (p["w"], p["h"], p["kbps"]) == (720, 1280, rl.lp.PROFILES["720p30"]["kbps"])
    a = tl.segment_args("l.txt", "v.mp3", 30, "o.ts", profile=p)
    assert "scale=720:1280" in a[a.index("-filter_complex") + 1]
    assert a[a.index("-maxrate") + 1] == f"{p['kbps']}k"


def test_t1_raw_marks_keep_the_tools_own_words():
    clip = _t1_set()["clips"][1]
    t = "Call Maria at 9.15 and move the budget meeting to room for."
    m = tr.checks_for(clip, t)[1]["marks"]
    rm = tr.raw_marks(t, m)
    assert rm[0] == ("Call", "ok") and rm[-1] == ("for.", "sub") and len(rm) == len(t.split())
    assert tr.raw_marks("x y", [("q", "ok")]) == [("q", "ok")]          # misaligned: fall back


def test_t1_node_job_row_is_shipped_disabled():
    for f in ("config.json", "config.example.json"):
        cfg = json.loads((ROOT / f).read_text(encoding="utf-8"))
        assert cfg["trials_live"] is False
        row = next(j for j in cfg["node_jobs"] if j["name"] == "live_trials")
        assert row["enabled"] is False and row["cmd"] == ["{python}", "scripts/trials_live.py"]
        assert row["start_utc"] == tr.SLOT_UTC and row["slot_minutes"] == tr.SHOW_MINUTES
        assert row["pulse_file"] == "logs/trials_live.log" and row["days"] == ["sat"]


def test_t1_voice_mix_places_each_clip():
    import trials_live as tl
    a = tl.voice_mix_args([("a.mp3", 0), ("b.mp3", 61.5)], 90, "o.wav")
    fc = a[a.index("-filter_complex") + 1]
    assert "adelay=0|0" in fc and "adelay=61500|61500" in fc and a[a.index("-t") + 1] == "90"


def test_t1_main_refuses_other_lengths_and_youtube_out(monkeypatch, tmp_path):
    import trials_live as tl
    monkeypatch.setattr(tl.rl, "keep_awake", lambda on: None)
    monkeypatch.setattr(tl, "SESSIONS", tmp_path / "s.jsonl")
    monkeypatch.setattr(tl, "LOG", tmp_path / "l.log")
    assert tl.main(["--minutes", "10"]) == 2
    assert tl.main(["--out", "rtmps://a.rtmp.youtube.com/live2/k"]) == 2
    assert tl.main(["--start-at", "6pm", "--out", "x.flv"]) == 2


def test_t1_main_off_switch_and_key_redaction(monkeypatch, capsys, tmp_path):
    import trials_live as tl
    monkeypatch.setattr(tl.rl, "keep_awake", lambda on: None)
    monkeypatch.setattr(tl, "SESSIONS", tmp_path / "s.jsonl")
    monkeypatch.setattr(tl, "LOG", tmp_path / "l.log")
    monkeypatch.setattr(tl, "run_show", lambda *a, **k: pytest.fail("must not stream"))
    monkeypatch.setenv("TRIALS_LIVE", "0")
    assert tl.main([]) == 0
    monkeypatch.setenv("TRIALS_LIVE", "1")
    monkeypatch.setattr(tl, "trials_day", lambda now=None: True)
    monkeypatch.setenv("YT_TRIALS_STREAM_KEY", "abcd-SECRET-KEY-1234")
    monkeypatch.setenv("YT_TRIALS_STREAM_URL", "rtmps://a.rtmp.youtube.com.evil.test/live2")
    assert tl.main([]) == 2
    out = capsys.readouterr().out + (tmp_path / "l.log").read_text(encoding="utf-8") \
        + (tmp_path / "s.jsonl").read_text(encoding="utf-8")
    assert "SECRET" not in out
    tl.rl._SECRETS.clear()


def test_t1_wait_and_late_start():
    import trials_live as tl
    now = dt.datetime(2026, 11, 7, 18, 30, tzinfo=dt.timezone.utc)
    assert tl.wait_until("18:45", now) == 900 and tl.late_by("18:45", now) == -900
    late = dt.datetime(2026, 11, 7, 18, 51, tzinfo=dt.timezone.utc)
    assert tl.late_by("18:45", late) > tr.LATE_START_MAX
    assert tl.trials_day(now) and not tl.trials_day(now - dt.timedelta(days=1))
