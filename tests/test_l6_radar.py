"""v3-L.6 Radar Live show pass (docs/spec/ai-pulse-v3l6.md). Pure functions only:
no network, no ffmpeg, no browser."""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from factverse import radar as rd       # noqa: E402
import radar_live as rl                 # noqa: E402

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def _l6_gh(i, velocity, stars=500):
    return {"id": f"gh:o/r{i}", "kind": "github", "name": f"r{i}", "owner": "o",
            "url": f"https://github.com/o/r{i}", "desc": "a tool", "stars": stars,
            "velocity": velocity, "age_days": 3}


def _l6_hf(i, trending, kind="hf"):
    return {"id": f"{'hfs' if kind == 'space' else 'hf'}:o/m{i}", "kind": kind,
            "name": f"m{i}", "owner": "o", "url": f"https://huggingface.co/o/m{i}",
            "desc": "x", "likes": 100 + i, "trending": trending, "age_days": 2}


# ------------------------------------------------------------------ inventory (row 1)
def test_l6_github_windows_partition_thirty_days_newest_first():
    assert rd.github_windows(NOW) == ["2026-10-25..2026-11-01", "2026-10-18..2026-10-25",
                                      "2026-10-02..2026-10-18"]


def test_l6_github_wide_dedupes_and_survives_a_failed_window(monkeypatch):
    pages = iter([[_l6_gh(1, 9), _l6_gh(2, 8)], None, [_l6_gh(2, 8), _l6_gh(3, 7)]])
    monkeypatch.setattr(rd, "_github_page", lambda created, now: next(pages))
    got = rd.fetch_github_wide(NOW)
    assert sorted(t["id"] for t in got) == ["gh:o/r1", "gh:o/r2", "gh:o/r3"]


def test_l6_github_wide_is_none_only_when_every_window_failed(monkeypatch):
    monkeypatch.setattr(rd, "_github_page", lambda created, now: None)
    assert rd.fetch_github_wide(NOW) is None
    monkeypatch.setattr(rd, "_github_page", lambda created, now: [])
    assert rd.fetch_github_wide(NOW) == []


def test_l6_space_quotes_its_authors_short_description():
    s = {"id": "nvidia/simready-central", "likes": 321, "trendingScore": 196, "sdk": "docker",
         "createdAt": "2026-09-28T14:52:11.000Z",
         "cardData": {"title": "SimReady Central",
                      "short_description": "Semantic search for 3D assets"}}
    t = rd.tool_from_hf_space(s, NOW)
    assert t["id"] == "hfs:nvidia/simready-central" and t["kind"] == "space"
    assert t["name"] == "SimReady Central" and t["desc"] == "Semantic search for 3D assets"
    assert t["url"] == "https://huggingface.co/spaces/nvidia/simready-central"
    assert t["readme"].startswith("https://huggingface.co/spaces/")
    assert rd.kind_label(t) == "HF SPACE" and rd.is_hf(t)
    assert "docker app" in rd.chips(t) and any("Spaces" in f for f in rd.facts(t))
    assert rd.tool_from_hf_space({"id": "noslash"}, NOW) is None


def test_l6_hf_wide_keeps_a_source_that_answered(monkeypatch):
    class R:
        def __init__(self, code, data):
            self.status_code, self._d = code, data

        def json(self):
            return self._d
    answers = iter([R(500, None), R(200, [{"id": "a/b", "likes": 1, "trendingScore": 2}])])
    monkeypatch.setattr(rd, "_get", lambda url, **kw: next(answers))
    got = rd.fetch_hf_wide(NOW)
    assert [t["kind"] for t in got] == ["space"]


# ------------------------------------------------------------------ boards (row 3)
def test_l6_sections_rank_each_source_by_its_own_measure():
    tools = [_l6_gh(1, 50), _l6_gh(2, 900), _l6_hf(1, 10), _l6_hf(2, 80, "space")]
    s = rd.board_sections(tools, {}, n=4)
    assert [r["id"] for r in s["github"]] == ["gh:o/r2", "gh:o/r1"]
    assert [r["id"] for r in s["hf"]] == ["hfs:o/m2", "hf:o/m1"]
    assert [r["rank"] for r in s["github"]] == [1, 2] and [r["rank"] for r in s["hf"]] == [1, 2]
    assert s["github"][0]["measure"] == "900/day" and s["hf"][0]["measure"] == "trend 80"


def test_l6_spotlight_below_the_cut_takes_its_sections_last_slot():
    tools = [_l6_gh(i, 100 - i) for i in range(1, 8)]
    s = rd.board_sections(tools, {}, n=4, include="gh:o/r7")
    assert [r["rank"] for r in s["github"]] == [1, 2, 3, 7]
    assert rd.section_rank(tools, tools[6]) == 7


def test_l6_status_label_and_staleness():
    t = _l6_gh(1, 5)
    assert rd.status_label(t, {}) == "NEW ON THE RADAR"
    assert rd.status_label(t, {"gh:o/r1": {"at": "x", "number": 3}}) == "BACK ON THE RADAR"
    assert rd.is_stale(None, NOW)
    assert not rd.is_stale(NOW - timedelta(minutes=29), NOW)
    assert rd.is_stale(NOW - timedelta(minutes=31), NOW)


def test_l6_sections_narration_never_ranks_across_sources():
    s = rd.board_sections([_l6_gh(1, 900), _l6_hf(1, 80)], {"gh:o/r1": 400})
    text = rd.sections_narration(s, NOW)
    assert "On GitHub, the fastest riser is r1, at about 900 stars a day" in text
    assert "On Hugging Face, m1 leads the trending list." in text
    assert "up 100 stars" in text
    assert rd.sections_narration({"github": [], "hf": []}, NOW) == ""


def test_l6_end_narration_states_the_true_reason():
    assert "Every fresh tool" in rd.end_narration(12, "exhausted", "8 PM")
    t = rd.end_narration(12, "time", "")
    assert "end of today's session" in t and "12 tools" in t and "back every day" not in t
    assert "back every day at 8 PM" in rd.end_narration(3, "time", "8 PM")


# ------------------------------------------------------------------ narration (row 5)
GOOD_L6 = ("Turning scanned documents into text is slow. " + "This tool reads them locally. " * 18
           + "It has 2,164 stars.")


def test_l6_prompt_orders_benefit_evidence_limitation():
    p = rd._prompt(_l6_gh(1, 5), ["2,164 stars on GitHub"], "readme")
    for s in ("the problem it solves", "one concrete piece of evidence",
              "limitations are not documented yet", '"use_it_for"', "100-160 words"):
        assert s in p


def test_l6_benefit_line_has_its_own_gate(monkeypatch):
    monkeypatch.setattr(rd.fv, "GEMINI_KEY", "k")
    facts = ["2,164 stars on GitHub"]
    readme = "README " * 60 + " 2,164"
    for use, kept in (("turn scanned PDFs into text", True),
                      ("unlock insane speed on your laptop", False),
                      ("turn every single scanned PDF you own into searchable text", False),
                      ("run it 10x faster", False),
                      ("go", False)):
        monkeypatch.setattr(rd.llm, "generate_json",
                            lambda *a, **k: {"narration": GOOD_L6, "use_it_for": use})
        got = rd.llm_spotlight(_l6_gh(1, 5), facts, readme)
        assert got["narration"] == GOOD_L6
        assert (got["use_it_for"] == use) is kept, use


# ------------------------------------------------------------------ music (row 10)
def test_l6_playlist_is_every_track_shuffled_stably_per_day():
    tracks = ["a.mp3", "b.mp3", "c.mp3", "d.mp3", "e.mp3"]
    d1 = rl.playlist_order(tracks, date(2026, 11, 1))
    assert sorted(d1) == tracks
    assert d1 == rl.playlist_order(list(reversed(tracks)), date(2026, 11, 1))
    days = {tuple(rl.playlist_order(tracks, date(2026, 11, k))) for k in range(1, 8)}
    assert len(days) > 1
    assert rl.playlist_order([], date(2026, 11, 1)) == []


def test_l6_tracks_are_normalised_to_the_bed_level():
    a = rl.normalize_args("in.mp3", "out.wav")
    assert "loudnorm=I=-36.8:TP=-2:LRA=11" in a and a[-1] == "out.wav"
    assert "pcm_s16le" in a


def test_l6_concat_playlist_escapes_quotes():
    body = rl.concat_playlist(["C:/m/it's.wav", "C:/m/b.wav"])
    assert body.splitlines()[0] == "ffconcat version 1.0"
    assert "file 'C:/m/it'\\''s.wav'" in body


def test_l6_playlist_bed_is_read_by_the_concat_demuxer_at_unity_gain():
    a = rl.segment_args("list.txt", "v.mp3", 14, "s.ts", music="pl.ffconcat",
                        music_at=12.5, music_gain=1.0)
    i = a.index("pl.ffconcat")
    assert a[i - 6:i] == ["12.500", "-f", "concat", "-safe", "0", "-i"]
    fc = a[a.index("-filter_complex") + 1]
    assert "[2:a]volume=1.0[m]" in fc and "normalize=0" in fc


def test_l6_voice_gain_is_applied_only_when_set():
    assert "volume=" not in " ".join(rl.segment_args("l.txt", "v.mp3", 10, "s.ts"))
    a = rl.segment_args("l.txt", "v.mp3", 10, "s.ts", voice_gain_db=-2.0)
    assert a[a.index("-af") + 1] == "volume=-2.0dB,apad"


# ------------------------------------------------------------------ CTA (row 8)
def test_l6_first_cta_after_value_then_every_fifteen_minutes():
    assert rl.cta_window(0, 44, 165) == (None, 165)
    win, nxt = rl.cta_window(132, 44, 165)       # 132..176 reaches 165
    assert win == (33.0, 38.0) and nxt == 165 + 900
    win, nxt = rl.cta_window(1060, 44, 1065)
    assert win == (5.0, 10.0) and nxt == 1065 + 900


def test_l6_cta_never_starts_at_zero_and_skips_a_segment_too_short():
    win, nxt = rl.cta_window(165, 20, 165)
    assert win == (2.0, 7.0)
    assert rl.cta_window(160, 6, 165) == (None, 165)


# ------------------------------------------------------------------ length (row 7, 9)
def test_l6_session_minutes_precedence_and_clamp():
    assert rl.session_minutes(10, {"target_minutes": 240}, 120) == 10
    assert rl.session_minutes(None, {"target_minutes": 240}, 120) == 240
    assert rl.session_minutes(None, None, 120) == 120
    assert rl.session_minutes(900, None, 120) == 360
    assert rl.session_minutes(None, None, "junk") == rl.SESSION_MINUTES   # bad config: default
    assert rl.session_minutes(None, {"target_minutes": "x"}, 120) == 120


def test_l6_manifest_counts_only_for_today_and_when_ready():
    today = date(2026, 11, 2)
    ok = {"date": "2026-11-02", "status": "ready", "target_minutes": 180,
          "broadcast_id": "abc", "stage": "S1"}
    assert rl.manifest_for_today(ok, today) == {"target_minutes": 180.0,
                                                "broadcast_id": "abc", "stage": "S1"}
    assert rl.manifest_for_today({**ok, "date": "2026-11-01"}, today) is None
    assert rl.manifest_for_today({**ok, "status": "failed"}, today) is None
    assert rl.manifest_for_today({**ok, "target_minutes": 9999}, today) is None
    assert rl.manifest_for_today({**ok, "target_minutes": "x"}, today) is None
    assert rl.manifest_for_today(["not", "a", "dict"], today) is None


def test_l6_wrap_is_asked_before_the_target():
    assert not rl.wrap_due(7200 - rl.WRAP_LEAD - 1, 7200)
    assert rl.wrap_due(7200 - rl.WRAP_LEAD, 7200)


# ------------------------------------------------------------------ next up (row 6)
def test_l6_next_spotlight_is_the_one_announced():
    p = rl.Producer(None, None, {})
    a, b, c = _l6_gh(1, 9), _l6_gh(2, 8), _l6_gh(3, 7)
    assert p._pick_next([a, b, c]) is a
    p.next_tool = c
    assert p._pick_next([a, b, c]) is c
    p.next_tool = _l6_gh(9, 1)                    # announced tool vanished from the pool
    assert p._pick_next([a, b]) is a
