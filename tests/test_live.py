"""v3-L live pilot: preflight encoder settings and the pilot scorecard.
Pure functions only — no ffmpeg, no network (CLAUDE.md: tests never run ffmpeg)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import live_preflight as lp      # noqa: E402
import live_scorecard as ls      # noqa: E402


# ------------------------------------------------------------ preflight args
def _opt(args, flag):
    return args[args.index(flag) + 1]


def test_encode_args_carry_youtubes_1080p30_recommendation():
    a = lp.encode_args("1080p30", "pattern", 20, "out.flv")
    assert _opt(a, "-c:v") == "libx264" and _opt(a, "-preset") == "veryfast"
    assert _opt(a, "-r") == "30"
    # 2 s keyframes at 30 fps, fixed: no scene-cut key frames in between
    assert _opt(a, "-g") == "60" and _opt(a, "-keyint_min") == "60"
    assert _opt(a, "-sc_threshold") == "0"
    # CBR at the recommended 14 Mbps
    for flag in ("-b:v", "-minrate", "-maxrate", "-bufsize"):
        assert _opt(a, flag) == "14000k"
    assert _opt(a, "-c:a") == "aac" and _opt(a, "-b:a") == "128k"
    assert _opt(a, "-ar") == "44100" and _opt(a, "-ac") == "2"
    assert _opt(a, "-f") == "lavfi"           # the pattern source, first input
    assert a[-3:] == ["-f", "flv", "out.flv"]
    assert "testsrc2=size=1920x1080:rate=30" in a


def test_encode_args_720p_profile():
    a = lp.encode_args("720p30", "pattern", 20, "o.flv")
    assert _opt(a, "-b:v") == "8000k" and _opt(a, "-g") == "60"
    assert "testsrc2=size=1280x720:rate=30" in a


def test_desktop_source_uses_desktop_duplication_scaled_to_profile():
    a = lp.encode_args("720p30", "desktop", 10, "o.flv")
    src = next(x for x in a if x.startswith("ddagrab"))
    assert "framerate=30" in src and src.endswith("scale=1280:720")
    assert "gdigrab" not in a            # measured: GDI capture holds ~20 of 30 fps


def test_preflight_never_targets_a_network_ingest():
    for prof in lp.PROFILES:
        for src in ("pattern", "desktop"):
            joined = " ".join(lp.encode_args(prof, src, 10, "x.flv"))
            assert "rtmp" not in joined.lower() and "youtube" not in joined.lower()


def test_unknown_source_raises():
    try:
        lp.source_args("webcam", lp.PROFILES["1080p30"])
    except ValueError:
        return
    raise AssertionError("expected ValueError")


# ------------------------------------------------------------ preflight parse
def test_parse_progress_takes_the_last_block():
    text = "frame=10\nspeed=0.5x\ndrop_frames=0\ndup_frames=0\nprogress=continue\n" \
           "frame=600\nspeed=2.31x\ndrop_frames=1\ndup_frames=3\nprogress=end\n"
    assert lp.parse_progress(text) == {"speed": 2.31, "drop_frames": 1, "dup_frames": 3}


def test_parse_progress_survives_na_speed():
    assert lp.parse_progress("speed=N/A\n")["speed"] is None


def test_keyframe_gaps_reads_only_video_key_packets():
    pk = [{"stream_index": 0, "flags": "K__", "pts_time": "0.0"},
          {"stream_index": 0, "flags": "___", "pts_time": "1.0"},
          {"stream_index": 1, "flags": "K__", "pts_time": "1.5"},
          {"stream_index": 0, "flags": "K__", "pts_time": "2.0"},
          {"stream_index": 0, "flags": "K__", "pts_time": "4.0"}]
    assert lp.keyframe_gaps(pk, 0) == [2.0, 2.0]


def _probe(gaps=(2.0, 2.0, 1.0), w=1920, h=1080, rate="30/1", sr="44100"):
    t, packets = 0.0, [{"stream_index": 0, "flags": "K_", "pts_time": "0.0"}]
    for g in gaps:
        t += g
        packets.append({"stream_index": 0, "flags": "K_", "pts_time": str(t)})
    return {"streams": [
        {"index": 0, "codec_type": "video", "codec_name": "h264",
         "width": w, "height": h, "r_frame_rate": rate},
        {"index": 1, "codec_type": "audio", "codec_name": "aac",
         "sample_rate": sr, "channels": 2}], "packets": packets}


def _failed(results):
    return [n for n, ok, _ in results if not ok]


def test_evaluate_passes_a_good_pattern_run_and_tolerates_the_cut_last_gop():
    r = lp.evaluate(_probe(), {"speed": 2.3, "drop_frames": 0, "dup_frames": 0}, "1080p30")
    assert _failed(r) == []


def test_evaluate_flags_a_slow_encoder_and_a_wrong_gop():
    r = lp.evaluate(_probe(gaps=(2.0, 5.0, 2.0)),
                    {"speed": 0.8, "drop_frames": 0, "dup_frames": 0}, "1080p30")
    assert set(_failed(r)) == {"keyframe interval", "encoder speed >= 1.0x"}


def test_evaluate_capture_source_judges_duplicates_not_speed():
    # a capture is clamped to real time: 0.975x is normal, duplicates are not
    ok = lp.evaluate(_probe(), {"speed": 0.975, "drop_frames": 0, "dup_frames": 3},
                     "1080p30", "desktop")
    assert _failed(ok) == []
    bad = lp.evaluate(_probe(), {"speed": 0.975, "drop_frames": 0, "dup_frames": 102},
                      "1080p30", "desktop")
    assert _failed(bad) == ["duplicated frames <= 30"]


def test_evaluate_flags_wrong_resolution_and_sample_rate():
    r = lp.evaluate(_probe(w=1536, h=864, sr="48000"),
                    {"speed": 2.0, "drop_frames": 0, "dup_frames": 0}, "1080p30")
    assert set(_failed(r)) == {"resolution", "audio sample rate"}


# ------------------------------------------------------------ scorecard
def _session(n, hours=1.0, subs=0, peak=2, health="yes", notice="no"):
    return {"session": str(n), "date": f"2026-10-{n:02d}", "video_id": "x",
            "duration_min": "45", "peak_concurrent": str(peak),
            "watch_hours_7d": str(hours), "avg_view_duration_s": "",
            "subs_gained": str(subs), "stream_health_ok": health,
            "policy_notice": notice, "owner_minutes": "60", "notes": ""}


def _verdict(rows):
    sessions, problems = ls.parse_rows(rows)
    assert problems == []
    return ls.verdict(sessions)[0]


def test_scorecard_needs_four_sessions():
    assert _verdict([_session(i, hours=9, subs=9) for i in range(1, 4)]) == "INSUFFICIENT DATA"


def test_scorecard_policy_notice_stops_even_before_four_sessions():
    assert _verdict([_session(1, notice="yes")]) == "STOP"


def test_scorecard_continue_needs_all_three_bars():
    good = [_session(i, hours=2.0, subs=1, peak=5) for i in range(1, 5)]
    assert _verdict(good) == "CONTINUE"
    one_unhealthy = good[:3] + [_session(4, hours=2.0, subs=1, peak=5, health="no")]
    assert _verdict(one_unhealthy) == "REVISE"
    too_few_subs = [_session(i, hours=2.0, subs=0, peak=5) for i in range(1, 5)]
    assert _verdict(too_few_subs) == "REVISE"


def test_scorecard_stop_needs_low_hours_and_low_peak():
    dead = [_session(i, hours=0.2, peak=2) for i in range(1, 5)]
    assert _verdict(dead) == "STOP"
    # same hours but one session drew a crowd: not a stop
    spike = dead[:3] + [_session(4, hours=0.2, peak=3)]
    assert _verdict(spike) == "REVISE"


def test_scorecard_reports_a_bad_row_instead_of_guessing():
    bad = _session(1)
    bad["watch_hours_7d"] = "about two"
    blank = {c: "" for c in ls.COLUMNS}
    sessions, problems = ls.parse_rows([bad, blank, _session(2)])
    assert len(sessions) == 1 and len(problems) == 1 and "watch_hours_7d" in problems[0]


def test_channel_baseline_latest_snapshot_wins_and_windows_28_days():
    old = {"channel_days": [["2026-09-01", 10, 600, 0, 0, 5], ["2026-09-28", 1, 60, 0, 0, 1]]}
    new = {"channel_days": [["2026-09-28", 2, 120, 0, 0, 2], ["2026-08-01", 9, 6000, 0, 0, 9]]}
    lines = [json.dumps(old), "not json", json.dumps(new)]
    b = ls.channel_baseline(lines)
    assert (b["from"], b["to"]) == ("2026-09-01", "2026-09-28")
    assert b["watch_hours"] == 12.0 and b["subs"] == 7     # 600+120 min; 08-01 out of window


def test_projection_is_a_rolling_year_not_a_countdown():
    # today's channel: ~8 h per 28 d; 8 sessions × 2 h on top
    rows = dict((t, (y, need, ok)) for t, y, need, ok in ls.projection(8.0, 2.0, 8))
    year, need, ok = rows["expanded (fan funding)"]
    assert year == round(24 * 365 / 28) and ok is False
    assert need == round(3000 * 28 / 365, 1)
    assert ls.projection(240.0, 0, 0)[0][3] is True


def test_channel_baseline_names_and_excludes_rewatch_days():
    snap = {"channel_days": [["2026-09-01", 27, 120, 19, 6.1, 0],
                             ["2026-09-02", 127, 465, 506, 150.93, 0]]}
    b = ls.channel_baseline([json.dumps(snap)])
    assert b["watch_hours"] == 9.8 and b["watch_hours_excl_rewatch"] == 2.0
    assert b["rewatch_days"] == ["2026-09-02"]
