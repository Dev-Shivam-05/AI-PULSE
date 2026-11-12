"""v3-R.3: readable recordings (D9), viewer replies and the one-line answer (D11).

docs/spec/ai-pulse-v3r.md. No network, no ffmpeg, no browser, no LLM: every seam is
stubbed as the consumer sees it. The cohort flag is turned on per test (conftest
turns it off suite-wide).
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from factverse import ai_pipeline as ap    # noqa: E402
from factverse import evidence as ev       # noqa: E402
from factverse import replies as rp        # noqa: E402
from factverse import screencap as sc      # noqa: E402
from factverse import state_merge as sm    # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _r3a_on(monkeypatch, on=True):
    monkeypatch.setenv("RECOVERY_COHORT", "1" if on else "0")


# ================================================================ D9: readable stills
def test_r3a_still_values_make_the_canvas_exactly():
    assert (sc.STILL_VIEW_W * sc.STILL_DSF, sc.STILL_VIEW_H * sc.STILL_DSF) == (sc.REC_W, sc.REC_H)
    # one still never outlasts the 5 s scroll rule even at recut's maximum stretch
    assert sc.STILL_SECONDS * sc.MAX_SLOW <= 5.0


@pytest.mark.parametrize("url, out", [
    ("https://github.com/Zagitta/gpu-unlock", "https://github.com/Zagitta/gpu-unlock#readme"),
    ("https://github.com/Zagitta/gpu-unlock/", "https://github.com/Zagitta/gpu-unlock#readme"),
    ("https://github.com/Zagitta/gpu-unlock/issues", "https://github.com/Zagitta/gpu-unlock/issues"),
    ("https://github.com/Zagitta/gpu-unlock#install", "https://github.com/Zagitta/gpu-unlock#install"),
    ("https://huggingface.co/nvidia/model", "https://huggingface.co/nvidia/model"),
])
def test_r3a_first_page_opens_at_the_readme(url, out):
    assert sc.first_page_url(url) == out


def test_r3a_stills_list_shows_each_still_and_repeats_the_last():
    txt = sc.stills_list(["a/s0.png", "a/s1.png"], 3.0)
    assert txt.splitlines() == ["file 'a/s0.png'", "duration 3.000", "file 'a/s1.png'",
                                "duration 3.000", "file 'a/s1.png'"]
    assert sc.stills_list([]) == ""
    args = sc._stills_args("l.txt", "rec.mp4")
    assert args[args.index("-f") + 1] == "concat" and args[-1] == "rec.mp4"
    assert "scale=1920:1080" in args[args.index("-vf") + 1]


def _r3a_fake_ffmpeg(seen):
    def run(args, timeout=600):
        seen.append(args)
        Path(args[-1]).write_bytes(b"0" * 2000)
        return True
    return run


def test_r3a_cohort_capture_shoots_stills_not_a_scroll(monkeypatch, tmp_path):
    _r3a_on(monkeypatch)
    monkeypatch.setattr(sc.fv, "TEMP", tmp_path)
    asked = []

    def shoot(urls, out, t):
        asked.append(list(urls))
        pngs = []
        for i in range(3):
            p = Path(out) / f"still_{i:04d}.png"
            p.write_bytes(b"png")
            pngs.append(str(p))
        return pngs, pngs[0]
    monkeypatch.setattr(sc, "_shoot_pages", shoot)
    monkeypatch.setattr(sc, "_record_pages", lambda *a, **k: (_ for _ in ()).throw(AssertionError("scroll")))
    seen = []
    monkeypatch.setattr(sc, "_ffmpeg", _r3a_fake_ffmpeg(seen))
    monkeypatch.setattr(sc, "_probe_duration", lambda p: 9.0)
    out = sc.capture({"scenes": [{"narration": "w " * 40}] * 4, "source_url": "https://github.com/o/r"})
    assert asked == [sc.browse_plan("https://github.com/o/r")]
    assert out and out["screenshot"].endswith("still_0000.png") and out["rec_seconds"] == 9.0
    assert seen[0][seen[0].index("-f") + 1] == "concat"
    lst = (tmp_path / "screencap" / "stills.txt").read_text(encoding="utf-8")
    assert lst.count("duration 3.000") == 3


def test_r3a_failed_stills_never_fall_back_to_a_desktop_scroll(monkeypatch, tmp_path):
    _r3a_on(monkeypatch)
    monkeypatch.setattr(sc.fv, "TEMP", tmp_path)
    monkeypatch.setattr(sc, "_shoot_pages", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no browser")))
    monkeypatch.setattr(sc, "_record_pages", lambda *a, **k: (_ for _ in ()).throw(AssertionError("scroll")))
    monkeypatch.setattr(sc, "_ffmpeg", _r3a_fake_ffmpeg([]))
    out = sc.capture({"scenes": [{"narration": "w " * 40}] * 4, "source_url": "https://github.com/o/r"})
    assert out is None                                                # D9: no scroll fallback


def test_r3a_cohort_off_keeps_the_desktop_recording(monkeypatch, tmp_path):
    _r3a_on(monkeypatch, False)
    monkeypatch.setattr(sc.fv, "TEMP", tmp_path)
    monkeypatch.setattr(sc, "_shoot_pages", lambda *a, **k: (_ for _ in ()).throw(AssertionError("stills")))
    monkeypatch.setattr(sc, "_record_pages",
                        lambda urls, out, t: ([(str(Path(out) / "a.webm"), 2.5)], "shot.png"))
    monkeypatch.setattr(sc, "_ffmpeg", _r3a_fake_ffmpeg([]))
    monkeypatch.setattr(sc, "_probe_duration", lambda p: 60.0)
    assert sc.capture({"scenes": [{"narration": "w " * 40}] * 4, "source_url": "https://github.com/o/r"})


# ================================================================ D11: the one-line answer
def _r3a_script(**over):
    s = {"format": "tool", "title": "demo: Does it run on Windows?", "answer_line": "Per its README, Linux only.",
         "description": "Hook paragraph.\n\nMore.\n\n#AI", "evidence": ev.docs_record(),
         "deliverable": {"kind": "command", "text": "make install", "url": "https://github.com/o/r"},
         "source_url": "https://github.com/o/r", "scenes": []}
    s.update(over)
    return s


def test_r3a_answer_line_is_the_first_description_line_once(monkeypatch):
    _r3a_on(monkeypatch)
    s = _r3a_script()
    ap.place_description_blocks(s)
    ap.place_description_blocks(s)                                   # idempotent: called twice
    line = f"Per its README, Linux only. — {ev.LABELS['docs']}"
    assert s["description"].split("\n")[0] == line and s["description"].count(line) == 1
    assert "🔧 Try it yourself" in s["description"]                  # the blocks are still there


def test_r3a_channel_comment_leads_with_the_answer(monkeypatch):
    _r3a_on(monkeypatch)
    c = ap.pinned_comment(_r3a_script())
    assert c.startswith(f"Per its README, Linux only. — {ev.LABELS['docs']}") and "make install" in c
    _r3a_on(monkeypatch, False)
    assert ap.pinned_comment(_r3a_script()).startswith("Copy-paste to try it")   # off: unchanged
    assert ap.cohort_answer_line(_r3a_script()) == ""


def test_r3a_answer_line_without_evidence_says_not_tested(monkeypatch):
    _r3a_on(monkeypatch)
    s = _r3a_script()
    s.pop("evidence")
    assert ap.cohort_answer_line(s).endswith(f"— Not tested by {ap.fv.CHANNEL_NAME}")
    assert ap.cohort_answer_line(_r3a_script(answer_line="")) == ""


# ================================================================ D11: viewer replies
_CH = "UCchannel"


def _thread(cid, text, author="UCviewer", video="VIDEO000001", when="2026-11-09T10:00:00Z", replies=()):
    return {"id": f"T{cid}", "snippet": {"videoId": video, "topLevelComment": {"id": cid, "snippet": {
        "textOriginal": text, "publishedAt": when, "videoId": video,
        "authorChannelId": {"value": author}}}},
        "replies": {"comments": [{"snippet": {"authorChannelId": {"value": a}}} for a in replies]}}


def test_r3a_pending_skips_own_answered_known_and_old_comments():
    today = dt.date(2026, 11, 12)
    ths = [_thread("c1", "Does it work on 50 series cards"),
           _thread("c2", "my own pinned comment", author=_CH),
           _thread("c3", "already answered by hand", replies=[_CH]),
           _thread("c4", "known", ),
           _thread("c5", "ancient", when="2026-07-01T10:00:00Z"),
           _thread("c6", "earlier question", when="2026-11-01T10:00:00Z"),
           "junk"]
    out = rp.pending(ths, _CH, {"c4": {"status": "answered"}}, today)
    assert [c["comment"] for c in out] == ["c6", "c1"]                 # oldest first
    assert out[1]["video"] == "VIDEO000001" and out[1]["thread"] == "Tc1"


def test_r3a_video_row_finds_long_forms_and_their_shorts():
    rows = [{"status": "PUBLISHED", "youtube_url": "https://youtube.com/watch?v=LONGFORM001",
             "shorts": [{"url": "https://youtube.com/watch?v=SHORT000001"}], "source_url": "https://github.com/o/r"},
            {"status": "FACTCHECK_BLOCKED", "youtube_url": "https://youtube.com/watch?v=XXXXXXXXXXX"}]
    assert rp.video_row("LONGFORM001", rows) is rows[0] and rp.video_row("SHORT000001", rows) is rows[0]
    assert rp.video_row("XXXXXXXXXXX", rows) is None
    assert rp.source_url_of("LONGFORM001", rows[0]) == "https://github.com/o/r"


def test_r3a_older_rows_take_the_catalogue_source(monkeypatch):
    monkeypatch.setattr(rp.memory, "tools_index",
                        lambda path=None: {"4MTEDi4MdnQ": {"source_url": "https://github.com/Zagitta/gpu-unlock"}})
    row = {"status": "PUBLISHED", "youtube_url": "https://youtube.com/watch?v=4MTEDi4MdnQ"}
    assert rp.source_url_of("4MTEDi4MdnQ", row) == "https://github.com/Zagitta/gpu-unlock"
    assert rp.source_url_of("nope", None) == ""


@pytest.mark.parametrize("raw, status", [
    ({"question": True, "on_topic": True, "settled": True, "reply": "The README lists RTX 50 as not supported."},
     "answered"),
    ({"question": "false", "on_topic": "true", "reply": "x"}, "not_question"),        # strings are not True
    ({"question": True, "on_topic": True, "reply": "DM me on telegram for the fix"}, "not_question"),
    ({"question": True, "on_topic": True, "reply": "Ask @someone about it"}, "not_question"),
    ({"question": False, "on_topic": True, "reply": "x"}, "not_question"),
    ({"question": True, "on_topic": False, "reply": "x"}, "not_question"),
    ({"question": True, "on_topic": True, "reply": ""}, "failed"),
    (None, "failed"), ("text", "failed"),
])
def test_r3a_decide(raw, status):
    assert rp.decide(raw)[0] == status


def test_r3a_clean_reply_drops_bare_domains():
    t = rp.clean_reply("Grab it at www.evil-example.com/win or evil-example.com/x today. README.md says no.")
    assert "evil" not in t and "README.md says no." in t


def test_r3a_clean_reply_drops_links_markdown_and_runs_long():
    t = rp.clean_reply("**No** — see https://evil.test/x for `details`. " + "More words here. " * 60)
    assert "http" not in t and "*" not in t and "`" not in t and len(t) <= rp.REPLY_MAX
    assert rp.clean_reply(["a"]) == "" and rp.clean_reply(None) == ""


class _R3aExec:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class _R3aYt:
    """channels / commentThreads / comments with recorded calls."""
    def __init__(self, threads, boom_on=None):
        self._threads, self.posted, self.boom_on = threads, [], boom_on

    def channels(self):
        return self

    def commentThreads(self):
        return _R3aThreads(self)

    def comments(self):
        return _R3aComments(self)

    def list(self, **kw):
        return _R3aExec(lambda: {"items": [{"id": _CH}]})


class _R3aThreads:
    def __init__(self, yt):
        self.yt = yt

    def list(self, **kw):
        assert kw["allThreadsRelatedToChannelId"] == _CH
        return _R3aExec(lambda: {"items": self.yt._threads})


class _R3aComments:
    def __init__(self, yt):
        self.yt = yt

    def insert(self, part, body):
        def go():
            if self.yt.boom_on and self.yt.boom_on == body["snippet"]["parentId"]:
                raise RuntimeError("quota")
            self.yt.posted.append((body["snippet"]["parentId"], body["snippet"]["textOriginal"]))
            return {}
        return _R3aExec(go)


def _r3a_rows():
    return [{"status": "PUBLISHED", "title": "gpu-unlock", "youtube_url": "https://youtube.com/watch?v=VIDEO000001",
             "source_url": "https://github.com/Zagitta/gpu-unlock"}]


def test_r3a_run_answers_questions_and_records_the_rest(monkeypatch):
    monkeypatch.setattr(rp, "source_text", lambda url: "Blackwell (RTX 50): Not supported.")
    answers = {"Does it work on 50 series cards": {"question": True, "on_topic": True, "settled": True,
                                                    "reply": "No. The README lists RTX 50 as not supported."},
               "nice video": {"question": False, "on_topic": True}}
    prompts = []
    monkeypatch.setattr(rp.llm, "generate_json",
                        lambda p, **k: prompts.append(p) or answers[p.split("VIEWER COMMENT: ")[1].split("\n")[0]])
    yt = _R3aYt([_thread("c1", "Does it work on 50 series cards"), _thread("c2", "nice video"),
                 _thread("c3", "what about laptops?", video="UNKNOWN0001")])
    state = {}
    counts = rp.run_once(yt, _r3a_rows(), state, dt.date(2026, 11, 12))
    assert yt.posted == [("Tc1", "No. The README lists RTX 50 as not supported.")]
    assert state["c1"]["status"] == "answered" and state["c2"]["status"] == "not_question"
    assert state["c3"]["status"] == "no_source"                        # no ledger row, no catalogue entry
    assert counts == {"answered": 1, "not_question": 1, "no_source": 1, "failed": 0}
    assert "Blackwell (RTX 50): Not supported." in prompts[0]
    assert rp.run_once(yt, _r3a_rows(), state, dt.date(2026, 11, 12))["answered"] == 0   # idempotent


def test_r3a_a_failed_post_is_not_recorded_and_others_still_run(monkeypatch):
    monkeypatch.setattr(rp, "source_text", lambda url: "docs")
    monkeypatch.setattr(rp.llm, "generate_json",
                        lambda p, **k: {"question": True, "on_topic": True, "settled": False, "reply": "Docs do not say."})
    yt = _R3aYt([_thread("c1", "q1?"), _thread("c2", "q2?")], boom_on="Tc1")
    state = {}
    counts = rp.run_once(yt, _r3a_rows(), state, dt.date(2026, 11, 12))
    assert "c1" not in state and state["c2"]["status"] == "answered" and counts["failed"] == 1


def test_r3a_main_never_raises_and_honours_the_kill_switch(monkeypatch, capsys):
    monkeypatch.setenv("COMMENT_REPLIES", "0")
    assert rp.main() == 0 and "off" in capsys.readouterr().out
    monkeypatch.setenv("COMMENT_REPLIES", "1")
    monkeypatch.setattr(rp, "_youtube", lambda: 1 / 0)
    monkeypatch.setattr(rp, "load_state", lambda path=None: {})
    monkeypatch.setattr(rp.learn, "read_runs", lambda path=None: [])
    assert rp.main() == 0 and "replies skipped" in capsys.readouterr().out


def test_r3a_replied_state_has_the_both_halves_treatment():
    wf = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    assert "state/replied.json" in sm.FILES and "state/replied.json" in wf
    step = wf.index("python -m factverse.replies")
    assert step < wf.index("- name: Save state back to repo")         # above the state-save
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    assert cfg["comment_replies"] is True
    assert json.loads((ROOT / "state" / "replied.json").read_text(encoding="utf-8")) == {}
    names = [Path(f).name for f in sm.FILES]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("ours, theirs", [
    ('{"a": {"status": "answered"}}', '{"b": {"status": "not_question"}}'),
    ("42", '{"b": {"status": "not_question"}}'), ("null", "{}"), ('"str"', None), (None, '{"b": 1}'),
])
def test_r3a_replied_merge_never_raises_and_unions(ours, theirs):
    out = sm.merge_file("state/replied.json", ours, theirs)
    merged = json.loads(out)
    assert isinstance(merged, (dict, str, int)) or merged is None
    if ours and ours.startswith("{") and theirs and theirs.startswith("{"):
        assert set(merged) == set(json.loads(ours)) | set(json.loads(theirs))


def test_r3a_theirs_wins_a_conflict():
    assert rp.merge({"a": 1}, {"a": 2, "b": 3}) == {"a": 1, "b": 3}
    assert rp.merge(None, "x") == {} and rp.merge({"a": 1}, None) == {"a": 1}
