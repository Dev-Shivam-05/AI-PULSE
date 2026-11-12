"""v3-R.2: the recovery cohort launch (docs/spec/ai-pulse-v3r.md, D1-D5, D7, D8, D12).

Every test turns `recovery_cohort` on explicitly (conftest turns it off suite-wide).
No network, no ffmpeg, no LLM: every seam is stubbed as the consumer sees it.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from factverse import ai_pipeline as ap    # noqa: E402
from factverse import evidence as ev       # noqa: E402
from factverse import native_short as ns   # noqa: E402
from factverse import shorts as sh         # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
_R2_GH = "https://github.com/acme/demo-tool"


def _r2_on(monkeypatch, on=True):
    monkeypatch.setenv("RECOVERY_COHORT", "1" if on else "0")


def _r2_queue(monkeypatch, items):
    monkeypatch.setitem(ap.fv.CONFIG, "cohort_queue", items)


# ================================================================ config (the locked table)
def test_r2_config_carries_the_locked_cohort():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    example = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    assert cfg["recovery_cohort"] is True
    assert dt.date.fromisoformat(cfg["cohort_start"]).weekday() == 0          # D1: a Monday
    urls = [q["url"] for q in cfg["cohort_queue"]]
    assert urls == ["https://github.com/Zagitta/gpu-unlock",                 # D12, in order
                    "https://github.com/omlahore/RemoveMacAI",
                    "https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B",
                    "https://github.com/physicsdolphin/nv-uefi-unlocker",
                    "https://github.com/CopilotKit/OpenBot",
                    "https://github.com/zai-org/ZCode"]
    assert all(q["question"].endswith("?") and q["parent"] and q["family"] for q in cfg["cohort_queue"])
    # gpu-unlock and nv-uefi-unlocker are ONE subject family (D2)
    assert cfg["cohort_queue"][0]["family"] == cfg["cohort_queue"][3]["family"]
    for k in ("recovery_cohort", "cohort_start", "cohort_queue"):
        assert example[k] == cfg[k]
    assert ap.COHORT_LONG_WEEKDAYS == (0, 2, 4) and ap.COHORT_SHORT_UTC == "18:45"


# ================================================================ D1: the schedule
def test_r2_cohort_day_mon_wed_fri_from_the_start_date(monkeypatch):
    monkeypatch.setitem(ap.fv.CONFIG, "cohort_start", "2026-11-16")
    week = [dt.date(2026, 11, 16) + dt.timedelta(days=i) for i in range(7)]   # Mon..Sun
    assert [ap.cohort_day(d) for d in week] == ["long", "rest", "long", "rest", "long", "rest", "rest"]
    assert ap.cohort_day(dt.date(2026, 11, 13)) == "rest"                     # a Friday BEFORE the start
    monkeypatch.setitem(ap.fv.CONFIG, "cohort_start", "not a date")
    assert ap.cohort_day(dt.date(2026, 11, 13)) == "long"                     # unreadable: no hold-back


def test_r2_short_slot_is_the_next_day_at_1845_utc():
    assert ap.cohort_short_slot("2026-11-16T16:45:00Z") == "2026-11-17T18:45:00Z"
    assert ap.cohort_short_slot("2026-11-30T16:45:00Z") == "2026-12-01T18:45:00Z"
    assert ap.cohort_short_slot(None) is None and ap.cohort_short_slot("garbage") is None


def test_r2_rest_day_publishes_nothing_and_exits_clean(monkeypatch):
    _r2_on(monkeypatch)
    rows = []
    monkeypatch.setattr(ap, "cohort_day", lambda d: "rest")
    monkeypatch.setattr(ap, "record_run", lambda **kw: rows.append(kw))
    monkeypatch.setattr(ap.signal_engine, "rank", lambda limit=20: 1 / 0)    # never reached
    monkeypatch.setattr(ap, "already_published_today", lambda: 1 / 0)
    assert ap.run(publish=True) == {"status": "COHORT_REST_DAY"}             # truthy: exit 0
    assert rows == [{"status": "COHORT_REST_DAY", "format": "-"}]


def test_r2_long_day_continues_to_the_duplicate_guard(monkeypatch):
    _r2_on(monkeypatch)
    rows = []
    monkeypatch.setattr(ap, "cohort_day", lambda d: "long")
    monkeypatch.setattr(ap, "record_run", lambda **kw: rows.append(kw))
    monkeypatch.setattr(ap, "already_published_today", lambda: True)
    assert ap.run(publish=True) == {"status": "SKIPPED_DUPLICATE_DAY"}
    assert rows[-1]["status"] == "SKIPPED_DUPLICATE_DAY"


@pytest.mark.parametrize("lane", ["news", "evergreen", "roundup", "debate"])
def test_r2_a_forced_paused_lane_is_refused(monkeypatch, lane):
    _r2_on(monkeypatch)
    rows = []
    monkeypatch.setattr(ap, "record_run", lambda **kw: rows.append(kw))
    monkeypatch.setattr(ap.signal_engine, "rank", lambda limit=20: 1 / 0)
    assert ap.run(publish=True, force_format=lane) is None
    assert rows == [{"status": "COHORT_LANE_PAUSED", "format": lane}]


def test_r2_a_forced_tool_run_is_not_held_by_the_rest_day(monkeypatch):
    _r2_on(monkeypatch)
    monkeypatch.setattr(ap, "cohort_day", lambda d: "rest")
    monkeypatch.setattr(ap, "record_run", lambda **kw: None)
    monkeypatch.setattr(ap, "already_published_today", lambda: True)
    assert ap.run(publish=True, force_format="tool") == {"status": "SKIPPED_DUPLICATE_DAY"}


# ================================================================ D3: only the tool lane
def test_r2_decide_format_is_tool_on_every_day(monkeypatch):
    _r2_on(monkeypatch)
    monkeypatch.setattr(ap, "viral_pick", lambda r: 1 / 0)                  # no viral check at all
    for d in range(7):
        day = dt.date(2026, 11, 16) + dt.timedelta(days=d)
        assert ap.decide_format(None, [], today=day) == ("tool", None)
    _r2_on(monkeypatch, False)
    assert ap.decide_format(None, [], today=dt.date(2026, 11, 22))[0] == "roundup"   # off: unchanged


def test_r2_fallback_re_runs_the_tool_lane_never_a_paused_one(monkeypatch):
    _r2_on(monkeypatch)
    assert ap._fallback_format("tool", None, False, True) == "tool"
    assert ap._fallback_format("tool", "tool", True, True) == "tool"
    assert ap._fallback_format("evergreen", None, True, False) == "tool"
    assert ap._fallback_format("tool", "tool", False, True) is None          # owner-forced: no fallback
    _r2_on(monkeypatch, False)
    assert ap._fallback_format("tool", None, False, True) == "evergreen"     # off: unchanged


# ================================================================ D12: the topic queue
def _r2_item(n, url=None):
    return {"parent": f"PARENT{n}", "family": f"fam{n}", "title": f"acme/tool{n}",
            "url": url or f"https://github.com/acme/tool{n}", "question": f"What does tool {n} need?"}


def test_r2_queue_serves_in_order_and_skips_published_sources(monkeypatch):
    _r2_queue(monkeypatch, [_r2_item(1), _r2_item(2), {"url": "ftp://x"}, "junk", _r2_item(3)])
    rows = [{"status": "PUBLISHED", "source_url": "https://github.com/acme/tool1/"},
            {"status": "FACTCHECK_BLOCKED", "source_url": "https://github.com/acme/tool2"}]
    items = ap.cohort_queue_items(rows)
    assert [i["url"] for i in items] == ["https://github.com/acme/tool2", "https://github.com/acme/tool3"]
    it = items[0]
    assert it["kind"] == "tool" and it["followup_question"] == "What does tool 2 need?"
    assert it["followup_parent"] == "PARENT2" and it["followup_family"] == "fam2"
    assert ap.memory.followup_of(it)["question"] == "What does tool 2 need?"
    assert "What does tool 2 need?" in ap.memory.followup_prompt(it)


def test_r2_queue_never_raises(monkeypatch):
    _r2_queue(monkeypatch, "not a list")
    assert ap.cohort_queue_items([]) == []
    _r2_queue(monkeypatch, [_r2_item(1)])
    monkeypatch.setattr(ap.learn, "read_runs", lambda p=None: 1 / 0)
    assert ap.cohort_queue_items() == []


def _r2_tool_lane(monkeypatch, queue, ranked, script=None):
    tried = []
    monkeypatch.setattr(ap, "cohort_queue_items", lambda rows=None: queue)
    monkeypatch.setattr(ap.memory, "followup_items", lambda *a, **k: [])
    monkeypatch.setattr(ap, "too_many_failures", lambda t: False)
    monkeypatch.setattr(ap, "_trials_recap_blocked", lambda c: False)
    monkeypatch.setattr(ap, "mark_failed", lambda t: None)
    monkeypatch.setattr(ap.evidence, "probe", lambda c, readme=None: {"source": "none"})
    monkeypatch.setattr(ap, "pick_evergreen_topic", lambda r: (_ for _ in ()).throw(AssertionError("filler")))
    monkeypatch.setattr(ap, "script_news", lambda *a, **k: (_ for _ in ()).throw(AssertionError("filler")))
    monkeypatch.setattr(ap, "script_tool", lambda c: tried.append(c) or (dict(script) if script else None))
    return tried


def test_r2_tool_lane_takes_the_queue_first_and_skips_no_probe(monkeypatch):
    _r2_on(monkeypatch)
    monkeypatch.setenv("EVIDENCE_ENGINE", "1")
    monkeypatch.setenv("EVIDENCE_REQUIRED", "1")
    item = {"title": "acme/queued", "url": "https://github.com/acme/queued", "kind": "tool",
            "followup_question": "Does it run on Windows?", "followup_parent": "P", "followup_family": "f"}
    tried = _r2_tool_lane(monkeypatch, [item],
                          [{"title": "acme/trending", "kind": "tool", "url": "https://github.com/acme/trending"}],
                          script={"title": "T", "scenes": []})
    s = ap.build_script("tool", [{"title": "acme/trending", "kind": "tool",
                                  "url": "https://github.com/acme/trending"}])
    assert [c["url"] for c in tried] == ["https://github.com/acme/queued"]   # probe "none" did NOT skip it
    assert s["followup"] == {"parent": "P", "family": "f", "question": "Does it run on Windows?"}


def test_r2_no_qualified_candidate_publishes_nothing_never_filler(monkeypatch, capsys):
    _r2_on(monkeypatch)
    tried = _r2_tool_lane(monkeypatch, [], [{"title": "acme/a", "kind": "tool", "url": _R2_GH}])
    assert ap.build_script("tool", [{"title": "acme/a", "kind": "tool", "url": _R2_GH}]) is None
    assert len(tried) == 1 and "publishing nothing (cohort D7)" in capsys.readouterr().out


# ================================================================ D4: the documentation route
def test_r2_labels_are_the_owner_wording_only_in_the_cohort(monkeypatch):
    _r2_on(monkeypatch, False)
    assert ev.label("hosted") == "Hosted test" and ev.label("author") == "Author demo"
    _r2_on(monkeypatch)
    ch = ap.fv.CHANNEL_NAME
    assert ev.label("hosted") == f"Tested by {ch} — hosted demo"
    assert ev.label("author") == f"Author's demo — not tested by {ch}"
    assert ev.label("docs") == f"From the docs — not tested by {ch}" == ev.LABELS["docs"]


def test_r2_docs_record_is_labelled_not_admissible_and_on_the_ledger():
    d = ev.docs_record(ev.empty("no hosted demo"))
    assert d["source"] == "docs" and d["status"] == "NOT_RUN" and d["note"] == "no hosted demo"
    assert d["label"] == ev.LABELS["docs"] and not ev.admissible(d)
    assert ev.writer_brief(d) == ""                   # the docs brief is separate
    assert ev.ledger_fields({"evidence": d}) == ("docs", "NOT_RUN")
    assert ev.screen_label(d) == ev.LABELS["docs"] and ev.screen_label(ev.empty()) == ""
    line = ev.attribution_line(d)
    assert line.startswith(ev.DOCS_MARK) and ev.LABELS["docs"] in line
    brief = ev.docs_brief()
    assert ev.LABELS["docs"] in brief and "we tested" in brief and "NOT run" in brief


def test_r2_docs_overclaims_catch_testing_and_your_machine():
    script = {"evidence": ev.docs_record(), "scenes": [
        {"narration": "We tested it on a laptop."}, {"narration": "It works on your machine today."},
        {"narration": "The README says it supports Linux."}]}
    hits = [h.lower() for h in ev.overclaims(script)]
    assert "we tested" in hits and "works on your machine" in hits and len(hits) == 2


def _r2_scenes(n=6):
    return [{"scene_num": i + 1, "narration": f"the tool sorts a folder of files by type part {i}",
             "visual_query": "laptop"} for i in range(n)]


def _r2_script_tool(monkeypatch, gathered, item=None):
    readme = ("The tool sorts files for you. " * 60) + "\n```bash\npip install demo-tool\n```\n"
    prompts = []
    monkeypatch.setattr(ap, "fetch_text", lambda u, limit=4000: readme[:limit])
    monkeypatch.setattr(ap, "_verified_facts", lambda u: {})
    monkeypatch.setattr(ap, "_top_issues", lambda u: [])
    monkeypatch.setattr(ap.evidence, "gather", lambda it, **k: gathered)
    ans = {"title": "Demo Tool", "scenes": _r2_scenes(),
           "deliverable": {"kind": "command", "text": "pip install demo-tool", "url": _R2_GH},
           "evidence": {"source": "hosted", "status": "PASSED_FIXED_TEST"}}     # planted: must not survive
    monkeypatch.setattr(ap.llm, "generate_json",
                        lambda p, **k: prompts.append(p) or json.loads(json.dumps(ans)))
    s = ap.script_tool(item or {"title": "acme/demo-tool", "source": "github/trending", "url": _R2_GH})
    return s, prompts


def test_r2_no_evidence_takes_the_docs_route_instead_of_a_skip(monkeypatch):
    _r2_on(monkeypatch)
    monkeypatch.setenv("EVIDENCE_ENGINE", "1")
    monkeypatch.setenv("EVIDENCE_REQUIRED", "1")
    item = {"title": "acme/demo-tool", "source": "queue", "url": _R2_GH, "kind": "tool",
            "followup_question": "Does demo-tool run on Windows?"}
    s, prompts = _r2_script_tool(monkeypatch, ev.empty("no hosted demo"), item)
    assert s and s["evidence"]["source"] == "docs"                    # not the planted hosted one
    p = prompts[0]
    assert "Before You Install" in p and ev.LABELS["docs"] in p and "Does demo-tool run on Windows?" in p
    assert "COHORT title formula" in p and "direct ANSWER" in p
    assert "Scene 1 HOOK" not in p and "179K STARS" not in p


def test_r2_could_not_look_also_takes_the_docs_route(monkeypatch):
    _r2_on(monkeypatch)
    monkeypatch.setenv("EVIDENCE_ENGINE", "1")
    s, _ = _r2_script_tool(monkeypatch, None)
    assert s and s["evidence"]["source"] == "docs"
    monkeypatch.setenv("EVIDENCE_ENGINE", "0")                          # engine off, cohort on
    s, _ = _r2_script_tool(monkeypatch, None)
    assert s and s["evidence"]["source"] == "docs"


def test_r2_cohort_off_keeps_the_row_17_skip(monkeypatch):
    _r2_on(monkeypatch, False)
    monkeypatch.setenv("EVIDENCE_ENGINE", "1")
    monkeypatch.setenv("EVIDENCE_REQUIRED", "1")
    s, prompts = _r2_script_tool(monkeypatch, ev.empty("none"))
    assert s is None and prompts == []


def test_r2_label_chip_rides_from_zero_until_scene_two(monkeypatch):
    _r2_on(monkeypatch)
    script = {"evidence": ev.docs_record()}
    assert ap.cohort_label_chip(script, [0.0, 5.2, 11.0]) == [(0.0, 5.2, ev.LABELS["docs"])]
    assert ap.cohort_label_chip(script, [0.0, 12.0]) == [(0.0, 7.0, ev.LABELS["docs"])]
    assert ap.cohort_label_chip(script, None) == [(0.0, 7.0, ev.LABELS["docs"])]
    assert ap.cohort_label_chip({"evidence": ev.empty()}, [0.0, 5.0]) == []
    assert ap.cohort_label_chip("junk", [0.0]) == []
    _r2_on(monkeypatch, False)
    assert ap.cohort_label_chip(script, [0.0, 5.2]) == []


def test_r2_output_contract_swaps_title_and_thumb_rules_only_in_the_cohort():
    off = ap._output_contract("10-14", "50-70", tool=True)
    on = ap._output_contract("10-14", "50-70", tool=True, cohort=True)
    assert "179K STARS" in off and "COHORT title formula" not in off
    assert "COHORT title formula" in on and "direct ANSWER" in on and "179K STARS" not in on


# ================================================================ D5 + D2: render path and Shorts
def test_r2_make_extras_makes_no_crop_shorts_in_the_cohort(monkeypatch):
    _r2_on(monkeypatch)
    monkeypatch.setattr(ap.thumbnail, "make", lambda *a, **k: "t.jpg")
    monkeypatch.setattr(ap.shorts_mod, "make_shorts", lambda *a, **k: 1 / 0)
    assert ap._make_extras("v.mp4", {"title": "T"}, [], [0.0], "", "") == ("t.jpg", [])


def _r2_run(monkeypatch, tmp_path, script, native, flags=None):
    """run(publish=True) with every render/network seam stubbed (the S.1 harness,
    plus the cohort's own seams). Returns (rows, uploads[(path, publish_at, title, thumb)])."""
    rows, uploads = [], []
    flags = {"native_shorts": True, "pilot_b": True, "auto_upload_youtube": True,
             "recovery_cohort": True, **(flags or {})}
    real_flag = ap.fv.flag
    monkeypatch.setattr(ap.fv, "flag", lambda n, default=False: flags[n] if n in flags else real_flag(n, default))
    monkeypatch.setattr(ap.fv, "TEMP", tmp_path)
    monkeypatch.setattr(ap.pilot_b, "STATE_FILE", tmp_path / "pilot_b.json")
    monkeypatch.setattr(ap, "cohort_day", lambda d: "long")
    monkeypatch.setattr(ap, "already_published_today", lambda: False)
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: None)
    monkeypatch.setattr(ap.signal_engine, "rank", lambda limit=20: [])
    monkeypatch.setattr(ap, "build_script", lambda f, r, v: script)
    monkeypatch.setattr(ap, "too_many_failures", lambda t: False)
    monkeypatch.setattr(ap.gates, "fact_check", lambda *a, **k: {"passed": True})
    monkeypatch.setattr(ap.gates, "confidence", lambda d: {"score": 0.9, "routing": "auto"})
    monkeypatch.setattr(ap.eng, "step3_download", lambda s: [[] for _ in s["scenes"]])
    monkeypatch.setattr(ap.screencap, "capture", lambda s: None)
    monkeypatch.setattr(ap.screencap, "inject_code_card", lambda *a, **k: None)
    monkeypatch.setattr(ap.receipts, "inject_receipt_clip", lambda *a, **k: None)
    monkeypatch.setattr(ap, "synthesize_voice", lambda n, s: ("a.mp3", [(0.0, 0.5, "w")]))
    monkeypatch.setattr(ap.captions, "transcribe_words", lambda a: [(0.0, 0.5, "w")])
    monkeypatch.setattr(ap.captions, "correct_words", lambda w, n: w)
    monkeypatch.setattr(ap.eng, "dur", lambda p: 300.0)
    monkeypatch.setattr(ap, "scene_durations", lambda s, w, d: None)
    monkeypatch.setattr(ap.infographics, "inject_cards", lambda *a, **k: (_ for _ in ()).throw(AssertionError("card")))
    built = tmp_path / "v.mp4"
    built.write_bytes(b"\0" * 64)
    monkeypatch.setattr(ap.eng, "step5_build", lambda *a, **k: str(built))
    monkeypatch.setattr(ap.thumbnail, "make", lambda *a, **k: "t.jpg")
    monkeypatch.setattr(ap.shorts_mod, "make_shorts", lambda *a, **k: (_ for _ in ()).throw(AssertionError("crop")))
    monkeypatch.setattr(ap.native_short, "make", native)
    monkeypatch.setattr(ap.scheduling, "long_slot", lambda: "2026-11-16T16:45:00Z")
    monkeypatch.setattr(ap.captions, "build_ass", lambda *a, **k: "c.ass")
    burned = []
    monkeypatch.setattr(ap.captions, "burn_ass", lambda v, a, **k: burned.append(k.get("citations")) or v)
    monkeypatch.setattr(ap.branding, "add_intro_outro", lambda v, **k: (_ for _ in ()).throw(AssertionError("sting")))
    monkeypatch.setattr(ap.l2, "inject", lambda v, at, **k: (v, {"cold_open": k.get("cold_open")}))
    monkeypatch.setattr(ap, "qa_video", lambda v, d: True)
    monkeypatch.setattr(ap.eng, "step8_meta", lambda s, n: [{"title": f"Meta {i} #Shorts"} for i in range(n)])
    monkeypatch.setattr(ap, "_last_published_url", lambda: "")

    def fake_upload(path, title, desc, tags, thumb=None, is_short=False, publish_at=None):
        uploads.append((path, publish_at, title, thumb))
        return ("https://youtube.com/shorts/SHORT000001" if is_short
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
    return rows, uploads, burned


def _r2_native_ok(script, hook="", excerpt=""):
    return {"path": "out/short_nv_x.mp4", "match": "same_question", "attempts": 2,
            "measured": {"duration": 24.0, "source": "asr", "first_speech": 0.2, "script_words": 50,
                         "sentence_ends": [3.0, 6.0, 12.0, 18.0, 21.0]},
            "min_px": 60, "warnings": [],
            "spec": {"headline": "Linux only", "title": "Does it run on Windows? #Shorts", "question": "q"}}


def _r2_script(fmt="evergreen"):
    return {"title": "acme/demo-tool: Does it run on Windows?", "description": "How it works.",
            "tags": ["ai"], "format": fmt, "grounding": "",
            "scenes": [{"scene_num": i, "narration": "a calm explainer " * 10, "visual_query": "x"}
                       for i in range(1, 9)]}


def test_r2_run_publishes_one_native_short_the_next_day_and_no_sting(monkeypatch, tmp_path):
    rows, uploads, _ = _r2_run(monkeypatch, tmp_path, _r2_script(), _r2_native_ok)
    row = rows[-1]
    assert row["status"] == "PUBLISHED"
    longs = [u for u in uploads if "short" not in u[0]]
    shorts = [u for u in uploads if "short" in u[0]]
    assert len(longs) == 1 and longs[0][1] == "2026-11-16T16:45:00Z"
    assert len(shorts) == 1 and "_nv_" in shorts[0][0]                    # D2: native only
    assert shorts[0][1] == "2026-11-17T18:45:00Z"                         # Tue 18:45 UTC
    assert row["shorts"][0]["slot"] == "18:45" and row["shorts"][0]["engine"] == "native"
    assert "experiment" not in row                                        # Pilot B superseded


def test_r2_a_skipped_native_means_no_short_that_day(monkeypatch, tmp_path):
    def skipped(script, hook="", excerpt=""):
        ns.last_skip = "a diagram label is false"
        return None
    rows, uploads, _ = _r2_run(monkeypatch, tmp_path, _r2_script(), skipped)
    assert rows[-1]["status"] == "PUBLISHED" and [u for u in uploads if "short" in u[0]] == []


def test_r2_tool_video_gets_a_thumbnail_and_its_native_short(monkeypatch, tmp_path):
    """The latent P.1 hole: a non-pilot tool video with evidence_engine on took the
    clean-copy branch and was uploaded with no thumbnail and no Shorts."""
    script = dict(_r2_script("tool"), evidence=ev.docs_record())
    rows, uploads, burned = _r2_run(monkeypatch, tmp_path, script, _r2_native_ok,
                                    flags={"evidence_engine": True, "evidence_required": True,
                                           "receipts_check": False})
    longs = [u for u in uploads if "short" not in u[0]]
    assert rows[-1]["status"] == "PUBLISHED"
    assert longs[0][3] == "t.jpg"                                         # a real thumbnail
    assert len([u for u in uploads if "_nv_" in u[0]]) == 1
    assert rows[-1]["evidence_source"] == "docs"
    assert burned and (0.0, 7.0, ev.LABELS["docs"]) in burned[0]          # D4/D5 chip from 0:00


# ================================================================ D8: the native Short validator
def _r2_native_answer(**over):
    a = {"question": "Why does AI run on GPUs?", "headline": "GPUs vs CPUs for AI",
         "sentences": ["AI runs on GPUs because they do thousands of small sums at once.",
                       "A CPU has a few strong cores that work one task after another.",
                       "A GPU has thousands of simple cores working at the same time.",
                       "But for branching everyday code, the CPU is still faster.",
                       "So parallel math goes to the GPU, and decisions stay on the CPU."],
         "answer": 1, "qualification": 4,
         "diagram": {"template": "compare", "slots": {
             "left": [{"text": "CPU cores", "cue": "CPU has"}, {"text": "few strong cores", "cue": "strong cores"}],
             "right": [{"text": "GPU cores", "cue": "GPU has"}, {"text": "thousands of cores", "cue": "simple cores"}]}},
         "title": "Why AI runs on GPUs"}
    a.update(over)
    return a


_R2_SRC = "A CPU has a few powerful cores. A GPU has thousands of simpler cores."


def test_r2_label_vocabulary_is_a_warning_on_the_lenient_attempt():
    raw = _r2_native_answer(diagram={"template": "steps", "slots": {"steps": [
        {"text": "banana pudding", "cue": ""}, {"text": "GPU cores", "cue": ""}, {"text": "CPU cores", "cue": ""}]}})
    spec, f = ns.validate(raw, _R2_SRC)
    assert spec is None and any("shares no spoken word" in x for x in f)  # strict: unchanged
    spec, f = ns.validate(raw, _R2_SRC, strict=False)
    assert spec and f == [] and any("shares no spoken word" in w for w in spec["warnings"])


@pytest.mark.parametrize("over, needle", [
    ({"sentences": ["AI runs on GPUs because they do 4096 sums at once.",
                    "A CPU has a few strong cores that work one task after another."]},
     "numbers not in the source"),
    ({"diagram": {"template": "bars", "slots": {}}}, "diagram must be"),
    ({"headline": ""}, "headline must be"),
    ({"sentences": []}, "no sentences"),
])
def test_r2_truth_and_render_failures_still_block_when_lenient(over, needle):
    spec, f = ns.validate(_r2_native_answer(**over), _R2_SRC, strict=False)
    assert spec is None and any(needle in x for x in f), f


@pytest.mark.parametrize("msg, style", [
    ("headline must be 1-8 words (got 9)", True), ("headline must be 1-8 words (got 0)", False),
    ("headline has hype words: ['insane']", True), ("sentence 1 has 15 words (max 14)", True),
    ("70 spoken words (max 65); drop a sentence, never cut one", True),
    ("a diagram label shares no spoken word, or shows a number that is not spoken", True),
    ("speech starts at 0.40s (by 0.3s)", True), ("duration 29.10s (must be 20-28s)", True),
    ("at 0.0s only 5/7 text elements are fully drawn", True),
    ("numbers not in the source facts: ['4096']", False), ("render failed", False),
    ("text does not fit at 60px: shorten the headline or labels", False),
    ("smallest on-screen text is 48px (min 60)", False),
    ("no word timings could be measured from the encoded file", False), ("voice synthesis failed", False),
])
def test_r2_style_failure_classification(msg, style):
    assert ns.is_style_failure(msg) is style


def test_r2_make_ships_style_failures_only_on_the_repair_attempt(monkeypatch):
    _r2_on(monkeypatch)
    raw = _r2_native_answer(diagram={"template": "steps", "slots": {"steps": [
        {"text": "banana pudding", "cue": ""}, {"text": "GPU cores", "cue": ""}, {"text": "CPU cores", "cue": ""}]}})
    calls, strict_seen = [], []
    monkeypatch.setattr(ns.llm, "generate_json", lambda *a, **k: calls.append(1) or dict(raw))
    monkeypatch.setattr(ns, "source_text", lambda s: _R2_SRC)

    def fake_build(spec, tag="", strict=True):
        strict_seen.append(strict)
        return {"path": "nv.mp4", "measured": {"duration": 24.0, "first_speech": 0.2, "script_words": 50,
                                               "source": "asr"}, "warnings": []}, []
    monkeypatch.setattr(ns, "build", fake_build)
    res = ns.make({"title": "T"})
    assert res and res["attempts"] == 2 and len(calls) == 2 and strict_seen == [False]
    assert any("shares no spoken word" in w for w in res["warnings"]) and ns.last_warnings == res["warnings"]
    _r2_on(monkeypatch, False)
    calls.clear()
    assert ns.make({"title": "T"}) is None and "shares no spoken word" in ns.last_skip   # off: unchanged


# ================================================================ visible defects
def test_r2_markdown_emphasis_never_reaches_a_title_hook_or_label():
    s = ap._validate_script({"title": "What the robot *can't* do", "titles": ["*A* `B`"],
                             "thumb_text": "*LINUX ONLY*", "scenes": _r2_scenes()}, "T")
    assert s["title"] == "What the robot can't do" and s["thumb_text"] == "LINUX ONLY"
    assert all("*" not in t and "`" not in t for t in s["titles"])
    m = sh.normalize_moments([{"scene_num": 2, "hook_text": "What the robot *can't* do yet"}], 8)
    assert m[0]["hook_text"] == "What the robot can't do yet"
    assert ns._clean("**Linux** only") == "Linux only"
