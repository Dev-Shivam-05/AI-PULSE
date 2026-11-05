"""
v3-S.1: the native concept Short (docs/spec/ai-pulse-v3s1.md, review row 7).

A 20-28 s vertical Short with its OWN script, written from the day's topic by one
model call: a headline of at most 8 words over ONE complete diagram (a comparison
or causal steps), fully drawn at 0.00 s and held to the end, while the voice
answers the question in its first sentence. It replaces the storyboard engine's
Short; the crop excerpt stays as the control and is not touched (row 8).

The timeline is checked against the ENCODED file, not the script: the audio is
pulled back out of the finished mp4 and timed by faster-whisper, the duration is
ffprobe's, and the text size and frame-0 completeness come from the renderer's
own metadata. One automatic repair attempt (a second model call that is told
what failed); a second failure skips the native Short for the day.

Fail soft everywhere: make() returns None (the reason in `last_skip`) and never
raises. Playwright is imported inside storyboard.render_meta only.
"""
from __future__ import annotations

import difflib
import json
import math
import re
import subprocess
from datetime import datetime
from pathlib import Path

from factverse import config as fv
from factverse import captions as cap
from factverse import gates
from factverse import llm
from factverse import storyboard as sb

# ------------------------------------------------------------------ locked values
# Round 3 (03_chatgpt.md §2 "Native concept Short"), copied verbatim into the spec.
W, H = sb.W, sb.H                     # 1080x1920
HEADLINE_WORDS = 8
FIRST_SPEECH_S = 0.30
FIRST_SENTENCE_WORDS = 14
FIRST_SENTENCE_END_S = 5.00
ANSWER_BY_S = 7.0
MIN_LEN_S, MAX_LEN_S = 20.0, 28.0
MAX_WORDS = 65
END_MARGIN_S = 2.0                    # takeaway + qualification complete by duration - 2 s
NO_REVEAL_S = 2.0                     # nothing of the headline/diagram moves before 2 s
MIN_TEXT_PX = 60
REPAIRS = 1
TEMPLATES = ("compare", "steps")      # "at least one visible causal step or comparison"
# Delegated (spec "Delegated decisions"): margins INSIDE the round-3 limits, so a
# whisper timestamp a few frames off cannot fail a Short that meets the rule.
LEAD_S = 0.15                         # first word placed at 0.15 s (limit 0.30)
HOLD_S = 2.5                          # held after the last word (limit 2.0)
SILENCE_DB, SILENCE_MIN_S = -45, 0.10  # fallback onset only (no whisper)
FRAME_S = 1.0 / sb.FPS
CTA_TERMS = ("subscribe", "full video", "link in", "like and", "follow us", "follow for",
             "comment below", "check out the channel")

last_skip = ""                        # why the last make() returned None


# ------------------------------------------------------------------ text helpers
def _clean(v) -> str:
    return sb._clean_text(v)


def spoken_words(text_or_sentences) -> int:
    if isinstance(text_or_sentences, (list, tuple)):
        text_or_sentences = " ".join(str(s) for s in text_or_sentences)
    return sum(1 for w in str(text_or_sentences).split() if any(c.isalnum() for c in w))


def _as_sentences(v) -> list[str]:
    """A list of complete sentences from whatever the model sent (coerced)."""
    if isinstance(v, str):
        parts = re.split(r"(?<=[.!?])\s+", v)
    elif isinstance(v, list):
        parts = [x for x in v if isinstance(x, (str, int, float)) and not isinstance(x, bool)]
    else:
        parts = []
    out = []
    for p in parts:
        s = re.sub(r"https?://\S+", "", _clean(p)).strip()
        if not s or not any(c.isalnum() for c in s):
            continue
        if s[-1] not in ".!?":
            s += "."
        out.append(s)
    return out


def _as_index(v, hi: int, default: int) -> int:
    try:
        i = int(float(v))
    except (TypeError, ValueError):
        return default
    return i if 0 <= i <= hi else default


def _numbers_ok(texts: list[str], source: str) -> list[str]:
    have = set(sb._numbers(source))
    return [n for t in texts for n in sb._numbers(t) if n not in have]


# ------------------------------------------------------------------ the model call
def _excerpt_block(hook: str, excerpt: str) -> str:
    if not excerpt:
        return ""
    return (f"\nTODAY'S EXCERPT SHORT (a clip of the video) is hooked \"{_clean(hook)[:120]}\" and says:\n"
            f"{_clean(excerpt)[:1200]}\nIf that excerpt answers a real question, answer the SAME question.\n")


def prompt(script: dict, source: str, hook: str = "", excerpt: str = "") -> str:
    title = _clean(script.get("title"))[:140]
    narration = " ".join(_clean(s.get("narration")) for s in (script.get("scenes") or [])
                         if isinstance(s, dict))[:3000]
    return f"""You write ONE 20-28 second vertical YouTube Short that answers one question BY ITSELF.
It is not a clip of a longer video: it is a self-contained concept answer drawn as ONE complete
diagram that is fully on screen from the first frame and stays there to the end.
TODAY'S TOPIC: {title}
TODAY'S VIDEO NARRATION (context): {narration}
{_excerpt_block(hook, excerpt)}
RULES
- "headline": at most {HEADLINE_WORDS} words; names the subject. No hype words, no all-caps.
- "sentences": the spoken narration, a list of COMPLETE sentences, at most {MAX_WORDS} words in total.
- Sentence 1 has at most {FIRST_SENTENCE_WORDS} words and states the answer itself, never a promise to explain later.
- The core answer is sentence 1 or 2; "answer" is its number.
- "diagram": ONE of
  - compare {{"left": [el, ...], "right": [el, ...]}}: 2-3 elements per side, element 1 is the column title,
    every element at most {sb.COMPARE_WORDS} words;
  - steps {{"steps": [el, ...]}}: 3-5 short causal steps in the order you speak them.
  el = {{"text": "...", "cue": "1-3 words copied from your sentences, spoken when we point at it"}}.
  Every diagram label must reuse a word you SPEAK. The diagram must show a cause or a comparison,
  not restate a sentence. Space is tight (all text is drawn at 60 px or larger on a phone): keep
  the headline and every label as short as the meaning allows.
- A necessary qualification ("only when...", "not for...") is spoken BEFORE the last sentence;
  "qualification" is its number, or 0 when none is needed. Never leave a misleading simplification.
- The last sentence is the complete takeaway.
- No greeting, no channel name, no "subscribe", no "watch the full video".
- Every number exactly as written in SOURCE FACTS; no number that is not there.
- "title": the Short's YouTube title, at most 60 characters, naming the concrete subject.
Return ONLY JSON:
{{"question":"...","headline":"...","sentences":["...","..."],"answer":1,"qualification":0,
 "diagram":{{"template":"compare","slots":{{"left":[{{"text":"...","cue":"..."}}],"right":[{{"text":"...","cue":"..."}}]}}}},
 "title":"..."}}

SOURCE FACTS: {source[:6000]}"""


def repair_prompt(base: str, raw, failures: list[str]) -> str:
    try:
        prev = json.dumps(raw, ensure_ascii=False)[:3000]
    except (TypeError, ValueError):
        prev = str(raw)[:3000]
    return (base + "\n\nYOUR PREVIOUS ANSWER FAILED THESE CHECKS (measured on the rendered video):\n- "
            + "\n- ".join(failures[:8]) + f"\nPREVIOUS ANSWER: {prev}\n"
            "Return the corrected JSON only. Keep what passed; shorten rather than cut a sentence.")


def source_text(script: dict) -> str:
    """What the native Short's numbers are checked against: the fact-check sources
    plus the long-form narration (already fact-checked by run())."""
    narration = " ".join(str(s.get("narration", "")) for s in (script.get("scenes") or [])
                         if isinstance(s, dict))
    return gates.fact_sources(script) + "\n" + narration


# ------------------------------------------------------------------ validation
def validate(raw, source: str) -> tuple[dict | None, list[str]]:
    """Coerce and check the model's answer. (spec, []) or (None, failures)."""
    if not isinstance(raw, dict):
        return None, ["the answer was not a JSON object"]
    f: list[str] = []
    headline = _clean(raw.get("headline"))
    sentences = _as_sentences(raw.get("sentences"))
    narration = " ".join(sentences)
    if not headline or len(headline.split()) > HEADLINE_WORDS:
        f.append(f"headline must be 1-{HEADLINE_WORDS} words (got {len(headline.split())})")
    if gates.hype_terms(headline):
        f.append(f"headline has hype words: {gates.hype_terms(headline)}")
    if not sentences:
        f.append("no sentences")
        return None, f
    n1 = spoken_words(sentences[0])
    if n1 > FIRST_SENTENCE_WORDS:
        f.append(f"sentence 1 has {n1} words (max {FIRST_SENTENCE_WORDS})")
    total = spoken_words(sentences)
    if total > MAX_WORDS:
        f.append(f"{total} spoken words (max {MAX_WORDS}); drop a sentence, never cut one")
    answer = _as_index(raw.get("answer"), len(sentences), 1) or 1
    qual = _as_index(raw.get("qualification"), len(sentences), 0)
    if qual and qual == len(sentences) and len(sentences) > 1:
        f.append("the qualification is the last sentence; it must come before the takeaway")
    low = narration.lower()
    cta = [t for t in CTA_TERMS if t in low]
    if cta:
        f.append(f"a call to action in the narration: {cta}")
    d = raw.get("diagram") if isinstance(raw.get("diagram"), dict) else {}
    template = _clean(d.get("template")).lower()
    els = sb._slots(template, d.get("slots"), "") if template in TEMPLATES else None
    if template == "compare" and els is not None:
        if sum(1 for e in els if e["role"] in ("litem", "ritem")) < 1:
            els = None                       # two bare titles are not a comparison
    if els is None:
        f.append("diagram must be a valid compare (titles + items) or steps (3-5 steps)")
    elif not sb.gate_ok(els, narration):
        f.append("a diagram label shares no spoken word, or shows a number that is not spoken")
    if headline and not sb.gate_ok([{"text": headline}], narration):
        f.append("the headline shares no spoken word, or shows a number that is not spoken")
    bad = _numbers_ok([headline, narration] + [e["text"] for e in (els or [])], source)
    if bad:
        f.append(f"numbers not in the source facts: {sorted(set(bad))[:5]}")
    if f:
        return None, f
    title = re.sub(r"#shorts", "", _clean(raw.get("title")), flags=re.I).strip()
    if not title or len(title) > 60 or gates.hype_terms(title):
        title = headline
    return {"question": _clean(raw.get("question"))[:200], "headline": headline,
            "sentences": sentences, "answer": answer, "qualification": qual,
            "template": template, "els": els, "title": f"{title} #Shorts"}, []


def match_level(spec: dict, excerpt: str) -> str:
    """Pilot B pairing: "same_question" when every diagram label is grounded in the
    crop excerpt's own narration (the v3-G.1 gate, reused), else the weaker
    "concept_family" (both come from the same day's topic)."""
    if excerpt and spec.get("els") and sb.gate_ok(spec["els"], excerpt):
        return "same_question"
    return "concept_family"


# ------------------------------------------------------------------ board
def board(spec: dict, words: list, length: float) -> dict:
    """ONE beat: the headline + the whole diagram, drawn at t = -10 (fully on screen
    at frame 0, no entrance). A diagram label is POINTED AT (the 240 ms highlight)
    when its cue is spoken — only inside [2 s, length - 2 s), so nothing moves in the
    first 2 s and the final visual is held."""
    els = [dict(e, t=-10.0, hl=[]) for e in spec["els"]]
    head = {"role": "head", "text": spec["headline"], "cue": "", "t": -10.0, "hl": []}
    wn = [sb._norm_word(w[2]) for w in words]
    for e in els:
        i = sb._match(wn, e.get("cue", ""), 0, len(wn))
        if i is not None:
            t = round(float(words[i][0]), 3)
            if NO_REVEAL_S <= t and t + sb.HIGHLIGHT_S <= length - END_MARGIN_S:
                e["hl"].append(t)
    b = {"W": W, "H": H, "length": float(length), "floor": MIN_TEXT_PX,
         "beats": [{"template": spec["template"], "start": 0.0, "end": float(length),
                    "narration": " ".join(spec["sentences"]), "w0": 0, "w1": len(words),
                    "els": els, "head": head, "stack": spec["template"] == "compare"}]}
    b["intervals"] = sb.timeline(b)
    return b


# ------------------------------------------------------------------ timing
def plan_length(words: list) -> tuple[float, float] | None:
    """(shift, length): trim the TTS lead so the first word starts at LEAD_S, then
    hold HOLD_S after the last word; length is at least MIN_LEN_S (the hold grows)
    and rounded up to a whole frame. None when the speech cannot fit MAX_LEN_S."""
    if not words:
        return None
    shift = max(0.0, float(words[0][0]) - LEAD_S)
    end = float(words[-1][1]) - shift
    length = max(MIN_LEN_S, end + HOLD_S)
    length = math.ceil(length / FRAME_S - 1e-6) * FRAME_S
    return (round(shift, 3), round(length, 3)) if length <= MAX_LEN_S + 1e-6 else None


def _tokens_of(sentences: list[str]) -> tuple[list[str], list[int]]:
    toks, ends = [], []
    for s in sentences:
        for w in s.split():
            c = cap._clean_word(w).lower()
            if any(ch.isalnum() for ch in c):
                toks.append(c)
        ends.append(len(toks))
    return toks, ends


def sentence_ends(words: list, sentences: list[str]) -> list[float]:
    """When each sentence FINISHES in `words` (timed words of the encoded audio).

    Alignment as captions.correct_words does it (equal blocks and equal-length
    replacements). A sentence ends just before the first aligned word of any LATER
    sentence — conservative: an unaligned word at a boundary counts as the earlier
    sentence's, never makes it finish sooner."""
    if not words or not sentences:
        return []
    toks, ends = _tokens_of(sentences)
    a = [cap._clean_word(w[2]).lower() for w in words]
    tw: list[int | None] = [None] * len(toks)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=toks, autojunk=False).get_opcodes():
        if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
            for k in range(j2 - j1):
                tw[j1 + k] = i1 + k
    out = []
    for end in ends:
        nxt = next((tw[j] for j in range(end, len(toks)) if tw[j] is not None), None)
        out.append(round(float(words[-1][1] if nxt is None else words[max(0, nxt - 1)][1]), 3))
    return out


def parse_silences(stderr: str) -> list[tuple[float, float | None]]:
    """[(start, end|None)] from ffmpeg silencedetect output, in order."""
    out: list[tuple[float, float | None]] = []
    for line in (stderr or "").splitlines():
        m = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        if m:
            out.append((max(0.0, float(m.group(1))), None))
            continue
        m = re.search(r"silence_end:\s*([\d.]+)", line)
        if m and out and out[-1][1] is None:
            out[-1] = (out[-1][0], float(m.group(1)))
    return out


def parse_onset(stderr: str) -> float | None:
    """First speech onset: the end of a silence that starts at 0, else 0.0 (sound
    from the first sample). None when the whole file is silent."""
    sil = parse_silences(stderr)
    if sil and sil[0][0] <= 0.01:
        return sil[0][1]
    return 0.0


def parse_offset(stderr: str, duration: float) -> float | None:
    """Last speech offset: the start of a silence that runs to the end of the file
    (ffmpeg closes it at EOF, or never), else the duration (sound to the end)."""
    sil = parse_silences(stderr)
    if sil and (sil[-1][1] is None or sil[-1][1] >= duration - FRAME_S):
        return sil[-1][0]
    return duration if duration else None


def extract_args(mp4: str, wav: str) -> list[str]:
    return [fv.FFMPEG or "ffmpeg", "-y", "-i", str(mp4), "-vn", "-ac", "1", "-ar", "16000", str(wav)]


def silence_args(mp4: str) -> list[str]:
    return [fv.FFMPEG or "ffmpeg", "-hide_banner", "-i", str(mp4), "-vn", "-af",
            f"silencedetect=noise={SILENCE_DB}dB:d={SILENCE_MIN_S}", "-f", "null", "-"]


def measure(mp4: str, sentences: list[str], planned: list | None = None) -> dict:
    """The timeline of the ENCODED file.

    Two independent reads of the audio pulled back out of the mp4: whisper word
    timings ("asr"), and the energy onset/offset from silencedetect. Whisper clamps
    the first word to 0.00 s and smears word edges, so the gate takes the LATER of
    the two for the first speech and the takeaway's end (conservative). Without
    whisper the planned TTS timings are re-anchored on the measured onset
    ("tts+silencedetect")."""
    from factverse import shorts as shorts_mod  # noqa: PLC0415 — puts scripts/ on the path
    dur = round(float(shorts_mod.eng.dur(mp4) or 0.0), 3)
    m = {"duration": dur, "source": "none", "first_speech": None, "last_speech": None,
         "asr_first": None, "onset": None, "offset": None, "asr_words": None,
         "script_words": spoken_words(sentences), "sentence_ends": []}
    words = []
    wav = fv.TEMP / "nv_measure.wav"
    try:
        r = subprocess.run(silence_args(mp4), capture_output=True, text=True, timeout=120)
        m["onset"], m["offset"] = parse_onset(r.stderr), parse_offset(r.stderr, dur)
        r = subprocess.run(extract_args(mp4, str(wav)), capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and wav.exists():
            words = cap.transcribe_words(str(wav)) or []
        if words:
            m["source"], m["asr_words"] = "asr", len(words)
            m["asr_first"] = round(float(words[0][0]), 3)
        elif planned and m["onset"] is not None:
            d = m["onset"] - float(planned[0][0])
            words = [(s + d, e + d, w) for (s, e, w) in planned]
            m["source"] = "tts+silencedetect"
    except Exception as e:  # noqa: BLE001
        print(f"  ↻ native measure failed: {type(e).__name__}")
    if words:
        ends = sentence_ends(words, sentences)
        first, last = float(words[0][0]), float(words[-1][1])
        if m["onset"] is not None:
            first = max(first, float(m["onset"]))
        if m["offset"] is not None and ends:
            last = max(last, float(m["offset"]))
            ends[-1] = round(max(ends[-1], float(m["offset"])), 3)
        m["first_speech"], m["last_speech"], m["sentence_ends"] = round(first, 3), round(last, 3), ends
    return m


def gate(m: dict, spec: dict, meta: dict | None) -> list[str]:
    """Round 3's native rules against a measured timeline; [] = pass. Pure."""
    f: list[str] = []
    ends = m.get("sentence_ends") or []
    dur = float(m.get("duration") or 0.0)
    if m.get("first_speech") is None or not ends:
        return ["no word timings could be measured from the encoded file"]
    if m["first_speech"] > FIRST_SPEECH_S:
        f.append(f"speech starts at {m['first_speech']:.2f}s (by {FIRST_SPEECH_S}s)")
    if spoken_words(spec["sentences"][0]) > FIRST_SENTENCE_WORDS:
        f.append(f"sentence 1 is over {FIRST_SENTENCE_WORDS} words")
    if ends[0] > FIRST_SENTENCE_END_S:
        f.append(f"sentence 1 ends at {ends[0]:.2f}s (by {FIRST_SENTENCE_END_S}s): shorten it")
    a = int(spec.get("answer") or 1)
    if a > len(ends) or ends[a - 1] > ANSWER_BY_S:
        f.append(f"the answer (sentence {a}) ends after {ANSWER_BY_S}s")
    if not (MIN_LEN_S - FRAME_S <= dur <= MAX_LEN_S + FRAME_S):
        f.append(f"duration {dur:.2f}s (must be {MIN_LEN_S:.0f}-{MAX_LEN_S:.0f}s)")
    if int(m.get("script_words") or 0) > MAX_WORDS:
        f.append(f"{m['script_words']} spoken words (max {MAX_WORDS})")
    if ends[-1] > dur - END_MARGIN_S:
        f.append(f"the takeaway ends at {ends[-1]:.2f}s, after duration - {END_MARGIN_S:.0f}s")
    q = int(spec.get("qualification") or 0)
    if q and (q > len(ends) or ends[q - 1] > dur - END_MARGIN_S):
        f.append(f"the qualification ends after duration - {END_MARGIN_S:.0f}s")
    if len(str(spec.get("headline", "")).split()) > HEADLINE_WORDS:
        f.append(f"headline over {HEADLINE_WORDS} words")
    return f + (meta_failures(meta) if meta is not None else [])


def meta_failures(meta: dict) -> list[str]:
    """The renderer's own metadata against the 60 px and frame-0 rules."""
    f: list[str] = []
    if meta.get("unfit"):
        return [f"text does not fit at {MIN_TEXT_PX}px: shorten the headline or labels"]
    px = meta.get("min_px")
    if px is None or float(px) < MIN_TEXT_PX:
        f.append(f"smallest on-screen text is {px}px (min {MIN_TEXT_PX})")
    for t in (str(0.0), str(NO_REVEAL_S)):
        s = (meta.get("shown") or {}).get(t) or {}
        if not s.get("total") or s.get("shown") != s.get("total"):
            f.append(f"at {t}s only {s.get('shown')}/{s.get('total')} text elements are fully drawn")
    return f


# ------------------------------------------------------------------ render
def voice(text: str):
    """Own TTS path (own files: the long-form's voice.* must never be overwritten).
    Kokoro when the long-form uses it, else edge-tts with word boundaries."""
    from factverse import tts_kokoro  # noqa: PLC0415
    if str(getattr(fv, "TTS_PROVIDER", "") or "kokoro").lower() in ("kokoro", "clone") \
            and tts_kokoro.available():
        out = tts_kokoro.synth(text, str(fv.TEMP / "nv_voice.wav"))
        if out:
            return out, None
    out = str(fv.TEMP / "nv_voice.mp3")
    words = cap.synth_with_words(text, fv.VOICE, fv.RATE, out)
    return (out, words) if words else (None, None)


def mux_args(vis: str, audio: str, shift: float, length: float, brand: str, out: str) -> list[str]:
    """Picture + the voice with its lead trimmed (input seek), padded to `length`.
    The watermark is the control's (42 px, top-left); no hook overlay, no CTA."""
    wm = (f"drawtext=fontfile=short.ttf:text='{brand}':fontsize=42:fontcolor=white:"
          f"borderw=2:bordercolor=black:x=44:y=54")
    return [fv.FFMPEG or "ffmpeg", "-y", "-i", str(vis), "-ss", f"{shift:.3f}", "-i", str(audio),
            "-filter_complex",
            f"[0:v]setsar=1,{wm}[v];[1:a]apad,atrim=0:{length:.3f},asetpts=PTS-STARTPTS[a]",
            "-map", "[v]", "-map", "[a]", "-t", f"{length:.3f}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-c:a", "aac", "-b:a", "128k", str(out)]


def caption_args(raw: str, ass_name: str, out: str) -> list[str]:
    return [fv.FFMPEG or "ffmpeg", "-y", "-i", str(raw), "-vf", f"ass={ass_name}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-c:a", "copy",
            "-movflags", "+faststart", str(out)]


def planned_metrics(spec: dict, words: list, length: float) -> dict:
    return {"duration": length, "source": "planned", "first_speech": float(words[0][0]),
            "script_words": spoken_words(spec["sentences"]),
            "sentence_ends": sentence_ends(words, spec["sentences"])}


def build(spec: dict, tag: str = "") -> tuple[dict | None, list[str]]:
    """Voice -> plan -> render -> mux -> captions -> MEASURE THE FILE -> gate."""
    from factverse import shorts as shorts_mod  # noqa: PLC0415 — sets the engine path
    text = " ".join(spec["sentences"])
    audio, words = voice(text)
    if not audio:
        return None, ["voice synthesis failed"]
    if not words:
        words = cap.transcribe_words(audio)
    if not words:
        return None, ["no word timings for the voice"]
    words = cap.correct_words(words, text)
    pl = plan_length(words)
    if not pl:
        sp = float(words[-1][1]) - float(words[0][0])
        return None, [f"the spoken part is {sp:.1f}s; it must finish by {MAX_LEN_S - HOLD_S:.1f}s"]
    shift, length = pl
    tw = [(round(s - shift, 3), round(e - shift, 3), w) for (s, e, w) in words]
    pre = gate(planned_metrics(spec, tw, length), spec, None)
    if pre:
        return None, pre                     # fail fast: no render for a doomed timeline
    bd = board(spec, tw, length)
    vis, meta = sb.render_meta(bd, str(fv.TEMP / f"nv_vis{tag}.mp4"), tw, demote_unfit=False,
                               probes=(0.0, NO_REVEAL_S))
    if not vis:
        return None, (meta_failures(meta) if meta.get("unfit") else []) or ["render failed"]
    fonts_dir = shorts_mod._ensure_font()
    raw = fv.TEMP / f"nv_raw{tag}.mp4"
    r = subprocess.run(mux_args(vis, audio, shift, length, fv.CHANNEL_NAME, str(raw)),
                       cwd=str(fonts_dir), capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not raw.exists() or raw.stat().st_size < 10000:
        return None, [f"mux failed: {(r.stderr or '')[-160:]}"]
    ass = Path(cap.build_ass(tw, str(fv.TEMP / f"nv{tag}.ass"), play_w=W, play_h=H,
                             fontsize=68, max_words=3, margin_v=620))
    final = fv.SHORTS / f"short{tag}{sb.NATIVE_MARK}{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    r = subprocess.run(caption_args(str(raw), ass.name, str(final)), cwd=str(ass.parent),
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not final.exists() or final.stat().st_size < 10000:
        return None, [f"caption pass failed: {(r.stderr or '')[-160:]}"]
    m = measure(str(final), spec["sentences"], planned=tw)
    fails = gate(m, spec, meta)
    if fails:
        try:
            final.unlink()                   # a failed Short must never be found and uploaded
        except OSError:
            pass
        return None, fails
    return {"path": str(final), "measured": m, "min_px": meta.get("min_px"),
            "shown": meta.get("shown"), "render_s": meta.get("seconds"), "shift": shift,
            "length": length}, []


def make(script: dict, hook: str = "", excerpt: str = "", tag: str = "") -> dict | None:
    """The day's native Short, or None (reason in `last_skip`). Never raises.
    At most 1 + REPAIRS model calls."""
    global last_skip
    last_skip = ""
    failures: list[str] = []
    try:
        src = source_text(script)
        base = prompt(script, src, hook, excerpt)
        raw = llm.generate_json(base, temperature=0.4, max_tokens=2048)
        for attempt in range(1 + REPAIRS):
            if attempt:
                raw = llm.generate_json(repair_prompt(base, raw, failures), temperature=0.3,
                                        max_tokens=2048)
            spec, failures = validate(raw, src)
            if spec:
                res, failures = build(spec, tag)
                if res:
                    res.update(spec=spec, attempts=attempt + 1, match=match_level(spec, excerpt))
                    m = res["measured"]
                    print(f"  🧩 Native Short: {m['duration']:.1f}s, speech at {m['first_speech']:.2f}s, "
                          f"{m['script_words']} words, timed by {m['source']} (attempt {attempt + 1})")
                    return res
            print(f"  ↻ native short attempt {attempt + 1} failed: {'; '.join(failures)[:240]}")
        last_skip = "; ".join(failures)[:300] or "unknown"
    except Exception as e:  # noqa: BLE001 — the native Short must never cost the day
        last_skip = f"{type(e).__name__}: {str(e)[:120]}"
    print(f"  ↷ native short skipped: {last_skip}")
    return None
