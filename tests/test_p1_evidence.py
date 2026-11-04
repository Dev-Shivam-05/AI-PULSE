"""v3-P.1: evidence engine + claim substantiation (docs/spec/ai-pulse-v3p1.md).

Network, ffmpeg, the browser and the LLM are never touched: every seam is
stubbed as the consumer sees it (ap.evidence.*, ev._http_get, ap.llm.*).
tests/conftest.py turns the three P.1 switches OFF by default; each test here
turns on what it needs with _p1_on.
"""
import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factverse import ai_pipeline as ap
from factverse import evidence as ev
from factverse import gates
from factverse import site

_P1_GH = "https://github.com/acme/demo-tool"
_P1_HF = "https://huggingface.co/acme/demo-model"


def _p1_on(monkeypatch, engine=True, required=True, claims=True):
    monkeypatch.setenv("EVIDENCE_ENGINE", "1" if engine else "0")
    monkeypatch.setenv("EVIDENCE_REQUIRED", "1" if required else "0")
    monkeypatch.setenv("CLAIM_SUBSTANTIATION", "1" if claims else "0")


def _p1_scenes(n=6, text="the tool sorts a folder of files by type"):
    return [{"scene_num": i + 1, "narration": f"{text} part {i}", "visual_query": "laptop"}
            for i in range(n)]


def _p1_author_ev(tmp_path, **over):
    clip = tmp_path / "evidence_author.mp4"
    clip.write_bytes(b"\0" * 2000)
    e = ev.empty()
    e.update({"source": "author", "status": "NOT_RUN", "label": "Author demo",
              "wording": ev.wording("NOT_RUN"), "clip": str(clip), "clip_seconds": 12.0,
              "url": f"{_P1_GH}/blob/{'a' * 40}/docs/demo.gif",
              "observed": 'The README presents this demo as "sorting files".',
              "version": "a" * 40,
              "rights": {"path": "docs/demo.gif", "commit": "a" * 40, "license": "MIT",
                         "copyright": "Copyright (c) 2026 Acme", "notice": "",
                         "modified": "Modified by ToolDojo: scaled and re-encoded."}})
    e.update(over)
    return e


def _p1_hosted_ev(tmp_path, **over):
    clip = tmp_path / "evidence_hosted.mp4"
    clip.write_bytes(b"\0" * 2000)
    e = ev.empty()
    obs = "In our hosted-demo run, this input produced image output in about 2 seconds."
    e.update({"source": "hosted", "status": "PASSED_FIXED_TEST", "label": "Hosted test",
              "wording": ev.wording("PASSED_FIXED_TEST"), "clip": str(clip), "clip_seconds": 9.0,
              "url": "https://acme-demo.hf.space", "input": "the Space's first example: cat.jpg",
              "observed": obs, "supported_claims": [obs]})
    e.update(over)
    return e


# ================================================================ the contract
def test_p1_status_wording_is_round_3_verbatim_and_labels_fixed():
    assert ev.WORDING == {
        "NOT_RUN": "Not independently tested.",
        "PASSED_FIXED_TEST": "Passed this specific test.",
        "FAILED_FIXED_TEST": "This test failed under these conditions.",
        "TIMED_OUT": "Did not complete within our 120-second execution limit.",
        "INCONCLUSIVE": "We could not establish a result.",
    }
    assert ev.label("hosted") == "Hosted test" and ev.label("author") == "Author demo"
    assert ev.label("sandbox") == "Sandbox test" and ev.label("none") == ""
    assert ev.CAPTURE_DEADLINE == 120.0 and (ev.CLIP_MIN, ev.CLIP_MAX) == (8.0, 20.0)
    e = ev.empty("x")
    for k in ("source", "status", "label", "wording", "clip", "clip_seconds", "url",
              "captured_at", "input", "observed", "supported_claims", "rights", "version"):
        assert k in e
    assert e["source"] == "none" and not ev.admissible(e)


def test_p1_admissible_needs_a_clip_on_disk_and_the_right_status(tmp_path):
    a = _p1_author_ev(tmp_path)
    assert ev.admissible(a)
    assert not ev.admissible(dict(a, clip=str(tmp_path / "missing.mp4")))
    assert not ev.admissible(dict(a, rights=dict(a["rights"], license="")))
    assert not ev.admissible(dict(a, rights=None))
    h = _p1_hosted_ev(tmp_path)
    assert ev.admissible(h)
    for st in ("FAILED_FIXED_TEST", "TIMED_OUT", "INCONCLUSIVE", "NOT_RUN"):
        assert not ev.admissible(dict(h, status=st)), st
    assert not ev.admissible("planted") and not ev.admissible(None)


def test_p1_ledger_fields_are_coerced_strings(tmp_path):
    assert ev.ledger_fields({"evidence": _p1_author_ev(tmp_path)}) == ("author", "NOT_RUN")
    assert ev.ledger_fields({}) == ("", "")
    assert ev.ledger_fields({"evidence": "x"}) == ("", "")
    assert ev.ledger_fields({"evidence": {"source": ["a"], "status": 7}}) == ("", "")
    assert ev.ledger_fields(None) == ("", "")


def test_p1_catalog_view_drops_the_local_clip(tmp_path):
    v = ev.catalog_view(_p1_author_ev(tmp_path))
    assert "clip" not in v and v["source"] == "author" and v["version"] == "a" * 40
    assert ev.catalog_view(None) is None


# ================================================================ README parsing
_P1_README = """# Demo Tool
![build](https://img.shields.io/badge/x.svg)
## Quick look
![Sorting a folder](docs/assets/demo.gif)
<img src="./docs/hero.png" alt="hero still">
<video src="https://github.com/user-attachments/assets/1234-5678"></video>
https://github.com/user-attachments/assets/abcd-ef
![rel](https://github.com/acme/demo-tool/releases/download/v1/clip.mp4)
![other](https://raw.githubusercontent.com/someone/else/main/x.gif)
## Features
<img src="https://raw.githubusercontent.com/acme/demo-tool/main/media/usage.mp4" alt="usage clip">
![blob](https://github.com/Acme/Demo-Tool/blob/main/media/b.webm?raw=true)
![escape](../../etc/passwd.gif)
Try it: https://huggingface.co/spaces/acme/demo and https://acme-demo.hf.space
"""


def test_p1_readme_media_accepts_only_committed_animated_media():
    acc, rej = ev.readme_media(_P1_README, "github", "acme/demo-tool")
    assert [m["path"] for m in acc] == ["docs/assets/demo.gif", "media/usage.mp4", "media/b.webm"]
    assert acc[0]["alt"] == "Sorting a folder" and acc[0]["heading"] == "Quick look"
    assert acc[1]["alt"] == "usage clip" and acc[1]["heading"] == "Features"
    whys = {r["ref"][:45]: r["why"] for r in rej}
    assert any("unresolved provenance" in w for w in whys.values())
    assert sum("unresolved provenance" in r["why"] for r in rej) == 2   # <video> + bare link
    assert any(r["why"] == "release asset (not committed in the repo)" for r in rej)
    assert any(r["why"] == "external host" for r in rej)                 # other repo + badge
    assert any(r["why"] == "still image" for r in rej)
    assert any(r["why"] == "unsafe path" for r in rej)


def test_p1_resolve_asset_hf_and_traversal():
    assert ev.resolve_asset("https://huggingface.co/acme/demo-model/resolve/main/assets/reel.mp4",
                            "hf", "acme/demo-model") == ("assets/reel.mp4", "")
    assert ev.resolve_asset("https://huggingface.co/other/m/resolve/main/a.mp4",
                            "hf", "acme/demo-model")[0] == ""
    assert ev.resolve_asset("a/../../b.gif", "github", "acme/x")[0] == ""
    assert ev.resolve_asset("//cdn.example.com/a.gif", "github", "acme/x")[1] == "external host"
    assert ev.resolve_asset("a\\b.gif", "github", "acme/x")[0] == ""


def test_p1_pick_media_prefers_demo_names_then_video():
    media = [{"path": "a/pet.gif", "ext": ".gif", "alt": ""},
             {"path": "a/clip.mp4", "ext": ".mp4", "alt": ""},
             {"path": "a/hero.gif", "ext": ".gif", "alt": ""},
             {"path": "a/x.gif", "ext": ".gif", "alt": "Demo of sorting"}]
    assert [m["path"] for m in ev.pick_media(media)] == ["a/hero.gif", "a/x.gif", "a/clip.mp4",
                                                         "a/pet.gif"]


def test_p1_readme_spaces_ids_and_hosts():
    assert ev.readme_spaces(_P1_README) == ["acme/demo", "acme-demo.hf.space"]
    assert ev.readme_spaces("") == [] and ev.readme_spaces(None) == []


def test_p1_copyright_line_skips_the_apache_template():
    mit = "MIT License\n\nCopyright (c) 2026 anymodel bot contributors\n\nPermission is hereby"
    assert ev.copyright_line(mit) == "Copyright (c) 2026 anymodel bot contributors"
    apache = "Apache License\n...\n   Copyright [yyyy] [name of copyright owner]\n"
    assert ev.copyright_line(apache) == ""
    assert ev.copyright_line("Copyright 2026 wangzan101") == "Copyright 2026 wangzan101"
    assert ev.copyright_line(None) == ""


# ================================================================ clip planning (pure)
def test_p1_author_plan_keeps_the_sequence_whole_when_it_can():
    assert ev.author_plan(1.0) is None and ev.author_plan("x") is None
    assert ev.author_plan(float("nan")) is None
    p = ev.author_plan(4.0)
    assert p["length"] == 4.0 and p["speed"] == 1.0 and p["seconds"] == 8.0 and p["whole"]
    p = ev.author_plan(15.7)
    assert p["speed"] == 1.0 and p["seconds"] == 15.7
    p = ev.author_plan(30.0)                       # whole, sped up to CLIP_MAX
    assert p["length"] == 30.0 and p["speed"] == 1.5 and p["seconds"] == 20.0 and p["whole"]
    p = ev.author_plan(44.9)                       # longer than 2x: first 20 s
    assert p["length"] == 20.0 and p["speed"] == 1.0 and not p["whole"]
    assert "first 20.0 s of 44.9 s" in ev.modification(p, 44.9)
    assert "sped up 1.50x" in ev.modification(ev.author_plan(30.0), 30.0)
    assert "last frame held" in ev.modification(ev.author_plan(4.0), 4.0)


def test_p1_master_args_letterbox_speed_and_hold():
    args = ev.master_args("in.gif", "out.mp4", 0.0, 4.0)
    vf = args[args.index("-vf") + 1]
    assert "tpad=stop_mode=clone:stop_duration=4.000" in vf and "pad=1920:1080" in vf
    assert args[args.index("-t", args.index("-vf")) + 1] == "8.000"
    args = ev.master_args("in.mp4", "o.mp4", 0.0, 30.0, speed=1.5)
    vf = args[args.index("-vf") + 1]
    assert vf.startswith("setpts=0.666667*") and "stop_duration=0.000" in vf


def test_p1_slot_plan_holds_short_and_speeds_long_keeping_the_end():
    p = ev.slot_plan(12.0, 20.0)
    assert p == {"start": 0.0, "speed": 1.0, "hold": 8.5, "out": 20.5}
    p = ev.slot_plan(15.0, 12.0)                     # 1.25x fits
    assert p["start"] == 0.0 and p["speed"] == 1.25 and p["out"] == 12.5
    p = ev.slot_plan(20.0, 10.0)                     # past 1.5x: drop the HEAD
    assert p["speed"] == 1.5 and p["start"] == 5.0 and p["out"] == 10.5
    assert ev.slot_plan(0, 10) is None and ev.slot_plan(5, "x") is None


def test_p1_slot_args_burn_the_label_from_frame_zero():
    plan = ev.slot_plan(12.0, 20.0)
    args = ev.slot_args("c.mp4", "l.png", "o.mp4", plan)
    g = args[args.index("-filter_complex") + 1]
    assert "overlay=48:40" in g and "tpad=stop_mode=clone:stop_duration=8.500" in g
    assert args[args.index("-t") + 1] == "20.500" and "-loop" in args
    g2 = ev.slot_args("c.mp4", "", "o.mp4", plan)
    assert "overlay" not in g2[g2.index("-filter_complex") + 1]


def test_p1_hosted_cut_pads_and_compresses():
    c = ev.hosted_cut(10.0, 14.0)
    assert c == {"start": 9.0, "length": 7.5, "speed": 1.0, "seconds": 8.0}
    c = ev.hosted_cut(5.0, 40.0)                     # 38.5 s of sequence -> 1.925x
    assert c["speed"] == pytest.approx(1.925) and c["seconds"] == 20.0
    c = ev.hosted_cut(2.0, 110.0)                    # past MAX_SPEEDUP: keep the end
    assert c["speed"] == 4.0 and c["start"] + c["length"] == pytest.approx(112.5)
    assert ev.hosted_cut(10.0, 5.0) is None


# ================================================================ Gradio plan + classify
def _p1_cfg(examples=True, gallery=False, primary=True):
    comps = [{"id": 1, "type": "image", "props": {"label": "Input"}},
             {"id": 2, "type": "button", "props": {"value": "Generate",
                                                    "variant": "primary" if primary else "secondary"}},
             {"id": 3, "type": "image", "props": {"label": "Result", "elem_id": "out-img"}},
             {"id": 4, "type": "number", "props": {"label": "Seed"}},
             {"id": 9, "type": "button", "props": {"value": "Clear", "variant": "secondary"}}]
    deps = [{"targets": [[2, "click"]], "inputs": [1], "outputs": [3, 4]},
            {"targets": [[9, "click"]], "inputs": [], "outputs": [1, 3]}]
    if examples:
        comps.append({"id": 5, "type": "dataset", "props": {
            "samples": [[{"path": "/tmp/gradio/abc/cat.jpg", "orig_name": "cat.jpg"}],
                        [{"path": "/tmp/x/dog.jpg"}]]}})
        deps.append({"targets": [[5, "click"]], "inputs": [5], "outputs": [1]})
    if gallery:
        comps.append({"id": 6, "type": "gallery", "props": {}})
        deps.append({"targets": [[6, "select"]], "inputs": [], "outputs": [1, 4]})
    return {"components": comps, "dependencies": deps, "version": "5.0"}


def test_p1_gradio_plan_uses_the_spaces_own_examples():
    p = ev.gradio_plan(_p1_cfg())
    assert p["button"] == "#component-2" and p["button_text"] == "Generate"
    assert p["example"] == "#component-5" and p["example_type"] == "dataset"
    assert p["outputs"] == ["#out-img"] and p["output_types"] == ["image"]   # number dropped
    assert p["output_labels"] == ["Result"]
    assert p["inputs"] == ["the Space's first example: cat.jpg", "the Space's second example: dog.jpg"]
    assert "/tmp" not in json.dumps(p)                                         # never a path
    g = ev.gradio_plan(_p1_cfg(examples=False, gallery=True))
    assert g["example"] == "#component-6" and g["example_type"] == "gallery"
    assert ev.gradio_plan(_p1_cfg(examples=False)) is None                     # no fixed input
    assert ev.gradio_plan({"components": "x"}) is None and ev.gradio_plan(None) is None


@pytest.mark.parametrize("outcome,status", [
    ({"unavailable": True}, None),
    ({"error": "ZeroGPU quota exceeded. You have exceeded your GPU quota"}, None),
    ({"error": "Please log in to use this Space"}, None),
    ({"error": "ValueError: bad image"}, "FAILED_FIXED_TEST"),
    ({"changed": True, "nonempty": True, "visible": True}, "PASSED_FIXED_TEST"),
    ({"changed": True, "nonempty": True, "visible": False}, "INCONCLUSIVE"),
    ({"changed": True, "nonempty": True, "pending": True, "visible": True}, "INCONCLUSIVE"),
    ({"deadline": True, "queued": True}, None),
    ({"deadline": True}, "TIMED_OUT"),
    ({"inconclusive": "TimeoutError: no button"}, "INCONCLUSIVE"),
    ("garbage", "INCONCLUSIVE"),
])
def test_p1_classify_maps_outcomes_to_the_five_statuses(outcome, status):
    assert ev.classify(outcome) == status


def _p1_png(color=None, noise=False):
    from PIL import Image
    img = Image.new("RGB", (64, 64), color or (255, 255, 255))
    if noise:
        for x in range(0, 64, 2):
            for y in range(64):
                img.putpixel((x, y), (0, 0, 0))
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def test_p1_visible_result_needs_a_change_and_a_non_blank_region():
    blank, striped = _p1_png(), _p1_png(noise=True)
    assert ev.visible_result("image", blank, striped)
    assert not ev.visible_result("image", striped, striped)        # nothing changed
    assert not ev.visible_result("model3d", striped, _p1_png((0, 0, 0)))   # changed to blank
    assert ev.visible_result("textbox", None, None, "a caption")
    assert not ev.visible_result("textbox", None, None, "  ")
    assert ev.pixel_change(b"junk", b"junk") == (0.0, 0.0)
    assert ev.result_slot({"output_types": ["textbox", "image"]}) == 1
    assert ev.result_slot({"output_types": ["textbox"]}) == 0


# ================================================================ probe / gather (stubbed network)
class _P1Resp:
    def __init__(self, status=200, text="", js=None):
        self.status_code, self.text, self._js = status, text, js

    def json(self):
        if self._js is None:
            raise ValueError("no json")
        return self._js


def _p1_net(monkeypatch, pages):
    def fake(url, **kw):
        for key, val in pages.items():
            if key in url:
                if isinstance(val, Exception):
                    raise val
                return val
        return _P1Resp(404)
    monkeypatch.setattr(ev, "_http_get", fake)


def test_p1_probe_finds_author_media_on_a_licensed_repo(monkeypatch):
    _p1_net(monkeypatch, {
        "raw.githubusercontent.com/acme/demo-tool/HEAD/README.md": _P1Resp(text=_P1_README.split("Try it:")[0]),
        "api.github.com/repos/acme/demo-tool": _P1Resp(js={"license": {"spdx_id": "MIT"},
                                                          "default_branch": "main"}),
    })
    pr = ev.probe({"url": _P1_GH})
    assert pr["source"] == "author" and pr["license_ok"] and pr["branch"] == "main"
    assert [m["path"] for m in pr["author"]][0] == "media/usage.mp4"     # "usage" + a video file


def test_p1_probe_prefers_a_running_space_and_rejects_other_licences(monkeypatch):
    _p1_net(monkeypatch, {
        "raw.githubusercontent.com/acme/demo-tool/HEAD/README.md": _P1Resp(text=_P1_README),
        "api.github.com/repos/acme/demo-tool": _P1Resp(js={"license": {"spdx_id": "AGPL-3.0"}}),
        "huggingface.co/api/spaces/acme/demo": _P1Resp(js={"sdk": "gradio", "host": "https://acme-demo.hf.space",
                                                           "runtime": {"stage": "RUNNING"}, "sha": "f" * 40}),
    })
    pr = ev.probe({"url": _P1_GH})
    assert pr["source"] == "hosted" and not pr["license_ok"]
    assert pr["hosted"][0]["sha"] == "f" * 40
    # the same README with a SLEEPING space and a non-admitted licence: nothing
    _p1_net(monkeypatch, {
        "raw.githubusercontent.com/acme/demo-tool/HEAD/README.md": _P1Resp(
            text="# x\n![d](demo.gif)\nhttps://huggingface.co/spaces/acme/demo"),
        "api.github.com/repos/acme/demo-tool": _P1Resp(js={"license": {"spdx_id": "CC-BY-4.0"}}),
        "huggingface.co/api/spaces/acme/demo": _P1Resp(js={"sdk": "gradio", "runtime": {"stage": "SLEEPING"},
                                                           "host": "https://acme-demo.hf.space"}),
    })
    assert ev.probe({"url": _P1_GH})["source"] == "none"


def test_p1_probe_says_when_it_could_not_look(monkeypatch):
    _p1_net(monkeypatch, {})                                   # every URL 404s
    assert ev.probe({"url": _P1_GH}) is None
    assert ev.probe({"url": "https://www.producthunt.com/p/x"}) is None
    assert ev.probe("not a dict") is None
    _p1_net(monkeypatch, {"raw.githubusercontent.com": RuntimeError("boom")})
    monkeypatch.setattr(ev, "_readme_raw", lambda k, i: 1 / 0)
    assert ev.probe({"url": _P1_GH}) is None                   # raised inside: None, not a raise


def test_p1_gather_prefers_hosted_then_falls_back_to_author(monkeypatch, tmp_path):
    pr = {"source": "hosted", "kind": "github", "ident": "acme/demo-tool", "license_ok": True,
          "license": "MIT", "hosted": [{"id": "acme/demo", "host": "https://acme-demo.hf.space",
                                        "sdk": "gradio", "stage": "RUNNING"}],
          "author": [{"path": "docs/demo.gif", "ext": ".gif"}], "rejected": []}
    calls = []
    monkeypatch.setattr(ev, "try_hosted", lambda p, o, d: calls.append("hosted") or (None, ["x: FAILED"]))
    monkeypatch.setattr(ev, "try_author", lambda p, o: calls.append("author") or _p1_author_ev(tmp_path))
    got = ev.gather({"url": _P1_GH}, out_dir=tmp_path, probe_result=pr)
    assert calls == ["hosted", "author"] and got["source"] == "author"
    # hosted passes: author is never tried
    calls.clear()
    monkeypatch.setattr(ev, "try_hosted", lambda p, o, d: calls.append("hosted") or (_p1_hosted_ev(tmp_path), []))
    assert ev.gather({"url": _P1_GH}, out_dir=tmp_path, probe_result=pr)["source"] == "hosted"
    assert calls == ["hosted"]


def test_p1_gather_none_record_and_could_not_look(monkeypatch, tmp_path):
    pr = {"source": "none", "kind": "github", "ident": "acme/x", "license_ok": False,
          "license": "AGPL-3.0", "hosted": [], "author": [{"path": "a.gif", "ext": ".gif"}],
          "rejected": []}
    got = ev.gather({"url": _P1_GH}, out_dir=tmp_path, probe_result=pr)
    assert got["source"] == "none" and "AGPL-3.0" in got["note"]
    monkeypatch.setattr(ev, "probe", lambda item, readme=None: None)
    assert ev.gather({"url": _P1_GH}, out_dir=tmp_path) is None
    monkeypatch.setattr(ev, "probe", lambda item, readme=None: {"oops": 1})   # KeyError inside
    assert ev.gather({"url": _P1_GH}, out_dir=tmp_path) is None


class _P1Stream:
    def __init__(self, chunks, headers=None, status=200):
        self.chunks, self.headers, self.status_code = chunks, headers or {}, status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_content(self, n):
        yield from self.chunks


def test_p1_bounded_download_has_a_byte_cap_and_a_wall_clock(monkeypatch, tmp_path):
    import requests
    dest = tmp_path / "a.gif"
    monkeypatch.setattr(requests, "get", lambda *a, **k: _P1Stream([b"x" * 10] * 3))
    assert ev.bounded_download("u", dest, max_bytes=100) == 30 and dest.exists()
    monkeypatch.setattr(requests, "get", lambda *a, **k: _P1Stream([b"x" * 60] * 3))
    assert ev.bounded_download("u", dest, max_bytes=100) is None and not dest.exists()
    monkeypatch.setattr(requests, "get", lambda *a, **k: _P1Stream([], {"content-length": "999"}))
    assert ev.bounded_download("u", dest, max_bytes=100) is None
    # a slow drip: requests' per-read timeout never fires, the wall clock does
    ticks = iter([0.0, 0.0, 30.0, 61.0, 90.0])
    monkeypatch.setattr(ev.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(requests, "get", lambda *a, **k: _P1Stream([b"x"] * 4))
    assert ev.bounded_download("u", dest, max_bytes=100, seconds=60) is None
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(OSError("net")))
    assert ev.bounded_download("u", dest) is None


def test_p1_attribution_is_one_line_with_licence_copyright_notice_and_modification(tmp_path):
    a = _p1_author_ev(tmp_path, rights=dict(_p1_author_ev(tmp_path)["rights"], license="Apache-2.0",
                                            notice="Mika Copyright 2026 wangzan101"))
    line = ev.attribution_line(a)
    assert "\n" not in line and line.startswith(ev.AUTHOR_MARK)
    for part in (a["url"], "Apache-2.0 License", "Copyright (c) 2026 Acme",
                 "NOTICE: Mika Copyright 2026 wangzan101", "Modified by ToolDojo"):
        assert part in line
    assert ev.attribution_line(_p1_hosted_ev(tmp_path)) == ""
    assert ev.attribution_line({"source": "author", "rights": "x"}) == ""


def test_p1_label_text_names_date_or_repo(tmp_path):
    assert ev.label_text(_p1_hosted_ev(tmp_path)).startswith("Hosted test · 20")
    assert ev.label_text(_p1_author_ev(tmp_path)) == "Author demo · acme/demo-tool"
    assert ev.label_text(ev.empty()) == ""


# ================================================================ writer hand-off + overclaims
def test_p1_writer_brief_states_what_each_source_allows(tmp_path):
    a = ev.writer_brief(_p1_author_ev(tmp_path))
    assert "The author's demo shows" in a and "did NOT run this tool" in a
    assert "Not independently tested." in a and "we tested" in a      # named as forbidden
    h = ev.writer_brief(_p1_hosted_ev(tmp_path))
    assert "In our hosted-demo run" in h and "Passed this specific test." in h
    assert "works offline" in h
    assert ev.writer_brief(ev.empty()) == ""


def test_p1_overclaims_by_source(tmp_path):
    s = {"evidence": _p1_author_ev(tmp_path), "scenes": [
        {"narration": "The author's demo shows it sorting files."},
        {"narration": "We tested it on a folder and in our testing it was quick."}]}
    assert ev.overclaims(s) == ["We tested", "in our testing"]
    s["scenes"][1]["narration"] = "It is not independently tested."
    assert ev.overclaims(s) == []
    h = {"evidence": _p1_hosted_ev(tmp_path), "scenes": [
        {"narration": "In our hosted-demo run, this input produced a rotated image."},
        {"narration": "It works offline and runs on your laptop."}]}
    assert ev.overclaims(h) == ["works offline", "runs on your laptop"]
    assert ev.overclaims({"scenes": [{"narration": "we tested"}]}) == []     # no evidence
    assert ev.overclaims({"evidence": _p1_author_ev(tmp_path), "scenes": ["x", None]}) == []


def test_p1_fact_sources_read_the_evidence_the_writer_was_given(tmp_path):
    s = {"grounding": "README text", "evidence": _p1_hosted_ev(tmp_path),
         "verified_facts": {"stars": 10}}
    src = gates.fact_sources(s)
    assert src.index("VERIFIED FACTS") < src.index("EVIDENCE") < src.index("README text")
    assert "In our hosted-demo run" in src
    assert gates.fact_sources({"grounding": "g"}) == "g"


# ================================================================ planted key (the receipts trap)
def test_p1_validate_script_pops_a_planted_evidence():
    s = {"title": "T", "scenes": _p1_scenes(), "evidence": {"source": "hosted",
                                                            "status": "PASSED_FIXED_TEST"}}
    out = ap._validate_script(s, "T")
    assert "evidence" not in out
    assert "evidence" in ap._CARRY


@pytest.mark.parametrize("pass_name", ["critique_pass", "enforce_length", "enforce_max_length",
                                       "advice"])
def test_p1_a_planted_evidence_never_survives_a_rewrite_pass(monkeypatch, tmp_path, pass_name):
    real = _p1_author_ev(tmp_path)
    planted = {"source": "hosted", "status": "PASSED_FIXED_TEST", "clip": "/etc/x.mp4",
               "supported_claims": ["2x faster"]}
    if pass_name == "enforce_max_length":
        base_n, new_n, words = 8, 8, "word " * 120
        new_words = "word " * 70
    elif pass_name == "enforce_length":
        base_n, new_n, words, new_words = 6, 8, "short ", "a much longer narration " * 12
    else:
        base_n, new_n, words, new_words = 8, 8, "word " * 80, "word " * 80
    script = {"title": "T", "thumb_text": "", "description": "d", "tags": [], "format": "tool",
              "scenes": _p1_scenes(base_n, words), "evidence": real}
    answer = {"title": "T2", "description": "d", "tags": [], "evidence": planted,
              "scenes": _p1_scenes(new_n, new_words)}
    monkeypatch.setattr(ap.llm, "generate_json", lambda p, **k: json.loads(json.dumps(answer)))
    if pass_name == "critique_pass":
        out = ap.critique_pass(script)
    elif pass_name == "enforce_length":
        out = ap.enforce_length(script, 400)
    elif pass_name == "enforce_max_length":
        out = ap.enforce_max_length(script, 900)
    else:   # the advice-gate rewrite in run(): validate, then _carry_over
        fixed = ap._validate_script(json.loads(json.dumps(answer)), "T")
        out = ap._carry_over(script, fixed)
    assert out is not script, "the rewrite must actually have been applied"
    assert out["evidence"] == real


# ================================================================ script_tool integration
def _p1_tool_stubs(monkeypatch, gathered, answer=None):
    readme = ("The tool sorts files for you. " * 60) + "\n```bash\npip install demo-tool\n```\n"
    prompts = []
    monkeypatch.setattr(ap, "fetch_text", lambda u, limit=4000: readme[:limit])
    monkeypatch.setattr(ap, "_verified_facts", lambda u: {})
    monkeypatch.setattr(ap, "_top_issues", lambda u: [])
    monkeypatch.setattr(ap.evidence, "gather", lambda item, **k: gathered)
    ans = answer or {"title": "Demo Tool", "scenes": _p1_scenes(),
                     "deliverable": {"kind": "command", "text": "pip install demo-tool", "url": _P1_GH},
                     "evidence": {"source": "hosted", "status": "PASSED_FIXED_TEST"}}
    monkeypatch.setattr(ap.llm, "generate_json", lambda p, **k: prompts.append(p) or json.loads(json.dumps(ans)))
    return prompts


def test_p1_no_admissible_evidence_skips_the_candidate_without_a_writer_call(monkeypatch, capsys):
    _p1_on(monkeypatch)
    prompts = _p1_tool_stubs(monkeypatch, ev.empty("no hosted demo, no committed demo media"))
    assert ap.script_tool({"title": "acme/demo-tool", "source": "github/trending", "url": _P1_GH}) is None
    assert prompts == []
    assert "no admissible evidence" in capsys.readouterr().out
    prompts = _p1_tool_stubs(monkeypatch, None)                       # could not look
    assert ap.script_tool({"title": "acme/demo-tool", "source": "g", "url": _P1_GH}) is None
    assert prompts == []


def test_p1_admissible_evidence_reaches_the_writer_and_the_script(monkeypatch, tmp_path):
    _p1_on(monkeypatch)
    real = _p1_author_ev(tmp_path)
    prompts = _p1_tool_stubs(monkeypatch, real)
    s = ap.script_tool({"title": "acme/demo-tool", "source": "github/trending", "url": _P1_GH})
    assert s and s["evidence"] == real                                # not the planted one
    assert "The author's demo shows" in prompts[0] and "EVIDENCE" in prompts[0]


def test_p1_required_off_proceeds_with_a_none_record(monkeypatch):
    _p1_on(monkeypatch, required=False)
    _p1_tool_stubs(monkeypatch, None)
    s = ap.script_tool({"title": "acme/demo-tool", "source": "g", "url": _P1_GH})
    assert s and s["evidence"]["source"] == "none"


def test_p1_engine_off_is_the_previous_behaviour(monkeypatch):
    _p1_on(monkeypatch, engine=False)
    called = []
    _p1_tool_stubs(monkeypatch, None)
    monkeypatch.setattr(ap.evidence, "gather", lambda *a, **k: called.append(1))
    s = ap.script_tool({"title": "acme/demo-tool", "source": "g", "url": _P1_GH})
    assert s and "evidence" not in s and called == []


def test_p1_probe_gate_skips_before_the_three_slots(monkeypatch):
    _p1_on(monkeypatch)
    tried = []
    probes = {"https://github.com/a/none1": {"source": "none"},
              "https://github.com/a/none2": {"source": "none"},
              "https://github.com/a/unknown": None,
              "https://github.com/a/author": {"source": "author"},
              "https://github.com/a/hosted": {"source": "hosted"},
              "https://github.com/a/fourth": {"source": "author"}}
    monkeypatch.setattr(ap.evidence, "probe", lambda c, readme=None: probes[c["url"]])
    monkeypatch.setattr(ap, "script_tool", lambda c: tried.append((c["url"], c.get("_evidence_probe"))) or None)
    monkeypatch.setattr(ap, "mark_failed", lambda t: None)
    monkeypatch.setattr(ap, "pick_evergreen_topic", lambda r: None)
    monkeypatch.setattr(ap, "script_news", lambda *a, **k: None)
    ap.build_script("tool", [{"title": u.rsplit("/", 1)[-1], "kind": "tool", "url": u} for u in probes])
    assert [u for u, _ in tried] == ["https://github.com/a/unknown", "https://github.com/a/author",
                                     "https://github.com/a/hosted"]
    assert tried[1][1] == {"source": "author"}                         # handed to gather


# ================================================================ description attribution
def test_p1_attribution_line_sits_under_the_deliverable_once(monkeypatch, tmp_path):
    _p1_on(monkeypatch)
    a = _p1_author_ev(tmp_path)
    s = {"title": "Demo Tool", "format": "tool", "description": "Hook line.\n\nBody text.",
         "deliverable": {"kind": "command", "text": "pip install demo-tool", "url": _P1_GH},
         "evidence": a}
    ap.place_description_blocks(s)
    ap.place_description_blocks(s)                                       # idempotent
    d = s["description"]
    line = ev.attribution_line(a)
    assert d.count(ev.AUTHOR_MARK) == 1 and line in d
    assert d.index(ap._DL_MARK) < d.index(line) < d.index("Body text.")
    # a rewrite mangled the line: the stale copy is cut, the true one goes back
    s["description"] = d.replace(line, ev.AUTHOR_MARK + " something else")
    ap.place_description_blocks(s)
    assert s["description"].count(ev.AUTHOR_MARK) == 1 and line in s["description"]
    # hosted evidence carries no attribution line
    h = dict(s, evidence=_p1_hosted_ev(tmp_path), description="Hook.\n\nBody.")
    ap.place_description_blocks(h)
    assert ev.AUTHOR_MARK not in h["description"]


# ================================================================ clip placement
def test_p1_place_clip_replaces_the_recording_and_leads(monkeypatch, tmp_path):
    monkeypatch.setattr(ev.fv, "TEMP", tmp_path)
    made = []
    monkeypatch.setattr(ev, "render_slot_clip",
                        lambda e, share, out, with_label=True: made.append((share, with_label)) or out)
    s = {"evidence": _p1_author_ev(tmp_path)}
    clips = [["t/statcard_01.mp4", "t/screencap/chunk_000.mp4"], ["t/screencap/chunk_001.mp4"]]
    assert ev.place_clip(s, clips, [20.0, 30.0]) == 10.0
    assert clips[0][0].endswith("evidence_slot.mp4") and clips[0][1] == "t/statcard_01.mp4"
    assert len(clips[0]) == 2 and clips[1] == ["t/screencap/chunk_001.mp4"]    # never stacked
    assert made == [(10.0, True)]
    # an empty scene: the clip is its only one
    clips = [[], ["x"]]
    assert ev.place_clip(s, clips, [18.0, 5.0]) == 18.0 and len(clips[0]) == 1


def test_p1_place_clip_fails_soft_and_says_so(monkeypatch, tmp_path):
    monkeypatch.setattr(ev, "render_slot_clip", lambda *a, **k: None)
    clips = [["t/screencap/chunk_000.mp4"]]
    assert ev.place_clip({"evidence": _p1_author_ev(tmp_path)}, clips, [20.0]) is None
    assert clips == [["t/screencap/chunk_000.mp4"]]                             # untouched
    assert ev.place_clip({"evidence": ev.empty()}, clips, [20.0]) is None
    assert ev.place_clip({"evidence": _p1_author_ev(tmp_path)}, clips, None) is None
    monkeypatch.setattr(ev, "render_slot_clip", lambda *a, **k: 1 / 0)
    assert ev.place_clip({"evidence": _p1_author_ev(tmp_path)}, clips, [20.0]) is None


def test_p1_lead_index():
    assert ev.lead_index([]) is None
    assert ev.lead_index(["a/statcard_1.mp4", "a/chunk.mp4"]) == 1
    assert ev.lead_index(["a/codecard.mp4", "a/receiptcard.mp4"]) == 0


# ================================================================ substantiation (row 3)
def test_p1_the_gpu_unlock_title_is_attributed(monkeypatch):
    _p1_on(monkeypatch)
    s = {"title": "Double Your AI Speed: gpu-unlock for GeForce RTX",
         "thumb_text": "2X AI SPEED. FREE.", "format": "tool"}
    r = gates.substantiate_claims(s)
    assert s["title"] == "Claimed 2× AI Speed: gpu-unlock for GeForce RTX"
    assert s["thumb_text"] == "CLAIMED 2X AI SPEED."
    assert r["fixed"] == ["title", "thumb_text"]


def test_p1_news_claims_are_attributed_or_dropped(monkeypatch):
    _p1_on(monkeypatch)
    s = {"title": "Codex: 60% Sales Boost, 75+ Hrs Saved", "thumb_text": "", "format": "news"}
    gates.substantiate_claims(s)
    assert s["title"] == "Codex: Claimed 60% Sales Boost, Claimed 75+ Hrs Saved"
    s = {"title": "Nvidia Backs AI Startup Cutting GPU Costs", "thumb_text": "56% GPU Cost Cut"}
    r = gates.substantiate_claims(s)
    assert s["thumb_text"] == "" and r["fixed"] == ["thumb_text"]   # 5 words cannot burn


def test_p1_a_claim_mid_clause_is_dropped_or_replaced_never_mangled(monkeypatch):
    _p1_on(monkeypatch)
    s = {"title": "Make Stable Diffusion 3x Faster", "titles": ["Make Stable Diffusion 3x Faster",
                                                                "Stable Diffusion, Explained"]}
    gates.substantiate_claims(s)
    assert s["title"] == "Stable Diffusion, Explained"              # the clean alternate
    s = {"title": "Jev Ultrafast: Free AI Agent Runs Websites in 7 Secs", "format": "tool",
         "signal_title": "acme/jev: fast agent"}
    gates.substantiate_claims(s)
    assert s["title"] == "How to use jev (free)"                    # dropped, then the template
    s = {"title": "Big Model: Runs 3x Faster, Local Setup Guide", "format": "news"}
    gates.substantiate_claims(s)
    assert "3x" not in s["title"] and "Big Model" in s["title"]


def test_p1_an_observed_claim_stays(monkeypatch, tmp_path):
    _p1_on(monkeypatch)
    h = _p1_hosted_ev(tmp_path, supported_claims=["The output appeared 2x faster than the input"])
    s = {"title": "2x Faster: Demo Tool Tested", "thumb_text": "2X FASTER", "evidence": h}
    r = gates.substantiate_claims(s)
    assert s["title"] == "2x Faster: Demo Tool Tested" and r["fixed"] == []
    # an author demo supports NOTHING, even with the same sentence planted in it
    a = _p1_author_ev(tmp_path, supported_claims=["2x faster"])
    s = {"title": "2x Faster: Demo Tool", "evidence": a}
    gates.substantiate_claims(s)
    assert s["title"] == "Claimed 2x Faster: Demo Tool"


def test_p1_substantiation_is_a_noop_off_and_never_raises(monkeypatch):
    _p1_on(monkeypatch, claims=False)
    s = {"title": "Double Your Speed: x"}
    assert gates.substantiate_claims(s)["fixed"] == [] and s["title"] == "Double Your Speed: x"
    _p1_on(monkeypatch)
    for junk in (None, "x", {"title": 5, "thumb_text": ["a"], "evidence": "planted"}):
        gates.substantiate_claims(junk)
    s = {"title": "A" * 80 + ": 2x Faster"}                          # attribution would overflow
    gates.substantiate_claims(s)
    assert len(s["title"]) <= gates.TITLE_MAX and "2x" not in s["title"]


def test_p1_outcome_claims_detector():
    claims = lambda t: [c["text"] for c in gates.outcome_claims(t)]
    assert claims("Make SD 3x Faster") == ["3x"]
    assert claims("Runs 2.5× quicker") == ["2.5×"]
    assert claims("3 times faster inference") == ["3 times faster"]
    assert claims("Cuts costs by 40%") == ["Cuts costs by 40%"]
    assert claims("Run Llama in 10 Seconds") == ["in 10 Seconds"]
    for clean in ("RTX 4090 vs 2x2 grid", "AI Music Now Half of All Uploads",
                  "68% of Americans Fear Tech", "Grok vs GPT: 97% Democrat Lean",
                  "FREE. 2,408 STARS.", "Run Nemotron: 40 Languages Offline", "Double-click it"):
        assert claims(clean) == [], clean


def test_p1_thumb_fits_is_measured_and_word_capped():
    assert gates.thumb_fits("CLAIMED 2X AI SPEED.")
    assert not gates.thumb_fits("CLAIMED 56% GPU COST CUT")         # 5 words: the composer cuts one
    assert not gates.thumb_fits("X" * 27)
    assert gates.thumb_fits("")


# ================================================================ run(): ledger + order
def _p1_run(monkeypatch, tmp_path, script):
    rows = []
    monkeypatch.setattr(ap.fv, "TEMP", tmp_path)
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: None)
    monkeypatch.setattr(ap.signal_engine, "rank", lambda limit=20: [])
    monkeypatch.setattr(ap, "decide_format", lambda f, r: ("tool", None))
    monkeypatch.setattr(ap, "build_script", lambda f, r, v: script)
    monkeypatch.setattr(ap, "too_many_failures", lambda t: False)
    monkeypatch.setattr(ap.screencap, "capture", lambda s: None)
    monkeypatch.setattr(ap.screencap, "inject_code_card", lambda *a, **k: 0)
    monkeypatch.setattr(ap.receipts, "install_scene_idx", lambda s: None)
    monkeypatch.setattr(ap.receipts, "inject_receipt_clip", lambda *a, **k: 0)
    monkeypatch.setattr(ap.eng, "step3_download", lambda s: [["stock.mp4"] for _ in s["scenes"]])
    monkeypatch.setattr(ap, "synthesize_voice", lambda n, s: ("a.mp3", [(0.0, 0.5, "w")]))
    monkeypatch.setattr(ap.captions, "transcribe_words", lambda a: [(0.0, 0.5, "w")])
    monkeypatch.setattr(ap.captions, "correct_words", lambda w, n: w)
    monkeypatch.setattr(ap.eng, "dur", lambda p: 300.0)
    monkeypatch.setattr(ap, "scene_durations", lambda s, w, d: [50.0] * len(s["scenes"]))
    monkeypatch.setattr(ap.infographics, "inject_cards", lambda *a, **k: None)
    built = {}
    monkeypatch.setattr(ap.eng, "step5_build", lambda s, clips, *a, **k: built.update(clips=clips) or "v.mp4")
    monkeypatch.setattr(ap.thumbnail, "make", lambda *a, **k: "t.jpg")
    monkeypatch.setattr(ap.shorts_mod, "make_shorts", lambda *a, **k: [])
    monkeypatch.setattr(ap.captions, "build_ass", lambda *a, **k: "c.ass")
    monkeypatch.setattr(ap.captions, "burn_ass", lambda v, a, **k: v)
    monkeypatch.setattr(ap.branding, "add_intro_outro", lambda v, **k: v)
    monkeypatch.setattr(ap.l2, "inject", lambda v, at: (v, {}))
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
    monkeypatch.setattr(ap, "_fall_back", lambda *a, **k: None)
    monkeypatch.setattr(ap.gates, "fact_check", lambda *a, **k: {"passed": True})
    monkeypatch.setattr(ap.gates, "verify_synthesis", lambda *a, **k: {"present": True})
    monkeypatch.setattr(ap.gates, "replication_test", lambda *a, **k: {"passed": True})
    monkeypatch.setattr(ap.evidence, "render_slot_clip",
                        lambda e, share, out, with_label=True: str(tmp_path / "evidence_slot.mp4"))
    ap.run(publish=False)
    return rows, built


def _p1_tool_script(tmp_path, title, thumb, narr="the tool sorts files", evd=None):
    s = {"title": title, "titles": [title], "thumb_text": thumb, "description": "Hook.\n\nBody.",
         "tags": ["ai"], "scenes": _p1_scenes(8, narr + " " + "word " * 80)}
    s = ap._validate_script(s, title)
    s.update(format="tool", grounding="", deliverable=None, evidence=evd)
    return s


def test_p1_run_fixes_the_title_before_the_ledger_and_leads_scene_one(monkeypatch, tmp_path):
    _p1_on(monkeypatch)
    a = _p1_author_ev(tmp_path)
    s = _p1_tool_script(tmp_path, "Double Your AI Speed: demo-tool for RTX", "FREE", evd=a)
    rows, built = _p1_run(monkeypatch, tmp_path, s)
    row = rows[-1]
    assert row["title"] == "Claimed 2× AI Speed: demo-tool for RTX"
    assert row["evidence_source"] == "author" and row["evidence_status"] == "NOT_RUN"
    assert row["claims_fixed"] == ["title"]
    assert built["clips"][0][0].endswith("evidence_slot.mp4") and len(built["clips"][0]) == 1


def test_p1_run_blocks_an_overclaim_over_an_author_demo(monkeypatch, tmp_path):
    _p1_on(monkeypatch)
    s = _p1_tool_script(tmp_path, "Demo Tool Sorts Files", "FREE",
                        narr="we tested it and it sorts files", evd=_p1_author_ev(tmp_path))
    rows, _ = _p1_run(monkeypatch, tmp_path, s)
    assert rows[-1]["status"] == "OVERCLAIM_BLOCKED"


def test_p1_run_with_a_non_tool_script_writes_empty_evidence_fields(monkeypatch, tmp_path):
    _p1_on(monkeypatch)
    s = _p1_tool_script(tmp_path, "How Transformers Work", "")
    s["format"] = "evergreen"
    s.pop("evidence")
    rows, built = _p1_run(monkeypatch, tmp_path, s)
    assert rows[-1]["evidence_source"] == "" and rows[-1]["evidence_status"] == ""
    assert built["clips"][0] == ["stock.mp4"]


# ================================================================ catalog
def test_p1_site_catalog_entry_carries_the_evidence_without_its_clip(monkeypatch, tmp_path):
    saved = []
    monkeypatch.setattr(site, "enabled", lambda: True)
    monkeypatch.setattr(site, "load_catalog", lambda path=None: [])
    monkeypatch.setattr(site, "save_catalog", lambda entries, path=None: saved.append(entries) or True)
    monkeypatch.setattr(site, "rebuild", lambda entries=None: 1)
    s = {"title": "Demo Tool", "format": "tool", "cheat_sheet": "2026-11-04-demo-tool.pdf",
         "deliverable": {"kind": "command", "text": "pip install demo-tool", "url": _P1_GH},
         "evidence": _p1_author_ev(tmp_path)}
    assert site.publish_page(s, {}, "")
    e = saved[0][0]["evidence"]
    assert e["source"] == "author" and "clip" not in e


def test_p1_text_fetches_are_bounded_too(monkeypatch):
    """A Space's own server answers /config: a slow drip or a huge body must cost
    the fetch, never hold the run (requests' timeout is not a deadline)."""
    import requests

    class _S(_P1Stream):
        encoding = "utf-8"
    monkeypatch.setattr(requests, "get", lambda *a, **k: _S([b'{"a": 1}']))
    r = ev._http_get("https://x.hf.space/config")
    assert r.status_code == 200 and r.json() == {"a": 1}
    monkeypatch.setattr(ev, "TEXT_MAX_BYTES", 10)
    monkeypatch.setattr(requests, "get", lambda *a, **k: _S([b"x" * 8] * 3))
    assert ev._http_get("u") is None
    monkeypatch.setattr(ev, "TEXT_MAX_BYTES", 10 ** 6)
    ticks = iter([0.0, 10.0, 31.0, 40.0])
    monkeypatch.setattr(ev.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(requests, "get", lambda *a, **k: _S([b"x"] * 3))
    assert ev._http_get("u") is None
