"""v3-G.4b production basics: music bed pick + mix, scene dissolves, outro line.
Pure functions only — no ffmpeg, no network (CLAUDE.md). Spec: docs/spec/ai-pulse-v3g4b.md."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import factverse_engine as eng          # noqa: E402
from factverse import branding as br    # noqa: E402


def _g4b_fc(args):
    return args[args.index("-filter_complex") + 1]


# ------------------------------------------------------------------ music bed
def test_g4b_bed_glob_reads_only_the_bed_folder(tmp_path, monkeypatch):
    """The old pick globbed assets/music/*.mp3 — where branding._audio also looks
    for intro.mp3/outro.mp3 — so a dropped sting could become the bed."""
    music = tmp_path / "music"
    (music / "bed" / "sub").mkdir(parents=True)
    for name in ("intro.mp3", "outro.mp3", "bg_music.mp3", "top.mp3"):
        (music / name).write_bytes(b"x")
    (music / "bed" / "b.mp3").write_bytes(b"x")
    (music / "bed" / "a.mp3").write_bytes(b"x")
    (music / "bed" / "SOURCES.txt").write_text("rules")
    (music / "bed" / "sub" / "deep.mp3").write_bytes(b"x")
    monkeypatch.setattr(eng, "MUSIC", music)
    got = [p.name for p in eng.bed_tracks()]
    assert got == ["a.mp3", "b.mp3"]
    for day in range(366):
        assert Path(eng.pick_bed(eng.bed_tracks(), day)).name not in (
            "intro.mp3", "outro.mp3", "bg_music.mp3", "top.mp3", "deep.mp3")


def test_g4b_bed_glob_is_empty_without_the_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(eng, "MUSIC", tmp_path / "music")
    assert eng.bed_tracks() == []
    assert eng.pick_bed([], 200) is None


def test_g4b_bed_pick_is_deterministic_by_day_of_year():
    tracks = ["c.mp3", "a.mp3", "b.mp3"]          # any order in, sorted inside
    assert eng.pick_bed(tracks, 0) == "a.mp3"
    assert eng.pick_bed(tracks, 1) == "b.mp3"
    assert eng.pick_bed(tracks, 2) == "c.mp3"
    assert eng.pick_bed(tracks, 283) == "b.mp3"    # 283 % 3 == 1
    assert eng.pick_bed(tracks, 283) == eng.pick_bed(list(reversed(tracks)), 283)


def test_g4b_bed_mix_keeps_the_voice_at_unity():
    """amix's default normalize=1 halved the voice whenever a bed existed
    (measured -19.8 -> -25.7 LUFS). The bed is 0.07, faded in 1 s and out 2 s."""
    fc = _g4b_fc(eng.mux_args("j.mp4", "v.mp3", 300.0, "f.mp4", bgm="bed/a.mp3"))
    assert "amix=inputs=2:duration=first:normalize=0[a]" in fc
    assert "volume=0.07," in fc
    assert "afade=t=in:st=0:d=1.0" in fc
    assert "afade=t=out:st=298.000:d=2.0" in fc          # ends exactly at adur
    assert "aloop=loop=-1:size=2e+09,atrim=0:300.0" in fc  # one track looped, as before
    assert "sidechaincompress" not in fc                 # no ducking
    assert "[1:a]aformat=fltp:44100:stereo,volume=1.0[voice]" in fc


def test_g4b_no_bed_reproduces_todays_mux_args():
    want = ["ffmpeg", "-y", "-i", "j.mp4", "-i", "v.mp3",
            "-filter_complex",
            "[0:v]trim=0:300.0,setpts=PTS-STARTPTS[v];[1:a]aformat=fltp:44100:stereo[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", "f.mp4"]
    assert eng.mux_args("j.mp4", "v.mp3", 300.0, "f.mp4") == want
    assert eng.mux_args("j.mp4", "v.mp3", 300.0, "f.mp4", bgm=None) == want


# ------------------------------------------------------------------ dissolves
def test_g4b_dissolve_plan_skips_sting_and_insight_boundaries():
    # 10 scenes, all produced a segment: boundaries 0 (sting) and 8 (L2) are hard
    plan = eng.dissolve_plan(list(range(10)), 10)
    assert len(plan) == 9
    assert plan[0] is False and plan[8] is False
    assert all(plan[1:8])
    assert sum(plan) == 7


def test_g4b_dissolve_plan_hard_cuts_around_an_empty_scene():
    # scene 4 produced no segment: the join 3 -> 5 spans boundaries 3 and 4
    seg_scenes = [0, 1, 2, 3, 5, 6, 7, 8, 9]
    plan = eng.dissolve_plan(seg_scenes, 10)
    joins = list(zip(seg_scenes, seg_scenes[1:]))
    by = dict(zip(joins, plan))
    assert by[(3, 5)] is False
    assert by[(0, 1)] is False and by[(8, 9)] is False
    assert by[(1, 2)] and by[(2, 3)] and by[(5, 6)] and by[(7, 8)]


def test_g4b_dissolve_plan_small_videos():
    assert eng.dissolve_plan([0], 1) == []
    assert eng.dissolve_plan([0, 1], 2) == [False]
    assert eng.dissolve_plan([0, 1, 2], 3) == [False, False]   # 0 is sting, 1 is n-2
    assert eng.dissolve_plan([0, 1, 2, 3], 4) == [False, True, False]


def test_g4b_xfade_offsets_are_cumulative_probed_minus_half_a_second():
    durs = [9.0, 31.5, 28.0, 35.2, 30.1]
    plan = [False, True, True, False]
    graph, out = eng.xfade_graph(durs, plan)
    parts = graph.split(";")
    # every input is re-timed to 0 and one timebase (TS segments start at pts 1.4 s)
    for i in range(5):
        assert parts[i].startswith(f"[{i}:v]setpts=PTS-STARTPTS,fps=30,format=yuv420p,settb=AVTB")
    # incoming segments of a dissolve are head-padded by 0.5 s of their first frame
    assert "tpad" not in parts[0] and "tpad" not in parts[1]
    assert parts[2].endswith(",tpad=start_mode=clone:start_duration=0.5[s2]")
    assert parts[3].endswith(",tpad=start_mode=clone:start_duration=0.5[s3]")
    assert "tpad" not in parts[4]
    joins = parts[5:]
    assert joins[0] == "[s0][s1]concat=n=2:v=1:a=0[x0]"
    assert joins[1] == "[x0][s2]xfade=transition=fade:duration=0.5:offset=40.000[x1]"  # 9+31.5-0.5
    assert joins[2] == "[x1][s3]xfade=transition=fade:duration=0.5:offset=68.000[x2]"  # 40.5+28-0.5
    assert joins[3] == "[x2][s4]concat=n=2:v=1:a=0[x3]"
    assert out == "[x3]"


def test_g4b_xfade_graph_refuses_unusable_durations():
    assert eng.xfade_graph([9.0], []) is None
    assert eng.xfade_graph([9.0, 5.0], [True, True]) is None      # plan length mismatch
    assert eng.xfade_graph([9.0, 0.0, 5.0], [True, True]) is None  # a failed probe
    assert eng.xfade_graph([9.0, 0.4, 5.0], [True, True]) is None  # shorter than the dissolve
    assert eng.xfade_join_args(["a", "b"], [0, 0], [True], "o.mp4") is None


def test_g4b_xfade_join_keeps_the_encoder():
    args = eng.xfade_join_args(["a.ts", "b.ts", "c.ts"], [10.0, 10.0, 10.0],
                               [False, True], "j.mp4")
    assert args[:8] == ["ffmpeg", "-y", "-i", "a.ts", "-i", "b.ts", "-i", "c.ts"]
    assert args[-8:] == ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-an", "j.mp4"]
    assert args[args.index("-map") + 1] == "[x1]"


def test_g4b_concat_join_reproduces_todays_args():
    assert eng.concat_join_args("c.txt", "j.mp4") == [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "c.txt",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-an", "j.mp4"]


def _g4b_join(monkeypatch, tmp_path, xfade_ok=True, ok_after=None, transitions=True,
              seg_scenes=None):
    calls = []

    def fake_run(cmd, timeout=600, label=""):
        calls.append(cmd)
        return xfade_ok if "-filter_complex" in cmd else True

    monkeypatch.setattr(eng, "safe_run", fake_run)
    monkeypatch.setattr(eng, "dur", lambda p: 30.0)
    seg_scenes = seg_scenes if seg_scenes is not None else list(range(10))
    segs = [f"seg_{i:03d}.ts" for i in seg_scenes]
    oks = iter(ok_after if ok_after is not None else [True, True])
    res = eng.join_scenes(segs, seg_scenes, 10, tmp_path / "joined.mp4",
                          tmp_path / "concat.txt", lambda: next(oks),
                          transitions=transitions)
    return res, calls


def test_g4b_join_applies_dissolves_when_the_graph_works(monkeypatch, tmp_path):
    (ok, how), calls = _g4b_join(monkeypatch, tmp_path)
    assert ok and how == "7 applied"
    assert len(calls) == 1 and "-filter_complex" in calls[0]


def test_g4b_join_falls_back_when_the_graph_fails(monkeypatch, tmp_path):
    (ok, how), calls = _g4b_join(monkeypatch, tmp_path, xfade_ok=False, ok_after=[True])
    assert ok and how == "fallback (hard cuts)"
    assert calls[-1] == eng.concat_join_args(tmp_path / "concat.txt", tmp_path / "joined.mp4")


def test_g4b_join_falls_back_when_the_duration_is_wrong(monkeypatch, tmp_path):
    # ffmpeg exited 0 but _join_ok said no: the concat join runs and decides
    (ok, how), calls = _g4b_join(monkeypatch, tmp_path, ok_after=[False, True])
    assert ok and how == "fallback (hard cuts)"
    assert len(calls) == 2 and "-f" in calls[1] and "concat" in calls[1]


def test_g4b_join_fallback_still_reports_a_failed_concat(monkeypatch, tmp_path):
    (ok, how), _calls = _g4b_join(monkeypatch, tmp_path, xfade_ok=False, ok_after=[False])
    assert ok is False and how == "fallback (hard cuts)"


def test_g4b_join_survives_a_raising_probe(monkeypatch, tmp_path):
    def boom(p):
        raise RuntimeError("probe died")
    monkeypatch.setattr(eng, "safe_run", lambda cmd, timeout=600, label="": True)
    monkeypatch.setattr(eng, "dur", boom)
    ok, how = eng.join_scenes(["a", "b", "c", "d"], [0, 1, 2, 3], 4, tmp_path / "j.mp4",
                              tmp_path / "c.txt", lambda: True)
    assert ok and how == "fallback (hard cuts)"


def test_g4b_transitions_off_is_todays_join(monkeypatch, tmp_path):
    (ok, how), calls = _g4b_join(monkeypatch, tmp_path, transitions=False, ok_after=[True])
    assert ok and how == "off"
    assert calls == [eng.concat_join_args(tmp_path / "concat.txt", tmp_path / "joined.mp4")]


def test_g4b_no_eligible_boundary_is_todays_join(monkeypatch, tmp_path):
    (ok, how), calls = _g4b_join(monkeypatch, tmp_path, seg_scenes=[0, 1], ok_after=[True])
    assert ok and how == "0 applied"
    assert len(calls) == 1 and "-filter_complex" not in calls[0]


def test_g4b_dissolve_is_15_frames():
    assert eng.XFADE_S * eng.FPS == 15


# ------------------------------------------------------------------ config + outro
def test_g4b_flags_default_on_in_both_configs():
    import json
    root = Path(__file__).resolve().parent.parent
    for name in ("config.json", "config.example.json"):
        cfg = json.loads((root / name).read_text(encoding="utf-8"))
        assert cfg["transitions"] is True and cfg["music_bed"] is True, name


def test_g4b_outro_line_fits_both_bumpers():
    """Text burned on a frame is MEASURED (CLAUDE.md). The outro draws it with
    br._font(40) on 1280 px; the vertical outro with br._font(48) on 1080 px."""
    from PIL import Image, ImageDraw
    assert br.OUTRO_LINE == "for AI you can use"
    d = ImageDraw.Draw(Image.new("L", (10, 10)))
    for size, frame_w in ((40, br.W), (48, 1080)):
        bb = d.textbbox((0, 0), br.OUTRO_LINE, font=br._font(size))
        assert bb[2] - bb[0] < frame_w * 0.5, (size, bb)
    src = (Path(__file__).resolve().parent.parent / "factverse").glob("*.py")
    assert not any("for daily AI news" in p.read_text(encoding="utf-8") for p in src)
