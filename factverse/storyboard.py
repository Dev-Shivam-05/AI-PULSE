"""
v3-G.1: storyboard Shorts (docs/spec/ai-pulse-v3g1.md).

The model storyboards a Short from its exact narration; this module validates the
answer, holds every on-screen word to what is spoken (the grounding gate), times
each element to the word that says it, and renders the result as a native
1080x1920 clip with headless Chromium stepping a deterministic page.

Everything is fail-soft: plan() and render() return None and the caller keeps
today's crop path. Playwright is imported inside render() only — the CI test job
does not install it.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

from factverse import config as fv
from factverse import llm

# ------------------------------------------------------------------ locked values
W, H, FPS = 1080, 1920, 30                   # row 7
CRF, PRESET = "20", "medium"                 # row 7
MIN_BEATS, MAX_BEATS = 3, 8                  # row 3
TEMPLATES = ("statement", "number", "compare", "steps", "chat", "bars", "headline")  # row 4
STATEMENT_WORDS, NUMBER_LABEL_WORDS, COMPARE_WORDS = 6, 7, 5
CHAT_USER_WORDS, CHAT_AI_WORDS, HEADLINE_WORDS = 12, 18, 16
ENTER_S, HIGHLIGHT_S, COUNT_S, BAR_S, STAGGER_S = 0.32, 0.24, 0.70, 0.70, 0.12  # row 9
TYPE_CPS = 32                                # row 9
MAX_GAP_S = 2.5                              # row 6
MATURE_DAYS = 2                              # row 13 (Shorts)
STOP_WORDS = frozenset(
    "about also been being could does done each even from have into just like make made more "
    "most much only over same some such than that them then there these they this those very "
    "what when where which while will with would your".split())
PAGE = fv.ASSETS / "storyboard" / "storyboard.html"


# ------------------------------------------------------------------ helpers
def engine_index(day) -> int:
    """Row 2: even day-of-year -> Short 1 (index 0), odd -> Short 2 (index 1)."""
    return 0 if day.timetuple().tm_yday % 2 == 0 else 1


def engine_of(path) -> str:
    """Row 13: the A/B arm a rendered Short belongs to, from its file name. A
    substring test — never a path split (the Windows/CI separator trap)."""
    return "storyboard" if "_sb_" in str(path) else "crop"


def _norm_word(w: str) -> str:
    return re.sub(r"[^a-z0-9%]", "", str(w).lower())


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(text).lower())


def _numbers(text: str) -> list[str]:
    return [n.replace(",", "") for n in re.findall(r"\d+(?:[.,]\d+)*", str(text))]


def _clean_text(v) -> str:
    s = re.sub(r"[\x00-\x1f\x7f]", " ", str(v if v is not None else ""))
    return re.sub(r"\s+", " ", s).strip()


def _el(v) -> dict | None:
    """A model text element {text, cue} — coerced; a bare string is text with no cue."""
    if isinstance(v, str):
        v = {"text": v, "cue": ""}
    if not isinstance(v, dict):
        return None
    text = _clean_text(v.get("text"))
    return {"text": text, "cue": _clean_text(v.get("cue"))[:60]} if text else None


def _words(n: str) -> int:
    return len(str(n).split())


# ------------------------------------------------------------------ validation (row 4)
def _slots(template: str, slots, source_domain: str) -> list[dict] | None:
    """Template slots -> ordered element list, or None when the shape/limits fail."""
    if not isinstance(slots, dict):
        return None
    if template == "statement":
        line = _el(slots.get("line"))
        if not line or _words(line["text"]) > STATEMENT_WORDS:
            return None
        acc = _clean_text(slots.get("accent"))
        return [dict(line, role="line", accent=acc if acc and acc in line["text"].split() else "")]
    if template == "number":
        val, lab = _el(slots.get("value")), _el(slots.get("label"))
        if not val or not lab or not _numbers(val["text"]) or _words(lab["text"]) > NUMBER_LABEL_WORDS:
            return None
        return [dict(val, role="value"), dict(lab, role="label")]
    if template == "compare":
        sides = []
        for side in ("left", "right"):
            raw = slots.get(side)
            items = [_el(x) for x in (raw if isinstance(raw, list) else [])]
            if not 1 <= len(items) <= 3 or any(i is None or _words(i["text"]) > COMPARE_WORDS for i in items):
                return None
            sides += [dict(items[0], role=f"{side[0]}title")] + [dict(i, role=f"{side[0]}item") for i in items[1:]]
        return sides
    if template == "steps":
        raw = slots.get("steps")
        steps = [_el(x) for x in (raw if isinstance(raw, list) else [])]
        if not 3 <= len(steps) <= 5 or any(s is None for s in steps):
            return None
        return [dict(s, role="step") for s in steps]
    if template == "chat":
        user, ai = _el(slots.get("user")), _el(slots.get("ai"))
        if not user or not ai or _words(user["text"]) > CHAT_USER_WORDS or _words(ai["text"]) > CHAT_AI_WORDS:
            return None
        return [dict(user, role="user"), dict(ai, role="ai")]
    if template == "bars":
        raw = slots.get("bars")
        rows = raw if isinstance(raw, list) else []
        if not 2 <= len(rows) <= 5:
            return None
        out = []
        for r in rows:
            if not isinstance(r, dict):
                return None
            lab, val = _el(r.get("label")), _clean_text(r.get("value"))
            nums = _numbers(val)
            if not lab or not nums:
                return None
            out.append(dict(lab, role="bar", value=val, num=float(nums[0])))
        return out
    if template == "headline":
        line = _el(slots.get("line"))
        if not source_domain or not line or _words(line["text"]) > HEADLINE_WORDS:
            return None
        acc = _clean_text(slots.get("accent"))
        return [{"role": "chip", "text": source_domain, "cue": "", "exempt": True},
                dict(line, role="line", accent=acc if acc and acc in line["text"].split() else "")]
    return None


# ------------------------------------------------------------------ cue matching (row 6)
def _match(words_norm: list[str], cue: str, lo: int, hi: int) -> int | None:
    """Index of the first run of consecutive words equal to `cue`, in [lo, hi)."""
    c = [_norm_word(w) for w in str(cue).split() if _norm_word(w)]
    if not c:
        return None
    for i in range(max(0, lo), max(0, hi - len(c) + 1)):
        if words_norm[i:i + len(c)] == c:
            return i
    return None


# ------------------------------------------------------------------ the gate (row 5)
def gate_ok(elements: list[dict], narration: str) -> bool:
    spoken_nums = set(_numbers(narration))
    spoken_tok = set(_tokens(narration))
    for e in elements:
        if e.get("exempt"):
            continue
        texts = [e["text"]] + ([e["value"]] if e.get("value") else [])
        for t in texts:
            if any(n not in spoken_nums for n in _numbers(t)):
                return False
        content = [w for w in _tokens(e["text"]) if len(w) >= 4 and w not in STOP_WORDS]
        if not any(w in spoken_tok for w in content):
            return False
    return True


def _statement_of(narr_words: list[str]) -> list[dict]:
    return [{"role": "line", "text": " ".join(narr_words[:STATEMENT_WORDS]), "cue": "", "accent": ""}]


# ------------------------------------------------------------------ plan
def build_board(raw, words: list, length: float, source_domain: str = "") -> dict | None:
    """Model answer + the window's (start, end, word) list -> a renderable board."""
    beats_raw = raw.get("beats") if isinstance(raw, dict) else None
    if not isinstance(beats_raw, list) or not words:
        return None
    wn = [_norm_word(w[2]) for w in words]
    starts = [float(w[0]) for w in words]
    beats, cursor, kept = [], 0, 0
    for b in beats_raw[:MAX_BEATS]:
        if not isinstance(b, dict):
            continue
        if not beats:
            idx = 0                                   # beat 1 always starts at 0.0
        else:
            idx = _match(wn, b.get("cue", ""), cursor + 1, len(wn))
            if idx is None:
                continue                              # its time goes to the previous beat
        cursor = idx
        beats.append({"template": str(b.get("template", "")), "slots": b.get("slots"), "w0": idx})
    if len(beats) < MIN_BEATS:
        return None
    out = []
    for k, b in enumerate(beats):
        w1 = beats[k + 1]["w0"] if k + 1 < len(beats) else len(words)
        narr_words = [w[2] for w in words[b["w0"]:w1]]
        narration = " ".join(narr_words)
        start = 0.0 if k == 0 else starts[b["w0"]]
        end = starts[w1] if w1 < len(words) else float(length)
        els = _slots(b["template"], b["slots"], source_domain) if b["template"] in TEMPLATES else None
        template = b["template"]
        if els is not None and gate_ok(els, narration):
            kept += 1
        else:
            template, els = "statement", _statement_of(narr_words)
        out.append({"template": template, "start": round(start, 3), "end": round(end, 3),
                    "narration": narration, "w0": b["w0"], "w1": w1, "els": els})
    print(f"  🎨 Storyboard: {kept}/{len(out)} beats kept")
    board = {"W": W, "H": H, "length": float(length), "beats": out}
    time_elements(board, words)
    return board


def time_elements(board: dict, words: list) -> dict:
    """Reveal times (row 6), bar stagger, highlight replays for the 2.5 s rule."""
    wn = [_norm_word(w[2]) for w in words]
    starts = [float(w[0]) for w in words]
    for k, b in enumerate(board["beats"]):
        prev_t = b["start"]
        seen = set()
        for e in b["els"]:
            e["hl"] = []
            if k == 0:
                e["t"] = -10.0                        # frame 1 is fully drawn (row 6)
                if e.get("accent"):
                    e["hl"].append(-10.0 + ENTER_S)   # ... accent included, already swept
                continue
            i = _match(wn, e.get("cue", ""), b["w0"], b["w1"])
            t = starts[i] if i is not None else prev_t
            t = max(b["start"], t)
            if e.get("role") == "bar":
                while round(t, 3) in seen:           # same resolved time -> 120 ms stagger
                    t += STAGGER_S
                seen.add(round(t, 3))
            e["t"] = round(t, 3)
            prev_t = t
            if e.get("accent"):
                e["hl"].append(round(t + ENTER_S, 3))
        if k > 0 and b["els"]:
            # a beat whose first element is cued later would show an EMPTY stage
            # until then; it starts on that word and the previous beat holds (row 6)
            first = min(e["t"] for e in b["els"])
            if first > b["start"]:
                b["start"] = first
                board["beats"][k - 1]["end"] = first
    _gap_rule(board)
    board["intervals"] = timeline(board)
    return board


def _events(board: dict) -> list[float]:
    ev = []
    for b in board["beats"]:
        ev.append(b["start"])
        for e in b["els"]:
            if e["t"] >= 0:
                ev.append(e["t"])
            ev.extend(e["hl"])
    return sorted(set(round(x, 3) for x in ev if x >= 0))


def _gap_rule(board: dict) -> None:
    """Replay the most recently revealed element's highlight at the midpoint of
    any gap longer than MAX_GAP_S (including the gap to the end)."""
    length = board["length"]
    for _ in range(64):
        ev = _events(board) + [length]
        gap = next(((a, b) for a, b in zip(ev, ev[1:]) if b - a > MAX_GAP_S), None)
        if not gap:
            return
        mid = round((gap[0] + gap[1]) / 2, 3)
        target = None
        for b in board["beats"]:
            if b["start"] <= mid < b["end"] or (b is board["beats"][-1] and mid >= b["start"]):
                shown = [e for e in b["els"] if e["t"] <= mid and not e.get("exempt")]
                target = max(shown, key=lambda e: e["t"]) if shown else None
                break
        if target is None:
            return
        target["hl"].append(mid)
        target["hl"].sort()


def _anim_len(e: dict) -> float:
    role = e.get("role")
    if role == "value":
        return max(ENTER_S, COUNT_S)
    if role == "bar":
        return max(ENTER_S, BAR_S)
    if role in ("user", "ai"):
        return max(ENTER_S, len(e["text"]) / TYPE_CPS)
    return ENTER_S


def timeline(board: dict) -> list[list[float]]:
    """Intervals in which something moves — the only frames the renderer captures."""
    iv = []
    for b in board["beats"]:
        for e in b["els"]:
            if e["t"] >= 0:
                iv.append([e["t"], e["t"] + _anim_len(e)])
            iv.extend([h, h + HIGHLIGHT_S] for h in e["hl"])
    return [[round(max(0.0, a), 3), round(min(b, board["length"]), 3)] for a, b in sorted(iv)
            if a < board["length"] and b > 0]


def frame_times(board: dict) -> list[float]:
    ts = {0.0}
    for b in board["beats"]:
        if b["start"] < board["length"]:
            ts.add(round(b["start"], 3))
    step = 1.0 / FPS
    for a, b in board.get("intervals") or timeline(board):
        t = a
        while t < b:
            ts.add(round(t, 3))
            t += step
        ts.add(round(b, 3))
    return sorted(t for t in ts if 0 <= t < board["length"])


def concat_list(frames: list[tuple[str, float]], length: float) -> str:
    """ffmpeg concat-demuxer script: each frame holds until the next; the last one
    holds to the end (and is listed twice, the demuxer's own rule)."""
    lines = ["ffconcat version 1.0"]
    for i, (path, t) in enumerate(frames):
        nxt = frames[i + 1][1] if i + 1 < len(frames) else length
        p = str(path).replace("\\", "/").replace("'", "'\\''")
        lines += [f"file '{p}'", f"duration {max(0.001, nxt - t):.3f}"]
    if frames:
        lines.append(f"file '{str(frames[-1][0]).replace(chr(92), '/')}'")
    return "\n".join(lines) + "\n"


def encode_args(list_path: str, out_mp4: str) -> list[str]:
    return [fv.FFMPEG or "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
            "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", PRESET,
            "-crf", CRF, "-an", out_mp4]


# ------------------------------------------------------------------ the model call
def _prompt(narration: str, length: float, source_domain: str) -> str:
    head = ('- headline {"line": {"text","cue"}, "accent": "one word of line"?} (line <= 16 words; '
            f"shown next to the source chip {source_domain} WITHOUT quotation marks)\n"
            if source_domain else "")
    return f"""You are storyboarding a {length:.0f}-second vertical explainer Short.
Draw the narration's own example; never decorate; never add a fact. Every word on screen must be
copied from the narration below, and every number exactly as written there. Choose 3-8 beats.
Each beat starts where its "cue" (1-3 words copied from the narration) is spoken; every element
{{"text","cue"}} appears when its own cue is spoken. Beat 1 starts at the first word.
TEMPLATES (slots):
- statement {{"line": {{"text","cue"}}, "accent": "one word of line"?}} (line <= 6 words)
- number {{"value": {{"text","cue"}}, "label": {{"text","cue"}}}} (value is a number as spoken; label <= 7 words)
- compare {{"left": [el, ...], "right": [el, ...]}} (1-3 elements per side, each <= 5 words; element 1 is the column title)
- steps {{"steps": [el, ...]}} (3-5 elements, in the order spoken)
- chat {{"user": el, "ai": el}} (user <= 12 words, ai <= 18 words: someone asks, an AI answers)
- bars {{"bars": [{{"label": el, "value": "71%"}}, ...]}} (2-5 bars; every value spoken in the narration)
{head}Return ONLY JSON {{"beats":[{{"cue":"...","template":"...","slots":{{...}}}}]}}

NARRATION: {narration}"""


def plan(words: list, length: float, source_domain: str = "") -> dict | None:
    """One Gemini call (row 3) -> validated, gated, timed board, or None."""
    try:
        if not words:
            return None
        narration = " ".join(str(w[2]) for w in words)
        raw = llm.generate_json(_prompt(narration, length, source_domain), temperature=0.4,
                                max_tokens=4096)
        return build_board(raw, words, length, source_domain)
    except Exception as e:  # noqa: BLE001 — a storyboard must never cost the Short
        print(f"  ↻ storyboard plan failed: {type(e).__name__}")
        return None


# ------------------------------------------------------------------ render (row 11)
def demote(board: dict, beat_idx: list[int], words: list) -> dict:
    """Beats whose text did not fit at 44 px become statements (row 10)."""
    for k in beat_idx:
        if 0 <= k < len(board["beats"]):
            b = board["beats"][k]
            b["template"], b["els"] = "statement", _statement_of(b["narration"].split())
    return time_elements(board, words)


def render(board: dict, out_mp4: str, words: list) -> str | None:
    t0 = time.monotonic()
    fdir = fv.TEMP / "sb_frames"
    try:
        from playwright.sync_api import sync_playwright
        shutil.rmtree(fdir, ignore_errors=True)
        fdir.mkdir(parents=True, exist_ok=True)
        frames = []
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
                page.goto(PAGE.resolve().as_uri())
                page.wait_for_function("window.__ready === true", timeout=15000)
                unfit = page.evaluate("b => window.__load(b)", board)
                if unfit:
                    board = demote(board, list(unfit), words)
                    page.evaluate("b => window.__load(b)", board)
                for i, t in enumerate(frame_times(board)):
                    page.evaluate("t => window.__seek(t)", t)
                    path = fdir / f"{i:05d}.png"
                    page.screenshot(path=str(path))
                    frames.append((str(path), t))
            finally:
                browser.close()
        lst = fdir / "list.txt"
        lst.write_text(concat_list(frames, board["length"]), encoding="utf-8")
        r = subprocess.run(encode_args(str(lst), str(out_mp4)), capture_output=True, text=True,
                           timeout=600)
        if r.returncode != 0 or not Path(out_mp4).exists() or Path(out_mp4).stat().st_size < 10000:
            print(f"  ↻ storyboard encode failed: {(r.stderr or '')[-200:]}")
            return None
        print(f"  🎨 Storyboard short rendered in {time.monotonic() - t0:.1f}s ({len(frames)} frames)")
        return str(out_mp4)
    except Exception as e:  # noqa: BLE001
        print(f"  ↻ storyboard render failed: {type(e).__name__}: {str(e)[:120]}")
        return None
