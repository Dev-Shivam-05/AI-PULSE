"""
Receipts: the channel actually checks the tool before recommending it.

spec v3-E.2 (docs/spec/ai-pulse-v3e2.md). The check DOWNLOADS, it never EXECUTES:
pip is pinned to wheels (--only-binary :all: — an sdist download runs setup.py, a
wheel download runs nothing), git clone runs no hooks, and a curl-style deliverable
is fetched with requests and never piped to a shell. Anything that would need to
execute candidate code (docker, npx, piped sh) is refused outright.

Everything fails soft: the daily run is unattended, so a miss costs the beat and
the footage, never the video — and the seam SAYS which happened (run() logs each
of the three outcomes distinctly).
"""
from __future__ import annotations

import datetime as _dt
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from factverse import config as fv
from factverse.screencap import INSTALL_KW, _ffmpeg, _mono_font

PIP_TIMEOUT = 180
CLONE_TIMEOUT = 180
FETCH_TIMEOUT = 60          # WALL-CLOCK for the whole fetch, not requests' per-read gap
FETCH_MAX_BYTES = 2_000_000_000   # disk guard: past this the fetch is refused, not measured
MAX_LINES = 8
FPS = 30

_PIP_RE = re.compile(r"\bpip3?(?:\.exe)?\s+install\s+(.+)", re.IGNORECASE)
_CLONE_RE = re.compile(r"\bgit\s+clone\s+(\S+)", re.IGNORECASE)
_FETCH_RE = re.compile(r"\b(?:curl|wget)\s+(.+)", re.IGNORECASE)
# A segment that needs a shell to mean anything (pipes, chaining, command
# substitution, docker, npx) is not download-checkable. Measuring the 10KB
# install.sh of a `curl ... | sh` line — or of its `&& sh install.sh` /
# `$(curl ...)` cousins, which the review caught slipping through — and
# stamping it as "the download" would be a lie.
_REFUSE_RE = re.compile(r"\||&&|;|\$\(|`|\bdocker\b|\bnpx\b|<\(", re.IGNORECASE)
# leading alphanumeric: kills `.`, `..` and every flag-shaped residue — a local
# directory target would make pip BUILD it, which executes the build backend
_PKG_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# flags whose ARGUMENT is not a package (pip install -r requirements.txt would
# otherwise "check" whatever PyPI squatter owns that literal name)
_CONSUMING_FLAGS = {"-r", "--requirement", "-c", "--constraint", "-e", "--editable",
                    "-t", "--target", "-i", "--index-url", "--extra-index-url",
                    "-f", "--find-links"}


def _pip_target(rest: str) -> str:
    """First non-flag token after `install`, reduced to a bare package name.
    A URL install (git+https://...) is a SOURCE build — pip would execute its
    setup.py — so it is refused here, not merely failed later."""
    toks = rest.split()
    i = 0
    while i < len(toks):
        tok = toks[i]
        if tok.startswith("-"):
            i += 2 if tok.split("=")[0] in _CONSUMING_FLAGS else 1
            continue
        if "://" in tok or tok.startswith("git+"):
            return ""
        name = re.split(r"[\[=<>~!;@]", tok)[0].strip("'\"`")
        return name if _PKG_OK.match(name) else ""
    return ""


def check_plan(deliverable_text: str, dest: str) -> dict | None:
    """PURE: parse the deliverable into a download-only check, or None.
    Segments split exactly like command_grounded; the first checkable one wins."""
    for seg in re.split(r"[•\n]+", str(deliverable_text or "")):
        seg = seg.strip()
        if not seg or _REFUSE_RE.search(seg):
            continue
        m = _PIP_RE.search(seg)
        if m:
            pkg = _pip_target(m.group(1))
            if pkg:
                return {"kind": "pip", "target": pkg, "dest": dest,
                        "args": [sys.executable, "-m", "pip", "download", pkg,
                                 "--no-deps", "--only-binary", ":all:",
                                 "--no-cache-dir",  # a cached wheel is a 0.1s "download" — a lie
                                 "--progress-bar", "off", "--no-input", "-d", dest]}
            continue
        m = _CLONE_RE.search(seg)
        if m and m.group(1).startswith(("http://", "https://")):
            return {"kind": "clone", "target": m.group(1), "dest": dest,
                    "args": ["git", "clone", "--depth", "1", m.group(1), dest]}
        m = _FETCH_RE.search(seg)
        if m:
            url = next((t.strip("'\"") for t in m.group(1).split()
                        if t.startswith(("http://", "https://"))), "")
            if url:
                return {"kind": "fetch", "target": url, "dest": dest, "args": []}
    return None


def _round_mb(nbytes: int) -> float | int:
    """1 decimal under 10 MB, whole numbers from 10 up — and never 0 for a real
    download: a 10KB script would otherwise narrate 'at 0 megabytes'."""
    mb = nbytes / 1e6
    if mb >= 10:
        return int(round(mb))
    return max(0.1, round(mb, 1)) if nbytes > 0 else 0


def _num(x) -> str:
    """18.0 -> '18' — TTS reads '.0' as 'point zero'."""
    return str(int(x)) if float(x) == int(float(x)) else str(x)


def _pypi_info(pkg: str) -> dict:
    """Latest version + its upload date from the registry, or {}. Fail-soft:
    the lookup garnishes the ledger row, it must never cost the check."""
    try:
        import requests
        r = requests.get(f"https://pypi.org/pypi/{pkg}/json", timeout=15)
        if r.status_code != 200:
            return {}
        d = r.json()
        out = {}
        v = (d.get("info") or {}).get("version")
        if v:
            out["version"] = str(v)
        urls = d.get("urls") or []
        if urls and urls[0].get("upload_time"):
            out["released"] = str(urls[0]["upload_time"])[:10]
        return out
    except Exception:
        return {}


def _dest_bytes(dest: Path) -> int:
    return sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())


def _basename(p: str) -> str:
    """Last path segment on EITHER separator — pathlib's .name is a no-op for a
    backslash path on posix, which turned the Saved rule into a lie on the very
    CI the suite runs on."""
    return re.split(r"[\\/]+", str(p).rstrip("\\/"))[-1]


def _clean_lines(raw: str) -> list[str]:
    """The footage shows the TOOL's output, not the runner's housekeeping: pip's
    [notice] upgrade nags are dropped, and the lines that carry a local path —
    pip's 'Saved <path>' and git's "Cloning into '<path>'..." — keep only its
    last segment. The live frame inspection caught the machine's own directory
    layout burned onto a to-be-published video; the review caught the clone
    branch re-shipping the same leak."""
    out = []
    for l in str(raw or "").splitlines():
        l = l.strip()
        if not l or l.startswith("[notice]"):
            continue
        m = re.match(r"(?i)(saved\s+)(\S+)$", l)
        if m:
            l = m.group(1) + _basename(m.group(2))
        m = re.match(r"(?i)(cloning into ')([^']+)('.*)$", l)
        if m:
            l = m.group(1) + _basename(m.group(2)) + m.group(3)
        out.append(l)
    return out[:MAX_LINES]


def run_check(plan: dict) -> dict | None:
    """Execute the download-only plan and measure it. None on any failure —
    timeout, nonzero exit, empty destination, network. Removes the destination
    after measuring (a torch wheel is GBs of runner disk)."""
    if not plan:
        return None
    dest = Path(plan.get("dest") or (plan["args"][-1] if plan.get("args")
                                     else fv.TEMP / "receipts_dl"))
    try:
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        t0 = time.monotonic()
        if plan["kind"] in ("pip", "clone"):
            timeout = PIP_TIMEOUT if plan["kind"] == "pip" else CLONE_TIMEOUT
            r = subprocess.run(plan["args"], capture_output=True, text=True,
                               timeout=timeout)
            if r.returncode != 0:
                return None
            lines = _clean_lines((r.stdout or "") + "\n" + (r.stderr or ""))
        else:  # fetch — requests stream, no subprocess, never piped anywhere
            import requests
            # the URL is README-verbatim = attacker-controlled: the filename is
            # sanitized so it cannot walk out of dest (backslashes are path
            # separators on the supervised Windows box), and the stream gets the
            # WALL-CLOCK deadline requests' own timeout does not provide — a
            # server dripping one byte a minute would otherwise hold the
            # unattended run until the CI job kill, on both cron firings.
            name = re.sub(r"[^A-Za-z0-9._-]", "_",
                          _basename(plan["target"].split("?")[0])).lstrip(".") or "download"
            deadline = time.monotonic() + FETCH_TIMEOUT
            got = 0
            with requests.get(plan["target"], stream=True,
                              timeout=FETCH_TIMEOUT) as r:
                if r.status_code != 200:
                    return None
                with open(dest / name, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        got += len(chunk)
                        if time.monotonic() > deadline or got > FETCH_MAX_BYTES:
                            return None
                        f.write(chunk)
            lines = [f"fetching {plan['target']}", f"saved {name}"]
        seconds = round(time.monotonic() - t0, 1)
        nbytes = _dest_bytes(dest)
        if nbytes <= 0:
            return None
        out = {"kind": plan["kind"], "target": plan["target"], "seconds": seconds,
               "mb": _round_mb(nbytes), "lines": lines,
               "date": _dt.date.today().isoformat()}
        if plan["kind"] == "pip":
            out.update(_pypi_info(plan["target"]))
        return out
    except Exception:
        return None
    finally:
        shutil.rmtree(dest, ignore_errors=True)


# ------------------------------------------------------------------ the beat
def install_scene_idx(script: dict) -> int | None:
    """The scene the beat and the footage belong to: the first scene after the
    hook (and before the finale) that narrates installing/running the tool —
    the same selection inject_code_card makes, from the same keyword tuple."""
    scenes = script.get("scenes") or []
    for i in range(1, len(scenes) - 1):
        if any(w in str(scenes[i].get("narration", "")).lower() for w in INSTALL_KW):
            return i
    return None


def beat_text(result: dict) -> str:
    d = _dt.date.fromisoformat(result["date"])
    return (f"Checked by {fv.CHANNEL_NAME} on {d:%B} {d.day}: the download finished "
            f"in {_num(result['seconds'])} seconds at {_num(result['mb'])} megabytes.")


def add_beat(script: dict, result: dict) -> bool:
    """Append the beat to the install scene's narration and pin the result on
    the script. False when the script has no install scene — spec #8: then the
    video ships with no beat and no clip at all."""
    i = install_scene_idx(script)
    if i is None:
        return False
    sc = script["scenes"][i]
    sc["narration"] = str(sc.get("narration", "")).rstrip() + " " + beat_text(result)
    script["receipts"] = result
    return True


# ------------------------------------------------------------------ the clip
_BG = (13, 17, 23)
_CARD = (22, 27, 34)
_OUTLINE = (48, 54, 61)
_GREY = (139, 148, 158)
_TEXT = (230, 237, 243)
_GREEN = (63, 185, 80)


def _display_cmd(result: dict) -> str:
    """The command line the clip opens with — an abbreviation of the real check
    (the housekeeping flags dropped), never of a command we did not run."""
    k, t = result["kind"], result["target"]
    if k == "pip":
        return f"pip download {t} --only-binary :all:"
    if k == "clone":
        return f"git clone --depth 1 {t}"
    name = t.rstrip("/").rsplit("/", 1)[-1] or "download"
    return f"curl -L -o {name} {t}"


def make_terminal_clip(result: dict, out_mp4: str, seconds: float) -> str | None:
    """Real terminal footage of the check: the command, then its real output
    lines revealed over the first 70%, then the receipts summary holding to the
    end. Rendered to exactly `seconds` — the C.3 law for animated clips."""
    if not result or seconds <= 0:
        return None
    from PIL import Image, ImageDraw
    W, H = 1280, 720
    fdir = fv.TEMP / "receipt_fr"
    try:
        shutil.rmtree(fdir, ignore_errors=True)
        fdir.mkdir(parents=True, exist_ok=True)
        fnt = _mono_font(22)
        fnt_small = _mono_font(18)
        cx0, cy0, cx1, cy1 = int(W * 0.08), int(H * 0.12), int(W * 0.92), int(H * 0.88)
        x0 = cx0 + 48
        line_h = int(22 * 1.7)
        probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        cw = probe.textlength("M", font=fnt) or 13
        max_chars = max(10, int((cx1 - 24 - x0) / cw))
        # "OK:", never "✔" — the live frame inspection showed the check mark as
        # tofu in JetBrains Mono, and a width probe cannot detect tofu (it HAS
        # width). The repo has shipped this class of bug before ("star glyph
        # becomes a word"); a word is the deterministic fix.
        summary = (f"OK: {_num(result['mb'])} MB in {_num(result['seconds'])}s "
                   f"— checked by {fv.CHANNEL_NAME} {result['date']}")
        if len(summary) > max_chars:   # a long configured channel name must not overrun
            summary = summary[:max_chars - 1] + "…"
        trunc = lambda l, budget: (l[:budget - 1] + "…") if len(l) > budget else l
        # the command row is drawn 2 glyphs in (after the $), so its budget is 2 short
        content = ([trunc(_display_cmd(result), max_chars - 2)]
                   + [trunc(l, max_chars) for l in list(result.get("lines", []))[:MAX_LINES]])
        # CEIL, not floor: a clip even 1/30s short of its share makes step5_build
        # loop it, and the wrapped first frame flashes at the scene cut. A frame
        # long is cut from the held summary — invisible.
        n = max(2, -int(-FPS * seconds // 1))
        for fr in range(n):
            t = fr / (n - 1)
            img = Image.new("RGB", (W, H), _BG)
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([cx0, cy0, cx1, cy1], radius=16,
                                fill=_CARD, outline=_OUTLINE, width=2)
            for j, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
                d.ellipse([cx0 + 24 + j * 34, cy0 + 22, cx0 + 40 + j * 34, cy0 + 38],
                          fill=c)
            d.text((cx0 + 24, cy0 + 60), "we ran the check ourselves",
                   font=fnt_small, fill=_GREY)
            y = cy0 + 60 + int(22 * 2.4)
            shown = len(content) if t >= 0.7 else int(t / 0.7 * len(content)) + 1
            for j, line in enumerate(content[:shown]):
                if y > cy1 - 2 * line_h:
                    break
                if j == 0:
                    d.text((x0, y), "$", font=fnt, fill=_GREEN)
                    d.text((x0 + int(cw * 2), y), line, font=fnt, fill=_TEXT)
                else:
                    d.text((x0, y), line, font=fnt, fill=_GREY)
                y += line_h
            if t >= 0.7:
                d.text((x0, min(y + line_h // 2, cy1 - line_h - 8)), summary,
                       font=fnt, fill=_GREEN)
            d.rectangle([(0, H - 8), (W, H)], fill=(220, 38, 38))  # brand baseline
            img.save(fdir / f"{fr:04d}.png")
        ok = _ffmpeg([fv.FFMPEG or "ffmpeg", "-y", "-framerate", str(FPS),
                      "-i", str(fdir / "%04d.png"),
                      "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                      "-pix_fmt", "yuv420p", "-an", out_mp4], timeout=300)
        if ok and Path(out_mp4).exists() and Path(out_mp4).stat().st_size > 20000:
            return out_mp4
    except Exception as e:
        print(f"   ⚠️ receipts clip failed: {e}")
    finally:
        shutil.rmtree(fdir, ignore_errors=True)
    return None


def inject_receipt_clip(script: dict, scene_clips: list,
                        scene_durs: list | None = None) -> int:
    """Lead the install scene with the real footage. Runs AFTER inject_cards
    and inject_code_card: a statcard or codecard already leading the scene is
    REPLACED (share = sdur/len), anything else is joined (share = sdur/(len+1))
    — a scene's time splits equally between its clips, so the clip is rendered
    to exactly the share step5_build will give it. The final scene keeps the
    code card either way."""
    result = script.get("receipts")
    if not result or not scene_clips:
        return 0
    i = install_scene_idx(script)
    if i is None or i >= len(scene_clips):
        return 0
    clips = scene_clips[i]
    sdur = None
    if scene_durs and i < len(scene_durs):
        try:
            sdur = float(scene_durs[i])
        except (TypeError, ValueError):
            sdur = None
    if not sdur or sdur <= 0:
        return 0
    replacing = bool(clips) and ("statcard" in str(clips[0])
                                 or "codecard" in str(clips[0]))
    share = sdur / len(clips) if replacing else sdur / (len(clips) + 1)
    clip = make_terminal_clip(result, str(fv.TEMP / "receiptcard.mp4"), share)
    if not clip:
        return 0
    if replacing:
        clips[0] = clip
    else:
        clips.insert(0, clip)
    print(f"  🧾 Receipts footage leads scene {i + 1} ({share:.1f}s)")
    return 1
