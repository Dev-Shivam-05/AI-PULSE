"""v3-P.2 long-form opening contract (review row 5) and the context-first arm (row 6).

spec docs/spec/ai-pulse-v3p2.md. A Pilot A video has a FIXED scene architecture
(round 3 §3, per evidence source), so the renderer and the gate know where each
rule lives:

  proof-first     scene 1 = the result        (frame 0, >= 40% of the frame for 2 s)
                  scene 2 = who it is for + a prerequisite/limitation (by 0:15)
  context-first   scene 1 = task + suitability (0:00-0:15, a complete card at frame 0)
                  scene 2 = the result        (first displayed at 0:15-0:16)
  both            scene 3 = the first safe step (by 0:25, readable >= 5 s, >= 48 px)
                  scene 4 = the input -> action -> output sequence (labelled)
                  ...     = details, what the evidence does not establish, decision

`place_opening` renders those scenes to their EXACT slot shares after the
narration timings exist (the C.3 law) — one clip per scene, because step5_build
splits a scene's time equally between its clips. `measure` checks the ENCODED
file: frames sampled from the mp4 against the rendered references, and audio
word timings (whisper on the encoded audio when it is installed, else the
narration's own timings, which the mux places at 0 when no sting is added).
Every seam fails soft; nothing here raises into run().
"""
from __future__ import annotations

import difflib
import json
import re
import shutil
import subprocess
from pathlib import Path

from factverse import config as fv

ARMS = ("proof", "context")

# ------------------------------------------------------------- locked (round 3 §2)
RESULT_AREA_MIN = 0.40          # of the frame, during the first 2 s
RESULT_AREA_SECONDS = 2.0
FIRST_SPEECH_BY = 0.50
FIRST_SENTENCE_WORDS = 16
FIRST_SENTENCE_BY = 6.50
LIMITATION_BY = 15.0
STEP_BY = 25.0
STEP_MIN_SECONDS = 5.0
LABEL_MIN_PX = 32
TEXT_MIN_PX = 48
DURATION_MIN, DURATION_MAX = 150.0, 210.0
PAIR_MAX_DIFF = 0.15
CONTEXT_RESULT_FROM, CONTEXT_RESULT_TO = 15.0, 16.0

# ------------------------------------------------------------- delegated (spec)
WPS = 2.5                       # narration words per second the budgets assume (150 wpm)
PILOT_MIN_WORDS, PILOT_MAX_WORDS = 400, 500     # 160-200 s at WPS: inside 150-210 with margin
WRITER_FIRST_SENTENCE = 13      # asked of the writer: ends ~5.4 s, under the 6.5 s rule
PROOF_OPEN_WORDS = 36           # scenes 1+2 (proof): the limitation lands by ~14.4 s
CONTEXT_S1_WORDS = (28, 42)     # context scene 1 fills ~11-17 s of task context
CONTEXT_OPEN_WORDS = 56         # context scenes 1+2: the step scene starts by ~22 s
STEP_HOLD = 5.5                 # step card on screen; +0.5 covers the incoming dissolve
CONTEXT_RESULT_AT = 15.0        # where the renderer puts the result if scene 1 misses the window
SCALE_MAX = 4.0                 # most the result region is enlarged
AR_MIN, AR_MAX = 0.75, 4.0      # region aspect clamp: guarantees >= 40% coverage when it fits
DIFF_T = 24                     # per-pixel change (0-255) that marks the result region
BLOCK_DENSITY = 0.25            # share of a 12x12 block that must change to count as result
BASELINE_MIN_AREA = 0.04        # a change region smaller than this is a detail, not the result
MATCH_MAX = 14.0                # mean abs diff (0-255) for "this frame shows that reference"
BLANK_STD_MIN = 8.0
CAPTION_BAND = 0.78             # frames are compared above this height (burned captions below)
SCAN_SECONDS, SCAN_FPS = 32.0, 8
SLOT_PAD = 0.5
FPS = 30
BG = (13, 17, 23)
LIMIT_RX = re.compile(
    r"\b(?:requires?|required|needs?|prerequisites?|only\s+(?:works|runs|supports|for|on)|"
    r"does\s*n[o']t|doesn't|can't|cannot|won't|is\s*n[o']t\s+for|not\s+for|without|limit(?:s|ed|ation)?|"
    r"must\s+have|you(?:'ll)?\s+need|gpu|vram|cuda|api\s+key|account|sign\s+in|log\s+in)\b", re.I)
_NOT_TESTED = re.compile(r"not\s+independently\s+tested", re.I)

RESULT_SCENE = {"proof": 0, "context": 1}
LIMIT_SCENES = {"proof": (0, 1), "context": (0,)}
STEP_SCENE, SEQ_SCENE = 2, 3


# ============================================================ writer contract
def writer_block(arm: str, ev: dict, intent: str = "") -> str:
    """The STRUCTURE the pilot writer follows (replaces the tool lane's own)."""
    hosted = (ev or {}).get("source") == "hosted"
    if hosted:
        result = (f'In our hosted-demo run, … — state what THIS input produced (the observed result), '
                  f'at most {WRITER_FIRST_SENTENCE} words, starting "In our hosted-demo run".')
        step = ("the first action to reproduce it: open the hosted demo and select this example "
                "(never an install command for a hosted demo)")
        seq = "walk through input -> action -> output; say any waiting was sped up"
        rest = ("what this run does NOT establish (local setup, offline use, reliability, your "
                "hardware) — mark it \"filter\": true")
    else:
        result = (f'begin with the words "The author\'s demo shows" and state what it shows, at most '
                  f'{WRITER_FIRST_SENTENCE} words.')
        step = "the documented starting step from the README (its own command, verbatim)"
        seq = "replay the demo with TWO concrete observations about what it shows"
        rest = ("prerequisites, omitted conditions and one documented or reported limitation — "
                "mark it \"filter\": true")
    lim = ("one relevant prerequisite or limitation (use words like requires / needs / only / "
           "does not)")
    if arm == "context":
        opening = (f"- Scene 1 (TASK + SUITABILITY, {CONTEXT_S1_WORDS[0]}-{CONTEXT_S1_WORDS[1]} words): "
                   f"the first sentence states the TASK the viewer wants done, at most "
                   f"{WRITER_FIRST_SENTENCE} words; then who it suits and {lim}. Do NOT reveal the "
                   f"result yet.\n"
                   f"- Scene 2 (RESULT, at most 14 words): {result}\n"
                   f"- Scenes 1+2 together: at most {CONTEXT_OPEN_WORDS} words.\n")
    else:
        opening = (f"- Scene 1 (RESULT, at most 20 words): {result}\n"
                   f"- Scene 2 (FIT, at most 16 words): who it is for and {lim}"
                   + ("; say it is not independently tested" if not hosted else "") + ".\n"
                   f"- Scenes 1+2 together: at most {PROOF_OPEN_WORDS} words.\n")
    return (f"STRUCTURE (Pilot A, {arm}-first opening — exact scene order, overrides every other "
            f"structure rule):\n{opening}"
            f"- Scene 3 (FIRST STEP, 15-30 words): {step}.\n"
            f"- Scene 4 (SEQUENCE, 40-70 words): {seq}.\n"
            f"- Scenes 5-6 (DETAIL, 50-80 words each): useful details; one of them is {rest}.\n"
            f"- Final scene (DECISION, 30-50 words): the practical decision, \"the exact command is "
            f"in the description\", one genuinely relevant question. No subscribe line.\n"
            f"- 7-9 scenes, {PILOT_MIN_WORDS}-{PILOT_MAX_WORDS} words in total. No padding, no "
            f"greetings, no channel intro.\n"
            f"- Add a top-level field \"task\": the task the tool does, 2-5 words (e.g. \"Rotate "
            f"Images\"), no numbers.\n")


def scene_count_rule() -> tuple[str, str]:
    return "7-9", "15-80"


# ============================================================ text analysis
def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if s.strip()]


def first_sentence(script) -> str:
    sc = (script or {}).get("scenes") or []
    ss = sentences(sc[0].get("narration", "")) if sc else []
    return ss[0] if ss else ""


def _words(text) -> list[str]:
    return str(text or "").split()


def limitation(script, arm: str):
    """(scene index, sentence index, sentence) of the first prerequisite/limitation
    in the scenes where the arm must state it, else None. "Not independently
    tested" is the evidence's status, not the tool's limitation."""
    sc = (script or {}).get("scenes") or []
    for i in LIMIT_SCENES.get(arm, (0, 1)):
        if i >= len(sc):
            continue
        for j, s in enumerate(sentences(sc[i].get("narration", ""))):
            if LIMIT_RX.search(_NOT_TESTED.sub("", s)):
                return i, j, s
    return None


def lint(script, arm: str) -> list[str]:
    """Pre-render check of the writer contract (cheap; the encoded file is what the
    gate judges). Codes, not prose."""
    issues = []
    sc = (script or {}).get("scenes") or []
    if not 6 <= len(sc) <= 10:
        issues.append("scene_count")
        return issues
    first = first_sentence(script)
    if len(_words(first)) > FIRST_SENTENCE_WORDS:
        issues.append("first_sentence_long")
    ev = (script or {}).get("evidence") or {}
    low = first.lower().replace("’", "'")
    if arm == "proof":
        if ev.get("source") == "author" and not low.startswith("the author's demo shows"):
            issues.append("first_sentence_content")
        if ev.get("source") == "hosted" and "hosted" not in low:
            issues.append("first_sentence_content")
        if len(_words(sc[0]["narration"])) + len(_words(sc[1]["narration"])) > PROOF_OPEN_WORDS + 6:
            issues.append("opening_long")
    else:
        n1 = len(_words(sc[0]["narration"]))
        if not CONTEXT_S1_WORDS[0] <= n1 <= CONTEXT_S1_WORDS[1] + 6:
            issues.append("context_length")
        if n1 + len(_words(sc[1]["narration"])) > CONTEXT_OPEN_WORDS + 6:
            issues.append("opening_long")
    if limitation(script, arm) is None:
        issues.append("limitation_missing")
    total = sum(len(_words(s.get("narration", ""))) for s in sc)
    if not PILOT_MIN_WORDS - 30 <= total <= PILOT_MAX_WORDS + 30:
        issues.append("length")
    return issues


def fix_prompt(script: dict, issues: list[str], arm: str) -> str:
    """One repair instruction for the writer (the pre-render lint or the gate)."""
    want = {
        "first_sentence_long": f"scene 1's FIRST sentence must be at most {WRITER_FIRST_SENTENCE} words",
        "first_sentence_end": f"scene 1's FIRST sentence must be at most {WRITER_FIRST_SENTENCE - 2} words",
        "first_sentence_content": ("scene 1 must begin \"The author's demo shows\""
                                   if ((script.get("evidence") or {}).get("source") == "author")
                                   else "scene 1's first sentence must start \"In our hosted-demo run\""),
        "opening_long": "cut scenes 1 and 2 to "
                        + (f"{PROOF_OPEN_WORDS}" if arm == "proof" else f"{CONTEXT_OPEN_WORDS}")
                        + " words together",
        "context_length": f"scene 1 must be {CONTEXT_S1_WORDS[0]}-{CONTEXT_S1_WORDS[1]} words",
        "limitation_missing": "state one prerequisite or limitation (requires / needs / only / does not) "
                              + ("in scene 1" if arm == "context" else "in scene 2"),
        "limitation_late": "move the prerequisite or limitation earlier and shorten scenes 1-2",
        "step_late": "shorten scenes 1 and 2 so the first step (scene 3) starts sooner",
        "length": f"bring the total to {PILOT_MIN_WORDS}-{PILOT_MAX_WORDS} words by editing scenes 5+",
        "duration": f"bring the total to {PILOT_MIN_WORDS}-{PILOT_MAX_WORDS} words by editing scenes 5+",
        "pair_duration": "adjust scenes 5+ so the length matches its pair partner",
    }
    asks = [want[i] for i in issues if i in want] or ["tighten scenes 1-3"]
    keys = ("title", "titles", "thumb_text", "description", "tags", "task", "scenes")
    return ("Repair this video script JSON. Keep the same scene ORDER and roles, every fact, every "
            "command and every quote; change only what these rules require:\n- "
            + "\n- ".join(asks)
            + "\nNever add a claim. Return ONLY the full JSON (same schema).\n\nSCRIPT:\n"
            + json.dumps({k: script[k] for k in keys if k in script}, ensure_ascii=False))


# ============================================================ visuals (PIL + ffmpeg)
def _font(path: str, size: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(str(fv.FONTS / path), size)
    except Exception:
        from factverse import branding as br
        return br._font(size)


def _wrap(text: str, font, width: int, draw) -> list[str]:
    """Greedy word wrap MEASURED with the font that is drawn; a word longer than
    the width is split by characters (commands have long tokens)."""
    lines, cur = [], ""
    for word in str(text).split(" "):
        cand = (cur + " " + word).strip() if cur else word
        if draw.textlength(cand, font=font) <= width:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        cur = ""
        while draw.textlength(word, font=font) > width:
            lo, hi = 1, len(word)                 # longest prefix that fits (binary search)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if draw.textlength(word[:mid], font=font) <= width:
                    lo = mid
                else:
                    hi = mid - 1
            k = lo
            lines.append(word[:k])
            word = word[k:]
        cur = word
    if cur:
        lines.append(cur)
    return lines


def _fit_wrapped(text: str, face: str, start: int, width: int, max_lines: int, draw):
    """Largest size >= TEXT_MIN_PX at which `text` wraps into max_lines; at the
    floor it may need more lines (the caller sheds visibly, never silently)."""
    size = start
    while True:
        f = _font(face, size)
        lines = _wrap(text, f, width, draw)
        if len(lines) <= max_lines or size <= TEXT_MIN_PX:
            return size, f, lines
        size = max(TEXT_MIN_PX, size - 4)


def _canvas():
    from PIL import Image
    return Image.new("RGB", (fv.VIDEO_W, fv.VIDEO_H), BG)


def _paste_label(img, label_png: str) -> tuple[int, int, int, int] | None:
    from PIL import Image
    if not label_png or not Path(label_png).exists():
        return None
    lab = Image.open(label_png).convert("RGBA")
    img.paste(lab, (48, 40), lab)
    return (48, 40, 48 + lab.width, 40 + lab.height)


def region_plan(first, result, W: int | None = None, H: int | None = None) -> dict | None:
    """PURE (PIL images in, numbers out): the result region and how it is enlarged.
    Region = where the result frame differs from the clip's first frame (the
    input/output that changed), padded; its aspect is clamped to [AR_MIN, AR_MAX]
    around the change's centroid, then scaled (<= SCALE_MAX) to fit the frame.
    Returns crop box (source px), placement box (frame px) and the coverage."""
    import numpy as np
    W, H = W or fv.VIDEO_W, H or fv.VIDEO_H
    sw, sh = result.size
    a = np.asarray(first.convert("L").resize((192, 108)), dtype=np.int16)
    b = np.asarray(result.convert("L").resize((192, 108)), dtype=np.int16)
    raw = np.abs(a - b) > DIFF_T
    # Keep only DENSE change: 12x12-cell blocks (16x9 of them) where >= BLOCK_DENSITY
    # of the pixels changed. A swapped image or a new output is dense; a button
    # hover, a focus ring or an example's selection border is sparse — measured on
    # gradio/image_mod, those thin edits stretched the region over the whole page.
    blocks = raw.reshape(9, 12, 16, 12).mean(axis=(1, 3)) >= BLOCK_DENSITY
    mask = np.kron(blocks, np.ones((12, 12), dtype=bool)) & raw
    if mask.sum() < 4:                            # nothing changed: the content area itself
        bg = np.asarray(result.convert("RGB").resize((192, 108)), dtype=np.int16)
        mask = np.abs(bg - np.array(BG)).sum(axis=2) > 30
        if mask.sum() < 4:
            return None
    ys, xs = np.nonzero(mask)
    kx, ky = sw / 192.0, sh / 108.0
    x0, x1 = xs.min() * kx, (xs.max() + 1) * kx
    y0, y1 = ys.min() * ky, (ys.max() + 1) * ky
    cx, cy = xs.mean() * kx, ys.mean() * ky
    pad = 0.03 * max(sw, sh)
    x0, y0, x1, y1 = max(0, x0 - pad), max(0, y0 - pad), min(sw, x1 + pad), min(sh, y1 + pad)
    w, h = x1 - x0, y1 - y0
    if w / h < AR_MIN:                           # too tall: keep the rows around the change
        h = w / AR_MIN
        y0 = min(max(0.0, cy - h / 2), sh - h)
        y1 = y0 + h
    elif w / h > AR_MAX:                         # too wide: keep the columns around it
        w = h * AR_MAX
        x0 = min(max(0.0, cx - w / 2), sw - w)
        x1 = x0 + w
    scale = min(W / w, H / h, SCALE_MAX)
    pw, ph = w * scale, h * scale
    px, py = (W - pw) / 2, (H - ph) / 2
    return {"crop": [round(x0), round(y0), round(x1), round(y1)],
            "place": [round(px), round(py), round(px + pw), round(py + ph)],
            "scale": round(scale, 3), "coverage": round(pw * ph / (W * H), 4)}


def _ffmpeg(args: list[str], timeout: int = 600) -> bool:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).returncode == 0
    except Exception as e:  # noqa: BLE001
        print(f"     ⚠️ ffmpeg step failed: {e}")
        return False


def _probe(path: str) -> float:
    try:
        r = subprocess.run([fv.FFPROBE or "ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=60)
        return float((r.stdout or "0").strip() or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _grab(video: str, t: float, out_png: str) -> str | None:
    ok = _ffmpeg([fv.FFMPEG or "ffmpeg", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", str(video),
                  "-frames:v", "1", str(out_png)], timeout=120)
    return out_png if ok and Path(out_png).exists() else None


def pick_result_frame(clip: str, out_dir: Path) -> tuple[str, str] | None:
    """(first frame, result frame) PNGs of the evidence master clip. The result
    frame is the one in the last quarter that differs MOST from the first frame
    (a GIF that loops back to its start ends on the start, not the result)."""
    import numpy as np
    from PIL import Image
    d = _probe(clip)
    if d <= 0:
        return None
    first = _grab(clip, 0.0, str(out_dir / "first.png"))
    if not first:
        return None
    fa = np.asarray(Image.open(first).convert("L").resize((192, 108)), dtype=np.int16)
    best, best_score = None, -1.0
    for k in range(6):
        t = d * 0.75 + (d * 0.25 - 0.1) * k / 5
        p = _grab(clip, t, str(out_dir / f"cand_{k}.png"))
        if not p:
            continue
        sc = float(np.abs(np.asarray(Image.open(p).convert("L").resize((192, 108)),
                                     dtype=np.int16) - fa).mean())
        if sc >= best_score:            # ties go to the later frame (the settled result)
            best, best_score = p, sc
    if not best:
        return None
    shutil.copy(best, out_dir / "result.png")
    res = Image.open(best).convert("RGB")
    # The baseline is the EARLIEST SETTLED frame: a hosted clip opens 1 s before the
    # example click, while the page may still be laying out (measured on
    # gradio/image_mod: frame 0 had the buttons 380 px higher, so "what changed"
    # was the whole page). Of frame 0 and the frame at 1.0 s, the one whose dense
    # change region is SMALLER (but >= BASELINE_MIN_AREA of the frame) wins.
    choices = [first]
    if d > 3.0:
        one = _grab(clip, 1.0, str(out_dir / "first_1s.png"))
        if one:
            choices.append(one)
    best_base, best_area = first, None
    for c in choices:
        plan = region_plan(Image.open(c).convert("RGB"), res)
        if not plan:
            continue
        x0, y0, x1, y1 = plan["crop"]
        area = (x1 - x0) * (y1 - y0) / float(res.width * res.height)
        if area >= BASELINE_MIN_AREA and (best_area is None or area < best_area):
            best_base, best_area = c, area
    return best_base, str(out_dir / "result.png")


def render_result_still(first_png: str, result_png: str, label_png: str, out_png: str) -> dict | None:
    """The result region, cropped and enlarged onto the canvas, label top-left."""
    from PIL import Image
    first, res = Image.open(first_png).convert("RGB"), Image.open(result_png).convert("RGB")
    plan = region_plan(first, res)
    if not plan:
        return None
    crop = res.crop(tuple(plan["crop"]))
    x0, y0, x1, y1 = plan["place"]
    img = _canvas()
    img.paste(crop.resize((x1 - x0, y1 - y0), Image.LANCZOS), (x0, y0))
    plan["label_box"] = _paste_label(img, label_png)
    img.save(out_png)
    return plan


def render_context_card(task_text: str, tool_line: str, label_png: str, out_png: str) -> dict | None:
    """Context-first frame 0: complete and informative — the task, the tool, the
    source label. Every text measured; nothing below the caption band."""
    from PIL import ImageDraw
    img = _canvas()
    d = ImageDraw.Draw(img)
    width = int(fv.VIDEO_W * 0.86)
    size, f, lines = _fit_wrapped(task_text, "Inter-Black.ttf", 84, width, 3, d)
    lines = lines[:3]
    y = int(fv.VIDEO_H * 0.24)
    for ln in lines:
        d.text((int(fv.VIDEO_W * 0.07), y), ln, font=f, fill=(244, 247, 255))
        y += int(size * 1.22)
    tsize, tf, tl = _fit_wrapped(tool_line, "Inter-Black.ttf", 56, width, 1, d)
    d.text((int(fv.VIDEO_W * 0.07), y + 24), tl[0], font=tf, fill=(34, 211, 238))
    box = _paste_label(img, label_png)
    if y + 24 + tsize > fv.VIDEO_H * CAPTION_BAND:
        return None
    img.save(out_png)
    return {"text_px": min(size, tsize), "label_box": box}


def step_lines(script: dict) -> tuple[list[str], str] | None:
    """(plain instruction lines, command) for the step card. A hosted test's
    step is the demo action — never an install command (round 3 §2)."""
    ev = script.get("evidence") or {}
    if ev.get("source") == "hosted":
        host = re.sub(r"^https?://", "", str(ev.get("url") or "")).rstrip("/")
        pick = str(ev.get("input") or "its first example").replace("the Space's ", "")
        return ["1. Open the hosted demo:", "2. Pick " + pick, "3. Run it and compare the output"], host
    dl = script.get("deliverable") or {}
    cmd = str(dl.get("text") or "").strip()
    if not cmd:
        return None
    return ["Run the documented command:"], cmd


def render_step_card(script: dict, out_png: str) -> dict | None:
    """The first safe step, every glyph >= 48 px. A command that cannot fit at
    48 px in 5 lines is shed by whole lines with a visible pointer to the
    description — never cut silently."""
    from PIL import ImageDraw
    sl = step_lines(script)
    if not sl:
        return None
    lines, cmd = sl
    img = _canvas()
    d = ImageDraw.Draw(img)
    x, width = int(fv.VIDEO_W * 0.07), int(fv.VIDEO_W * 0.86)
    hf = _font("Inter-Black.ttf", 52)
    d.text((x, 60), "STARTING STEP", font=hf, fill=(255, 214, 10))
    y, sizes = 170, [52]
    hosted = (script.get("evidence") or {}).get("source") == "hosted"
    body = [lines[0]] if not hosted else lines[:1]
    for ln in body:
        s, f, wl = _fit_wrapped(ln, "Inter-Black.ttf", 56, width, 2, d)
        for w in wl:
            d.text((x, y), w, font=f, fill=(230, 237, 243))
            y += int(s * 1.25)
        sizes.append(s)
    cs, cf, cl = _fit_wrapped(cmd.replace("\n", " "), "JetBrainsMono-Regular.ttf", 64, width - 40, 4, d)
    shed = False
    if len(cl) > 4:
        cl, shed = cl[:3] + ["… full command in the description"], True
    box_top = y + 10
    box_bot = box_top + len(cl) * int(cs * 1.35) + 30
    d.rounded_rectangle([x - 10, box_top, x + width, box_bot], radius=16, fill=(22, 27, 34),
                        outline=(48, 54, 61), width=3)
    y = box_top + 18
    for k, w in enumerate(cl):
        d.text((x + 20, y), w, font=cf, fill=(126, 231, 135) if not (shed and k == len(cl) - 1)
               else (139, 148, 158))
        y += int(cs * 1.35)
    sizes.append(cs)
    y = box_bot + 26
    for ln in (lines[1:] if hosted else ["From the README — not run by " + fv.CHANNEL_NAME]):
        s, f, wl = _fit_wrapped(ln, "Inter-Black.ttf", 52, width, 2, d)
        for w in wl:
            d.text((x, y), w, font=f, fill=(230, 237, 243))
            y += int(s * 1.25)
        sizes.append(s)
    if y > fv.VIDEO_H * CAPTION_BAND:
        print(f"     ⚠️ step card overflows into the caption band ({y}px)")
        return None
    img.save(out_png)
    return {"text_px": min(sizes), "shed": shed}


# ============================================================ timeline (PURE)
def timeline(arm: str, durs: list) -> dict | None:
    """Which pieces each owned scene is rendered from, in seconds, plus the times
    the gate expects. pieces: [(kind, seconds)], kind in result/context/step/sequence."""
    try:
        d = [float(x) for x in durs]
    except (TypeError, ValueError):
        return None
    if arm not in ARMS or len(d) < 5 or min(d[:4]) <= 0:
        return None
    b = [0.0]
    for x in d:
        b.append(b[-1] + x)
    scenes: dict[int, list] = {}
    if arm == "proof":
        scenes[0] = [("result", d[0])]
        result_at = 0.0
    else:
        b1 = b[1]
        R = b1 if CONTEXT_RESULT_FROM <= b1 < CONTEXT_RESULT_TO else CONTEXT_RESULT_AT
        if R >= b[2] - 1.0:
            return None                            # scene 2 too short to show the result
        if R < b1:
            scenes[0] = [("context", R), ("result", b1 - R)]
            scenes[1] = [("result", d[1])]
        else:
            scenes[0] = [("context", d[0])]
            scenes[1] = ([("context", R - b1)] if R > b1 else []) + [("result", d[1] - (R - b1))]
        result_at = R
    step_at = b[STEP_SCENE]
    spill = max(0.0, STEP_HOLD - d[STEP_SCENE])
    scenes[STEP_SCENE] = [("step", d[STEP_SCENE])]
    if spill and d[SEQ_SCENE] - spill >= 1.0:
        scenes[SEQ_SCENE] = [("step", spill), ("sequence", d[SEQ_SCENE] - spill)]
    elif spill:
        scenes[SEQ_SCENE] = [("step", d[SEQ_SCENE])]
    else:
        scenes[SEQ_SCENE] = [("sequence", d[SEQ_SCENE])]
    step_len = d[STEP_SCENE] + min(spill, d[SEQ_SCENE]) if spill else d[STEP_SCENE]
    return {"arm": arm, "scenes": scenes, "bounds": b, "result_at": round(result_at, 3),
            "step_at": round(step_at, 3), "step_seconds": round(step_len, 3)}


# Every opening clip is TAGGED as what swscale actually produced from RGB (BT.601 =
# bt470bg, limited range) — the tags the screen recording's pieces carry. Measured
# 2026-11-04: an untagged still and a bt470bg recording piece concatenated in one
# scene made ffmpeg reconfigure its filter graph mid-join, drop 270 frames (9 s),
# and the dissolve join fell back to hard cuts.
_TAGS = ["-colorspace", "bt470bg", "-color_range", "tv"]


def _still_args(png: str, seconds: float, out: str) -> list[str]:
    return [fv.FFMPEG or "ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(png),
            "-t", f"{seconds:.3f}", "-vf", f"scale={fv.VIDEO_W}:{fv.VIDEO_H},setsar=1,format=yuv420p",
            "-r", str(FPS), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            *_TAGS, str(out)]


def _concat_args(parts: list[str], out: str) -> list[str]:
    args = [fv.FFMPEG or "ffmpeg", "-y"]
    for p in parts:
        args += ["-i", str(p)]
    graph = "".join(f"[{i}:v]setpts=PTS-STARTPTS,fps={FPS},format=yuv420p,"
                    f"setparams=range=tv:colorspace=bt470bg[v{i}];" for i in range(len(parts)))
    graph += "".join(f"[v{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=0[v]"
    return args + ["-filter_complex", graph, "-map", "[v]", "-an", "-c:v", "libx264",
                   "-preset", "veryfast", "-crf", "18", *_TAGS, str(out)]


def _sequence_piece(ev: dict, seconds: float, label_png: str, out: str) -> str | None:
    from factverse import evidence
    plan = evidence.slot_plan(ev.get("clip_seconds"), seconds)
    if not plan:
        return None
    plan = dict(plan, out=round(seconds, 3))
    ok = _ffmpeg(evidence.slot_args(ev["clip"], label_png, out, plan))
    return out if ok and Path(out).exists() else None


def place_opening(script: dict, scene_clips: list, durs: list, arm: str) -> dict | None:
    """Render the owned scenes (result / context / step / sequence) to their
    exact shares and REPLACE those scenes' clips. Returns the renderer metadata
    the gate checks, or None (scene_clips untouched) on any failure."""
    try:
        from factverse import evidence, querymap
        ev = script.get("evidence")
        if not evidence.admissible(ev) or not scene_clips or len(scene_clips) < 5:
            return None
        tl = timeline(arm, durs)
        if not tl:
            print("  ⚠️ opening: scene timings cannot carry the opening contract")
            return None
        out = fv.TEMP / "opening"
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True, exist_ok=True)
        label_png = evidence.render_label_png(evidence.label_text(ev), str(out / "label.png"))
        if not label_png:
            return None
        fr = pick_result_frame(ev["clip"], out)
        if not fr:
            return None
        refs = {"result": str(out / "ref_result.png"), "step": str(out / "ref_step.png")}
        rp = render_result_still(fr[0], fr[1], label_png, refs["result"])
        sp = render_step_card(script, refs["step"])
        if not rp or not sp:
            return None
        meta = {"arm": arm, "coverage": rp["coverage"], "region": rp, "label_px": evidence.LABEL_PX,
                "label_box": rp.get("label_box"), "step_px": sp["text_px"], "text_px": [sp["text_px"]],
                "refs": refs, "timeline": tl, "branding": "skipped", "cold_open": "skipped"}
        meta["label_px"] = _label_px(evidence.label_text(ev))
        if arm == "context":
            name, alias = querymap.name_alias(script)
            cp = render_context_card(first_sentence(script), f"{name or 'This tool'} · "
                                     f"{alias or ev.get('label', '')}", label_png,
                                     str(out / "ref_context.png"))
            if not cp:
                return None
            refs["context"] = str(out / "ref_context.png")
            meta["text_px"].append(cp["text_px"])
        made = {}
        for idx, pieces in tl["scenes"].items():
            parts = []
            for k, (kind, secs) in enumerate(pieces):
                last = k == len(pieces) - 1
                secs = secs + (SLOT_PAD if last else 0.0)
                pth = str(out / f"s{idx}_{k}_{kind}.mp4")
                if kind == "sequence":
                    p = _sequence_piece(ev, secs, label_png, pth)
                else:
                    p = pth if _ffmpeg(_still_args(refs[kind], secs, pth)) else None
                if not p:
                    print(f"  ⚠️ opening piece {idx}/{kind} failed")
                    return None
                parts.append(p)
            clip = str(out / f"scene_{idx}.mp4")
            # always through the concat encode, even for one part: it sets the tags
            if not _ffmpeg(_concat_args(parts, clip)):
                return None
            made[idx] = clip
        for idx, clip in made.items():
            scene_clips[idx][:] = [clip]
        # the final scene repeats the step card (the command at >= 48 px, round 3 §2)
        fin = str(out / "final_step.mp4")
        if _ffmpeg(_still_args(refs["step"], 6.0, fin)):
            last = scene_clips[-1]
            if last and "statcard" in str(last[0]):
                last[0] = fin
            else:
                last.insert(0, fin)
        meta["scenes"] = sorted(made)
        print(f"  🎬 Opening contract ({arm}-first): result {rp['coverage']:.0%} of frame, "
              f"step at {tl['step_at']:.1f}s for {tl['step_seconds']:.1f}s"
              + (f", result at {tl['result_at']:.1f}s" if arm == "context" else ""))
        return meta
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ opening placement failed ({type(e).__name__}: {e})")
        return None


def _label_px(text: str) -> int:
    """The size evidence.render_label_png draws the label at: the same measured
    fit (branding.fit_font, Inter Black, LABEL_PX down to 32 within 60% of the
    width), recomputed — the PNG itself does not record it."""
    from factverse import branding as br
    from factverse import evidence
    try:
        size, _f = br.fit_font(lambda s: _font("Inter-Black.ttf", s), [text], evidence.LABEL_PX,
                               int(fv.VIDEO_W * 0.6), floor=32, step=2)
        return int(size)
    except Exception:  # noqa: BLE001
        return 0


# ============================================================ the gate (encoded file)
def _load_small(path: str):
    from PIL import Image
    return Image.open(path).convert("RGB").resize((480, 270))


def frame_diff(a, b) -> float:
    """Mean abs RGB difference above the caption band, outside the top-right
    citation chip. PURE on two 480x270 images."""
    import numpy as np
    x = np.asarray(a, dtype=np.int16)[: int(270 * CAPTION_BAND)]
    y = np.asarray(b, dtype=np.int16)[: int(270 * CAPTION_BAND)]
    m = np.ones(x.shape[:2], dtype=bool)
    m[:40, 330:] = False
    return float(np.abs(x - y)[m].mean())


def frame_std(a) -> float:
    import numpy as np
    return float(np.asarray(a.convert("L"), dtype=np.float32).std())


def scan(video: str, out_dir: Path, seconds: float = SCAN_SECONDS, fps: int = SCAN_FPS) -> list[tuple[float, str]]:
    """(time, png) for the first `seconds` of the ENCODED file, `fps` frames a second."""
    d = out_dir / "scan"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    _ffmpeg([fv.FFMPEG or "ffmpeg", "-y", "-t", f"{seconds:.2f}", "-i", str(video),
             "-vf", f"fps={fps},scale=480:270", str(d / "f%05d.png")], timeout=600)
    return [((int(p.stem[1:]) - 1) / fps, str(p)) for p in sorted(d.glob("f*.png"))]


def runs_of(matches: list[tuple[float, bool]], step: float) -> list[tuple[float, float]]:
    """PURE: contiguous [start, end) windows where matched is True."""
    out, cur = [], None
    for t, ok in matches:
        if ok and cur is None:
            cur = t
        elif not ok and cur is not None:
            out.append((cur, t))
            cur = None
    if cur is not None and matches:
        out.append((cur, matches[-1][0] + step))
    return out


def _norm(w: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", str(w).lower())


def token_end(words: list, tokens: list[str], idx: int) -> float | None:
    """End time of script token `idx`, by aligning the timed words to the script
    tokens (whisper and TTS boundaries split differently). PURE."""
    if not words or idx < 0:
        return None
    a = [_norm(w[2]) for w in words]
    b = [_norm(t) for t in tokens]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    best = None
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            if blk.b + k <= idx:
                best = (blk.a + k, blk.b + k)
    if best is None:
        return None
    wi, ti = best
    wi = min(len(words) - 1, wi + (idx - ti))      # unmatched tail: count forward
    return float(words[wi][1])


def speech_timings(script, words: list, arm: str) -> dict:
    """First speech, the first sentence's word count and end, the limitation's end."""
    sc = script.get("scenes") or []
    tokens, offsets = [], []
    for s in sc:
        offsets.append(len(tokens))
        tokens += _words(s.get("narration", ""))
    first = first_sentence(script)
    n1 = len(_words(first))
    out = {"first_speech_at": round(float(words[0][0]), 3) if words else None,
           "first_sentence_words": n1,
           "first_sentence_end": token_end(words, tokens, n1 - 1) if n1 else None}
    lim = limitation(script, arm)
    if lim:
        i, j, _s = lim
        ss = sentences(sc[i].get("narration", ""))
        upto = offsets[i] + sum(len(_words(x)) for x in ss[: j + 1]) - 1
        out["limitation_end"] = token_end(words, tokens, upto)
        out["limitation_text"] = _s[:160]
    else:
        out["limitation_end"] = None
    return out


def encoded_words(video: str, narration: str):
    """Word timings of the ENCODED audio (whisper), or None when whisper is not
    installed — the caller then uses the narration's own timings."""
    try:
        import importlib.util
        if importlib.util.find_spec("faster_whisper") is None:
            return None
        from factverse import captions
        w = captions.transcribe_words(str(video))
        return captions.correct_words(w, narration) if w else None
    except Exception:  # noqa: BLE001
        return None


def measure(video: str, meta: dict, script: dict, words: list, audio_dur: float,
            partner_seconds: float | None = None) -> dict:
    """The opening gate, measured on the ENCODED file. Never raises."""
    m: dict = {"video": str(video)}
    fails: list[str] = []
    try:
        arm = meta["arm"]
        dur = _probe(video)
        m["duration_s"] = round(dur, 2)
        if not DURATION_MIN <= dur <= DURATION_MAX:
            fails.append("duration")
        if partner_seconds:
            diff = abs(dur - float(partner_seconds)) / max(1e-6, min(dur, float(partner_seconds)))
            m["pair_diff"] = round(diff, 4)
            if diff > PAIR_MAX_DIFF:
                fails.append("pair_duration")
        m["no_sting"] = bool(meta.get("branding") == "skipped" and abs(dur - float(audio_dur)) <= 1.0)
        if not m["no_sting"]:
            fails.append("sting")
        out = Path(meta["refs"]["result"]).parent
        frames = scan(video, out)
        if not frames:
            fails.append("frames")
            raise RuntimeError("no frames decoded")
        refs = {k: _load_small(v) for k, v in meta["refs"].items()}
        f0 = _load_small(frames[0][1])
        lead = "result" if arm == "proof" else "context"
        m["frame0_diff"] = round(frame_diff(f0, refs[lead]), 2)
        m["frame0_std"] = round(frame_std(f0), 2)
        if m["frame0_diff"] > MATCH_MAX or m["frame0_std"] < BLANK_STD_MIN:
            fails.append("frame0")
        step = 1.0 / SCAN_FPS
        loaded = [(t, _load_small(p)) for t, p in frames]
        res_match = [(t, frame_diff(img, refs["result"]) <= MATCH_MAX) for t, img in loaded]
        step_match = [(t, frame_diff(img, refs["step"]) <= MATCH_MAX) for t, img in loaded]
        rw, sw = runs_of(res_match, step), runs_of(step_match, step)
        m["result_windows"] = [[round(a, 3), round(b, 3)] for a, b in rw]
        m["step_windows"] = [[round(a, 3), round(b, 3)] for a, b in sw]
        m["coverage"] = meta.get("coverage")
        if arm == "proof":
            ok2 = bool(rw and rw[0][0] == 0.0 and rw[0][1] >= RESULT_AREA_SECONDS)
            m["result_first_2s"] = ok2
            if not ok2 or (meta.get("coverage") or 0) < RESULT_AREA_MIN:
                fails.append("result_area")
        else:
            m["result_at"] = round(rw[0][0], 3) if rw else None
            if not rw or not CONTEXT_RESULT_FROM <= rw[0][0] <= CONTEXT_RESULT_TO:
                fails.append("result_window")
        m["step_at"] = round(sw[0][0], 3) if sw else None
        m["step_seconds"] = round(sw[0][1] - sw[0][0], 3) if sw else 0.0
        if not sw or sw[0][0] > STEP_BY:
            fails.append("step_late")
        elif m["step_seconds"] < STEP_MIN_SECONDS:
            fails.append("step_short")
        m["label_px"] = meta.get("label_px")
        m["text_px_min"] = min(meta.get("text_px") or [0])
        from factverse import captions
        m["caption_px"] = round(50 * fv.VIDEO_H / captions.LAYOUT_H)
        if (m["label_px"] or 0) < LABEL_MIN_PX:
            fails.append("label_size")
        if m["text_px_min"] < TEXT_MIN_PX or m["caption_px"] < TEXT_MIN_PX:
            fails.append("text_size")
    except Exception as e:  # noqa: BLE001
        m["error"] = f"{type(e).__name__}: {e}"
        if not fails:
            fails.append("measure_error")
    try:
        narration = " ".join(s.get("narration", "") for s in script.get("scenes") or [])
        ew = encoded_words(video, narration)
        m["timing_source"] = "encoded_audio_whisper" if ew else "narration_words"
        sp = speech_timings(script, ew or words, meta.get("arm", "proof"))
        m.update(sp)
        if sp["first_speech_at"] is None or sp["first_speech_at"] > FIRST_SPEECH_BY:
            fails.append("first_speech")
        if sp["first_sentence_words"] > FIRST_SENTENCE_WORDS:
            fails.append("first_sentence_long")
        if sp["first_sentence_end"] is None or sp["first_sentence_end"] > FIRST_SENTENCE_BY:
            fails.append("first_sentence_end")
        if sp["limitation_end"] is None:
            fails.append("limitation_missing")
        elif sp["limitation_end"] > LIMITATION_BY:
            fails.append("limitation_late")
    except Exception as e:  # noqa: BLE001
        m["speech_error"] = f"{type(e).__name__}: {e}"
        fails.append("speech_error")
    m["failures"] = sorted(set(fails))
    m["passed"] = not m["failures"]
    return m


SCRIPT_FIXES = {"first_sentence_long", "first_sentence_end", "first_sentence_content", "opening_long",
                "context_length", "limitation_missing", "limitation_late", "step_late", "duration",
                "pair_duration", "length"}


def repair_kind(failures: list[str]) -> str:
    """"script" when the writer must change words (then re-voice and re-render),
    else "render" (re-render the same script once)."""
    return "script" if any(f in SCRIPT_FIXES for f in failures or []) else "render"


def ledger_view(m) -> dict | None:
    """The gate's result for the ledger: coerced scalars only."""
    if not isinstance(m, dict):
        return None
    keep = ("passed", "failures", "duration_s", "frame0_diff", "coverage", "result_at", "step_at",
            "step_seconds", "first_speech_at", "first_sentence_words", "first_sentence_end",
            "limitation_end", "label_px", "text_px_min", "timing_source", "attempts")
    out = {}
    for k in keep:
        v = m.get(k)
        if isinstance(v, bool) or v is None or isinstance(v, (int, float, str)):
            out[k] = v
        elif isinstance(v, list):
            out[k] = [str(x) for x in v]
    return out


# ============================================================ descriptive chapters
def chapter_candidates(script: dict, starts: list, meta: dict) -> list[tuple[float, str]]:
    """(start, label) for the sections a pilot video really has."""
    sc = script.get("scenes") or []
    if not starts or len(starts) != len(sc) or not isinstance(meta, dict):
        return []
    arm = meta.get("arm")
    hosted = (script.get("evidence") or {}).get("source") == "hosted"
    tl = meta.get("timeline") or {}
    c = []
    if arm == "context":
        c.append((0.0, "Task and requirements"))
        c.append((float(tl.get("result_at") or starts[1]), "Observed result"))
    else:
        c.append((0.0, "Observed result"))
        if limitation(script, "proof") and limitation(script, "proof")[0] == 1:
            c.append((float(starts[1]), "Requirements"))
    c.append((float(tl.get("step_at") or starts[STEP_SCENE]), "Starting step"))
    seq = (tl.get("scenes") or {}).get(SEQ_SCENE) or []
    if any(k == "sequence" for k, _s in seq):          # the sequence really is on screen
        spill = sum(s for k, s in seq if k == "step")
        c.append((float(starts[SEQ_SCENE]) + spill,
                  "Input to output" if hosted else "The author's demo, step by step"))
    for i in range(SEQ_SCENE + 1, len(sc) - 1):
        if LIMIT_RX.search(_NOT_TESTED.sub("", sc[i].get("narration", ""))):
            c.append((float(starts[i]), "Limitations"))
            break
    c.append((float(starts[-1]), "Decision and next step"))
    return c
