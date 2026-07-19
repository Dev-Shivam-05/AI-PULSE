"""
AI Pulse content pipeline v2.

Turns real AI-news signals into three video formats engineered for watch time
and monetization safety, then renders/publishes through the proven engine steps.

Format choice is VIRALITY-FIRST (the channel's primary goal): every day the
viral judge scores the top-ranked stories on shock, stakes, and broad appeal.
  * news       — runs whenever a story scores >= VIRAL_THRESHOLD (hot stories
                 are the viral ceiling; the judge's angle steers the script)
  * evergreen  — the default when nothing is hot: search-driven explainers that
                 compound watch hours for months (the monetization floor)
  * roundup    (Sun) — curated weekly top-5 (curation = added value = policy-safe)

Safety rails (YouTube's 2025 "inauthentic content" policy is the #1 threat):
  * every script passes a critique/retention rewrite pass (originality + hooks)
  * a verbatim-overlap gate blocks scripts that copy their source article
  * a render QA gate blocks broken/silent/truncated videos from publishing
  * uploads carry the synthetic-media disclosure flag
  * topics are only marked "used" after the video actually succeeds

Run:
    python -m factverse.ai_pipeline           # render only (safe)
    python -m factverse.ai_pipeline publish   # render + upload
    python -m factverse.ai_pipeline publish news|evergreen|roundup   # force format

Exit code is 0 only when the run truly succeeded — CI goes red otherwise.
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import re
import sys
from pathlib import Path

import requests

from factverse import config as fv
from factverse import llm
from factverse import captions
from factverse import branding
from factverse import voice
from factverse import tts_kokoro
from factverse import thumbnail
from factverse import shorts as shorts_mod
from factverse.intelligence import signal_engine

# Reuse the proven render/publish steps from the original engine (lives in scripts/).
sys.path.insert(0, str(fv.BASE / "scripts"))
import factverse_engine as eng  # noqa: E402


# --------------------------------------------------------------- state
USED_TOPICS = fv.BASE / "used_topics.json"
USED_URLS = fv.BASE / "used_urls.json"
FAILED_TOPICS = fv.STATE / "failed_topics.json"
RUNS_LOG = fv.STATE / "runs.jsonl"


def _read_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def mark_used(title: str, url: str = "") -> None:
    used = _read_json(USED_TOPICS, [])
    used.append(title)
    _write_json(USED_TOPICS, used[-300:])
    if url:
        urls = _read_json(USED_URLS, [])
        urls.append(url)
        _write_json(USED_URLS, urls[-300:])


def _fail_key(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (title or "").lower()).strip()[:80]


def mark_failed(title: str) -> None:
    fails = _read_json(FAILED_TOPICS, {})
    k = _fail_key(title)
    fails[k] = fails.get(k, 0) + 1
    _write_json(FAILED_TOPICS, fails)


def too_many_failures(title: str) -> bool:
    return _read_json(FAILED_TOPICS, {}).get(_fail_key(title), 0) >= 2


def record_run(**fields) -> None:
    """Append one JSON line per run — the ground truth a future learning loop needs."""
    fields.setdefault("timestamp", _dt.datetime.now().isoformat(timespec="seconds"))
    try:
        with open(RUNS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(fields, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"   ⚠️ could not write run record: {e}")


# --------------------------------------------------------------- grounding
def fetch_text(url: str, limit: int = 4000) -> str:
    """Best-effort fetch of a page as readable plain text (grounds the script)."""
    if not url:
        return ""
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 FactVerse"}, timeout=20)
        ctype = r.headers.get("content-type", "")
        if r.status_code != 200 or ("html" not in ctype and "text" not in ctype):
            return ""
        t = r.text
        t = re.sub(r"(?is)<(script|style|nav|footer|header|noscript|form|aside).*?</\1>", " ", t)
        t = re.sub(r"(?s)<[^>]+>", " ", t)
        t = html.unescape(t)
        t = re.sub(r"\s+", " ", t).strip()
        # A real article has real length; a bot-wall/paywall stub does not.
        return t[:limit] if len(t) > 400 else ""
    except Exception:
        return ""


# --------------------------------------------------------------- policy gates
def _shingles(text: str, n: int = 8) -> set:
    words = re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def verbatim_overlap(narration: str, source_text: str) -> float:
    """Fraction of the narration's 8-word shingles that appear verbatim in the source."""
    ns = _shingles(narration)
    if not ns or not source_text:
        return 0.0
    ss = _shingles(source_text)
    return len(ns & ss) / len(ns)


def qa_video(video: str, expected_audio: float) -> bool:
    """Block broken renders from ever being published."""
    try:
        p = Path(video)
        if not p.exists() or p.stat().st_size < 2_000_000:
            print("   ❌ QA: video missing or suspiciously small")
            return False
        d = eng.dur(video)
        if d < 60:
            print(f"   ❌ QA: video only {d:.0f}s")
            return False
        # intro+outro add ~7s; allow generous drift but catch truncation
        if expected_audio and d < expected_audio * 0.75:
            print(f"   ❌ QA: video {d:.0f}s vs narration {expected_audio:.0f}s — truncated")
            return False
        import subprocess
        r = subprocess.run([fv.FFPROBE or "ffprobe", "-v", "error", "-select_streams", "a",
                            "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(video)],
                           capture_output=True, text=True, timeout=30)
        if "audio" not in (r.stdout or ""):
            print("   ❌ QA: no audio stream")
            return False
        return True
    except Exception as e:
        print(f"   ⚠️ QA check error (failing safe): {e}")
        return False


# --------------------------------------------------------------- script schema
_BANNED_DATED = ("today", "yesterday", "this week", "just announced", "breaking")


def _validate_script(s: dict, fallback_title: str, source_url: str = "") -> dict | None:
    """Enforce the script contract so a partial LLM response can't crash mid-render."""
    if not s or not isinstance(s.get("scenes"), list) or len(s["scenes"]) < 5:
        return None
    scenes = []
    for sc in s["scenes"]:
        narration = str(sc.get("narration", "")).strip()
        vq = str(sc.get("visual_query", "")).strip() or "computer technology"
        if narration:
            scenes.append({"scene_num": len(scenes) + 1, "narration": narration, "visual_query": vq})
    if len(scenes) < 5:
        return None
    s["scenes"] = scenes
    title = str(s.get("title") or fallback_title or "AI, Explained")[:95]
    s["title"] = re.sub(r"[<>]", "", title).strip()
    if not s.get("description"):
        s["description"] = f"{s['title']} — clearly explained by {fv.CHANNEL_NAME}."
    desc = str(s["description"])
    if source_url and source_url not in desc:
        desc += f"\n\nSource: {source_url}"
    if "#AI" not in desc:
        desc += "\n\n#AI #ArtificialIntelligence #TechNews"
    s["description"] = desc
    s.setdefault("tags", [])
    brand = ["ai", "artificial intelligence", "ai news", "machine learning",
             "tech news", "ai explained", "technology", "deep learning", fv.CHANNEL_NAME.lower()]
    existing = [str(t).lower() for t in s["tags"]]
    for b in brand:
        if b not in existing and len(s["tags"]) < 28:
            s["tags"].append(b)
    s["thumb_text"] = re.sub(r"[<>]", "", str(s.get("thumb_text", ""))).strip()[:26]
    s["source_url"] = source_url
    return s


_VISUAL_RULES = """- VISUAL ALIGNMENT IS CRITICAL: each scene's visual_query must LITERALLY match what that
  sentence is about, be 2-4 SIMPLE words (stock-site search terms, not descriptions),
  and be a real, concrete scene a stock site actually has.
  * GOOD (literal, filmable): "data center servers", "person typing code", "robot arm factory",
    "computer chip macro", "smartphone screen app", "engineer at computer", "self driving car",
    "glowing server racks", "person using laptop", "circuit board macro", "stock trading screen".
  * BAD (abstract/metaphor -> random irrelevant footage): "balance scale", "abstract thought",
    "question mark", "lightbulb idea". NEVER use metaphors or symbolic objects.
  * Vary the queries across scenes."""

_RETENTION_RULES = """RETENTION ENGINEERING (non-negotiable):
- Scene 1 = the HOOK: open with the single most surprising fact/stake as a direct statement or
  question, then a one-line PROMISE of what the viewer will understand by the end. No greetings,
  no "welcome back", no channel intro. Max 2 sentences before the first payoff begins.
- Open a curiosity loop in the first third ("and the strangest part comes later") and pay it off
  near the end.
- Every 3-4 scenes, use a pattern interrupt: a sharp question, a "but here's the problem", a
  concrete number, or a comparison a normal person can feel.
- Use concrete numbers and real comparisons, never vague hype. Short sentences. Spoken language.
- Final scene = crisp takeaway + ONE question to the audience + "subscribe" CTA in one sentence."""


def _output_contract(scene_range: str, words_per_scene: str) -> str:
    return f"""OUTPUT FIELDS:
- titles: 3 DIFFERENT title options, each <=70 chars, curiosity + the key concrete noun,
  keyword near the front, no clickbait lies.
- title: the strongest of the 3.
- thumb_text: 2-4 PUNCHY words for the thumbnail (NOT the title — e.g. "CHEAPER THAN GPT?",
  "NO MORE CODERS?", "10X FASTER").
- description: 150+ words; first 2 lines = hook + main keyword; 5-7 hashtags incl. #AI; end with
  "Subscribe to {fv.CHANNEL_NAME}".
- tags: ~18 relevant tags.
- scenes: {scene_range} scenes, {words_per_scene} words each. Each scene: scene_num, narration,
  visual_query.

Return ONLY JSON:
{{"titles":["..."],"title":"...","thumb_text":"...","description":"...","tags":["..."],
"scenes":[{{"scene_num":1,"narration":"...","visual_query":"..."}}]}}"""


# --------------------------------------------------------------- virality judge
VIRAL_THRESHOLD = 7.0


def viral_pick(ranked: list[dict], top_n: int = 8):
    """Score today's top stories for viral potential. Returns
    (item, score, angle, hook_idea) for the hottest one, or None."""
    cands = ranked[:top_n]
    if not cands:
        return None
    listing = "\n".join(f"{i+1}. {c['title']}  ({c['source']})" for i, c in enumerate(cands))
    prompt = f"""You are a viral-content strategist for a faceless AI/tech YouTube channel.
Score each story 1-10 for VIRAL POTENTIAL. High scores require: genuine shock/surprise,
real stakes for ordinary people (jobs, money, privacy, safety), broad appeal beyond tech
insiders, emotional charge (awe / fear / outrage / wonder), and an obvious one-line
"stop scrolling" framing. Punish: incremental version releases, academic papers, niche
developer tooling, and anything a non-tech person wouldn't care about.

{listing}

Return ONLY JSON, every story included, best first:
{{"picks":[{{"n":1,"viral_score":8,"angle":"the viral angle in one sentence",
"hook_idea":"the exact first spoken line"}}]}}"""
    d = llm.generate_json(prompt)
    if not d or not isinstance(d.get("picks"), list):
        return None
    best = None
    for p in d["picks"]:
        try:
            n, score = int(p.get("n", 0)), float(p.get("viral_score", 0))
        except (TypeError, ValueError):
            continue
        if 1 <= n <= len(cands) and (best is None or score > best[1]):
            best = (cands[n - 1], score, str(p.get("angle", "")), str(p.get("hook_idea", "")))
    return best


# --------------------------------------------------------------- format: news
def script_news(item: dict, viral_hint: tuple | None = None) -> dict | None:
    title, source, url = item["title"], item["source"], item.get("url", "")
    grounding = fetch_text(url)
    ground_block = (
        f"\nSOURCE EXCERPT (ground every claim in this; NEVER copy sentences verbatim — always "
        f"rephrase in your own spoken words):\n{grounding}\n"
        if grounding else "\n(No source excerpt available — stay general and clearly attribute.)\n"
    )
    angle_block = ""
    if viral_hint:
        _, _, angle, hook_idea = viral_hint
        if angle or hook_idea:
            angle_block = (f"\nEDITORIAL ANGLE (lean into this — it is why the story can go viral):"
                           f"\n- Angle: {angle}\n- Opening-line idea: {hook_idea}\n"
                           f"(Stay accurate; the angle sharpens the framing, it never invents facts.)\n")
    prompt = f"""You are the lead writer for {fv.CHANNEL_NAME}, an authoritative faceless AI/tech
YouTube channel. Write an ENGAGING but strictly ACCURATE explainer on this real development.

HEADLINE: {title}
SOURCE: {source}  ({url})
{ground_block}{angle_block}
ACCURACY RULES:
- Attribute uncertain claims ("according to {source}"). Never invent numbers or quotes.
- Spend at least a third of the video on WHY THIS MATTERS to a curious general-tech viewer:
  what changes for their job, money, phone, or daily life. That analysis is YOUR added value.
{_RETENTION_RULES}
{_VISUAL_RULES}

{_output_contract("14-18", "55-80")}"""
    s = llm.generate_json(prompt, max_tokens=8192)
    s = _validate_script(s, title, url)
    if s:
        s["grounding"] = grounding
        s["format"] = "news"
    return s


# --------------------------------------------------------------- format: evergreen
def pick_evergreen_topic(signals: list[dict]) -> dict | None:
    """Turn current signal themes into a durable, search-driven question topic."""
    used = _read_json(USED_TOPICS, [])[-60:]
    themes = "; ".join(i["title"][:70] for i in signals[:10]) or "large language models, AI agents, AI chips"
    prompt = f"""You are the strategist for {fv.CHANNEL_NAME}, an AI/tech education YouTube channel.

Current AI news themes (for relevance only): {themes}
ALREADY COVERED (never repeat or near-repeat): {"; ".join(t[:60] for t in used)}

Propose 5 EVERGREEN video topics a general tech audience actively SEARCHES for — "how does X
actually work", "why is X such a big deal", "what happens when X", "X vs Y, honestly". They must
stay accurate and interesting for at least a year (no ephemeral version-number news). Favor
topics with a built-in curiosity gap and real search volume.

Return ONLY JSON: {{"topics":[{{"title_idea":"...","search_question":"the exact question people
type","angle":"1-2 sentences on the unique take"}}]}}"""
    d = llm.generate_json(prompt)
    if not d or not d.get("topics"):
        return None
    used_norm = [t.lower() for t in used]
    for t in d["topics"]:
        idea = str(t.get("title_idea", "")).strip()
        if idea and idea.lower() not in used_norm and not too_many_failures(idea):
            return t
    return None


def script_evergreen(topic: dict) -> dict | None:
    prompt = f"""You are the lead writer for {fv.CHANNEL_NAME}, an authoritative faceless AI/tech
YouTube channel. Write a TIMELESS, search-optimized explainer.

TOPIC: {topic['title_idea']}
SEARCH QUESTION IT MUST FULLY ANSWER: {topic.get('search_question', topic['title_idea'])}
ANGLE: {topic.get('angle', '')}

TIMELESSNESS RULES:
- This video must still be accurate and satisfying in one year. NEVER use these words:
  {", ".join(_BANNED_DATED)}. No "recently", no specific product versions unless essential.
- Structure it like a mini documentary: setup -> tension/problem -> resolution -> what it means.
- Be technically correct but explain like a brilliant friend, not a textbook. Concrete analogies.
- Never invent numbers; use well-established facts only.
{_RETENTION_RULES}
{_VISUAL_RULES}

{_output_contract("16-20", "60-85")}"""
    s = llm.generate_json(prompt, max_tokens=8192)
    s = _validate_script(s, topic.get("title_idea", ""))
    if s:
        s["grounding"] = ""
        s["format"] = "evergreen"
    return s


# --------------------------------------------------------------- format: roundup
def script_roundup(items: list[dict]) -> dict | None:
    picked, seen_sources = [], set()
    for it in items:
        src = it.get("source", "")
        if src in seen_sources and len(seen_sources) > 2:
            continue
        seen_sources.add(src)
        picked.append(it)
        if len(picked) == 5:
            break
    if len(picked) < 3:
        return None
    stories = []
    for i, it in enumerate(picked, 1):
        g = fetch_text(it.get("url", ""), limit=1200)
        stories.append(f"STORY {i}: {it['title']} (source: {it['source']}, {it.get('url','')})\n"
                       f"EXCERPT: {g[:900] if g else '(none — attribute carefully)'}")
    stories_block = "\n\n".join(stories)
    prompt = f"""You are the lead writer for {fv.CHANNEL_NAME}. Write this week's AI ROUNDUP —
a countdown of the {len(picked)} AI stories that actually mattered this week, best for last.

{stories_block}

ROUNDUP RULES:
- 2-3 scenes per story: what happened (rephrased in your own words, attributed) + why it matters.
- Between stories use one-line transitions that tease the next ("number two is the one companies
  are scared of").
- Scene 1 = hook: tease the #1 story WITHOUT revealing it + promise the full picture.
- Never copy source sentences verbatim; your curation and analysis are the added value.
{_VISUAL_RULES}

{_output_contract("14-18", "50-75")}"""
    s = llm.generate_json(prompt, max_tokens=8192)
    s = _validate_script(s, "This Week in AI", picked[0].get("url", ""))
    if s:
        s["grounding"] = " ".join(fetch_text(it.get("url", ""), limit=1000) for it in picked[:3])
        s["format"] = "roundup"
        s["roundup_items"] = [{"title": it["title"], "url": it.get("url", "")} for it in picked]
    return s


# --------------------------------------------------------------- quality passes
def critique_pass(script: dict) -> dict:
    """One ruthless retention-editor pass. Falls back to the original on any failure."""
    try:
        compact = {k: script[k] for k in ("titles", "title", "thumb_text", "description", "tags", "scenes")
                   if k in script}
        prompt = f"""You are a ruthless YouTube retention editor. Improve this script for a faceless
AI/tech channel. Judge: (1) does scene 1 hook in the first 8 words with a real curiosity gap and a
promise? (2) is there a mid-video open loop and payoff? (3) any vague hype, filler, repeated ideas,
or sentences that sound like a written article instead of speech? (4) is the best of the 3 titles
actually the strongest (curiosity + concrete noun + keyword early)? (5) does thumb_text create an
irresistible curiosity gap in <=4 words?

Rewrite EVERY weak part. Keep the same JSON schema and roughly the same length; keep every
visual_query unless the narration changed meaning. Never add facts that were not present.

SCRIPT:
{json.dumps(compact, ensure_ascii=False)}

Return ONLY the full corrected JSON (same schema)."""
        improved = llm.generate_json(prompt, max_tokens=8192, temperature=0.4)
        improved = _validate_script(improved, script["title"], script.get("source_url", ""))
        old_words = sum(len(sc["narration"].split()) for sc in script["scenes"])
        new_words = sum(len(sc["narration"].split()) for sc in improved["scenes"]) if improved else 0
        # an "improvement" that compresses the video is a regression — watch time is the product
        if (improved and len(improved["scenes"]) >= max(5, len(script["scenes"]) - 4)
                and new_words >= old_words * 0.75):
            for carry in ("format", "grounding", "roundup_items", "signal_title"):
                if carry in script:
                    improved[carry] = script[carry]
            print("  ✍️  Critique pass applied.")
            return improved
    except Exception as e:
        print(f"   ⚠️ critique pass skipped: {e}")
    return script


def enforce_length(script: dict, min_words: int) -> dict:
    words = sum(len(sc["narration"].split()) for sc in script["scenes"])
    if words >= min_words:
        return script
    try:
        prompt = f"""This YouTube script is too short ({words} words; it needs {min_words}+ to hit the
target watch time). Expand it by DEEPENING scenes (real examples, mechanisms, implications) — not
padding. Keep the same JSON schema, hooks, and visual_query values; add 2-4 new scenes with fresh
visual_query values where depth is missing. Never invent numbers.

SCRIPT:
{json.dumps({k: script[k] for k in ('title', 'thumb_text', 'description', 'tags', 'scenes')}, ensure_ascii=False)}

Return ONLY the full expanded JSON (same schema)."""
        bigger = llm.generate_json(prompt, max_tokens=8192, temperature=0.5)
        bigger = _validate_script(bigger, script["title"], script.get("source_url", ""))
        if bigger:
            new_words = sum(len(sc["narration"].split()) for sc in bigger["scenes"])
            if new_words > words:
                for carry in ("format", "grounding", "roundup_items", "signal_title"):
                    if carry in script:
                        bigger[carry] = script[carry]
                print(f"  ✍️  Expanded {words} -> {new_words} words.")
                return bigger
    except Exception as e:
        print(f"   ⚠️ length pass skipped: {e}")
    return script


# --------------------------------------------------------------- voice
def synthesize_voice(narration: str):
    """Provider chain: clone (local, non-commercial!) / kokoro -> edge. Returns (audio, words|None)."""
    provider = (str(fv.TTS_PROVIDER) or "kokoro").lower()

    if provider == "clone" and voice.available():
        print("  🎤 Cloned voice (LOCAL use only — Coqui CPML license is NON-COMMERCIAL;")
        print("     do not use the clone on monetized uploads).")
        out = voice.synth_clone(narration, str(fv.TEMP / "voice.wav"))
        if out:
            return out, None

    if provider in ("kokoro", "clone"):
        if tts_kokoro.available():
            print(f"  🎙️  Kokoro voice '{fv.KOKORO_VOICE}' (free, neural, local)...")
            out = tts_kokoro.synth(narration, str(fv.TEMP / "voice.wav"))
            if out:
                return out, None
        print("   ⚠️ Kokoro unavailable — falling back to edge-tts.")

    audio = str(fv.TEMP / "voice.mp3")
    words = captions.synth_with_words(narration, fv.VOICE, fv.RATE, audio)
    return (audio, words) if words else (None, None)


def build_chapters(script: dict, starts: list, shift: float) -> str:
    """YouTube chapter list from real scene timings (>=3 chapters, 0:00 first).
    Chapters lift navigation, search snippets, and 'key moments' — free algorithm juice."""
    scenes = script.get("scenes", [])
    if not starts or len(scenes) < 8 or len(starts) != len(scenes):
        return ""
    n = 5 if len(scenes) >= 12 else 4
    idxs = sorted({0} | {round(k * len(scenes) / n) for k in range(1, n)})
    idxs = [i for i in idxs if i < len(scenes)]
    labels = {}
    try:
        snippets = [{"n": i, "text": scenes[i]["narration"][:100]} for i in idxs]
        d = llm.generate_json(
            "For each snippet, give a punchy 2-5 word YouTube chapter title (title case, "
            "no numbering, no punctuation). Return ONLY JSON "
            '{"chapters":[{"n":<n>,"title":"..."}]}\n' + json.dumps(snippets, ensure_ascii=False))
        for c in (d or {}).get("chapters", []):
            labels[int(c.get("n", -1))] = re.sub(r"[<>]", "", str(c.get("title", ""))).strip()[:40]
    except Exception:
        pass
    lines, prev = [], -999.0
    for k, i in enumerate(idxs):
        t = 0.0 if i == 0 else float(starts[i]) + shift
        if t - prev < 12:          # YouTube requires sensibly spaced chapters
            continue
        prev = t
        label = labels.get(i) or ("The Hook" if i == 0 else f"Part {k + 1}")
        lines.append(f"{int(t // 60)}:{int(t % 60):02d} {label}")
    if len(lines) < 3:
        return ""
    return "Chapters:\n" + "\n".join(lines)


def scene_durations(script: dict, words: list, audio_dur: float) -> list | None:
    """Per-scene durations from real word timings, so visuals track the narration."""
    counts = [max(1, len(sc.get("narration", "").split())) for sc in script["scenes"]]
    total, n = sum(counts), len(words)
    if n < 20 or total < 20:
        return None
    bounds = [0.0]
    acc = 0
    for c in counts[:-1]:
        acc += c
        idx = min(n - 1, round(acc / total * n))
        bounds.append(float(words[idx][0]))
    bounds.append(max(float(audio_dur), float(words[-1][1])))
    durs = []
    for i in range(len(counts)):
        durs.append(max(1.5, bounds[i + 1] - bounds[i]))
    return durs


# --------------------------------------------------------------- orchestrate
def decide_format(force: str | None, ranked: list[dict]):
    """Virality-first format choice. Sunday keeps the roundup; every other day the
    viral judge decides: a genuinely hot story (>= VIRAL_THRESHOLD) overrides the
    calendar and runs as news; otherwise we bank an evergreen explainer.
    Returns (fmt, viral_hint)."""
    if force in ("news", "evergreen", "roundup"):
        return force, (viral_pick(ranked) if force == "news" else None)
    if _dt.date.today().weekday() == 6:
        return "roundup", None
    viral = viral_pick(ranked)
    if viral and viral[1] >= VIRAL_THRESHOLD:
        print(f"  🔥 Hot story (viral score {viral[1]:.0f}/10): {viral[0]['title'][:70]}")
        return "news", viral
    print(f"  🌤️  No breakout story today"
          f"{f' (best scored {viral[1]:.0f}/10)' if viral else ''} — banking an evergreen.")
    return "evergreen", None


def build_script(fmt: str, ranked: list[dict], viral_hint=None) -> dict | None:
    if fmt == "roundup":
        print("  🗞️  Weekly roundup from", len(ranked), "candidates")
        return script_roundup(ranked)
    if fmt == "news":
        # hottest story first, then ranking order
        order = list(ranked)
        if viral_hint and viral_hint[0] in order:
            order.remove(viral_hint[0])
            order.insert(0, viral_hint[0])
        for i, cand in enumerate(order[:3]):
            hint = viral_hint if (viral_hint and cand is viral_hint[0]) else None
            print(f"  📰 Trying: {cand['title'][:70]}  (fit={cand.get('fit_score')})")
            s = script_news(cand, viral_hint=hint)
            if s:
                s["signal_title"] = cand["title"]
                return s
            mark_failed(cand["title"])
            print("     ↻ script failed, trying next story...")
        return None
    # evergreen
    topic = pick_evergreen_topic(ranked)
    if not topic:
        print("   ⚠️ No evergreen topic — falling back to news format.")
        return build_script("news", ranked, viral_hint)
    print(f"  🌲 Evergreen: {topic['title_idea']}")
    s = script_evergreen(topic)
    if s:
        s["signal_title"] = topic["title_idea"]
    else:
        mark_failed(topic["title_idea"])
    return s


MIN_WORDS = {"news": 850, "evergreen": 1000, "roundup": 800}
MAX_OVERLAP = 0.08


def run(publish: bool = False, force_format: str | None = None) -> dict | None:
    print("=" * 70)
    print(f"  {fv.CHANNEL_NAME} — content pipeline v2 (viral-first)")
    print("=" * 70)
    ranked = [i for i in signal_engine.rank(limit=20) if not too_many_failures(i["title"])]
    fmt, viral = decide_format(force_format, ranked)
    print(f"  🧭 Format today: {fmt.upper()}")

    script = build_script(fmt, ranked, viral)
    if not script:
        print("  ❌ No script produced (LLM/signals down). Failing loudly.")
        record_run(status="NO_SCRIPT", format=fmt)
        return None

    # critique first, THEN enforce length — the editor pass tends to compress
    script = critique_pass(script)
    script = enforce_length(script, MIN_WORDS.get(script.get("format", fmt), 850))

    words_total = sum(len(sc["narration"].split()) for sc in script["scenes"])
    print(f"  ✅ Script: '{script['title']}' | {len(script['scenes'])} scenes | "
          f"{words_total} words (~{words_total / 150:.1f} min)")
    (fv.TEMP / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False),
                                         encoding="utf-8")

    # Policy gate: the narration must be a transformation, not a copy, of its source.
    narration = " . . . ".join(sc["narration"] for sc in script["scenes"])
    overlap = verbatim_overlap(narration, script.get("grounding", ""))
    if overlap > MAX_OVERLAP:
        print(f"  🛑 POLICY GATE: {overlap:.0%} of the narration is verbatim from the source. Blocking.")
        record_run(status="POLICY_BLOCKED", format=fmt, title=script["title"], overlap=round(overlap, 3))
        mark_failed(script.get("signal_title", script["title"]))
        return None

    # ---- render: clips -> voice -> word timing -> build (scene-synced) ----
    scene_clips = eng.step3_download(script)

    print("\n[4/10] 🎙️ Voiceover...")
    audio, edge_words = synthesize_voice(narration)
    if not audio:
        print("  ❌ Voice step failed.")
        record_run(status="VOICE_FAILED", format=fmt, title=script["title"])
        return None
    words = captions.transcribe_words(audio) or edge_words
    if not words:
        print("  ❌ Caption timing failed.")
        record_run(status="TIMING_FAILED", format=fmt, title=script["title"])
        return None
    audio_dur = eng.dur(audio)
    durs = scene_durations(script, words, audio_dur)
    starts = None
    if durs:
        starts = [0.0]
        for d in durs[:-1]:
            starts.append(starts[-1] + d)
    print(f"  ✅ Voice {Path(audio).suffix} | {audio_dur:.0f}s | {len(words)} timed words | "
          f"scene sync: {'ON' if durs else 'uniform fallback'}")

    video = eng.step5_build(script, scene_clips, audio, None, scene_durs=durs)
    if not video:
        print("  ❌ Build step failed.")
        mark_failed(script.get("signal_title", script["title"]))
        record_run(status="BUILD_FAILED", format=fmt, title=script["title"])
        return None

    # Thumbnail + Shorts from the CLEAN content (before long-form captions are burned).
    # Person-first thumbnail mined from this run's own footage; engine design is the fallback.
    thumb_name = str(fv.THUMBS / f"thumb_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
    thumb = (thumbnail.make(video, fv.TEMP, script.get("thumb_text", ""), thumb_name)
             or eng.step7_thumb(video, script["title"], thumb_text=script.get("thumb_text", "")))
    shorts = shorts_mod.make_shorts(video, script, words, scene_starts=starts)

    print("  📝 Burning live word-by-word captions...")
    ass = captions.build_ass(words, str(fv.TEMP / "captions.ass"), play_w=eng.WIDTH, play_h=eng.HEIGHT)
    video = captions.burn_ass(video, ass)

    print("\n  🎬 Branding (cold-open: hook first, then the sting)...")
    video = branding.add_intro_outro(video, split_at=(durs[0] if durs else None))

    if not qa_video(video, audio_dur):
        mark_failed(script.get("signal_title", script["title"]))
        record_run(status="QA_FAILED", format=fmt, title=script["title"])
        return None

    # chapters on the FINAL timeline (cold-open inserts the intro after scene 1)
    if starts:
        intro_shift = eng.dur(str(fv.ASSETS / "intro.mp4")) or 2.6
        chapters = build_chapters(script, starts, intro_shift)
        if chapters:
            script["description"] = script["description"].rstrip() + "\n\n" + chapters
            print(f"  📑 {chapters.count(chr(10))} chapters added to description")

    meta = eng.step8_meta(script, len(shorts))

    status, yt_url, yt_shorts = "RENDER_ONLY", None, []
    if publish and fv.flag("auto_upload_youtube"):
        print("\n  📤 Publishing...")
        yt_url = eng.yt_upload(video, script["title"], script["description"],
                               script.get("tags", []), thumb)
        if not yt_url:
            print("  ❌ Long-form upload failed — keeping topic unburned, failing the run.")
            eng.save_report(script, video, shorts, thumb, meta, None, [], status="UPLOAD_FAILED")
            record_run(status="UPLOAD_FAILED", format=fmt, title=script["title"])
            return None
        for i, sp in enumerate(shorts):
            mi = meta[i] if i < len(meta) else (meta[0] if meta else {})
            sd = f"🎬 FULL VIDEO: {yt_url}\n\n{mi.get('description', '')}"
            u = eng.yt_upload(sp, mi.get("title", script["title"] + " #Shorts"),
                              sd, script.get("tags", []) + ["Shorts"], is_short=True)
            if u:
                yt_shorts.append(u)
        status = "PUBLISHED"
    else:
        print("\n  ⏸️  Render-only (publish skipped).")

    # Success — only NOW is the topic burned.
    mark_used(script.get("signal_title", script["title"]), script.get("source_url", ""))
    for it in script.get("roundup_items", []):
        mark_used(it["title"], it.get("url", ""))

    report = eng.save_report(script, video, shorts, thumb, meta, yt_url, yt_shorts, status=status)
    record_run(status=status, format=fmt, title=script["title"], words=words_total,
               video=eng._rel(video), youtube_url=yt_url, shorts_published=len(yt_shorts),
               shorts_rendered=len(shorts),
               viral_score=(viral[1] if viral else None))
    eng.cleanup()
    print(f"\n  ✅ DONE [{status}] → {video}")
    return report


if __name__ == "__main__":
    args = [a.lower() for a in sys.argv[1:]]
    do_publish = "publish" in args
    forced = next((a for a in args if a in ("news", "evergreen", "roundup")), None)
    ok = run(publish=do_publish, force_format=forced)
    sys.exit(0 if ok else 1)
