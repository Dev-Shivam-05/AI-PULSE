"""v3-L.2 ToolDojo Radar Live: data, narration gate, timing, ffmpeg args, ingest guard.
Pure functions only — no ffmpeg, no browser, no network (CLAUDE.md)."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from factverse import radar as rd       # noqa: E402
import radar_live as rl                 # noqa: E402

NOW = datetime(2026, 10, 1, 14, 30, tzinfo=timezone.utc)


def _gh(full="acme/agentkit", stars=1000, created="2026-09-21T00:00:00Z",
        desc="An agent toolkit for the terminal", lang="Python", lic="MIT"):
    return rd.tool_from_github({"full_name": full, "stargazers_count": stars,
                                "created_at": created, "description": desc,
                                "language": lang, "license": {"spdx_id": lic}}, NOW)


def _hf(mid="lab/vision-8b", likes=500, trending=90, downloads=0, tag="image-text-to-text"):
    return rd.tool_from_hf({"id": mid, "likes": likes, "trendingScore": trending,
                            "downloads": downloads, "pipeline_tag": tag,
                            "createdAt": "2026-09-01T00:00:00Z"}, NOW)


# ------------------------------------------------------------------ parsing
def test_github_tool_fields_and_velocity():
    t = _gh()
    assert t["id"] == "gh:acme/agentkit" and (t["owner"], t["name"]) == ("acme", "agentkit")
    assert t["age_days"] == 10 and t["velocity"] == 100
    assert t["readme"] == "https://raw.githubusercontent.com/acme/agentkit/HEAD/README.md"


def test_github_noassertion_licence_and_bad_items():
    assert _gh(lic="NOASSERTION")["license"] == ""
    assert rd.tool_from_github({"full_name": "noslash"}, NOW) is None
    assert rd.tool_from_github("junk", NOW) is None


def test_api_text_is_one_bounded_line():
    t = _gh(desc="line one\n\x1b[31mline two\t" + "x" * 900)
    assert "\n" not in t["desc"] and "\x1b" not in t["desc"] and len(t["desc"]) <= 400


def test_hf_tool_fields():
    t = _hf()
    assert t["id"] == "hf:lab/vision-8b" and t["task"] == "image text to text"
    assert t["desc"] == "a trending image text to text model on Hugging Face"


def test_infinite_or_negative_numbers_become_zero():
    assert rd._int("Infinity") == 0 and rd._int(-5) == 0 and rd._int("12") == 12


# ------------------------------------------------------------------ pool
def test_screen_uses_the_tool_lanes_own_gate():
    kept, dropped = rd.screen([_gh(), _gh(full="x/model-uncensored", desc="uncensored")])
    assert [t["id"] for t in kept] == ["gh:acme/agentkit"]
    assert dropped[0][1] == "uncensored"


def test_rank_interleaves_github_by_velocity_and_hf_by_trending():
    a = _gh(full="a/slow", stars=100)            # 10/day
    b = _gh(full="b/fast", stars=5000)           # 500/day
    h1, h2 = _hf(mid="h/one", trending=5), _hf(mid="h/two", trending=50)
    assert [t["id"] for t in rd.rank([a, h1, b, h2])] == \
        ["gh:b/fast", "hf:h/two", "gh:a/slow", "hf:h/one"]


def test_board_gain_is_measured_since_the_stream_started():
    base = rd.update_baseline({}, [_gh(stars=1000)])
    rows = rd.board_rows([_gh(stars=1040)], base)
    assert rows[0]["gain"] == 40 and rows[0]["unit"] == "stars"
    # the baseline keeps the FIRST number of the session
    rd.update_baseline(base, [_gh(stars=1040)])
    assert base["gh:acme/agentkit"] == 1000


def test_fresh_honours_cooldown_and_session_spotlights():
    a, b, c = _gh(full="a/a"), _gh(full="b/b"), _gh(full="c/c")
    hist = {"gh:a/a": {"at": (NOW - timedelta(days=1)).isoformat(), "number": 1},
            "gh:b/b": {"at": (NOW - timedelta(days=4)).isoformat(), "number": 1}}
    ids = [t["id"] for t in rd.fresh([a, b, c], hist, {"gh:c/c"}, NOW)]
    assert ids == ["gh:b/b"]            # a: cooldown, c: already this session


def test_fresh_survives_a_corrupt_history_date():
    assert len(rd.fresh([_gh()], {"gh:acme/agentkit": {"at": "not a date"}}, set(), NOW)) == 1


# ------------------------------------------------------------------ narration
def test_facts_never_say_zero_downloads():
    assert not any("downloads" in f for f in rd.facts(_hf(downloads=0)))
    assert "1,234 downloads" in rd.facts(_hf(downloads=1234))


def test_back_on_the_radar_states_the_change():
    hist = {"gh:acme/agentkit": {"at": "2026-09-20T00:00:00+00:00", "number": 700}}
    t = _gh(stars=1000)
    assert "up 300 stars since the radar last covered it" in rd.facts(t, hist)
    assert rd.template_narration(t, 1, hist).startswith("Back on the radar: agentkit")


def test_template_narration_reads_the_facts():
    s = rd.template_narration(_gh(), 3)
    assert s.startswith("Number 3 on the radar: agentkit, from acme.")
    assert "1,000 stars on GitHub" in s and "In its own words: An agent toolkit" in s


def test_readable_rejects_cjk_descriptions():
    assert rd.readable("An agent toolkit for the terminal")
    assert not rd.readable("一个自己找热点、自己写日报的网站框架")
    assert not rd.readable("")
    assert rd.spotlightable(_gh(desc="一个自己找热点"), have_llm=True)
    assert not rd.spotlightable(_gh(desc="一个自己找热点"), have_llm=False)
    assert rd.spotlightable(_hf(), have_llm=False)       # our own English phrase


GOOD = ("agentkit is a terminal toolkit for building coding agents. It has 1,000 stars "
        "after 10 days, so it is young. Developers who script their own agents get "
        "a plugin system; the open question is how stable its API will be once more "
        "people depend on it.")


def test_narration_gate():
    grounding = "1,000 stars on GitHub; created 10 days ago"
    assert rd.narration_ok(GOOD, grounding)
    assert not rd.narration_ok(GOOD.replace("1,000", "9,000"), grounding)   # planted number
    assert not rd.narration_ok(GOOD + " It is mind-blowing.", grounding)    # hype
    assert not rd.narration_ok("Too short.", grounding)


def test_llm_narration_needs_a_key_and_passes_the_gate(monkeypatch):
    t, facts, readme = _gh(), rd.facts(_gh()), "README " * 60
    monkeypatch.setattr(rd.fv, "GEMINI_KEY", "")
    assert rd.llm_narration(t, facts, readme) is None
    monkeypatch.setattr(rd.fv, "GEMINI_KEY", "k")
    monkeypatch.setattr(rd.llm, "generate_json", lambda *a, **k: {"narration": GOOD})
    assert rd.llm_narration(t, facts, readme) == GOOD
    monkeypatch.setattr(rd.llm, "generate_json",
                        lambda *a, **k: {"narration": GOOD.replace("10 days", "77 days")})
    assert rd.llm_narration(t, facts, readme) is None
    monkeypatch.setattr(rd.llm, "generate_json", lambda *a, **k: ["not", "a", "dict"])
    assert rd.llm_narration(t, facts, readme) is None

    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(rd.llm, "generate_json", boom)
    assert rd.llm_narration(t, facts, readme) is None


def test_readme_fetch_refuses_foreign_hosts():
    assert rd.fetch_readme({"readme": "https://evil.test/README.md"}) == ""
    assert rd.fetch_readme({"readme": "file:///etc/passwd"}) == ""


def test_board_narration_names_the_top_and_the_climber():
    rows = [{"rank": 1, "id": "a", "name": "alpha", "number": 5000, "unit": "stars", "gain": 0},
            {"rank": 2, "id": "b", "name": "beta", "number": 900, "unit": "likes", "gain": 12}]
    s = rd.board_narration(rows, NOW)
    assert s.startswith("The board at 14:30 UTC. At the top: alpha, with 5,000 stars.")
    assert "Biggest climber since this stream started: beta, up 12 likes." in s
    assert rd.board_narration([], NOW) == ""


# ------------------------------------------------------------------ timing
def test_phrases_split_at_six_words_and_sentence_ends():
    words = [(i * 0.5, i * 0.5 + 0.4, w) for i, w in
             enumerate("one two three. four five six seven eight nine ten".split())]
    ph = rd.phrases(words)
    assert [p[2] for p in ph] == ["one two three.", "four five six seven eight nine", "ten"]
    assert ph[0][0] == 0.0 and ph[1][0] == 1.5


def test_segment_seconds_is_even_and_covers_the_tail():
    assert rd.segment_seconds(10.2) == 14       # 13.2 -> 14
    assert rd.segment_seconds(9.0) == 12        # 12 -> 12
    assert rd.segment_seconds(0) == 4           # 3 -> 4
    assert all(rd.segment_seconds(x / 10) % 2 == 0 for x in range(0, 900, 7))


def test_frame_times_are_seconds_plus_phrase_starts():
    assert rd.frame_times(4, [(0.0, 1, "a"), (1.25, 2, "b"), (9.0, 10, "late")]) == \
        [0.0, 1.0, 1.25, 2.0, 3.0]


# ------------------------------------------------------------------ streamer
def _opt(a, flag):
    return a[a.index(flag) + 1]


def test_segment_args_tile_two_second_gops():
    a = rl.segment_args("list.txt", "v.mp3", 14, "s.ts")
    assert _opt(a, "-g") == "60" and _opt(a, "-keyint_min") == "60"
    assert _opt(a, "-sc_threshold") == "0" and _opt(a, "-crf") == "20"
    assert _opt(a, "-maxrate") == "14000k" and _opt(a, "-t") == "14"
    assert _opt(a, "-ar") == "44100" and _opt(a, "-b:a") == "128k"
    assert _opt(a, "-muxdelay") == "0" and a[-3:] == ["-f", "mpegts", "s.ts"]
    assert "v.mp3" in a and not any("anullsrc" in x for x in a)


def test_silent_segment_uses_generated_silence():
    a = rl.segment_args("list.txt", None, 10, "s.ts")
    assert any(x.startswith("anullsrc=r=44100") for x in a)


def test_remux_shifts_onto_the_running_timeline():
    a = rl.remux_args("s.ts", 123.5)
    assert _opt(a, "-output_ts_offset") == "123.500" and _opt(a, "-c") == "copy"
    assert a[-1] == "pipe:1"


def test_stream_args_pace_copy_and_end_at_the_destination():
    a = rl.stream_args("rtmps://a.rtmps.youtube.com/live2/KEY")
    assert "-re" in a and _opt(a, "-c:v") == "copy" and _opt(a, "-f") == "mpegts"
    assert a[-3:] == ["-f", "flv", "rtmps://a.rtmps.youtube.com/live2/KEY"]


def test_board_every_fourth_segment():
    assert [rl.kind_of(i) for i in range(8)] == ["spotlight"] * 3 + ["board"] + \
        ["spotlight"] * 3 + ["board"]


def test_ingest_guard_only_trusts_rtmps_youtube_hosts():
    assert rl.valid_ingest("rtmps://a.rtmps.youtube.com/live2")
    assert rl.valid_ingest("rtmps://a.rtmps.youtube.com:443/live2")
    assert not rl.valid_ingest("rtmp://a.rtmp.youtube.com/live2")            # plain RTMP
    assert not rl.valid_ingest("rtmps://a.rtmps.youtube.com.evil.test/live2")
    assert not rl.valid_ingest("rtmps://evilyoutube.com/live2")
    assert not rl.valid_ingest("https://youtube.com/live2")
    assert not rl.valid_ingest("")
    assert rl.ingest_target("rtmps://h.youtube.com/live2/", " k1 ") == "rtmps://h.youtube.com/live2/k1"


def test_redact_hides_the_key_everywhere():
    line = "Output #0, flv, to 'rtmps://a.rtmps.youtube.com/live2/abcd-1234-efgh':"
    assert "abcd-1234-efgh" not in rl.redact(line, ["abcd-1234-efgh"])
    assert rl.redact("x", [""]) == "x"


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(rl, "LOG", tmp_path / "radar_live.log")
    monkeypatch.setattr(rl, "SESSIONS", tmp_path / "radar_sessions.jsonl")
    monkeypatch.setattr(rl, "_SECRETS", [])


def test_no_key_means_off(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.delenv("YT_STREAM_KEY", raising=False)
    assert rl.main([]) == 0
    assert "Radar Live is off" in (tmp_path / "radar_live.log").read_text(encoding="utf-8")


def test_a_bad_url_is_refused_and_the_key_never_logged(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("YT_STREAM_KEY", "abcd-1234-efgh")
    monkeypatch.setenv("YT_STREAM_URL", "rtmps://a.rtmps.youtube.com.evil.test/live2")
    called = []
    monkeypatch.setattr(rl, "run_session", lambda *a, **k: called.append(a))
    assert rl.main([]) == 2 and not called
    logs = (tmp_path / "radar_live.log").read_text(encoding="utf-8")
    logs += (tmp_path / "radar_sessions.jsonl").read_text(encoding="utf-8")
    assert "abcd-1234-efgh" not in logs


def test_out_flag_cannot_reach_youtube(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    called = []
    monkeypatch.setattr(rl, "run_session", lambda *a, **k: called.append(a))
    assert rl.main(["--out", "rtmps://a.rtmps.youtube.com/live2/x"]) == 2 and not called


def test_a_crash_in_the_session_is_logged_redacted_not_raised(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("YT_STREAM_KEY", "abcd-1234-efgh")
    monkeypatch.setenv("YT_STREAM_URL", "rtmps://a.rtmps.youtube.com/live2")

    def boom(dest, *a):
        raise ConnectionError(f"Max retries exceeded with url: {dest}")
    monkeypatch.setattr(rl, "run_session", boom)
    assert rl.main([]) == 1
    summary = json.loads((tmp_path / "radar_sessions.jsonl").read_text(encoding="utf-8"))
    assert summary["status"].startswith("crashed: ConnectionError")
    assert "abcd-1234-efgh" not in (tmp_path / "radar_live.log").read_text(encoding="utf-8")
    assert "abcd-1234-efgh" not in json.dumps(summary)


def test_segment_args_exact_frames_and_no_b_frames():
    a = rl.segment_args("list.txt", None, 12, "s.ts")
    assert _opt(a, "-frames:v") == "360"      # 12 s x 30 fps, no doubled last frame
    assert _opt(a, "-bf") == "0"              # DTS == PTS, so seams stay monotonic


def test_stream_audio_trims_priming_overlap_at_seams():
    af = _opt(rl.stream_args("x.flv"), "-af")
    assert "min_hard_comp=0.01" in af and af.startswith("aresample=async=")


def test_card_chips_are_short_and_carry_the_same_numbers():
    c = rd.chips(_gh(stars=1000))
    assert c == ["\u2605 1,000", "10 days old", "~100 \u2605/day", "Python", "MIT"]
    assert "1 day old" in rd.chips(_gh(created="2026-09-30T00:00:00Z"))
    assert rd.chips(_hf(downloads=0)) == ["\u2665 500", "30 days old", "image text to text"]
    hist = {"gh:acme/agentkit": {"at": "2026-09-20T00:00:00+00:00", "number": 700}}
    assert rd.chips(_gh(stars=1000), hist)[-1] == "+300 since last time"


def test_one_day_is_singular():
    assert "created 1 day ago" in rd.facts(_gh(created="2026-09-30T00:00:00Z"))


def test_hf_template_never_quotes_our_own_label_as_its_words():
    s = rd.template_narration(_hf(), 2)
    assert "In its own words" not in s and s.endswith("It is a trending image text to text model.")


def test_spotlight_outside_the_top_eight_takes_the_last_board_slot():
    tools = [_gh(full=f"o/t{i}", stars=1000 - i * 10) for i in range(10)]
    rows = rd.board_rows(tools, {}, include="gh:o/t9")
    assert len(rows) == 8 and rows[-1]["id"] == "gh:o/t9" and rows[-1]["rank"] == 10
    assert [r["rank"] for r in rd.board_rows(tools, {}, include="gh:o/t1")] == list(range(1, 9))


def test_punctuate_restores_the_scripts_punctuation():
    text = "Number 3 on the radar: dots, from feder-cr. Created 1 day ago."
    spoken = [(i * 0.3, i * 0.3 + 0.2, w) for i, w in enumerate(
        ["Number", "3", "on", "the", "radar", "dots", "from", "feder", "Created", "1", "day", "ago"])]
    out = [w[2] for w in rd.punctuate(spoken, text)]
    assert out[4] == "radar:" and out[5] == "dots," and out[-1] == "ago."
    assert out[7] == "feder"                 # no clean match: keeps the spoken form
    assert [p[2] for p in rd.phrases(rd.punctuate(spoken, text))][0] == \
        "Number 3 on the radar: dots,"
