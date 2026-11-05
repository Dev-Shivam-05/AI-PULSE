"""v3-M.1: memory record, follow-up rule, north-star ladder, search longevity,
second-slot shadow queue, long-form data cutoff (docs/spec/ai-pulse-v3m1.md).

Tests never touch the network, ffmpeg or the LLM. Helpers are prefixed `_m1_`
(the shared-module helper-name trap)."""
import datetime as dt
import json
import sys
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factverse import ai_pipeline as ap   # noqa: E402
from factverse import analytics as an     # noqa: E402
from factverse import learn               # noqa: E402
from factverse import memory              # noqa: E402
from factverse import northstar as ns     # noqa: E402
from factverse import shadow              # noqa: E402
from factverse import state_merge as sm   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
_M1_TODAY = dt.date(2026, 11, 4)


def _m1_flag(monkeypatch, **flags):
    """Pin config flags the way every consumer reads them (they share fv)."""
    real = memory.fv.flag

    def flag(name, default=False):
        return flags[name] if name in flags else real(name, default)
    monkeypatch.setattr(memory.fv, "flag", flag)


def _m1_resp(heads, rows):
    return {"columnHeaders": [{"name": h} for h in heads], "rows": rows}


def _m1_vid(n):
    return f"m1v{n:08d}"           # 11 chars, like a real YouTube id


def _m1_row(n, day="2026-10-20", fmt="tool", **extra):
    r = {"status": "PUBLISHED", "format": fmt, "title": f"Video {n}",
         "youtube_url": f"https://youtube.com/watch?v={_m1_vid(n)}",
         "publish_at": f"{day}T16:45:00Z", "timestamp": f"{day}T12:30:00"}
    r.update(extra)
    return r


def _m1_script(words_per_scene=70, n=8, **extra):
    s = {"title": "Run nv-uefi-unlocker", "description": "hook\n\nbody", "tags": ["a"],
         "thumb_text": "FREE",
         "format": "tool", "grounding": "g" * 2000, "source_url": "https://github.com/x/nv-uefi-unlocker",
         "deliverable": {"kind": "command", "text": "pip install x", "url": ""},
         "question_answered": "What does nv-uefi-unlocker unlock?",
         "questions_open": ["Does it work on a laptop GPU?", "How do I undo it?"],
         "followup": {"parent": _m1_vid(1), "family": "nvuefiunlocker", "question": "q?"},
         "scenes": [{"scene_num": i + 1, "narration": " ".join(["word"] * words_per_scene),
                     "visual_query": "v"} for i in range(n)]}
    s.update(extra)
    return s


# =============================================================== writer fields
def test_m1_questions_are_coerced_whatever_the_model_answers():
    assert memory.coerce_question({"q": 1}) == "" and memory.coerce_question(None) == ""
    assert memory.coerce_question(True) == ""
    assert memory.coerce_question("  What\nis it?  ") == "What is it?"
    assert len(memory.coerce_question("x" * 900)) == memory.QUESTION_MAX_CHARS
    # a string is split on lines, never iterated as characters
    assert memory.coerce_questions("Does it run on CPU?\nCan I undo it?") == [
        "Does it run on CPU?", "Can I undo it?"]
    assert memory.coerce_questions({"a": "b"}) == [] and memory.coerce_questions(7) == []
    assert memory.coerce_questions(["a", {"x": 1}, "a", "b", "c", "d"]) == ["a", "b", "c"]


def test_m1_validate_script_coerces_the_memory_fields():
    raw = _m1_script(questions_open="One?\nTwo?", question_answered=["not", "a", "string"])
    v = ap._validate_script(raw, "T", "https://github.com/x/y")
    assert v["questions_open"] == ["One?", "Two?"] and v["question_answered"] == ""
    assert "followup" not in v, "a planted follow-up must be popped"


def test_m1_every_lane_asks_for_the_memory_fields(monkeypatch):
    _m1_flag(monkeypatch, memory_fields=True)
    for tool in (False, True):
        c = ap._output_contract("10-14", "50-70", tool=tool)
        assert "question_answered" in c and "questions_open" in c
        assert '"question_answered":"...","questions_open":["..."]' in c
    _m1_flag(monkeypatch, memory_fields=False)
    off = ap._output_contract("10-14", "50-70")
    assert "question_answered" not in off and "questions_open" not in off
    # every lane writes through _output_contract (5 call sites)
    src = (ROOT / "factverse" / "ai_pipeline.py").read_text(encoding="utf-8")
    assert src.count("{_output_contract(") == 5


def test_m1_memory_fields_survive_every_rewrite_pass(monkeypatch):
    """The rewrite prompts never show these keys, so the rewritten JSON lacks them
    and _validate_script resets them. _CARRY must hand them back on every pass —
    and a follow-up PLANTED in a rewrite answer must die there."""
    for k in ("question_answered", "questions_open", "followup"):
        assert k in ap._CARRY
    rewrite = {"title": "T", "thumb_text": "X", "description": "new", "tags": [],
               "followup": {"parent": "forged00001", "family": "x", "question": "planted"},
               "scenes": [{"narration": " ".join(["word"] * 100), "visual_query": "v"}
                          for _ in range(6)]}                                  # 600 words
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: json.loads(json.dumps(rewrite)))
    for run_pass, wps in ((ap.critique_pass, 82),                    # 656 -> 600: cut
                          (lambda s: ap.enforce_length(s, 5000), 40),   # 320 -> 600: expanded
                          (lambda s: ap.enforce_max_length(s, 100), 82)):  # 656 -> 600: tightened
        out = run_pass(_m1_script(wps))
        assert out["description"].startswith("new"), "the pass should have applied"
        assert out["question_answered"] == "What does nv-uefi-unlocker unlock?"
        assert out["questions_open"] == ["Does it work on a laptop GPU?", "How do I undo it?"]
        assert out["followup"]["parent"] == _m1_vid(1), "the planted follow-up survived"


def test_m1_ledger_fields_never_raise_and_coerce(capsys):
    f = memory.ledger_fields(_m1_script())
    assert f["question_answered"].startswith("What does") and len(f["questions_open"]) == 2
    assert f["source_url"].endswith("nv-uefi-unlocker")
    assert f["followup_parent"] == _m1_vid(1) and f["followup_family"] == "nvuefiunlocker"
    assert memory.ledger_fields(None) == {}
    bad = {"questions_open": {"x": 1}, "question_answered": 3.5, "followup": "planted string"}
    g = memory.ledger_fields(bad)
    assert g["questions_open"] == [] and g["question_answered"] == "3.5"
    assert "followup_parent" not in g

    class Boom(dict):
        def get(self, *a, **k):
            raise RuntimeError("boom")
    assert memory.ledger_fields(Boom()) == {}
    assert "memory fields skipped" in capsys.readouterr().out


def test_m1_run_stores_the_memory_fields_in_the_ledger_row():
    src = (ROOT / "factverse" / "ai_pipeline.py").read_text(encoding="utf-8")
    # computed BEFORE the upload (never in the double-publish zone) ...
    assert src.index("_ledger_memory = memory.ledger_fields(script)") < src.index("eng.yt_upload(video")
    # ... and spread into the PUBLISHED record_run call
    assert "**_ledger_memory)" in src


# =============================================================== API query shapes
def test_m1_search_terms_args_match_the_documented_report():
    a = an.search_terms_args("abcdefghijk", "2026-10-07", "2026-11-03")
    assert a["dimensions"] == "insightTrafficSourceDetail"
    assert a["filters"] == "video==abcdefghijk;insightTrafficSourceType==YT_SEARCH"
    assert a["sort"] == "-views" and a["maxResults"] == 25 and a["metrics"] == "views"
    assert (a["startDate"], a["endDate"]) == ("2026-10-07", "2026-11-03")


def test_m1_window_is_the_28_days_ending_yesterday():
    # the 12.11 h baseline: Oct 7 - Nov 3, read on Nov 4
    assert an.window_28(_M1_TODAY) == ("2026-10-07", "2026-11-03")


def test_m1_north_star_args_use_content_type_as_a_dimension():
    a = an.content_type_args("2026-10-07", "2026-11-03")
    assert a["dimensions"] == "creatorContentType" and "filters" not in a
    assert a["metrics"].split(",")[0] == "estimatedMinutesWatched"
    t = an.vod_top_args("2026-10-07", "2026-11-03")
    assert t["dimensions"] == "video,creatorContentType" and "filters" not in t
    assert t["sort"] == "-estimatedMinutesWatched" and t["maxResults"] == 200


def test_m1_search_by_video_and_age_args():
    ids = [_m1_vid(i) for i in range(250)]
    a = an.search_by_video_args(ids, "2026-10-07", "2026-11-03")
    assert a["dimensions"] == "video,insightTrafficSourceType"
    assert a["filters"] == "video==" + ",".join(ids[-200:])
    assert an.search_by_video_args([], "a", "b") is None
    vids = [{"id": "old", "published": dt.date(2026, 8, 30)},
            {"id": "a", "published": dt.date(2026, 9, 20)},
            {"id": "b", "published": dt.date(2026, 11, 1)}]
    args, pub = an.age_args(vids, _M1_TODAY)
    assert set(pub) == {"a", "b"}, "only the last 63 days"
    assert args["startDate"] == "2026-09-20" and args["endDate"] == "2026-11-04"
    assert args["dimensions"] == "video,day,insightTrafficSourceType"
    assert args["filters"] == "video==a,b"
    many = [{"id": f"v{i}", "published": _M1_TODAY - dt.timedelta(days=62)} for i in range(900)]
    assert an.age_args(many, _M1_TODAY) == (None, {}), "videos x days must stay <= 50,000"


def test_m1_only_the_videos_the_rule_needs_get_a_terms_query():
    s28 = {f"v{i}": {"YT_SEARCH": n, "SUBSCRIBER": 999} for i, n in enumerate((5, 24, 25, 60, 186))}
    assert memory.pick_term_videos(s28) == ["v4", "v3", "v2"]
    many = {f"v{i:02d}": {"YT_SEARCH": 30 + i} for i in range(15)}
    assert len(memory.pick_term_videos(many)) == memory.TERMS_MAX_VIDEOS


class _M1Yta:
    """Answers each report by its dimensions; `boom` names the ones that raise."""
    def __init__(self, boom=()):
        self.boom, self.calls = set(boom), []

    def reports(self):
        return self

    def query(self, **kw):
        self.calls.append(kw)
        dims = kw.get("dimensions")
        if dims in self.boom:
            raise RuntimeError(f"{dims} exploded")
        if dims == "creatorContentType":
            ans = _m1_resp(["creatorContentType", "estimatedMinutesWatched", "views"],
                           [["VIDEO_ON_DEMAND", 726.6, 1756], ["SHORTS", 900, 7984],
                            ["LIVE_STREAM", 30, 12]])
        elif dims == "video,creatorContentType":
            ans = _m1_resp(["video", "creatorContentType", "estimatedMinutesWatched"],
                           [[_m1_vid(1), "VIDEO_ON_DEMAND", 400], ["shortxxxxxx", "SHORTS", 800],
                            [_m1_vid(2), "VIDEO_ON_DEMAND", 100]])
        elif dims == "video,insightTrafficSourceType":
            ans = _m1_resp(["video", "insightTrafficSourceType", "views"],
                           [[_m1_vid(1), "YT_SEARCH", 186], [_m1_vid(1), "SUBSCRIBER", 9],
                            [_m1_vid(2), "YT_SEARCH", 3]])
        elif dims == "insightTrafficSourceDetail":
            ans = _m1_resp(["insightTrafficSourceDetail", "views"],
                           [["nv-uefi-unlocker", 100], ["nv uefi unlocker", 86]])
        elif dims == "video,day,insightTrafficSourceType":
            ans = _m1_resp(["video", "day", "insightTrafficSourceType", "views",
                            "estimatedMinutesWatched"],
                           [[_m1_vid(1), "2026-10-20", "YT_SEARCH", 10, 30],
                            [_m1_vid(1), "2026-11-02", "YT_SEARCH", 4, 8]])
        else:
            ans = _m1_resp(["day", "views"], [["2026-11-01", 5]])

        class _Q:
            def execute(self):
                return ans
        return _Q()


def test_m1_collect_stores_every_m1_key(monkeypatch):
    _m1_flag(monkeypatch, north_star=True, memory_analytics=True)
    rows = [_m1_row(1, day="2026-10-20"), _m1_row(2, day="2026-10-25")]
    yta = _M1Yta()
    out = an.collect_m1(yta, _M1_TODAY, rows)
    assert out["north_star"]["by_type"]["VIDEO_ON_DEMAND"]["minutes"] == 726
    assert out["north_star"]["by_type"]["LIVE_STREAM"]["minutes"] == 30
    assert out["vod_top"]["videos"] == [[_m1_vid(1), 400], [_m1_vid(2), 100]], "Shorts dropped"
    assert out["search28"]["videos"][_m1_vid(1)] == {"YT_SEARCH": 186, "SUBSCRIBER": 9}
    # only the one video above the prefilter got a terms query
    terms = [c for c in yta.calls if c["dimensions"] == "insightTrafficSourceDetail"]
    assert len(terms) == 1 and _m1_vid(1) in terms[0]["filters"]
    assert out["search_terms"]["videos"] == {_m1_vid(1): [["nv-uefi-unlocker", 100],
                                                          ["nv uefi unlocker", 86]]}
    assert out["age_bands"][_m1_vid(1)]["search_bands"]["1-7"][0] == 10


def test_m1_one_failing_query_costs_only_its_own_key(monkeypatch, capsys):
    _m1_flag(monkeypatch, north_star=True, memory_analytics=True)
    rows = [_m1_row(1, day="2026-10-20")]
    out = an.collect_m1(_M1Yta(boom={"creatorContentType", "video,insightTrafficSourceType"}),
                        _M1_TODAY, rows)
    assert "north_star" not in out and "search28" not in out and "search_terms" not in out
    assert out["vod_top"]["videos"] and out["age_bands"]
    assert "north-star query skipped" in capsys.readouterr().out
    _m1_flag(monkeypatch, north_star=False, memory_analytics=False)
    yta = _M1Yta()
    assert an.collect_m1(yta, _M1_TODAY, rows) == {} and yta.calls == []


def test_m1_collect_keeps_the_ledger_query_last_and_the_old_reports(monkeypatch):
    """collect() runs the M.1 queries BEFORE the ledger query, in their own try."""
    _m1_flag(monkeypatch, north_star=True, memory_analytics=True, reach_report=False)
    monkeypatch.setattr(an.learn, "read_runs", lambda path=None: [_m1_row(1)])
    yta = _M1Yta(boom={"creatorContentType"})
    snap = an.collect(yta)
    assert snap["channel_days"] and snap["top_videos_7d"] is not None
    assert yta.calls[-1]["dimensions"] == "video" and "north_star" not in snap


# =============================================================== age bands
def test_m1_age_bands_normalise_per_observed_day():
    pub = {"a": dt.date(2026, 10, 1), "b": dt.date(2026, 10, 30)}
    resp = _m1_resp(["video", "day", "insightTrafficSourceType", "views", "estimatedMinutesWatched"],
                    [["a", "2026-10-01", "YT_SEARCH", 7, 10],     # age 1
                     ["a", "2026-10-03", "SUBSCRIBER", 5, 20],    # age 3, not search
                     ["a", "2026-10-09", "YT_SEARCH", 4, 4],      # age 9
                     ["a", "2026-11-02", "YT_SEARCH", 2, 2],      # age 33
                     ["b", "2026-11-02", "YT_SEARCH", 3, 6],      # age 4
                     ["zz", "2026-11-02", "YT_SEARCH", 99, 99],   # not ours
                     ["a", "not a day", "YT_SEARCH", 99, 99], "junk"])
    out = memory.aggregate_age(resp, pub)
    a, b = out["a"], out["b"]
    assert a["through"] == "2026-11-02"
    assert a["search_bands"] == {"1-7": [7, 7], "8-14": [4, 7], "15-28": [0, 14], "29-56": [2, 5]}
    assert b["search_bands"]["1-7"] == [3, 4] and b["search_bands"]["8-14"] == [0, 0]
    assert a["perf"]["72h"] == {"views": 12, "minutes": 30, "complete": True}
    assert a["perf"]["28d"]["complete"] is True and b["perf"]["7d"]["complete"] is False
    lon = {x["band"]: x for x in ns.longevity(out)}
    assert lon["1-7"]["videos"] == 2 and lon["1-7"]["views"] == 10 and lon["1-7"]["days"] == 11
    assert round(lon["1-7"]["per_day"], 3) == round(10 / 11, 3)
    assert lon["8-14"]["videos"] == 1, "a band with no observed day is not a zero"
    assert memory.aggregate_age(_m1_resp(["video"], [["a"]]), pub) == {}


# =============================================================== follow-up rule
def _m1_terms(videos, start="2026-10-07", end="2026-11-03"):
    return {"start": start, "end": end, "videos": videos}


_M1_NV = {_m1_vid(1): [["nv-uefi-unlocker", 100], ["nv uefi unlocker", 86], ["gpu unlock", 18]]}


def _m1_hosted(item):
    return "hosted", {"source": "hosted"}


def test_m1_hyphen_space_case_variants_are_one_family_raw_kept():
    assert memory.norm_query("nv-uefi-unlocker") == memory.norm_query("NV UEFI Unlocker")
    fams = memory.families(_m1_terms(_M1_NV))
    nv = fams["nvuefiunlocker"]
    assert nv["views"] == 186 and nv["parent"] == _m1_vid(1)
    assert [r[0] for r in nv["raw"]] == ["nv-uefi-unlocker", "nv uefi unlocker"]
    assert fams["gpuunlock"]["views"] == 18


def test_m1_followup_fires_on_the_nv_uefi_unlocker_case():
    """186 search views over two spellings in 28 days, an open question, hosted
    evidence -> ONE candidate, handed to the tool lane with its question."""
    rows = [_m1_row(1, questions_open=["Does it work on RTX 30 laptops?"],
                    source_url="https://github.com/x/nv-uefi-unlocker")]
    evs = memory.evaluate_followups(rows, _m1_terms(_M1_NV), _M1_TODAY, probe=_m1_hosted)
    assert [e["family"] for e in evs] == ["nvuefiunlocker"], "18-view family is below 50"
    ev = evs[0]
    assert ev["status"] == "candidate" and ev["views"] == 186
    assert ev["question"] == "Does it work on RTX 30 laptops?" and ev["evidence"] == "hosted"
    item = memory.candidate_item(ev)
    assert item["kind"] == "tool" and item["url"] == "https://github.com/x/nv-uefi-unlocker"
    assert item["followup_question"] == ev["question"] and item["followup_parent"] == _m1_vid(1)
    assert item["title"] == "nv-uefi-unlocker"


def test_m1_followup_cooldown_is_14_days_per_family_unless_exempt():
    parent = _m1_row(1, questions_open=["Q?"], source_url="https://github.com/x/nv-uefi-unlocker")

    def fu(day):
        return _m1_row(9, day=day, followup_family="nvuefiunlocker", followup_parent=_m1_vid(1))
    terms = _m1_terms(_M1_NV)
    recent = memory.evaluate_followups([parent, fu("2026-10-25")], terms, _M1_TODAY, probe=_m1_hosted)
    assert recent[0]["status"] == "cooldown" and recent[0]["last_followup"] == "2026-10-25"
    # day 14 after the last follow-up: free again
    old = memory.evaluate_followups([parent, fu("2026-10-21")], terms, _M1_TODAY, probe=_m1_hosted)
    assert old[0]["status"] == "candidate"
    for reason in ("correction", "material_change"):
        ex = memory.evaluate_followups([parent, fu("2026-11-02")], terms, _M1_TODAY,
                                       probe=_m1_hosted, exempt={"nvuefiunlocker": reason})
        assert ex[0]["status"] == "candidate" and ex[0]["exempt"] == reason
    other = memory.evaluate_followups([parent, fu("2026-11-02")], terms, _M1_TODAY,
                                      probe=_m1_hosted, exempt={"nvuefiunlocker": "popular"})
    assert other[0]["status"] == "cooldown"


def test_m1_followup_needs_all_three_conditions():
    src = "https://github.com/x/nv-uefi-unlocker"
    terms = _m1_terms(_M1_NV)
    no_q = memory.evaluate_followups([_m1_row(1, source_url=src)], terms, _M1_TODAY, probe=_m1_hosted)
    assert no_q[0]["status"] == "no_open_question"
    rows = [_m1_row(1, questions_open=["Q?"], source_url=src)]
    none = memory.evaluate_followups(rows, terms, _M1_TODAY, probe=lambda i: ("none", {}))
    assert none[0]["status"] == "no_evidence"
    unk = memory.evaluate_followups(rows, terms, _M1_TODAY, probe=lambda i: ("unknown", None))
    assert unk[0]["status"] == "evidence_unknown"
    # 49 attributed views is not 50
    low = memory.evaluate_followups(rows, _m1_terms({_m1_vid(1): [["nv-uefi-unlocker", 49]]}),
                                    _M1_TODAY, probe=_m1_hosted)
    assert low == []
    # no source URL on the row, but the tools index knows the video
    idx = {_m1_vid(1): {"source_url": src, "tool": "x/nv-uefi-unlocker - trending"}}
    via = memory.evaluate_followups([_m1_row(1, questions_open=["Q?"])], terms, _M1_TODAY,
                                    probe=_m1_hosted, index=idx)
    assert via[0]["status"] == "candidate" and via[0]["source_url"] == src
    assert memory.evaluate_followups([_m1_row(1, questions_open=["Q?"])], terms, _M1_TODAY,
                                     probe=_m1_hosted)[0]["status"] == "no_source"


def test_m1_followup_never_uses_lifetime_or_stale_windows():
    rows = [_m1_row(1, questions_open=["Q?"], source_url="https://github.com/x/nv-uefi-unlocker")]
    called = []

    def probe(item):
        called.append(item)
        return "hosted", {}
    life = memory.evaluate_followups(rows, _m1_terms(_M1_NV, start="2026-08-24"), _M1_TODAY, probe=probe)
    assert life[0]["status"] == "stale_window"
    stale = memory.evaluate_followups(rows, _m1_terms(_M1_NV, "2026-09-20", "2026-10-17"),
                                      _M1_TODAY, probe=probe)
    assert stale[0]["status"] == "stale_window" and not called


def test_m1_missing_evidence_module_is_unknown(monkeypatch):
    # Integration: once v3-P.1's evidence.py is imported, `from factverse import
    # evidence` reads the PACKAGE ATTRIBUTE first, so sys.modules alone no longer
    # stands in for the module. Patch both, as the import machinery sees them.
    import factverse as _m1_pkg
    monkeypatch.setitem(sys.modules, "factverse.evidence", None)   # import -> ImportError
    monkeypatch.delattr(_m1_pkg, "evidence", raising=False)
    assert memory.evidence_probe({"url": "x"}) == ("unknown", None)
    fake = types.ModuleType("factverse.evidence")
    fake.probe = lambda item: None                                  # fail-soft None
    monkeypatch.setitem(sys.modules, "factverse.evidence", fake)
    monkeypatch.setattr(_m1_pkg, "evidence", fake, raising=False)
    assert memory.evidence_probe({})[0] == "unknown"
    fake.probe = lambda item: {"source": "author"}
    assert memory.evidence_probe({})[0] == "author"
    fake.probe = lambda item: {"source": "none"}
    assert memory.evidence_probe({})[0] == "none"

    def boom(item):
        raise RuntimeError("x")
    fake.probe = boom
    assert memory.evidence_probe({})[0] == "unknown"


def test_m1_followup_items_kill_switch_and_fail_soft(monkeypatch, tmp_path, capsys):
    runs, ana = tmp_path / "r.jsonl", tmp_path / "a.jsonl"
    runs.write_text(json.dumps(_m1_row(1, questions_open=["Q?"],
                                       source_url="https://github.com/x/nv-uefi-unlocker")) + "\n",
                    encoding="utf-8")
    ana.write_text(json.dumps({"search_terms": _m1_terms(_M1_NV)}) + "\n", encoding="utf-8")
    monkeypatch.setattr(memory, "tools_index", lambda path=None: {})
    _m1_flag(monkeypatch, followup_candidates=False)
    assert memory.followup_items(_M1_TODAY, runs, ana, probe=_m1_hosted) == []
    _m1_flag(monkeypatch, followup_candidates=True)
    items = memory.followup_items(_M1_TODAY, runs, ana, probe=_m1_hosted)
    assert len(items) == 1 and items[0]["followup_family"] == "nvuefiunlocker"

    def boom(item):
        raise RuntimeError("probe exploded")
    assert memory.followup_items(_M1_TODAY, runs, ana, probe=boom) == []
    assert "follow-up candidates skipped" in capsys.readouterr().out


def test_m1_build_script_hands_the_followup_to_the_tool_lane_first(monkeypatch):
    item = memory.candidate_item({"tool": "nv-uefi-unlocker", "source_url": "https://github.com/x/nv-uefi-unlocker",
                                  "question": "Does it work on laptops?", "parent": _m1_vid(1),
                                  "family": "nvuefiunlocker"})
    monkeypatch.setattr(ap.memory, "followup_items", lambda: [item])
    monkeypatch.setattr(ap, "too_many_failures", lambda t: False)
    tried = []

    def fake_tool(c):
        tried.append(c)
        return {"format": "tool", "title": "T"}
    monkeypatch.setattr(ap, "script_tool", fake_tool)
    ranked = [{"kind": "tool", "title": "other/repo", "url": "https://github.com/o/repo"}]
    s = ap.build_script("tool", ranked)
    assert tried[0] is item, "the follow-up candidate goes first"
    assert s["followup"] == {"parent": _m1_vid(1), "family": "nvuefiunlocker",
                             "question": "Does it work on laptops?"}
    # an ordinary candidate carries no follow-up
    monkeypatch.setattr(ap.memory, "followup_items", lambda: [])
    tried.clear()
    assert "followup" not in ap.build_script("tool", ranked)


def test_m1_script_tool_writer_prompt_carries_the_question(monkeypatch):
    readme = "# Tool\n" + ("Real README text. " * 120) + "\n```\npip install tool\n```\n"
    monkeypatch.setattr(ap, "fetch_text", lambda url, limit=4000: readme[:limit])
    monkeypatch.setattr(ap, "_verified_facts", lambda url: {})
    monkeypatch.setattr(ap, "_top_issues", lambda url: [])
    prompts = []
    monkeypatch.setattr(ap.llm, "generate_json", lambda p, **k: prompts.append(p) or None)
    item = {"title": "x/tool", "source": "s", "url": "https://github.com/x/tool",
            "followup_question": "Does it run offline?"}
    assert ap.script_tool(item) is None
    assert "FOLLOW-UP:" in prompts[0] and "Does it run offline?" in prompts[0]
    prompts.clear()
    ap.script_tool({"title": "x/tool", "source": "s", "url": "https://github.com/x/tool"})
    assert "FOLLOW-UP:" not in prompts[0]


# =============================================================== the record
def test_m1_memory_record_has_every_field_group(tmp_path):
    rows = [_m1_row(1, questions_open=["Q?"], question_answered="What is it?",
                    source_url="https://github.com/x/nv-uefi-unlocker", evidence_source="hosted",
                    evidence_status="PASSED_FIXED_TEST", experiment="pilot_a", arm="proof"),
            _m1_row(2, day="2026-10-30", followup_parent=_m1_vid(1), followup_family="nvuefiunlocker")]
    snaps = [{"collected": "2026-11-04T18:00:00",
              "ledger_headers": ["video", "views", "estimatedMinutesWatched", "averageViewDuration"],
              "ledger_videos": [[_m1_vid(1), 300, 600, 120]],
              "search_terms": _m1_terms(_M1_NV),
              "search28": {"start": "2026-10-07", "end": "2026-11-03",
                           "videos": {_m1_vid(1): {"YT_SEARCH": 186}}},
              "age_bands": {_m1_vid(1): {"through": "2026-11-02", "perf": {
                  "72h": {"views": 5, "minutes": 9, "complete": True}},
                  "search_bands": {"1-7": [3, 7]}}}}]
    rec = memory.build_record(rows[0], rows, snaps)
    assert set(rec) == {"identity", "viewer_need", "evidence", "delivery", "performance", "demand"}
    assert rec["identity"]["canonical_tool"] == "nv-uefi-unlocker"
    assert rec["identity"]["experiment"] == "pilot_a" and rec["identity"]["arm"] == "proof"
    assert rec["viewer_need"]["followup_ids"] == [_m1_vid(2)]
    assert rec["evidence"] == {"source": "hosted", "status": "PASSED_FIXED_TEST"}
    assert rec["performance"]["72h"]["views"] == 5 and rec["performance"]["7d"] is None
    assert rec["performance"]["cumulative_since_floor"]["minutes"] == 600
    assert rec["demand"]["query_families"] == {"nvuefiunlocker": 186, "gpuunlock": 18}
    assert rec["demand"]["search_window"] == ["2026-10-07", "2026-11-03"]
    # script evidence wins over the ledger strings
    rec2 = memory.build_record(rows[0], rows, snaps, script={"evidence": {"source": "author",
                                                                          "status": "NOT_RUN"}})
    assert rec2["evidence"]["source"] == "author"


# =============================================================== north star
def _m1_ns_snap(end, vod_h, live_min=0, top=None, collected=None):
    e = dt.date.fromisoformat(end)
    start = (e - dt.timedelta(days=27)).isoformat()
    s = {"collected": collected or f"{end}T20:00:00",
         "north_star": {"start": start, "end": end, "by_type": {
             "VIDEO_ON_DEMAND": {"minutes": vod_h * 60, "views": 1},
             "LIVE_STREAM": {"minutes": live_min, "views": 1}}}}
    if top:
        s["vod_top"] = {"start": start, "end": end, "videos": top}
    return s


def test_m1_ladder_values_are_the_locked_ones():
    assert ns.BASELINE_H == 12.11
    assert [(s[0], s[1], s[2]) for s in ns.LADDER] == [
        ("2x", 24.22, 30), ("5x", 60.55, 60), ("10x", 121.10, 90),
        ("25x", 302.75, None), ("50x", 605.50, None), ("100x", 1211.00, None)]
    for name, target, _, _ in ns.LADDER:
        assert round(ns.BASELINE_H * float(name[:-1]), 2) == target


def test_m1_day_zero_is_the_first_pilot_a_publication():
    rows = [_m1_row(1, day="2026-11-01"), _m1_row(2, day="2026-11-03", experiment="pilot_a"),
            _m1_row(3, day="2026-11-05", experiment="pilot_a"),
            dict(_m1_row(4, day="2026-11-02", experiment="pilot_a"), status="FACTCHECK_BLOCKED")]
    assert ns.day_zero(rows) == dt.date(2026, 11, 3)
    assert ns.day_zero([_m1_row(1)]) is None
    assert all(ns.stage_status(s, None, _M1_TODAY, []) == "not started" for s in ns.LADDER)


def test_m1_stage_status_pending_unresolved_met_behind():
    two = ns.LADDER[0]
    d0 = dt.date(2026, 11, 1)
    assert ns.stage_status(two, d0, dt.date(2026, 11, 20), []) == "pending (day 19 of 30)"
    # due day reached, no window reaching the checkpoint -> unresolved, never failed
    old = ns.windows([_m1_ns_snap("2026-11-20", 40)])
    assert ns.stage_status(two, d0, dt.date(2026, 12, 2), old) == \
        "unresolved - insufficient observations"
    met = ns.windows([_m1_ns_snap("2026-11-30", 25, top=[["a", 10 * 60], ["b", 60]])])
    assert ns.stage_status(two, d0, dt.date(2026, 12, 2), met).startswith("hours met (25.00 h)")
    behind = ns.windows([_m1_ns_snap("2026-11-30", 20)])
    assert ns.stage_status(two, d0, dt.date(2026, 12, 2), behind) == "behind plan (20.00 of 24.22 h)"
    big = ns.windows([_m1_ns_snap("2026-11-30", 25, top=[["a", 20 * 60]])])
    assert "outlier-dependent" in ns.stage_status(two, d0, dt.date(2026, 12, 2), big)


def test_m1_fifty_x_needs_two_consecutive_windows():
    fifty = ns.LADDER[4]
    d0 = dt.date(2026, 11, 1)
    one = ns.windows([_m1_ns_snap("2027-03-01", 700)])
    assert ns.stage_status(fifty, d0, dt.date(2027, 3, 2), one).startswith("met in 1 window; unresolved")
    first_end = dt.date(2027, 3, 1) - dt.timedelta(days=28)
    both = ns.windows([_m1_ns_snap(first_end.isoformat(), 610), _m1_ns_snap("2027-03-01", 700)])
    assert ns.stage_status(fifty, d0, dt.date(2027, 3, 2), both) == "met in 2 consecutive windows"
    dip = ns.windows([_m1_ns_snap(first_end.isoformat(), 500), _m1_ns_snap("2027-03-01", 700)])
    assert ns.stage_status(fifty, d0, dt.date(2027, 3, 2), dip) == "met in 1 window (needs 2 consecutive)"


def test_m1_north_star_block_reads_live_separately_and_flags_outliers(tmp_path):
    ana = tmp_path / "a.jsonl"
    ana.write_text(json.dumps(_m1_ns_snap("2026-11-03", 12.11, live_min=90,
                                          top=[[_m1_vid(1), 8 * 60], [_m1_vid(2), 60]])) + "\n",
                   encoding="utf-8")
    text = ns.block([_m1_row(1)], ana, _M1_TODAY)
    assert "now: 12.11 h = 1.00x baseline" in text
    assert "live / archived-live (LIVE_STREAM), separate counter: 1.50 h" in text
    assert "66% (m1v00000001)  OUTLIER-DEPENDENT" in text
    assert "YPP qualified hours: MANUAL" in text
    assert 'day 0: not started (no PUBLISHED ledger row with experiment == "pilot_a")' in text
    for st in ns.LADDER:
        assert st[3] in text, "every stage prints its leading-evidence line"
    assert "insufficient observations = unresolved" in text
    # the per-video window must be the SAME window, or the share means nothing
    ana.write_text(json.dumps(dict(_m1_ns_snap("2026-11-03", 10),
                                   vod_top={"start": "x", "end": "2026-10-01",
                                            "videos": [["a", 6000]]})) + "\n", encoding="utf-8")
    assert "largest video share: unknown" in ns.block([], ana, _M1_TODAY)


def test_m1_north_star_block_on_empty_and_garbage_state(tmp_path):
    ana = tmp_path / "a.jsonl"
    ana.write_text('not json\n{"north_star": "junk"}\n{"north_star": {"by_type": []}}\n',
                   encoding="utf-8")
    text = ns.block([], ana, _M1_TODAY)
    assert "no north-star observation yet" in text and "no age-band data yet" in text
    assert ns.block([], tmp_path / "missing.jsonl", _M1_TODAY)


def test_m1_scoreboard_carries_the_new_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SHADOW_LOG", tmp_path / "none.jsonl")
    runs, ana = tmp_path / "r.jsonl", tmp_path / "a.jsonl"
    runs.write_text(json.dumps(_m1_row(1)) + "\n", encoding="utf-8")
    ana.write_text(json.dumps(_m1_ns_snap("2026-11-03", 3)) + "\n", encoding="utf-8")
    text = learn.scoreboard(runs, ana, _M1_TODAY)
    assert "north star - rolling 28-day ON-DEMAND" in text and "shadow queue" in text
    # a raising block costs only itself
    monkeypatch.setattr(ns, "block", lambda *a, **k: 1 / 0)
    text = learn.scoreboard(runs, ana, _M1_TODAY)
    assert "north star - rolling" not in text and "v3-D scoreboard" in text


# =============================================================== row 18
def test_m1_long_form_comparison_starts_after_the_counting_change():
    assert learn.DATA_FLOOR == "2026-08-24" and learn.LONGFORM_FLOOR == "2026-08-28"
    rows = [_m1_row(1, day="2026-08-25", fmt="news"), _m1_row(2, day="2026-08-28", fmt="news")]
    stats = learn.score(rows, {}, dt.date(2026, 9, 26))
    assert stats["format:news"]["videos"] == 1, "08-25 is not comparable"
    assert learn.ledger_ids(rows) == [_m1_vid(1), _m1_vid(2)], "still measured"


# =============================================================== shadow queue
def _m1_ap(pages=None, unsuitable=(), hang=None):
    pages = pages or {}

    def fetch(url, limit=4000):
        if hang and hang in url:
            time.sleep(5)
        return pages.get(url, "")[:limit]

    def tool_unsuitable(title, text=""):
        hit = next((t for t in unsuitable if t in title.lower() or t in text.lower()), None)
        return (bool(hit), hit or "")
    return types.SimpleNamespace(
        gates=types.SimpleNamespace(tool_unsuitable=tool_unsuitable),
        tool_source_eligible=ap.tool_source_eligible, _hf_readme_url=ap._hf_readme_url,
        _gh_readme_url=ap._gh_readme_url, fetch_text=fetch,
        TOOL_README_FETCH=ap.TOOL_README_FETCH, TOOL_GROUNDING_MIN=ap.TOOL_GROUNDING_MIN)


def _m1_cand(owner_repo, kind="tool"):
    return {"kind": kind, "title": owner_repo, "url": f"https://github.com/{owner_repo}"}


def _m1_raw(owner_repo):
    return f"https://raw.githubusercontent.com/{owner_repo}/HEAD/README.md"


def test_m1_prewriter_gate_runs_script_tools_checks_in_order(monkeypatch):
    monkeypatch.setattr(memory, "evidence_probe", lambda item: ("unknown", None))
    good = _m1_ap({_m1_raw("a/good"): "r" * 1500, _m1_raw("a/evil"): "a deepfake tool " * 100})
    g = shadow.prewriter_gate(_m1_cand("a/good"), good)
    assert g["passed"] and g["grounding_chars"] == 1500 and g["qualified"] == "unknown"
    thin = shadow.prewriter_gate(_m1_cand("a/thin"), good)
    assert not thin["grounding_ok"] and thin["qualified"] is False
    ph = shadow.prewriter_gate({"title": "x", "url": "https://www.producthunt.com/posts/x"}, good)
    assert ph["eligible"] is False and ph["grounding_chars"] == 0
    bad = _m1_ap({_m1_raw("a/evil"): "a deepfake tool " * 100}, unsuitable=("deepfake",))
    ev = shadow.prewriter_gate(_m1_cand("a/evil"), bad)
    assert ev["grounding_ok"] and not ev["suitable"] and ev["term"] == "deepfake"
    monkeypatch.setattr(memory, "evidence_probe", lambda item: ("hosted", {}))
    assert shadow.prewriter_gate(_m1_cand("a/good"), good)["qualified"] is True


def test_m1_shadow_check_skips_the_primary_and_stops_at_a_qualified_one(monkeypatch):
    monkeypatch.setattr(memory, "evidence_probe", lambda item: ("author", {}))
    fake = _m1_ap({_m1_raw(r): "r" * 1500 for r in ("p/prim", "b/two", "c/three")})
    ph = [{"kind": "tool", "title": f"PH {i}", "url": f"https://www.producthunt.com/products/{i}"}
          for i in range(3)]
    ranked = [_m1_cand("p/prim"), {"kind": "story", "title": "news"}, *ph, _m1_cand("q/thin"),
              _m1_cand("b/two"), _m1_cand("c/three"), _m1_cand("d/four")]
    res = shadow.check(ranked, "https://github.com/p/prim/", fake)
    # measured live 2026-11-04: ineligible pages must not spend the 3 slots
    assert res["candidates"] == 3 and res["screened_out"] == 3, "bounded to 3 second candidates"
    assert [c["title"] for c in res["checked"]] == ["q/thin", "b/two"], "stops at the first qualified"
    assert res["qualified"] is True and res["second"]["title"] == "b/two" and not res["timed_out"]


def test_m1_shadow_check_has_a_real_wall_clock(monkeypatch):
    monkeypatch.setattr(memory, "evidence_probe", lambda item: ("hosted", {}))
    slow = _m1_ap({}, hang="raw.githubusercontent.com")
    t0 = time.monotonic()
    res = shadow.check([_m1_cand("a/slow")], "", slow, budget_s=0.3)
    assert time.monotonic() - t0 < 2 and res["timed_out"] and res["qualified"] is False


def test_m1_after_run_records_automatic_publish_runs_only(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "evidence_probe", lambda item: ("unknown", None))
    _m1_flag(monkeypatch, shadow_queue=True)
    log, runs = tmp_path / "shadow.jsonl", tmp_path / "runs.jsonl"
    today = dt.datetime.utcnow().date().isoformat()
    runs.write_text(json.dumps({"status": "PUBLISHED", "format": "tool", "timestamp": f"{today}T12:40:00",
                                "source_url": "https://github.com/p/prim"}) + "\n", encoding="utf-8")
    fake = _m1_ap({_m1_raw("b/two"): "r" * 1500})
    ranked = [_m1_cand("p/prim"), _m1_cand("b/two")]
    monkeypatch.setenv("JOB_STARTED_AT", str(time.time() - 1800))
    row = shadow.after_run(ranked, fake, publish=True, forced=None, run_s=1500.2, path=log, runs_path=runs)
    assert row["qualified"] == "unknown" and row["second"]["title"] == "b/two"
    assert row["primary_url"] == "https://github.com/p/prim" and row["run_s"] == 1500.2
    assert 1790 < row["job_s"] < 1900
    assert json.loads(log.read_text(encoding="utf-8").splitlines()[-1])["date"] == today
    for kw in ({"publish": False, "forced": None}, {"publish": True, "forced": "tool"}):
        assert shadow.after_run(ranked, fake, run_s=1, path=log, runs_path=runs, **kw) is None
    assert shadow.after_run([], fake, publish=True, forced=None, run_s=1, path=log, runs_path=runs) is None
    _m1_flag(monkeypatch, shadow_queue=False)
    assert shadow.after_run(ranked, fake, publish=True, forced=None, run_s=1, path=log, runs_path=runs) is None
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1


def test_m1_after_run_never_raises(monkeypatch, tmp_path, capsys):
    _m1_flag(monkeypatch, shadow_queue=True)
    monkeypatch.setattr(shadow, "check", lambda *a, **k: 1 / 0)
    assert shadow.after_run([_m1_cand("a/b")], None, publish=True, forced=None, run_s=1,
                            path=tmp_path / "s.jsonl", runs_path=tmp_path / "missing.jsonl") is None
    assert "shadow queue skipped" in capsys.readouterr().out


def _m1_shadow_log(days, qualified_days, job_min=40, start=dt.date(2026, 11, 1)):
    out = []
    for i in range(days):
        d = start + dt.timedelta(days=i)
        out.append({"date": d.isoformat(), "qualified": i < qualified_days, "job_s": job_min * 60,
                    "run_s": 10})
    return out


def _m1_published(start, days, skip=()):
    return [_m1_row(i, day=(start + dt.timedelta(days=i)).isoformat())
            for i in range(days) if i not in skip]


def test_m1_shadow_evaluator_eligible_and_not():
    start = dt.date(2026, 11, 1)
    end = start + dt.timedelta(days=13)
    rows = _m1_published(start, 14)
    ok = shadow.evaluate(_m1_shadow_log(14, 10), rows, end)
    assert ok["verdict"] == "ELIGIBLE for the 1-vs-2 quantity test" and ok["qualified_days"] == 10
    nine = shadow.evaluate(_m1_shadow_log(14, 9), rows, end)
    assert nine["verdict"] == "not eligible: 9 of 10 qualified days"
    slow = shadow.evaluate(_m1_shadow_log(14, 12, job_min=61), rows, end)
    assert "p95 job time not under 60 min" in slow["verdict"]
    missed = shadow.evaluate(_m1_shadow_log(14, 12), _m1_published(start, 14, skip=(3,)), end)
    assert "1 missed primary upload(s)" in missed["verdict"]
    # today's missing upload is not final until the retry cron
    today_open = shadow.evaluate(_m1_shadow_log(14, 12), _m1_published(start, 13), end)
    assert today_open["verdict"].startswith("ELIGIBLE")
    # "unknown" evidence is never a qualified day
    unk = [dict(r, qualified="unknown") for r in _m1_shadow_log(14, 0)]
    u = shadow.evaluate(unk, rows, end)
    assert u["qualified_days"] == 0 and u["unknown_days"] == 14


def test_m1_shadow_evaluator_insufficient_observations_is_unresolved():
    start = dt.date(2026, 11, 1)
    ev = shadow.evaluate(_m1_shadow_log(9, 9), _m1_published(start, 9), start + dt.timedelta(days=8))
    assert ev["verdict"] == "unresolved - insufficient observations"
    assert shadow.evaluate([], [], _M1_TODAY)["verdict"] == "unresolved - insufficient observations"


def test_m1_p95_is_nearest_rank():
    assert shadow.p95([60] * 19 + [3600]) == 60
    assert shadow.p95([60] * 18 + [3600, 3600]) == 3600
    assert shadow.p95([]) is None


def test_m1_shadow_block_reads_the_log(tmp_path):
    log = tmp_path / "s.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in _m1_shadow_log(14, 11)) + "\nnot json\n",
                   encoding="utf-8")
    start = dt.date(2026, 11, 1)
    text = shadow.block(_m1_published(start, 14), log, start + dt.timedelta(days=13))
    assert "days with a qualified second candidate: 11" in text
    assert "p95 job time: 40.0 min" in text and "verdict: ELIGIBLE" in text


# =============================================================== state, config, CI
def test_m1_shadow_queue_gets_the_both_halves_treatment():
    assert "state/shadow_queue.jsonl" in sm.FILES
    pub = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    assert "state/shadow_queue.jsonl" in pub
    # written by the pipeline step, which runs BEFORE the state-save
    assert pub.index("python -m factverse.ai_pipeline publish") < pub.index("python -m factverse.state_merge")
    # the job clock starts in the first step
    assert pub.index('JOB_STARTED_AT=$(date +%s)') < pub.index("actions/checkout@v4")
    merged = sm.merge_file("state/shadow_queue.jsonl", '{"date":"a"}\n{"date":"b"}\n', '{"date":"a"}\n')
    assert merged.splitlines() == ['{"date":"a"}', '{"date":"b"}']


def test_m1_kill_switches_exist_in_both_configs():
    for name in ("config.json", "config.example.json"):
        cfg = json.loads((ROOT / name).read_text(encoding="utf-8"))
        for k in ("memory_fields", "memory_analytics", "north_star", "followup_candidates",
                  "shadow_queue"):
            assert cfg.get(k) is True, f"{k} missing in {name}"


def test_m1_shadow_runs_after_run_returns_in_main():
    src = (ROOT / "factverse" / "ai_pipeline.py").read_text(encoding="utf-8")
    main = src[src.index('if __name__ == "__main__":'):]
    assert main.index("ok = run(") < main.index("shadow.after_run(") < main.index("sys.exit(")
    assert "LAST_RANKED[:] = ranked" in src
