"""v3-K.1: task catalogue, task-follow alerts, useful tool pages, X off by default.

Spec: docs/spec/ai-pulse-v3k1.md. No network, no ffmpeg, no LLM: every seam the
module would call is stubbed as the consumer sees it.
"""
import datetime as _dt
import json
from pathlib import Path

import pytest

from factverse import notify, site, state_merge as sm, tasks

ROOT = Path(__file__).resolve().parents[1]
TODAY = _dt.date.today()
INP = "fixture-01.wav: 12 s of English speech"


def _k1_settings(**over):
    return lambda name, default=None: over.get(name, default)


def _k1_day(offset: int) -> str:
    return (TODAY + _dt.timedelta(days=offset)).isoformat()


def _k1_ev(source="hosted", status="PASSED_FIXED_TEST", day=0, url="https://hf.co/spaces/a/b",
           inp=INP, **over):
    ev = {"source": source, "status": status, "label": "", "wording": "",
          "clip": "/home/runner/clip.mp4", "clip_seconds": 12.5, "url": url,
          "captured_at": _k1_day(day), "input": inp, "observed": "Returned the sentence.",
          "supported_claims": [], "rights": None}
    ev.update(over)
    return ev


def _k1_row(name="a/asr", day=0, ev=None, title="Transcribe audio with ASR", page=None, **over):
    e = {"page": page or f"{_k1_day(day)}-{name.replace('/', '-')}.html",
         "pdf": "", "title": title, "date": _k1_day(day),
         "tool": f"{name} — trending Space on Hugging Face",
         "what": "A speech recognition demo.", "video_url": "https://youtube.com/watch?v=ABCDEFGHIJK",
         "video_id": "ABCDEFGHIJK", "evidence": ev}
    e.update(over)
    return e


def _k1_pair(day=0, a="PASSED_FIXED_TEST", b="FAILED_FIXED_TEST"):
    return [_k1_row("a/asr", day, _k1_ev(status=a, day=day, url="https://hf.co/spaces/a/asr")),
            _k1_row("b/asr", day, _k1_ev(status=b, day=day, url="https://hf.co/spaces/b/asr"))]


@pytest.fixture(autouse=True)
def _k1_config(monkeypatch):
    monkeypatch.setattr(site.fv, "setting", _k1_settings())
    for name in ("TASK_HUBS", "TASK_ALERTS", "TASK_FOLLOW_CHANNEL", "TWITTER"):
        monkeypatch.delenv(name, raising=False)


# ------------------------------------------------------------------ family
def test_task_family_is_one_fixed_family_or_nothing():
    f = tasks.task_family
    assert f({"title": "Run Nemotron-3.5-Transcribe: 40 Languages Offline",
              "tool": "nvidia/X — trending automatic speech recognition on Hugging Face"}) \
        == "speech-to-text"
    assert f({"title": "Kokoro TTS in 5 minutes"}) == "text-to-speech"
    assert f({"title": "Remove Background From Photos"}) == "background-removal"
    assert f({"title": "Read screenshots with OCR"}) == "ocr"
    assert f({"title": "Upscale old photos 4x"}) == "image-upscaling"
    assert f({"title": "Extract tables from PDF files", "what": "table extraction"}) == "pdf-tables"
    # ambiguous -> nothing: an ambiguous tool must never join a comparison
    assert f({"title": "Speech-to-text and text-to-speech in one toolkit"}) == ""
    # a word inside another word is not a match ("asr" in "kasra", "tts" in "watts")
    assert f({"title": "Kasra measures watts"}) == ""
    # only short surfaces: the uses / README never decide the family
    assert f({"title": "A coding agent", "uses": ["transcribe meetings"]}) == ""
    assert f(None) == "" and f({"title": 42}) == ""
    # stored value wins only when it is one of ours
    assert tasks.family_of({"task_family": "ocr", "title": "x"}) == "ocr"
    assert tasks.family_of({"task_family": "../evil", "title": "OCR demo"}) == "ocr"


# ------------------------------------------------------------------ evidence
def test_clean_evidence_drops_clip_recomputes_wording_and_guards_the_url():
    ev = tasks.clean_evidence(_k1_ev(label="Best tool ever", wording="It is the best.",
                                     url="javascript:alert(document.domain)"))
    assert "clip" not in ev
    assert ev["label"] == "Hosted test" and ev["wording"] == "Passed this specific test."
    assert ev["url"] == ""
    # an author demo can never carry a test result
    au = tasks.clean_evidence(_k1_ev(source="author", status="PASSED_FIXED_TEST"))
    assert au["status"] == "NOT_RUN" and au["wording"] == "Not independently tested."
    assert au["label"] == "Author demo"
    # garbage in, safe values out
    junk = tasks.clean_evidence({"source": "magic", "status": 7, "clip_seconds": float("inf"),
                                 "captured_at": "2026-13-45", "supported_claims": "one claim",
                                 "rights": {"license": "MIT", "modified": True}})
    assert junk["source"] == "none" and junk["status"] == "NOT_RUN"
    assert junk["clip_seconds"] == 0.0 and junk["captured_at"] == ""
    assert junk["supported_claims"] == ["one claim"]
    assert junk["rights"]["license"] == "MIT" and junk["rights"]["modified"] == "yes"
    assert tasks.clean_evidence(None) is None and tasks.clean_evidence("x") is None


def test_entry_for_stores_evidence_family_and_steps():
    s = {"title": "Transcribe audio on CPU", "cheat_sheet": "2026-11-04-t.pdf",
         "signal_title": "a/asr — trending", "deliverable": {"text": "pip install a"},
         "evidence": _k1_ev()}
    e = site.entry_for(s, {"what": "A speech recognition demo.", "steps": "one\ntwo"}, "")
    assert e["task_family"] == "speech-to-text"
    assert e["steps"] == ["one", "two"]
    assert e["evidence"]["status"] == "PASSED_FIXED_TEST" and "clip" not in e["evidence"]
    assert json.loads(json.dumps(e)) == e                      # catalog-serialisable
    assert site.entry_for({"title": "T"}, {}, "")["evidence"] is None


# ------------------------------------------------------------------ hub rules
def test_no_hub_without_two_comparable_hosted_tests():
    hub = lambda rows: tasks.hub(rows, "speech-to-text", TODAY)
    assert hub([]) is None
    # author demos only: never a hub
    assert hub([_k1_row("a/x", 0, _k1_ev(source="author", url="https://a")),
                _k1_row("b/x", 0, _k1_ev(source="author", url="https://b"))]) is None
    # one hosted tool, tested twice: still one tool
    assert hub([_k1_row("a/x", -1, _k1_ev(day=-1)), _k1_row("a/x", 0, _k1_ev(day=0))]) is None
    # two hosted tools on DIFFERENT inputs: not comparable
    assert hub([_k1_row("a/x", 0, _k1_ev(url="https://a", inp="one.wav")),
                _k1_row("b/x", 0, _k1_ev(url="https://b", inp="two.wav"))]) is None
    # NOT_RUN / INCONCLUSIVE hosted runs are not results
    assert hub([_k1_row("a/x", 0, _k1_ev(url="https://a")),
                _k1_row("b/x", 0, _k1_ev(url="https://b", status="INCONCLUSIVE"))]) is None
    h = hub(_k1_pair())
    assert h and h["state"] == "current" and len(h["tested"]) == 2
    assert h["passed"] == ["a/asr"]
    assert "Among the 2 options we tested on this input" in h["answer"]
    assert "best" not in h["answer"].lower()


def test_author_demo_is_a_candidate_profile_never_a_tested_position():
    rows = _k1_pair() + [_k1_row("c/asr", 0, _k1_ev(source="author", url="https://c"))]
    h = tasks.hub(rows, "speech-to-text", TODAY)
    assert [r["name"] for r in h["tested"]] == ["a/asr", "b/asr"]
    assert [r["name"] for r in h["candidates"]] == ["c/asr"]


def test_hub_states_are_explicit():
    h = lambda rows, today=TODAY, w=(): tasks.hub(rows, "speech-to-text", today, w)
    assert h(_k1_pair())["state"] == "current"
    assert h(_k1_pair(a="FAILED_FIXED_TEST", b="TIMED_OUT"))["state"] == "inconclusive"
    assert h(_k1_pair(), TODAY + _dt.timedelta(days=31))["state"] == "outdated"
    assert h(_k1_pair(), TODAY + _dt.timedelta(days=30))["state"] == "current"
    assert h(_k1_pair(), w=("speech-to-text",))["state"] == "withdrawn"


def test_history_separates_checked_again_from_recommendation_changed():
    rows = (_k1_pair(-3)
            + [_k1_row("b/asr", -2, _k1_ev(status="FAILED_FIXED_TEST", day=-2,
                                            url="https://hf.co/spaces/b/asr"))]
            + [_k1_row("b/asr", -1, _k1_ev(status="PASSED_FIXED_TEST", day=-1,
                                            url="https://hf.co/spaces/b/asr"))]
            + [_k1_row("a/asr", 0, _k1_ev(status="FAILED_FIXED_TEST", day=0,
                                           url="https://hf.co/spaces/a/asr"))])
    hist = tasks.hub(rows, "speech-to-text", TODAY)["history"]
    assert [e["kind"] for e in hist] == ["first_answer", "checked_again", "now_passes",
                                         "recommendation_changed"]
    assert hist[2]["flipped"] == ["b/asr"] and hist[2]["previous"] == ["a/asr"]
    assert hist[3]["answer"] == ["b/asr"]


def test_hubs_are_capped_and_switchable(monkeypatch):
    ocr = [_k1_row("o/1", 0, _k1_ev(url="https://o1", inp="p.png"), title="OCR demo one", what="An OCR demo."),
           _k1_row("o/2", 0, _k1_ev(url="https://o2", inp="p.png"), title="OCR demo two", what="An OCR demo."),
           _k1_row("o/3", 0, _k1_ev(url="https://o3", inp="p.png"), title="OCR demo three", what="An OCR demo.")]
    rows = _k1_pair() + ocr
    assert [h["family"] for h in tasks.hubs(rows, TODAY)] == ["ocr"]     # cap 1: most tools
    assert len(tasks.hubs(rows, TODAY, cap=2)) == 2
    # a withdrawn hub keeps its URL and never counts against the cap
    got = tasks.hubs(rows, TODAY, cap=1, withdrawn=["ocr"])
    assert sorted((h["family"], h["state"]) for h in got) == \
        [("ocr", "withdrawn"), ("speech-to-text", "current")]
    monkeypatch.setattr(site.fv, "setting", _k1_settings(task_hubs=False))
    assert tasks.hubs(rows, TODAY) == []
    monkeypatch.setattr(site.fv, "setting", _k1_settings(task_hubs_max="junk"))
    assert len(tasks.hubs(rows, TODAY)) == 1
    assert tasks.hubs(None, TODAY) == [] and tasks.hubs([42, "x", None], TODAY) == []


# ------------------------------------------------------------------ render
def test_render_hub_escapes_and_neutralises_hostile_values(monkeypatch):
    rows = _k1_pair()
    rows[0]["tool"] = "<script>alert(1)</script> — x"
    rows[0]["video_url"] = "javascript:alert(2)"
    rows.append(_k1_row("c/asr", 0, _k1_ev(source="author", url="javascript:alert(3)",
                                            rights={"license": "MIT", "path": "demo.gif"})))
    html = site.render_hub(tasks.hub(rows, "speech-to-text", TODAY), TODAY)
    assert "<script>alert(1)" not in html and "&lt;script&gt;" in html
    assert "javascript" not in html.lower()
    assert "Candidate profiles" in html and "Licence: MIT" in html
    assert "Not independently tested." in html
    assert site.render_hub(None).startswith("<!doctype html>")


def test_follow_offer_only_when_configured(monkeypatch):
    h = tasks.hub(_k1_pair(), "speech-to-text", TODAY)
    assert "Follow changes to this task" not in site.render_hub(h, TODAY)
    monkeypatch.setattr(site.fv, "setting", _k1_settings(task_follow_channel="@tooldojo_tasks"))
    html = site.render_hub(h, TODAY)
    assert 'href="https://t.me/tooldojo_tasks"' in html and "#speech_to_text" in html
    monkeypatch.setattr(site.fv, "setting", _k1_settings(task_follow_channel="x\" onmouseover=1"))
    assert "Follow changes" not in site.render_hub(h, TODAY)          # invalid name: hidden
    monkeypatch.setattr(site.fv, "setting", _k1_settings(task_follow_channel="tooldojo",
                                                         task_alerts=False))
    assert "Follow changes" not in site.render_hub(h, TODAY)          # alerts off: hidden
    monkeypatch.setattr(site.fv, "setting", _k1_settings(task_follow_channel="tooldojo"))
    w = tasks.hub(_k1_pair(), "speech-to-text", TODAY, ("speech-to-text",))
    assert "Follow changes" not in site.render_hub(w, TODAY)          # withdrawn: hidden


def test_tool_page_is_useful_and_honest():
    plain = site.render_page({"page": "p.html", "title": "T", "skip_if": "No GPU."})
    assert "Not independently tested." in plain and "Limitations" in plain
    assert "Everything on this page comes from its own documentation." in plain
    assert plain.count("No GPU.") == 1
    au = site.render_page(_k1_row("c/asr", 0, _k1_ev(
        source="author", url="javascript:alert(1)",
        rights={"path": "demo.gif", "commit": "abcdef1234567890", "license": "Apache-2.0",
                "copyright": "(c) Someone", "notice": "NOTICE text", "modified": False}),
        source_url="javascript:alert(2)"))
    assert "javascript" not in au.lower()
    assert "commit abcdef123456 · Licence: Apache-2.0 · (c) Someone · Notice: NOTICE text" in au
    old = site.render_page(_k1_row("o/1", -40, _k1_ev(day=-40)), today=TODAY)
    assert "Outdated:" in old
    linked = site.render_page(_k1_row(), hub="speech-to-text.html")
    assert 'href="../tasks/speech-to-text.html"' in linked
    # the video is above the decision, the decision above the command
    full = site.render_page(dict(_k1_row(), command="pip install a"))
    assert full.index("<iframe") < full.index('class="decision"') < full.index('id="cmd"')


def test_rebuild_writes_the_hub_and_lists_it(monkeypatch, tmp_path):
    monkeypatch.setattr(site, "DOCS", tmp_path)
    monkeypatch.setattr(site, "TOOLS_DIR", tmp_path / "tools")
    rows = _k1_pair()
    assert site.rebuild(rows) == 5                 # 2 pages + 1 hub + index + sitemap
    assert (tmp_path / "tasks" / "speech-to-text.html").exists()
    assert 'href="tasks/speech-to-text.html"' in (tmp_path / "index.html").read_text("utf-8")
    assert "/tasks/speech-to-text.html</loc>" in (tmp_path / "sitemap.xml").read_text("utf-8")
    page = (tmp_path / "tools" / rows[0]["page"]).read_text("utf-8")
    assert "../tasks/speech-to-text.html" in page
    assert site.rebuild(rows) == 0                 # deterministic: nothing changed


def test_one_bad_hub_never_freezes_the_site(monkeypatch, tmp_path):
    boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    monkeypatch.setattr(site, "DOCS", tmp_path)
    monkeypatch.setattr(site, "TOOLS_DIR", tmp_path / "tools")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(site, "render_hub", boom)
        assert site.rebuild(_k1_pair()) == 4       # 2 pages + index + sitemap
        assert "tasks/" not in (tmp_path / "index.html").read_text("utf-8")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(site.tasks, "hubs", boom)
        assert site.rebuild(_k1_pair()) >= 0       # no hubs, but the site still builds


def test_search_console_token_lands_on_the_index_only(monkeypatch):
    monkeypatch.setattr(site.fv, "setting", _k1_settings(google_site_verification="abcDEF123_-xyz"))
    assert 'name="google-site-verification" content="abcDEF123_-xyz"' in site.render_index([])
    assert "google-site-verification" not in site.render_page(_k1_row())
    monkeypatch.setattr(site.fv, "setting", _k1_settings(google_site_verification='x"><script>'))
    assert "google-site-verification" not in site.render_index([])


# ------------------------------------------------------------------ alerts
def _k1_changed_rows():
    """Yesterday: a passed, b failed. Today: b passes -> a material change."""
    return (_k1_pair(-1) + [_k1_row("b/asr", 0, _k1_ev(status="PASSED_FIXED_TEST", day=0,
                                                         url="https://hf.co/spaces/b/asr"),
                                    video_url="https://youtube.com/watch?v=BBBBBBBBBBB")])


def test_only_a_material_change_is_an_alert():
    evs = tasks.alert_events(_k1_changed_rows(), TODAY)
    assert [e["kind"] for e in evs] == ["now_passes"]
    assert tasks.alert_events(_k1_changed_rows(), TODAY + _dt.timedelta(days=2)) == []
    # a re-test with the same answer, or a new tool that changes nothing, is silent
    same = _k1_pair(-1) + [_k1_row("a/asr", 0, _k1_ev(day=0, url="https://hf.co/spaces/a/asr"))]
    assert tasks.alert_events(same, TODAY) == []
    assert tasks.alert_events(_k1_pair(0), TODAY) == []          # first answer: not a change
    # the id is stable, so idempotence holds across runs
    assert tasks.alert_events(_k1_changed_rows(), TODAY)[0]["id"] == \
        tasks.alert_events(_k1_changed_rows(), TODAY)[0]["id"]


def test_task_alert_body_is_escaped_for_telegram_and_fits():
    ev = tasks.alert_events(_k1_changed_rows(), TODAY)[0]
    text = notify.format_task_alert(ev, "https://youtube.com/watch?v=BBBBBBBBBBB")
    assert text.startswith("🔁 <b>Task update: Speech to text</b> #speech_to_text")
    assert "Full comparison: https://" in text and "/tasks/speech-to-text.html" in text
    assert "b/asr failed our fixed test before and passes it now" in text
    assert "materially changes" in text
    ev["trigger"]["ev"]["observed"] = "It's <b>fine</b> & " + "x" * 9000
    t2 = notify.format_task_alert(ev)
    assert "&#x27;" not in t2 and "<b>fine</b>" not in t2
    assert len(t2) <= notify.MAX_TEXT
    big = dict(ev, hub=dict(ev["hub"], label="L" * 5000))
    assert len(notify.format_task_alert(big)) <= notify.MAX_TEXT
    assert notify.format_task_alert(dict(ev, kind="checked_again")) == ""
    assert notify.format_task_alert(None) == ""


def test_alert_links_the_video_only_once_it_is_public():
    now = _dt.datetime(2026, 11, 4, 16, 55)
    url = "https://youtube.com/watch?v=BBBBBBBBBBB"
    pub = {"status": "PUBLISHED", "youtube_url": url, "publish_at": "2026-11-04T16:45:00Z"}
    assert notify._public_video(url, [pub], now) == url
    assert notify._public_video(url, [dict(pub, publish_at="2026-11-04T17:45:00Z")], now) == ""
    assert notify._public_video(url, [], now) == ""
    assert notify._public_video("javascript:x", [dict(pub, youtube_url="javascript:x")], now) == ""


def _k1_alert_env(monkeypatch, tmp_path, **cfg):
    cat = tmp_path / "cat.json"
    cat.write_text(json.dumps(_k1_changed_rows()), encoding="utf-8")
    monkeypatch.setattr(notify.site, "CATALOG", cat)
    monkeypatch.setattr(notify, "NOTIFIED_TASKS", tmp_path / "nt.json")
    monkeypatch.setattr(notify, "RUNS_LOG", tmp_path / "runs.jsonl")
    monkeypatch.setattr(notify.fv, "setting",
                        _k1_settings(**dict({"task_follow_channel": "tooldojo_tasks"}, **cfg)))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:SECRET")


def test_task_alert_posts_once_to_the_public_channel(monkeypatch, tmp_path, capsys):
    _k1_alert_env(monkeypatch, tmp_path)
    sent = []
    monkeypatch.setattr(notify, "send",
                        lambda text, link="", token=None, chat=None: sent.append((chat, link)) or False)
    notify._post_task_alerts()
    assert sent == [("@tooldojo_tasks", site.hub_url("speech-to-text.html"))]
    assert not (tmp_path / "nt.json").exists()          # a failure records nothing
    monkeypatch.setattr(notify, "send",
                        lambda text, link="", token=None, chat=None: sent.append((chat, link)) or True)
    notify._post_task_alerts()
    assert len(notify.load_notified(tmp_path / "nt.json")) == 1
    notify._post_task_alerts()                           # already sent: silent
    assert len(sent) == 2 and "no material change" in capsys.readouterr().out


def test_task_alert_is_a_no_op_until_configured(monkeypatch, tmp_path, capsys):
    calls = []
    _k1_alert_env(monkeypatch, tmp_path, task_follow_channel="")
    monkeypatch.setattr(notify, "send", lambda *a, **k: calls.append(1) or True)
    notify._post_task_alerts()
    assert "no public channel configured" in capsys.readouterr().out
    _k1_alert_env(monkeypatch, tmp_path, task_alerts=False)
    notify._post_task_alerts()
    assert "disabled by config" in capsys.readouterr().out
    _k1_alert_env(monkeypatch, tmp_path)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    notify._post_task_alerts()
    assert calls == [] and "bot not configured" in capsys.readouterr().out


def test_task_alert_never_raises_and_never_leaks_the_token(monkeypatch, tmp_path, capsys):
    import requests as _rq
    _k1_alert_env(monkeypatch, tmp_path)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    for name in ("task_alerts_enabled", "load_notified", "load_rows", "_public_video",
                 "format_task_alert", "send", "save_notified", "_token"):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(notify, name, lambda *a, **k: (_ for _ in ()).throw(
                RuntimeError("boom /bot123:SECRET/sendMessage")))
            assert notify.main() == 0, name
    for name in ("alert_events", "follow_channel"):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(notify.tasks, name, lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
            assert notify.main() == 0, name

    capsys.readouterr()             # the loop above is about "never raises", not the log
    # a raise BEFORE the token was read is still redacted (the env is read directly)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(notify, "task_alerts_enabled", lambda: (_ for _ in ()).throw(
            RuntimeError("boom /bot123:SECRET/sendMessage")))
        notify._post_task_alerts()
    assert "SECRET" not in capsys.readouterr().out

    def boom(url, json=None, timeout=None):
        raise _rq.exceptions.ConnectionError(f"Max retries exceeded with url: {url}")
    monkeypatch.setattr(notify.requests, "post", boom)
    notify._post_task_alerts()
    out = capsys.readouterr().out
    assert "SECRET" not in out and "telegram failed" in out


# ------------------------------------------------------------------ state + config
def test_task_alert_state_gets_the_both_halves_treatment():
    assert "state/notified_tasks.json" in sm.FILES
    names = [Path(f).name for f in sm.FILES]
    assert len(names) == len(set(names))                 # state_merge reads by basename
    pub = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    nyml = (ROOT / ".github/workflows/notify.yml").read_text(encoding="utf-8")
    assert "state/notified_tasks.json" in pub
    assert nyml.count("state/notified_tasks.json") == 2  # stash AND git add
    merged = json.loads(sm.merge_file("state/notified_tasks.json",
                                      json.dumps(["a", "b"]), json.dumps(["b", "c"])))
    assert sorted(merged) == ["a", "b", "c"]
    for junk in ("42", "null", '"str"', "{}"):
        assert sm.merge_file("state/notified_tasks.json", junk, json.dumps(["a"])) is not None


def test_kill_switches_exist_and_x_is_off_by_default(monkeypatch):
    for name in ("config.json", "config.example.json"):
        cfg = json.loads((ROOT / name).read_text(encoding="utf-8"))
        assert cfg["twitter"] is False, name
        assert cfg["task_hubs"] is True and cfg["task_hubs_max"] == 1, name
        assert cfg["task_hubs_withdrawn"] == [] and cfg["task_follow_channel"] == "", name
        assert cfg["task_alerts"] is True and cfg["google_site_verification"] == "", name
    monkeypatch.setattr(notify.fv, "setting", _k1_settings())     # key absent
    assert notify.x_enabled() is False
