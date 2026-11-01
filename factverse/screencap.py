"""v3-B original-visuals engine: screen-record the tool's real page.

For kind="tool" videos the visual source is the tool itself — a headless-Chromium
recording of its GitHub repo / HF model pages (1920x1080, dark) — README, then
releases / issues / commits (v3-B.5 browse_plan) — recut AFTER the narration is
timed into sequential, non-overlapping per-clip pieces (recut_plan), plus a
Pygments code card for the deliverable and the first page's screenshot for the
thumbnail. Replaces Pexels stock entirely when it succeeds; every entry point
fails soft (returns None) so the caller can fall back to stock.

Import rule: this module is imported by ai_pipeline at module level, and CI's
test job installs neither playwright nor a browser — so playwright and pygments
are ONLY imported inside the functions that use them (same pattern as
faster_whisper in captions.py).
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from factverse import config as fv

REC_W, REC_H = 1920, 1080     # the delivery canvas size (fv.VIDEO_W/H, v3-G.4)
HEAD_TRIM = 2.5               # first seconds of every recording are page-load blank
MIN_SEG = 4.0                 # a scene clip shorter than this reads as a glitch
# v3-B.5: 2.4 wps / 300 s cap under-recorded a median ~761-word script, and the
# shortfall was paid for with -stream_loop in step5_build — the visible loop.
REC_MIN, REC_MAX = 60.0, 480.0
WPS = 2.0                     # deliberately slow narration estimate, words per second
MAX_SLOW = 1.35               # v3-B.5: the most a recording may be stretched (setpts)
TAIL_PAD = 0.5                # frozen-frame margin past a piece's share (see recut_plan)
FPS = 30                      # recut pieces are encoded at the engine's FPS
SETTLE_MS = 3000              # after a page paints, let it settle (real content, kept)
BOTTOM_PAUSE_MS = 1400        # the reading rhythm's long pause, held at the bottom


# ------------------------------------------------------------- pure planners
def estimate_video_seconds(script: dict, wps: float = WPS) -> float:
    """Size the recording to the video we are about to make (script exists
    before visuals are fetched), so per-scene chunks rarely need looping."""
    words = sum(len(str(sc.get("narration", "")).split())
                for sc in (script.get("scenes") or []))
    if words <= 0:
        return REC_MIN
    return max(REC_MIN, min(REC_MAX, words / wps))


# GitHub / HF path heads that are site sections, not an owner — such a URL is not a
# repo or model page, so it is browsed as "just the page".
_GH_RESERVED = {"orgs", "topics", "features", "marketplace", "explore", "settings",
                "sponsors", "collections", "trending", "search", "login", "about"}
_HF_RESERVED = {"datasets", "spaces", "docs", "blog", "papers", "models", "collections",
                "organizations", "settings", "login", "posts", "learn", "tasks"}


def browse_plan(url: str) -> list[str]:
    """v3-B.5: the pages one recording visits, in order. A single README scrolled
    to the bottom and back was the same footage over and over (the "loop" the owner
    saw), so a repo is shown as its README, then releases, issues and commits; an HF
    model as its card, file tree and discussions. Anything else is just the page."""
    import re
    u = str(url or "").strip()
    m = re.match(r"https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+)", u)
    if m and m.group(1).lower() not in _GH_RESERVED:
        repo = m.group(2)[:-4] if m.group(2).endswith(".git") else m.group(2)
        base = f"https://github.com/{m.group(1)}/{repo}"
        return [base, base + "/releases", base + "/issues", base + "/commits"]
    m = re.match(r"https?://huggingface\.co/([\w.-]+)/([\w.-]+)", u)
    if m and m.group(1).lower() not in _HF_RESERVED:
        base = f"https://huggingface.co/{m.group(1)}/{m.group(2)}"
        return [base, base + "/tree/main", base + "/discussions"]
    return [u] if u.startswith("http") else []


def landed_on(expected: str, actual: str) -> bool:
    """A sub-page must not be recorded if the site redirected it elsewhere: a repo
    with Issues disabled sends /issues back to the README, which would put the
    README on screen twice — the repeat this phase removes."""
    from urllib.parse import urlparse
    e, a = urlparse(str(expected)), urlparse(str(actual or ""))
    ep, ap_ = e.path.rstrip("/").lower(), a.path.rstrip("/").lower()
    return a.netloc.lower().endswith(e.netloc.lower()) and (ap_ == ep or ap_.startswith(ep + "/"))


def page_budget(remaining: float, pages_left: int) -> float:
    """A page's time share: what is left of the target, split over the pages still
    to visit. A short page that hits its bottom early hands its unused time on."""
    return max(0.0, remaining) / max(1, pages_left)


def recut_plan(scene_clips: list, durs: list, provisional: set, rec_seconds: float,
               max_slow: float = MAX_SLOW, pad: float = TAIL_PAD) -> list[dict]:
    """v3-B.5: cut the recording AFTER the narration timings exist.

    One piece per recording clip, sized to the exact share step5_build gives that
    clip (durs[i] / len(scene_clips[i])), taken from SEQUENTIAL, non-overlapping
    spans of the recording. A recording shorter than the total is stretched
    uniformly (setpts, at most `max_slow`); whatever is still missing is a held
    last frame at the end of each piece (tpad clone) — spread in proportion to the
    shares, so every scene keeps motion. `pad` adds a frozen margin past the share:
    an encoded clip's probed length can land a frame short, and step5_build would
    then -stream_loop it once. Returns [] when there is nothing safe to plan.
    """
    if not scene_clips or not durs or len(durs) != len(scene_clips) or rec_seconds <= 0:
        return []
    slots = []
    for i, clips in enumerate(scene_clips):
        for j, c in enumerate(clips or []):
            if str(c) in provisional:
                slots.append((i, j, float(durs[i]) / len(clips)))
    need = sum(s for _i, _j, s in slots)
    if not slots or need <= 0:
        return []
    slow = 1.0 if rec_seconds >= need else min(max_slow, need / rec_seconds)
    # rec >= need: each piece reads exactly its share. Shorter: the shares tile the
    # WHOLE recording, so no span is read twice and none is skipped.
    scale = 1.0 if rec_seconds >= need else rec_seconds / need
    plan, cursor = [], 0.0
    for i, j, share in slots:
        src = share * scale
        hold = max(0.0, share - src * slow)
        plan.append({"scene": i, "slot": j, "start": round(cursor, 3), "src": round(src, 3),
                     "slow": round(slow, 4), "hold": round(hold + pad, 3),
                     "out": round(share + pad, 3), "share": round(share, 3)})
        cursor += src
    return plan


def stream_loops(slot_seconds: float, clip_seconds: float) -> int:
    """The -stream_loop count step5_build computes for a clip (engine line ~490);
    a mirror so a test can pin that a recut piece never triggers it."""
    import math
    cd = clip_seconds if clip_seconds > 0 else 5
    return max(0, int(math.ceil(slot_seconds / cd)) - 1)


def segment_plan(total_seconds: float, n_scenes: int,
                 min_len: float = MIN_SEG) -> list[tuple[float, float]]:
    """Split [0, total] into up to n_scenes sequential (start, length) chunks.
    A short recording yields fewer, longer chunks (scenes then share them)."""
    if total_seconds <= 0 or n_scenes <= 0:
        return []
    k = min(n_scenes, max(1, int(total_seconds // min_len)))
    length = total_seconds / k
    return [(round(i * length, 3), round(length, 3)) for i in range(k)]


def _join_args(takes: list[tuple[str, float]], dst: str) -> list[str]:
    """Trim each page's own page-load blank (its measured head) and join the pages
    into ONE recording. Every navigation is its own Playwright video, so the blank
    after each goto is removed the same way the first page's always was."""
    args = [fv.FFMPEG or "ffmpeg", "-y"]
    for webm, head in takes:
        args += ["-ss", str(head), "-i", str(webm)]
    chains = "".join(f"[{k}:v]fps={FPS},setpts=PTS-STARTPTS,setsar=1[v{k}];"
                     for k in range(len(takes)))
    ins = "".join(f"[v{k}]" for k in range(len(takes)))
    graph = f"{chains}{ins}concat=n={len(takes)}:v=1:a=0[v]"
    return args + ["-filter_complex", graph, "-map", "[v]", "-an", "-c:v", "libx264",
                   "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p", dst]


def _piece_args(src: str, dst: str, piece: dict) -> list[str]:
    """One recut piece: read [start, start+src) of the recording, stretch it by
    `slow`, then hold its last frame for `hold` seconds; output exactly `out`."""
    vf = (f"setpts={piece['slow']}*(PTS-STARTPTS),fps={FPS},"
          f"tpad=stop_mode=clone:stop_duration={piece['hold']}")
    return [fv.FFMPEG or "ffmpeg", "-y", "-ss", str(piece["start"]), "-t", str(piece["src"]),
            "-i", src, "-vf", vf, "-t", str(piece["out"]), "-an", "-c:v", "libx264",
            "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p", dst]


def _cut_args(src: str, dst: str, start: float, length: float) -> list[str]:
    return [fv.FFMPEG or "ffmpeg", "-y", "-ss", str(start), "-i", src,
            "-t", str(length), "-an", "-c:v", "libx264", "-preset", "ultrafast",
            "-crf", "23", dst]


def _still_args(png: str, mp4: str, seconds: float) -> list[str]:
    return [fv.FFMPEG or "ffmpeg", "-y", "-loop", "1", "-i", png,
            "-t", str(seconds), "-r", "30", "-c:v", "libx264", "-preset", "fast",
            "-crf", "20", "-pix_fmt", "yuv420p", "-an", mp4]


# ------------------------------------------------------------- process seams
def _ffmpeg(args: list[str], timeout: int = 600) -> bool:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0
    except Exception as e:
        print(f"   ⚠️ ffmpeg step failed: {e}")
        return False


def _probe_duration(path: str) -> float:
    try:
        r = subprocess.run([fv.FFPROBE or "ffprobe", "-v", "error",
                            "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", path],
                           capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


# ------------------------------------------------------------- recording
_AT_BOTTOM_JS = ("() => window.innerHeight + window.scrollY"
                 " >= document.body.scrollHeight - 80")


def _browse(page, seconds: float) -> None:
    """Scroll DOWN at the reading rhythm until the bottom or `seconds` is spent.
    v3-B.5: it never scrolls back to the top — the scroll-to-top-and-repeat was
    the loop; the caller moves on to the next page instead."""
    end = time.monotonic() + max(0.0, seconds)
    step = 0
    while time.monotonic() < end:
        try:
            if page.evaluate(_AT_BOTTOM_JS):
                left_ms = int(max(0.0, end - time.monotonic()) * 1000)
                page.wait_for_timeout(min(BOTTOM_PAUSE_MS, left_ms))
                return
            page.mouse.wheel(0, 300)
            # reading rhythm: two quick scrolls, then a longer pause
            page.wait_for_timeout(650 if step % 3 else 1400)
        except Exception:
            page.wait_for_timeout(1000)  # keep recording even if a scroll fails
        step += 1


def _record_pages(urls: list[str], out_dir: str,
                  target_seconds: float) -> tuple[list[tuple[str, float]], str]:
    """Record a slow human-style browse of `urls` in order, one Playwright page
    (so one .webm) per URL. Returns ([(webm, head), ...], screenshot) where head is
    that page's own seconds of blank page-load. A page that fails, answers >= 400
    or redirects off its path is skipped. When every page is exhausted before the
    target, recording simply stops — recut() holds the last frame, nothing loops.
    Playwright is imported here, not at module level — CI tests have no browser."""
    from playwright.sync_api import sync_playwright

    out = Path(out_dir)
    shot = ""
    kept = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": REC_W, "height": REC_H},
            record_video_dir=str(out),
            record_video_size={"width": REC_W, "height": REC_H},
            color_scheme="dark",
        )
        remaining = float(target_seconds)
        for k, url in enumerate(urls):
            if remaining <= 0:
                break
            page = ctx.new_page()            # recording starts here: blank until paint
            t0 = time.monotonic()
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                ok = resp is None or resp.status < 400
                if ok and k > 0:
                    ok = landed_on(url, page.url)
            except Exception as e:
                print(f"   ⏭️ page skipped ({url}): {str(e)[:80]}")
                ok = False
            if not ok:
                page.close()
                continue
            head = max(HEAD_TRIM, time.monotonic() - t0 + 0.3)   # slow pages: longer blank
            page.wait_for_timeout(SETTLE_MS)  # settle (real content, kept)
            if not shot:
                try:
                    shot = str(out / "page.png")
                    page.screenshot(path=shot)   # thumbnail base: the FIRST page
                except Exception:
                    shot = ""
            share = page_budget(remaining, len(urls) - k)
            _browse(page, share - (time.monotonic() - t0 - head))
            remaining -= time.monotonic() - t0 - head
            try:
                # ask while the page is alive: the driver is gone once the
                # sync_playwright block exits, and path() then raises
                kept.append((str(page.video.path()) if page.video else "", head))
            except Exception:
                pass
            page.close()
        ctx.close()                          # finalizes every .webm
        browser.close()
    takes = [(w, h) for w, h in kept if w and Path(w).exists()]
    if not takes:
        raise RuntimeError("no recording produced")
    return takes, shot


def capture(script: dict) -> dict | None:
    """Record the tool's pages and return {'scene_clips': list[list[path]] one
    per scene (PROVISIONAL — recut() replaces them once the narration timings
    exist), 'screenshot', 'recording', 'rec_seconds', 'provisional'}. None on any
    failure — the caller falls back to stock, and the second cron firing retries."""
    scenes = script.get("scenes") or []
    url = str(script.get("source_url") or "").strip()
    if not url.startswith("http"):
        url = str((script.get("deliverable") or {}).get("url", "")).strip()
    if not scenes or not url.startswith("http"):
        return None
    try:
        rec_dir = fv.TEMP / "screencap"
        shutil.rmtree(rec_dir, ignore_errors=True)
        rec_dir.mkdir(parents=True, exist_ok=True)
        takes, shot = _record_pages(browse_plan(url), str(rec_dir),
                                    estimate_video_seconds(script))
        trimmed = str(rec_dir / "recording.mp4")
        if not _ffmpeg(_join_args(takes, trimmed), timeout=900):
            return None
        total = _probe_duration(trimmed)
        if total < MIN_SEG:
            return None
        chunks = []
        for i, (start, length) in enumerate(segment_plan(total, len(scenes))):
            dst = str(rec_dir / f"chunk_{i:03d}.mp4")
            if (_ffmpeg(_cut_args(trimmed, dst, start, length))
                    and Path(dst).exists() and Path(dst).stat().st_size > 1000):
                chunks.append(dst)
        if not chunks:
            return None
        k, n = len(chunks), len(scenes)
        scene_clips = [[chunks[min(i * k // n, k - 1)]] for i in range(n)]
        return {"scene_clips": scene_clips, "screenshot": shot, "recording": trimmed,
                "rec_seconds": total, "provisional": sorted(set(chunks)),
                "pages": len(takes)}
    except Exception as e:
        print(f"   ⚠️ screen capture failed ({e}) — stock fallback.")
        return None


def recut(cap: dict, scene_clips: list, durs: list) -> int | None:
    """v3-B.5 seam: replace every provisional recording clip in `scene_clips`
    (in place) with a piece cut to its real slot share — see recut_plan. Runs
    right before step5_build, after every inject_* call has settled how many
    clips each scene holds. All or nothing: a failed piece leaves the provisional
    clips untouched and returns None (fail soft, and SAYS it failed)."""
    try:
        if not isinstance(cap, dict) or not cap.get("recording"):
            return None
        plan = recut_plan(scene_clips, durs, set(cap.get("provisional") or []),
                          float(cap.get("rec_seconds") or 0.0))
        if not plan:
            return None
        rec = str(cap["recording"])
        out_dir = Path(rec).parent
        made = []
        for pc in plan:
            dst = str(out_dir / f"piece_{pc['scene']:03d}_{pc['slot']}.mp4")
            if not (_ffmpeg(_piece_args(rec, dst, pc))
                    and Path(dst).exists() and Path(dst).stat().st_size > 1000):
                print(f"   ⚠️ recut piece {pc['scene']}/{pc['slot']} failed — "
                      f"keeping the provisional clips.")
                return None
            made.append((pc, dst))
        for pc, dst in made:
            scene_clips[pc["scene"]][pc["slot"]] = dst
        print(f"   ✂️ Recording recut to the narration: {len(made)} pieces, "
              f"x{plan[0]['slow']} speed, {cap.get('rec_seconds', 0):.0f}s recorded.")
        return len(made)
    except Exception as e:
        print(f"   ⚠️ recut failed ({e}) — keeping the provisional clips.")
        return None


# ------------------------------------------------------------- code cards
def _mono_font(size: int):
    from PIL import ImageFont
    for c in [str(fv.FONTS / "JetBrainsMono-Regular.ttf"),
              "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
              "C:/Windows/Fonts/consola.ttf"]:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_code_card_png(deliverable: dict, out_png: str,
                         size: tuple[int, int] = (1280, 720),
                         font_size: int = 22) -> str | None:
    """Terminal-style card for the deliverable (Pygments bash highlighting,
    JetBrains Mono 22px per spec decision 2). Returns out_png or None."""
    from PIL import Image, ImageDraw
    from pygments import lex
    from pygments.lexers import BashLexer
    from pygments.styles import get_style_by_name

    text = str((deliverable or {}).get("text", "")).strip()
    if not text:
        return None
    W, H = size
    img = Image.new("RGB", (W, H), (13, 17, 23))
    d = ImageDraw.Draw(img)
    cx0, cy0, cx1, cy1 = int(W * 0.08), int(H * 0.18), int(W * 0.92), int(H * 0.82)
    d.rounded_rectangle([cx0, cy0, cx1, cy1], radius=16,
                        fill=(22, 27, 34), outline=(48, 54, 61), width=2)
    for j, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([cx0 + 24 + j * 34, cy0 + 22, cx0 + 40 + j * 34, cy0 + 38], fill=c)
    kind = str((deliverable or {}).get("kind", "steps"))
    label = {"command": "RUN THIS", "repo": "GET THE REPO"}.get(kind, "DO THIS")
    fnt = _mono_font(font_size)
    d.text((cx0 + 24, cy0 + 60), f"{label} — free, link in description",
           font=_mono_font(max(16, font_size - 4)), fill=(139, 148, 158))

    style = get_style_by_name("monokai")
    cw = d.textlength("M", font=fnt) or font_size * 0.6
    x0, y = cx0 + 48, cy0 + 60 + int(font_size * 2.4)
    line_h = int(font_size * 1.7)
    d.text((x0, y), "$", font=fnt, fill=(63, 185, 80))
    x = x0 + int(cw * 2)
    for tok, val in lex(text, BashLexer()):
        color = (230, 237, 243)
        try:
            s = style.style_for_token(tok)
            if s and s.get("color"):
                color = tuple(int(s["color"][i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            pass
        for piece in val.splitlines(True):
            seg = piece.rstrip("\n")
            while seg and y <= cy1 - 2 * line_h:
                room = max(1, int((cx1 - 48 - x) / cw))
                head, seg = seg[:room], seg[room:]
                d.text((x, y), head, font=fnt, fill=color)
                x += int(d.textlength(head, font=fnt))
                if seg:
                    x, y = x0, y + line_h
            if piece.endswith("\n"):
                x, y = x0, y + line_h
    url = str((deliverable or {}).get("url", "")).strip()
    if url:
        d.text((cx0 + 24, cy1 - int(font_size * 1.8)), url[:90],
               font=_mono_font(max(16, font_size - 4)), fill=(110, 118, 129))
    d.rectangle([(0, H - 8), (W, H)], fill=(220, 38, 38))  # brand baseline
    img.save(out_png)
    return out_png if Path(out_png).exists() else None


def make_code_card(deliverable: dict, out_mp4: str, seconds: float = 6.0) -> str | None:
    """Still card -> silent mp4 clip (same contract as infographics cards)."""
    try:
        png = str(Path(out_mp4).with_suffix(".png"))
        if not render_code_card_png(deliverable, png):
            return None
        if (_ffmpeg(_still_args(png, out_mp4, seconds))
                and Path(out_mp4).exists() and Path(out_mp4).stat().st_size > 1000):
            return out_mp4
    except Exception as e:
        print(f"   ⚠️ code card failed: {e}")
    return None


# Scenes that narrate installing/running the tool — shared with the deterministic
# chapter builder (spec v3-E #6) so both surfaces agree on what an "install scene" is.
INSTALL_KW = ("install", "command", "clone", "pip ", "terminal", "run it", "set it up")


def _lead_with(clips: list, card: str) -> None:
    """Put the card first. A stat card already leading the scene is replaced —
    step5_build time-shares a scene equally between its clips, and a third clip
    would squeeze the command below readable length."""
    if clips and "statcard" in str(clips[0]):
        clips[0] = card
    else:
        clips.insert(0, card)


def inject_code_card(script: dict, scene_clips: list) -> int:
    """Lead the payoff scenes with the deliverable card: always the final scene
    ("the exact command is in the description"), plus the first scene after the
    hook that narrates installing/running it. Mirrors infographics.inject_cards."""
    dl = script.get("deliverable")
    if not dl or not scene_clips:
        return 0
    card = make_code_card(dl, str(fv.TEMP / "codecard.mp4"))
    if not card:
        return 0
    _lead_with(scene_clips[-1], card)
    placed = 1
    kw = INSTALL_KW
    scenes = script.get("scenes") or []
    for i in range(1, min(len(scenes), len(scene_clips)) - 1):   # never the hook
        if any(w in str(scenes[i].get("narration", "")).lower() for w in kw):
            _lead_with(scene_clips[i], card)
            placed += 1
            break
    return placed
