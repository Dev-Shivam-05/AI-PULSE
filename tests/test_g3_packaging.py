"""v3-G.3: packaging (docs/spec/ai-pulse-v3g3.md).

Prompts that stop rewarding fear, a title fallback that uses the model's own
alternates instead of shipping a gutted leftover, a long-form hype screen, three
new ledger fields, and impressions/CTR from the YouTube Reporting API.
Helpers are prefixed `_g3_` (the shared-module helper-name trap)."""
import inspect
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factverse import ai_pipeline as ap   # noqa: E402
from factverse import analytics as an    # noqa: E402
from factverse import gates              # noqa: E402
from factverse import learn              # noqa: E402


def _g3_flag(monkeypatch, **flags):
    """Pin config flags the way the consumer reads them (gates.fv / an.fv are config)."""
    real = gates.fv.flag

    def flag(name, default=False):
        return flags[name] if name in flags else real(name, default)
    monkeypatch.setattr(gates.fv, "flag", flag)


def _g3_scenes(text="the model explains how it works, step by step", n=6):
    return [{"scene_num": i + 1, "narration": f"{text} part {chr(97 + i)}",
             "visual_query": "person using laptop"} for i in range(n)]


# --------------------------------------------------------------- prompts (#2-#5)
def test_g3_viral_judge_scores_the_builder_not_the_fear(monkeypatch):
    seen = []
    monkeypatch.setattr(ap.llm, "generate_json", lambda p, **k: seen.append(p) or None)
    ap.viral_pick([{"title": "Ollama 0.9 ships tool calling", "source": "ollama.com"}])
    p = " ".join(seen[0].lower().split())   # prompt lines wrap
    for banned in ("fear", "outrage", "stop scrolling", "niche developer tooling",
                   "shock", "emotional charge"):
        assert banned not in p, banned
    assert "build with or use ai" in p and "primary source" in p
    assert "version bumps with no usable change" in p
    assert "papers with no usable artifact" in p
    assert "why a builder should care" in p
    assert ap.VIRAL_THRESHOLD == 10.0


def test_g3_news_angle_label_is_why_a_builder_should_care(monkeypatch):
    seen = []
    monkeypatch.setattr(ap, "fetch_text", lambda u, limit=4000: "grounded source text. " * 40)
    monkeypatch.setattr(ap.llm, "generate_json", lambda p, **k: seen.append(p) or None)
    ap.script_news({"title": "T", "source": "s", "url": "https://x.test/a"},
                   viral_hint=(None, 10, "you can now run it locally", "Run it locally."))
    assert "EDITORIAL ANGLE (why a builder should care):" in seen[0]
    assert "go viral" not in seen[0]


def test_g3_critique_prompt_carries_the_thumb_contract(monkeypatch):
    seen = []
    monkeypatch.setattr(ap.llm, "generate_json", lambda p, **k: seen.append(p) or None)
    s = {"title": "T", "titles": ["T"], "thumb_text": "FREE", "description": "d",
         "tags": [], "scenes": _g3_scenes()}
    assert ap.critique_pass(s) is s
    p = " ".join(seen[0].split())   # prompt lines wrap
    assert "curiosity gap" not in p.lower()
    assert "FREE" in p and "no question" in p and "2-4 words" in p
    assert "the concrete thing the" in p and "first 8 words" in p
    assert "no hype words" in p


def test_g3_output_contract_and_retention_promise(monkeypatch):
    plain, tool = ap._output_contract("5", "50"), ap._output_contract("5", "50", tool=True)
    for c in (plain, tool):
        assert "what the viewer can DO, USE, or" in c and "never how scared or angry to be" in c
    assert "[what you can do] + [tool name]" in tool
    assert "[what you can do]" not in plain
    assert "able to do, use or decide" in ap._RETENTION_RULES
    # the tool lane's real prompt carries the formula
    seen = []
    monkeypatch.setattr(ap, "fetch_text",
                        lambda u, limit=4000: "install: ```\npip install repo\n``` prose. " * 40)
    monkeypatch.setattr(ap, "_verified_facts", lambda u: {})
    monkeypatch.setattr(ap, "_top_issues", lambda u: [])
    monkeypatch.setattr(ap.llm, "generate_json", lambda p, **k: seen.append(p) or None)
    ap.script_tool({"title": "org/repo: helpful", "source": "gh", "url": "https://github.com/org/repo"})
    assert "[what you can do] + [tool name]" in seen[0]


# --------------------------------------------------------------- #6 packaging fallback
# The 8 published leftovers (state/runs.jsonl rows with packaging: ["title"]).
# `original` and the alternates come from state/assets/<run>/script.json `titles`,
# except 09-16 and 10-01: their `titles` were dropped by a rewrite pass (the _CARRY
# bug this phase fixes), so those two originals and alternates are RECONSTRUCTED —
# one number put back where the leftover shows the gap.
_G3_LEFTOVERS = [
    # (date, original, shipped leftover, alternates, expected pick, verified_facts)
    ("09-01", "AI Creates Art: Your Job Safe? 1000x Faster", "AI Creates Art: Your Job Safe? Faster",
     ["AI Creates Art: Your Job Safe? 1000x Faster", "AI vs. Human Art: Who's Really Creating?",
      "AI Art: 1000x Speed, Zero Soul?"], "AI vs. Human Art: Who's Really Creating?", {}),
    ("09-06", "Stable Diffusion: 5 Million Images Trained", "Stable Diffusion: Million Images Trained",
     ["Stable Diffusion: 5 Million Images Trained", "Midjourney: The 3 Steps to AI Art",
      "DALL-E: How AI Creates Anything"], "DALL-E: How AI Creates Anything", {}),
    ("09-13", "AI Agents Gone Rogue: 3 Scenarios", "AI Agents Gone Rogue: Scenarios",
     ["AI Agents Gone Rogue: 3 Scenarios", "Rogue AI: What Happens Next?",
      "AI Agents: The Unintended Consequences"], "Rogue AI: What Happens Next?", {}),
    ("09-16", "AI's Real Impact: 5 Industries Transformed", "AI's Real Impact: Industries Transformed",
     ["AI's Real Impact: 5 Industries Transformed", "AI at Work: What Changes in Your Industry"],
     "AI at Work: What Changes in Your Industry", {}),
    ("09-18", "Open vs Closed AI: Your 100% Guide", "Open vs Closed AI: Your Guide",
     ["Open vs Closed AI: Your 100% Guide", "AI Models: Open vs Closed Explained",
      "Open AI vs Closed AI: The Core Truth"], "AI Models: Open vs Closed Explained", {}),
    ("09-24", "LLMs: How 175 Billion Parameters Understand You",
     "LLMs: How Billion Parameters Understand You",
     ["LLMs: How 175 Billion Parameters Understand You",
      "Beyond Buzzwords: LLM Language Decoding Explained",
      "The Math Behind AI Understanding: LLM Secrets"],
     "Beyond Buzzwords: LLM Language Decoding Explained", {}),
    ("10-01", "ZCode: Get a Coding AI Running in 5 Min (7,286 Stars)",
     "ZCode: Get a Coding AI Running in Min (7,286 Stars)",
     ["ZCode: Get a Coding AI Running in 5 Min (7,286 Stars)",
      "Run a Free Coding AI Locally: ZCode (7,286 Stars)"],
     "Run a Free Coding AI Locally: ZCode (7,286 Stars)", {"stars": 7286}),
    ("10-08", "LLM Inner Workings: How 1 Trillion Parameters Learn",
     "LLM Inner Workings: How Trillion Parameters Learn",
     ["LLM Inner Workings: How 1 Trillion Parameters Learn",
      "Large Language Models Explained: The 3 Core Secrets",
      "AI's Brain: Demystifying Large Language Models"],
     "AI's Brain: Demystifying Large Language Models", {}),
]


def _g3_case(original, titles, facts, fmt="evergreen"):
    return {"title": original, "titles": titles, "thumb_text": "", "format": fmt,
            "signal_title": "zcode/zcode: coding ai",
            "scenes": [{"narration": "no figures are spoken in this video at all"}],
            "verified_facts": facts}


def test_g3_real_leftovers_take_the_clean_alternate(monkeypatch):
    _g3_flag(monkeypatch, honest_titles=True)
    for day, original, _, titles, want, facts in _G3_LEFTOVERS:
        s = _g3_case(original, titles, facts)
        r = gates.packaging_payoff(s)
        assert s["title"] == want, day
        assert r["title_alt"] is True and r["fixed"] == ["title"] and not r["ok"], day


def test_g3_without_an_alternate_the_strip_is_byte_identical(monkeypatch):
    _g3_flag(monkeypatch, honest_titles=True)
    for day, original, leftover, titles, _, facts in _G3_LEFTOVERS:
        # no alternates at all -> exactly what shipped
        s = _g3_case(original, [], facts)
        r = gates.packaging_payoff(s)
        assert s["title"] == leftover and r["title_alt"] is False, day
        # only UNCLEAN alternates (the original itself, hype, unsupported numbers)
        s = _g3_case(original, [original, "The Secret Behind It", "Top 9 Uses"], facts)
        gates.packaging_payoff(s)
        assert s["title"] == leftover, day
    # the flag off -> today's behaviour even with a clean alternate on offer
    _g3_flag(monkeypatch, honest_titles=False)
    for day, original, leftover, titles, _, facts in _G3_LEFTOVERS:
        s = _g3_case(original, titles, facts)
        assert gates.packaging_payoff(s)["title_alt"] is False
        assert s["title"] == leftover, day


def test_g3_the_tool_template_still_wins_when_nothing_is_clean(monkeypatch):
    _g3_flag(monkeypatch, honest_titles=True)
    gut = {"title": "40% off", "thumb_text": "OK", "format": "tool", "titles": ["50% off"],
           "signal_title": "ollama/ollama: run models",
           "scenes": [{"narration": "no numbers here"}], "verified_facts": {}}
    gates.packaging_payoff(gut)
    assert gut["title"] == "How to use ollama (free)"


@pytest.mark.parametrize("raw", ["Only One Title", None, {"a": "b"}, 7, [None, {"x": 1}, " ", 3],
                                 ["AI: Clean Option"], ("AI: Clean Option",)])
def test_g3_titles_of_any_shape_never_raise(monkeypatch, raw):
    _g3_flag(monkeypatch, honest_titles=True)
    s = _g3_case("Tool Runs 9x Faster Today", raw, {})
    gates.packaging_payoff(s)
    assert isinstance(s["title"], str) and "9x" not in s["title"]
    gates.longform_title_screen(dict(s, title="The Secret Tool"))
    v = ap._validate_script({"title": "T", "titles": raw, "scenes": _g3_scenes()}, "T")
    assert isinstance(v["titles"], list) and all(isinstance(t, str) and t for t in v["titles"])
    assert gates.title_options({"titles": raw}) == [
        str(t).strip() for t in (raw if isinstance(raw, (list, tuple)) else [raw] if isinstance(raw, str) else [])
        if isinstance(t, (str, int, float)) and str(t).strip()]


def test_g3_titles_survive_every_rewrite_pass(monkeypatch):
    """The documented _CARRY trap: 09-16 and 10-01 lost `titles` to a rewrite pass."""
    assert "titles" in ap._CARRY
    alts = ["Ollama: Run Llama Locally", "Run Llama Offline With Ollama"]
    short = {"title": "T", "titles": list(alts), "thumb_text": "FREE", "description": "d",
             "tags": [], "scenes": _g3_scenes("short"), "format": "tool"}
    longer = {"title": "T2", "description": "d", "tags": [],          # the rewrite has NO titles
              "scenes": _g3_scenes("a much longer narration " * 12, n=8)}
    monkeypatch.setattr(ap.llm, "generate_json", lambda p, **k: json.loads(json.dumps(longer)))
    out = ap.enforce_length(short, 400)
    assert out is not short and out["titles"] == alts
    # the tighten pass, from the other direction
    big = dict(short, scenes=_g3_scenes("word " * 120, n=8))
    smaller = {"title": "T3", "titles": "a planted string", "description": "d", "tags": [],
               "scenes": _g3_scenes("word " * 70, n=8)}
    monkeypatch.setattr(ap.llm, "generate_json", lambda p, **k: json.loads(json.dumps(smaller)))
    out = ap.enforce_max_length(big, 900)
    assert out is not big and out["titles"] == alts


# --------------------------------------------------------------- #7 long-form hype screen
def test_g3_the_5_billion_image_secret(monkeypatch):
    clean = "AI Image Generators: How Diffusion Draws a Picture"
    title = "AI Image Generators: The 5 Billion Image Secret"
    _g3_flag(monkeypatch, honest_titles=True)
    # (a) the number is unsupported -> #6 takes the alternate
    s = {"title": title, "titles": [title, clean], "thumb_text": "",
         "scenes": [{"narration": "trained on a huge pile of images"}]}
    assert gates.packaging_payoff(s)["title_alt"] and s["title"] == clean
    # (b) the number is SPOKEN -> #6 passes it, the hype screen catches "secret"
    s = {"title": title, "titles": [title, clean], "thumb_text": "",
         "scenes": [{"narration": "it learned from 5 billion images"}]}
    assert gates.packaging_payoff(s)["ok"] and s["title"] == title
    assert gates.longform_title_screen(s) == {"terms": ["secret"], "alt": True}
    assert s["title"] == clean
    # (c) no clean alternate -> kept, terms still reported
    s = {"title": title, "titles": [title, "The Secret of AI Art"],
         "scenes": [{"narration": "it learned from 5 billion images"}]}
    assert gates.longform_title_screen(s) == {"terms": ["secret"], "alt": False}
    assert s["title"] == title
    # (d) honest_titles off -> both are today's no-op
    _g3_flag(monkeypatch, honest_titles=False)
    s = {"title": title, "titles": [title, clean],
         "scenes": [{"narration": "it learned from 5 billion images"}]}
    assert gates.packaging_payoff(s)["ok"]
    assert gates.longform_title_screen(s) == {"terms": [], "alt": False}
    assert s["title"] == title


# --------------------------------------------------------------- #8 title_terms
def test_g3_title_terms_records_hype_and_fear_on_word_boundaries():
    assert gates.title_terms("Salesforce Koa: AI Labs' New Nightmare") == ["nightmare"]
    assert gates.title_terms("AI Users Worried: 68% of Americans Fear Tech") == ["fear", "worried"]
    assert gates.title_terms("Higgsfield AI: YouTubers' Secret AI Cash Cow?") == ["secret"]
    assert gates.title_terms("AI Agents Gone ROGUE: 3 Threats") == ["rogue", "threats"]
    # word boundaries: none of these is the term
    for clean in ("Threatened Species Tracker Uses AI", "Fearless Coding With Ollama",
                  "Crises Averted", "Run Llama 3 Locally With Ollama"):
        assert gates.title_terms(clean) == [], clean
    assert gates.title_terms(None) == [] and gates.title_terms(42) == []


# --------------------------------------------------------------- #9 ledger fields
def _g3_run_harness(monkeypatch, tmp_path, script):
    """run(publish=False) with every render/network seam stubbed; returns the
    kwargs of every record_run call."""
    rows = []
    monkeypatch.setattr(ap.fv, "TEMP", tmp_path)
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: None)
    monkeypatch.setattr(ap.signal_engine, "rank", lambda limit=20: [])
    monkeypatch.setattr(ap, "decide_format", lambda f, r: ("evergreen", None))
    monkeypatch.setattr(ap, "build_script", lambda f, r, v: script)
    monkeypatch.setattr(ap, "too_many_failures", lambda t: False)
    monkeypatch.setattr(ap.eng, "step3_download", lambda s: [[] for _ in s["scenes"]])
    monkeypatch.setattr(ap, "synthesize_voice", lambda n, s: ("a.mp3", [(0.0, 0.5, "w")]))
    monkeypatch.setattr(ap.captions, "transcribe_words", lambda a: [(0.0, 0.5, "w")])
    monkeypatch.setattr(ap.captions, "correct_words", lambda w, n: w)
    monkeypatch.setattr(ap.eng, "dur", lambda p: 300.0)
    monkeypatch.setattr(ap, "scene_durations", lambda s, w, d: None)
    monkeypatch.setattr(ap.infographics, "inject_cards", lambda *a, **k: None)
    monkeypatch.setattr(ap.eng, "step5_build", lambda *a, **k: "v.mp4")
    monkeypatch.setattr(ap.thumbnail, "make", lambda *a, **k: "t.jpg")
    monkeypatch.setattr(ap.shorts_mod, "make_shorts", lambda *a, **k: [])
    monkeypatch.setattr(ap.captions, "build_ass", lambda *a, **k: "c.ass")
    monkeypatch.setattr(ap.captions, "burn_ass", lambda v, a, **k: v)
    monkeypatch.setattr(ap.branding, "add_intro_outro", lambda v, **k: v)
    monkeypatch.setattr(ap.l2, "inject", lambda v, at: (v, {}))
    monkeypatch.setattr(ap, "qa_video", lambda v, d: True)
    monkeypatch.setattr(ap.eng, "step8_meta", lambda s, n: [])
    monkeypatch.setattr(ap, "mark_used", lambda *a, **k: None)
    monkeypatch.setattr(ap, "_save_asset_record", lambda *a, **k: None)
    monkeypatch.setattr(ap.eng, "save_report", lambda *a, **k: {"status": "RENDER_ONLY"})
    monkeypatch.setattr(ap.eng, "cleanup", lambda: None)
    monkeypatch.setattr(ap.eng, "_rel", lambda v: v)
    monkeypatch.setattr(ap, "record_run", lambda **kw: rows.append(kw))
    ap.run(publish=False)
    return rows


def _g3_script(title, titles, thumb="FREE. OFFLINE."):
    s = {"title": title, "titles": titles, "thumb_text": thumb,
         "description": "How the thing works.", "tags": ["ai"],
         "scenes": _g3_scenes("a calm explainer about local models and how they run", n=8)}
    s = ap._validate_script(s, title)
    s["format"], s["grounding"] = "evergreen", ""
    return s


def test_g3_ledger_row_carries_the_packaging_fields(monkeypatch, tmp_path, capsys):
    _g3_flag(monkeypatch, honest_titles=True)
    rows = _g3_run_harness(monkeypatch, tmp_path, _g3_script(
        "Ollama: The Secret Local AI Nightmare", ["Ollama: Run Llama on Your Laptop"]))
    row = rows[-1]
    assert row["status"] == "RENDER_ONLY"
    assert row["title"] == "Ollama: Run Llama on Your Laptop"
    assert row["thumb_text"] == "FREE. OFFLINE." and row["title_alt"] is True
    assert row["title_terms"] == []               # the alternate is clean
    assert "using alternate" in capsys.readouterr().out
    # no clean alternate: kept, logged, and the terms are recorded
    rows = _g3_run_harness(monkeypatch, tmp_path, _g3_script(
        "Ollama: The Secret Local AI Nightmare", ["Another Secret Option"]))
    row = rows[-1]
    assert row["title"] == "Ollama: The Secret Local AI Nightmare" and row["title_alt"] is False
    assert row["title_terms"] == ["secret", "nightmare"]
    assert ("Long-form title had hype (secret) — kept: no clean alternate"
            in capsys.readouterr().out)
    for r in rows:
        json.dumps(r)                              # every field is JSON-plain
    assert isinstance(row["thumb_text"], str) and isinstance(row["title_terms"], list)


def test_g3_ledger_fields_are_computed_before_the_upload():
    """Nothing new may raise between eng.yt_upload and record_run."""
    src = inspect.getsource(ap.run)
    upload = src.index("eng.yt_upload(")
    for name in ("_ledger_thumb =", "_ledger_title_alt =", "_ledger_title_terms =",
                 "gates.longform_title_screen("):
        assert src.index(name) < upload, name
    tail = src[src.index("record_run(status=status"):]
    for kw in ("thumb_text=_ledger_thumb", "title_alt=_ledger_title_alt",
               "title_terms=_ledger_title_terms"):
        assert kw in tail, kw


# --------------------------------------------------------------- #10-11 reach collection
def _g3_vid(n):
    return f"vid{n:08d}"


def _g3_runs():
    return [{"status": "PUBLISHED", "format": "news", "timestamp": f"2026-09-0{n}T12:30:00",
             "publish_at": f"2026-09-0{n}T16:45:00Z",
             "youtube_url": f"https://youtube.com/watch?v={_g3_vid(n)}"} for n in (1, 2)]


class _G3Exec:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class _G3Ytr:
    """Stub youtubereporting v1 client: jobs().list/create, jobs().reports().list."""
    def __init__(self, jobs=None, reports=None, boom=False):
        self.jobs_, self.reports_, self.boom, self.calls = jobs, reports or [], boom, []

    def _hit(self, name, value):
        self.calls.append(name)
        if self.boom:
            raise RuntimeError(f"{name} exploded")
        return value

    def jobs(self):
        self._hit("jobs", None)
        return self

    def list(self, **kw):
        if "jobId" in kw:
            return _G3Exec(lambda: self._hit("reports.list", {"reports": self.reports_}))
        return _G3Exec(lambda: self._hit("jobs.list", {"jobs": self.jobs_ or []}))

    def create(self, body):
        self.created = body
        return _G3Exec(lambda: self._hit("jobs.create", {"id": "job-new", **body}))

    def reports(self):
        self._hit("reports", None)
        return self

    def media(self):
        return self._hit("media", self)


_G3_JOB = [{"id": "job1", "reportTypeId": "channel_reach_basic_a1", "name": "tooldojo-reach"}]


def _g3_report(day, rid=None):
    return {"id": rid or f"r{day}", "startTime": f"{day}T07:00:00Z",
            "endTime": f"{day}T07:00:00Z", "createTime": f"{day}T20:00:00Z",
            "downloadUrl": f"https://youtubereporting.googleapis.com/v1/media/x/{rid or day}?alt=media"}


_G3_CSV = ("date,channel_id,video_id,video_thumbnail_impressions,video_thumbnail_impressions_ctr\n"
           f"20260902,UC1,{_g3_vid(1)},120,0.05\n"
           f"20260902,UC1,{_g3_vid(2)},80,0.025\n"
           "20260902,UC1,someoneelse,999,0.9\n")


class _G3Yta:
    """The two existing Analytics queries + the ledger query, all answering."""
    def reports(self):
        return self

    def query(self, **kw):
        rows = [[_g3_vid(1), 10, 1, 90, 40.0]] if "filters" in kw else [["2026-09-01", 5]]
        heads = (["video", "views", "estimatedMinutesWatched", "averageViewDuration",
                  "averageViewPercentage"] if "filters" in kw else ["day", "views"])
        return _G3Exec(lambda: {"rows": rows, "columnHeaders": [{"name": h} for h in heads]})


def _g3_env(monkeypatch, tmp_path, reach=True):
    monkeypatch.setattr(an, "OUT", tmp_path / "analytics.jsonl")
    monkeypatch.setattr(an.learn, "read_runs", lambda path=None: _g3_runs())
    _g3_flag(monkeypatch, reach_report=reach)


def test_g3_reach_client_that_raises_everywhere_costs_nothing_else(monkeypatch, tmp_path, capsys):
    _g3_env(monkeypatch, tmp_path)
    ytr = _G3Ytr(boom=True)
    snap = an.collect(_G3Yta(), ytr)
    assert snap["channel_days"] and snap["top_videos_7d"] and snap["ledger_videos"]
    assert "reach_rows" not in snap and "reach_headers" not in snap
    assert ytr.calls, "the stub was never reached"
    assert "↷ reach report: RuntimeError: jobs exploded" in capsys.readouterr().out
    # ...and a download that raises costs only its own report
    ytr = _G3Ytr(jobs=_G3_JOB, reports=[_g3_report("2026-09-02"), _g3_report("2026-09-03")])
    monkeypatch.setattr(an, "_download_report",
                        lambda c, url: (_ for _ in ()).throw(OSError("reset")) if "09-03" in url
                        else _G3_CSV.encode())
    snap = an.collect(_G3Yta(), ytr)
    assert len(snap["reach_rows"]) == 2
    assert "2026-09-03 skipped (OSError: reset)" in capsys.readouterr().out


def test_g3_reach_rows_are_filtered_and_never_downloaded_twice(monkeypatch, tmp_path):
    _g3_env(monkeypatch, tmp_path)
    downloads = []
    monkeypatch.setattr(an, "_download_report",
                        lambda c, url: downloads.append(url) or _G3_CSV.encode("utf-8-sig"))
    ytr = _G3Ytr(jobs=_G3_JOB, reports=[_g3_report("2026-09-02")])
    snap = an.collect(_G3Yta(), ytr)
    assert snap["reach_headers"] == ["date", "video_id", "video_thumbnail_impressions",
                                     "video_thumbnail_impressions_ctr"]
    assert snap["reach_rows"] == [["2026-09-02", _g3_vid(1), 120, 0.05],
                                  ["2026-09-02", _g3_vid(2), 80, 0.025]]   # someoneelse dropped
    assert len(downloads) == 1 and "jobs.create" not in ytr.calls
    an.OUT.write_text(json.dumps(snap) + "\n", encoding="utf-8")   # what main() appends
    snap2 = an.collect(_G3Yta(), _G3Ytr(jobs=_G3_JOB, reports=[_g3_report("2026-09-02")]))
    assert len(downloads) == 1, "an already-stored report was downloaded again"
    assert snap2["reach_rows"] == []


def test_g3_reach_creates_its_job_once_and_caps_downloads(monkeypatch, tmp_path, capsys):
    _g3_env(monkeypatch, tmp_path)
    ytr = _G3Ytr(jobs=[{"id": "other", "reportTypeId": "channel_basic_a2"}])
    snap = an.collect(_G3Yta(), ytr)
    assert ytr.created == {"reportTypeId": "channel_reach_basic_a1", "name": "tooldojo-reach"}
    assert snap["reach_rows"] == [] and "job created" in capsys.readouterr().out
    # 40 days on offer, one regenerated twice: 35 downloads, newest day first
    import datetime as dt
    days = [(dt.date(2026, 8, 1) + dt.timedelta(days=i)).isoformat() for i in range(40)]
    reps = [_g3_report(d) for d in days] + [dict(_g3_report(days[-1], "older"),
                                                 createTime=f"{days[-1]}T08:00:00Z")]
    got = []
    monkeypatch.setattr(an, "_download_report", lambda c, url: got.append(url) or b"")
    an.collect(_G3Yta(), _G3Ytr(jobs=_G3_JOB, reports=reps))
    assert len(got) == an.REACH_CAP == 35
    assert days[-1] in got[0] and "older" not in " ".join(got)


def test_g3_reach_kill_switch_makes_no_reporting_call(monkeypatch, tmp_path):
    _g3_env(monkeypatch, tmp_path, reach=False)
    ytr = _G3Ytr(jobs=_G3_JOB)
    snap = an.collect(_G3Yta(), ytr)
    assert ytr.calls == [] and "reach_rows" not in snap and snap["channel_days"]


def test_g3_parse_reach_csv_refuses_a_changed_layout():
    with pytest.raises(ValueError):
        an.parse_reach_csv("date,video_id,views\n20260902,x,1\n", {"x"})
    rows = an.parse_reach_csv(_G3_CSV.replace("0.025", "nan").replace("0.05", "Infinity"),
                              {_g3_vid(1), _g3_vid(2)})
    assert rows == []                                  # non-finite CTR rows are dropped


# --------------------------------------------------------------- #12 scoreboard
def test_g3_scoreboard_reach_columns_count_a_day_once(tmp_path):
    runs, ana = tmp_path / "runs.jsonl", tmp_path / "analytics.jsonl"
    rows = _g3_runs()
    rows[1]["format"] = "tool"
    runs.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    heads = list(an.REACH_HEADERS)
    old = {"collected": "2026-09-04T18:00:00", "reach_headers": heads,
           "reach_rows": [["2026-09-02", _g3_vid(1), 999, 0.9]]}            # superseded
    new = {"collected": "2026-09-05T18:00:00", "reach_headers": heads,
           "reach_rows": [["2026-09-02", _g3_vid(1), 100, 0.04],
                          ["2026-09-03", _g3_vid(1), 300, 0.08],
                          ["2026-09-03", _g3_vid(2), 50, "Infinity"]]}
    ana.write_text("\n".join(json.dumps(s) for s in (old, new, {"reach_rows": "junk"}))
                   + "\n{not json\n", encoding="utf-8")
    reach = learn.reach_metrics(ana)
    assert len(reach) == 3 and reach[("2026-09-02", _g3_vid(1))]["impr"] == 100
    by = learn.reach_by_format(learn.read_runs(runs), reach)
    assert by["format:news"]["impr"] == 400
    assert by["format:news"]["ctr"] == pytest.approx((100 * 0.04 + 300 * 0.08) / 400)
    assert by["format:tool"] == {"impr": 50, "ctr": 0.0}
    text = learn.scoreboard(runs, ana)
    line = next(ln for ln in text.splitlines() if ln.startswith("format:news") and "0.07" in ln)
    assert line.split()[1:] == ["400", "0.07"]
    assert "impr" in text and "CTR" in text
    # no reach data at all -> the columns render empty, nothing breaks
    ana.write_text("{}\n", encoding="utf-8")
    text = learn.scoreboard(runs, ana)
    assert next(ln for ln in text.splitlines()
                if ln.startswith("format:news") and ln.split()[1:] == ["0", "-"])
