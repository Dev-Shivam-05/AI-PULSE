"""v3-P.1 evidence engine: what a tool video may SHOW, and what it may CLAIM.

spec docs/spec/ai-pulse-v3p1.md (review 2026-11-04, rows 3, 4, 17). Every tool
video used to be a scrolling README: nothing on screen ever showed the tool
working. This module finds functional evidence for a candidate and records it as
the shared `script["evidence"]` dict (docs/spec/ai-pulse-v3-growth.md):

  (a) hosted  — the tool's own Hugging Face Space, driven in a clean browser with
                the Space's OWN example input, recorded, inside a 120 s total
                capture deadline. Success needs an independent check that the
                declared output components changed; a page saying "success" is not
                success. Sleeping / queued / quota-limited = unavailable, never a
                fabricated result.
  (c) author  — demo media committed IN the repo and referenced by its README,
                under MIT or Apache-2.0, with a rights record (path, commit,
                licence, copyright, NOTICE, modification). Status NOT_RUN: the
                channel did not run the tool, and the writer is told so.
  (b) sandbox — NOT built. Its admission gates are in the spec as a later phase.

Preference: hosted first, then author. `probe` is cheap (README text + JSON APIs,
no browser, no media download) and is what other phases may call.

Every seam fails soft and SAYS what happened: `probe`/`gather` return None only
when they could not look at all; a dict with source "none" means "looked, found
nothing admissible". Playwright is imported inside the function that drives the
browser (CI's test job has no browser) — the screencap.py rule.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from factverse import config as fv

# ------------------------------------------------------------- the contract
SOURCES = ("hosted", "author", "sandbox", "none", "docs")
STATUSES = ("NOT_RUN", "PASSED_FIXED_TEST", "FAILED_FIXED_TEST", "TIMED_OUT", "INCONCLUSIVE")
# viewer wording, verbatim from review round 3 (03_chatgpt.md §1)
WORDING = {
    "NOT_RUN": "Not independently tested.",
    "PASSED_FIXED_TEST": "Passed this specific test.",
    "FAILED_FIXED_TEST": "This test failed under these conditions.",
    "TIMED_OUT": "Did not complete within our 120-second execution limit.",
    "INCONCLUSIVE": "We could not establish a result.",
}
LABELS = {"hosted": "Hosted test", "author": "Author demo", "sandbox": "Sandbox test", "none": "",
          # spec v3-R D4: the documentation route that replaced row 17's skip
          "docs": f"From the docs — not tested by {fv.CHANNEL_NAME}"}
# spec v3-R D4 (docs/spec/ai-pulse-v3r.md): while the recovery cohort is on, the
# on-screen labels are the owner's locked wording. Scoped to the cohort so the
# Live Trials show and the K.1 site keep the P.1 contract they were built on.
COHORT_LABELS = {"hosted": f"Tested by {fv.CHANNEL_NAME} — hosted demo",
                 "author": f"Author's demo — not tested by {fv.CHANNEL_NAME}",
                 "docs": LABELS["docs"]}

# ------------------------------------------------------------- locked values
CAPTURE_DEADLINE = 120.0            # round 3 §3(a): total hosted-demo capture deadline
CLIP_MIN, CLIP_MAX = 8.0, 20.0      # round 3 §1(c): one action-to-result sequence, 8-20 s
# round 3 §1(c) / owner: MIT and Apache-2.0 cover documentation media. Keys are
# lowercased SPDX ids (GitHub answers "MIT", the HF card "mit").
AUTHOR_LICENSES = {"mit": "MIT", "apache-2.0": "Apache-2.0"}

# ------------------------------------------------------------- delegated values (spec)
AUTHOR_MEDIA_EXT = (".gif", ".mp4", ".webm")    # stills are not an action-to-result sequence
STILL_EXT = (".png", ".jpg", ".jpeg", ".webp", ".svg", ".bmp", ".avif")
ASSET_MIN_SECONDS = 2.0             # shorter animated media is decoration, not a sequence
AUTHOR_FETCH_SECONDS = 60.0         # wall clock for one asset download (receipts FETCH_TIMEOUT)
AUTHOR_MAX_BYTES = 50 * 1024 * 1024 # round 3's 50 MiB artifact ceiling, reused for one asset
NOTICE_MAX_CHARS = 300              # a NOTICE longer than this cannot ride in one line
HTTP_TIMEOUT = 15
MAX_SPACES = 3                      # Spaces checked per candidate
DEMO_HINTS = ("demo", "hero", "preview", "showcase", "example", "usage", "overview",
              "screencast", "walkthrough", "teaser")
REC_W, REC_H = 1280, 720            # hosted recording viewport (UI text stays legible)
HEAD_PAD, TAIL_HOLD = 1.0, 2.5      # seconds kept before the example click / after the result
MAX_SPEEDUP = 4.0                   # most a hosted wait may be compressed to fit CLIP_MAX
SLOT_MAX_SPEED = 1.5                # most a clip may be sped up to fit its scene slot
SLOT_PAD = 0.5                      # screencap.TAIL_PAD: a clip a frame short gets looped
LABEL_PX = 40                       # >= round 3's 32 px source-label floor at 1080p
FPS = 30
BG = "0x0D1117"                     # the code-card background, for letterboxing

_UNAVAILABLE_RX = re.compile(
    r"quota|exceeded|zerogpu|log ?in|sign ?in|too many requests|rate limit|paused|"
    r"sleeping|is busy|unavailable|restarting|building|no gpu|gpu task aborted", re.I)
_RESULT_TYPES = {"image", "video", "audio", "textbox", "markdown", "html", "json", "gallery",
                 "chatbot", "label", "file", "model3d", "plot", "dataframe",
                 "highlightedtext", "annotatedimage", "imageslider", "code"}


# ============================================================ small pure helpers
def wording(status: str) -> str:
    return WORDING.get(str(status or ""), "")


def label(source: str) -> str:
    src = str(source or "")
    if src in COHORT_LABELS and fv.flag("recovery_cohort", False):
        return COHORT_LABELS[src]
    return LABELS.get(src, "")


def empty(note: str = "") -> dict:
    """The record for "looked, found nothing admissible". `note` is log-only."""
    ev = {"source": "none", "status": "NOT_RUN", "label": "", "wording": wording("NOT_RUN"),
          "clip": "", "clip_seconds": 0.0, "url": "", "captured_at": _dt.date.today().isoformat(),
          "input": "", "observed": "", "supported_claims": [], "rights": None,
          # optional (K.1 renders it): the hosted Space's git sha / the author repo commit
          "version": ""}
    if note:
        ev["note"] = str(note)[:200]
    return ev


def admissible(ev) -> bool:
    """Evidence a video may be built on: a hosted test that PASSED, or an author
    demo with a full rights record — and in both cases a clip on disk."""
    if not isinstance(ev, dict):
        return False
    clip = str(ev.get("clip") or "")
    if not clip or not Path(clip).exists():
        return False
    if ev.get("source") == "hosted":
        return ev.get("status") == "PASSED_FIXED_TEST"
    if ev.get("source") == "author":
        r = ev.get("rights")
        return (ev.get("status") == "NOT_RUN" and isinstance(r, dict)
                and all(r.get(k) for k in ("path", "commit", "license", "modified")))
    return False


def ledger_fields(script) -> tuple[str, str]:
    """(evidence_source, evidence_status) for the ledger, coerced. A script with
    no evidence dict (every non-tool lane) answers ("", "")."""
    ev = script.get("evidence") if isinstance(script, dict) else None
    if not isinstance(ev, dict):
        return "", ""
    src, st = str(ev.get("source") or ""), str(ev.get("status") or "")
    return (src if src in SOURCES else ""), (st if st in STATUSES else "")


def catalog_view(ev) -> dict | None:
    """The evidence dict without its local clip path (tools_index.json)."""
    if not isinstance(ev, dict):
        return None
    return {k: v for k, v in ev.items() if k in (
        "source", "status", "label", "wording", "clip_seconds", "url", "captured_at",
        "input", "observed", "supported_claims", "rights", "version")}


def _norm_spdx(x) -> str:
    return str(x or "").strip().lower()


def _basename(p: str) -> str:
    """Last path segment on EITHER separator (receipts._basename: pathlib's .name
    keeps a backslash path whole on the ubuntu runner)."""
    return re.split(r"[\\/]+", str(p).rstrip("\\/"))[-1]


# ============================================================ source identity
def repo_of(url: str):
    """("github", "owner/repo") | ("hf", "owner/name") | None for a tool URL."""
    u = str(url or "").strip()
    m = re.match(r"https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", u)
    if m:
        return "github", f"{m.group(1)}/{m.group(2)}"
    m = re.match(r"https?://huggingface\.co/([\w.-]+)/([\w.-]+)/?$", u)
    if m and m.group(1).lower() not in ("spaces", "datasets", "docs", "blog", "papers"):
        return "hf", f"{m.group(1)}/{m.group(2)}"
    return None


# ============================================================ README parsing (pure)
_MEDIA_REF = re.compile(
    r"""!\[(?P<alt>[^\]]*)\]\(\s*<?(?P<md>[^)\s>]+)>?(?:\s+["'][^"']*["'])?\s*\)"""
    r"""|<(?:img|video|source)\b[^>]*?\bsrc\s*=\s*["'](?P<html>[^"']+)["']"""
    r"""|(?P<bare>https?://[^\s<>()"']+)""", re.I)
_ALT_ATTR = re.compile(r"""\balt\s*=\s*["']([^"']*)["']""", re.I)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.M)


def _ext(path: str) -> str:
    p = urlparse(path).path if "://" in path else path
    p = p.split("?")[0].split("#")[0].lower()
    m = re.search(r"\.[a-z0-9]{2,5}$", p)
    return m.group(0) if m else ""


def resolve_asset(ref: str, kind: str, ident: str) -> tuple[str, str]:
    """(in-repo path, "") when `ref` resolves to a file committed in THIS repo,
    else ("", reason). Provenance that cannot be resolved to a committed file is
    rejected (round 3 §1(c)): GitHub's user-attachments / user-images uploads,
    release downloads, LFS media hosts and every external host."""
    r = str(ref or "").strip()
    low = r.lower()
    if not r:
        return "", "empty"
    if "github.com/user-attachments" in low or "user-images.githubusercontent.com" in low \
            or "private-user-images" in low:
        return "", "unresolved provenance (GitHub upload, not a committed file)"
    if "/releases/download/" in low:
        return "", "release asset (not committed in the repo)"
    own = ident.lower()
    path = ""
    if "://" not in r:
        if r.startswith("//") or r.startswith("data:"):
            return "", "external host"
        path = r.split("#")[0].split("?")[0]
        path = path.lstrip("/")
        while path.startswith("./"):
            path = path[2:]
    else:
        u = urlparse(r)
        host, parts = u.netloc.lower(), [p for p in u.path.split("/") if p]
        if kind == "github" and host == "raw.githubusercontent.com" and len(parts) >= 4 \
                and f"{parts[0]}/{parts[1]}".lower() == own:
            path = "/".join(parts[3:])
        elif kind == "github" and host in ("github.com", "www.github.com") and len(parts) >= 5 \
                and f"{parts[0]}/{parts[1]}".lower() == own and parts[2] in ("raw", "blob"):
            path = "/".join(parts[4:])
        elif kind == "hf" and host == "huggingface.co" and len(parts) >= 5 \
                and f"{parts[0]}/{parts[1]}".lower() == own and parts[2] in ("resolve", "raw", "blob"):
            path = "/".join(parts[4:])
        else:
            return "", "external host"
    path = re.sub(r"%20", " ", path)
    if not path or ".." in path.split("/") or "\\" in path:
        return "", "unsafe path"
    return path, ""


def readme_media(text: str, kind: str, ident: str) -> tuple[list[dict], list[dict]]:
    """(accepted, rejected) demo-media references in README order. Accepted =
    animated media (AUTHOR_MEDIA_EXT) resolving to a committed in-repo path; each
    carries its alt text and nearest preceding heading (what the README says the
    demo shows — the writer may describe only that). Stills are rejected with
    their reason, so the probe can report them. PURE."""
    text = str(text or "")
    heads = [(m.start(), m.group(1).strip()) for m in _HEADING.finditer(text)]
    accepted, rejected, seen = [], [], set()
    for m in _MEDIA_REF.finditer(text):
        ref = m.group("md") or m.group("html") or m.group("bare") or ""
        ref = ref.strip().rstrip(".,;")
        ext = _ext(ref)
        if ext not in AUTHOR_MEDIA_EXT and ext not in STILL_EXT:
            # a bare link to a non-media page, or a user-attachments asset with no
            # extension (GitHub's own video embeds look exactly like that)
            low = ref.lower()
            if "user-attachments/assets" in low or "user-images.githubusercontent" in low:
                if ref not in seen:
                    seen.add(ref)
                    rejected.append({"ref": ref[:200], "why": "unresolved provenance "
                                     "(GitHub upload, not a committed file)"})
            continue
        if ref in seen:
            continue
        seen.add(ref)
        if ext in STILL_EXT:
            rejected.append({"ref": ref[:200], "why": "still image"})
            continue
        path, why = resolve_asset(ref, kind, ident)
        if not path:
            rejected.append({"ref": ref[:200], "why": why})
            continue
        alt = m.group("alt") or ""
        if not alt and m.group("html"):
            tag_start = text.rfind("<", 0, m.start("html"))
            tag_end = text.find(">", m.start("html"))
            am = _ALT_ATTR.search(text[tag_start:tag_end + 1]) if tag_start >= 0 else None
            alt = am.group(1) if am else ""
        heading = ""
        for at, h in heads:
            if at < m.start():
                heading = h
        accepted.append({"path": path, "ext": ext, "alt": re.sub(r"\s+", " ", alt).strip()[:120],
                         "heading": re.sub(r"[*_`]", "", heading)[:120], "ref": ref[:300]})
    return accepted, rejected


def pick_media(accepted: list[dict]) -> list[dict]:
    """Order accepted media: a name or alt that says demo/hero/preview first, then
    video containers before GIF, then README order. PURE and stable."""
    def score(i_m):
        i, m = i_m
        blob = f"{m.get('path', '')} {m.get('alt', '')}".lower()
        return (0 if any(h in blob for h in DEMO_HINTS) else 1,
                0 if m.get("ext") in (".mp4", ".webm") else 1, i)
    return [m for _i, m in sorted(enumerate(accepted), key=score)]


_SPACE_RX = re.compile(r"https?://(?:huggingface\.co/spaces/([\w.-]+/[\w.-]+)|([\w-]+)\.hf\.space)",
                       re.I)


def readme_spaces(text: str) -> list[str]:
    """Hosted demos the README links: Space ids ("owner/name") or bare hf.space
    hosts ("sub.hf.space"), first-seen order, deduplicated. PURE."""
    out = []
    for m in _SPACE_RX.finditer(str(text or "")):
        sid = m.group(1) or f"{m.group(2).lower()}.hf.space"
        sid = sid.rstrip(".")
        if sid not in out:
            out.append(sid)
    return out


_CR_TEMPLATE = re.compile(r"\[yyyy\]|\{yyyy\}|\[name of copyright owner\]|<year>|<copyright", re.I)


def copyright_line(text: str) -> str:
    """The first real "Copyright …" line of a licence/NOTICE text, or "". The
    Apache appendix template ("Copyright [yyyy] [name of copyright owner]") is not
    a notice. PURE."""
    for line in str(text or "").splitlines():
        s = line.strip().strip("#*> ").strip()
        if re.match(r"(?i)^(copyright\b|\(c\)|©)", s) and not _CR_TEMPLATE.search(s):
            if re.search(r"\d{4}|\(c\)|©", s, re.I):
                return re.sub(r"\s+", " ", s)[:200]
    return ""


# ============================================================ network seams
TEXT_FETCH_SECONDS = 30.0          # wall clock for one README / JSON / /config fetch
TEXT_MAX_BYTES = 5 * 1024 * 1024   # and its byte cap


class _Fetched:
    """The slice of a requests.Response the readers use, built from a bounded read."""

    def __init__(self, status_code: int, body: bytes, encoding: str | None):
        self.status_code = status_code
        self._body = body
        self.text = body.decode(encoding or "utf-8", errors="replace")

    def json(self):
        return json.loads(self.text)


def _http_get(url: str, **kw):
    """A bounded GET, or None. requests' `timeout` is a per-read gap, never a
    deadline (CLAUDE.md): a Space's own server answers /config, and a slow drip
    would hold the unattended run. So the body is streamed under a wall clock and
    a byte cap. The seam tests stub as `ev._http_get`."""
    try:
        import requests
        h = dict(kw.pop("headers", None) or {})
        h.setdefault("User-Agent", "Mozilla/5.0 ToolDojo-evidence")
        deadline = time.monotonic() + TEXT_FETCH_SECONDS
        with requests.get(url, headers=h, params=kw.get("params"), stream=True,
                          timeout=kw.get("timeout", HTTP_TIMEOUT)) as r:
            buf = bytearray()
            for chunk in r.iter_content(1 << 16):
                buf += chunk
                if len(buf) > TEXT_MAX_BYTES or time.monotonic() > deadline:
                    return None
            return _Fetched(r.status_code, bytes(buf), r.encoding)
    except Exception:
        return None


def _gh_headers(raw: bool = False) -> dict:
    import os
    h = {"Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json"}
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _json(url: str, headers: dict | None = None, params: dict | None = None):
    r = _http_get(url, headers=headers, params=params)
    if r is None or getattr(r, "status_code", 0) != 200:
        return None
    try:
        return r.json()
    except Exception:
        return None


def _text(url: str, headers: dict | None = None, max_chars: int = 200_000) -> str:
    r = _http_get(url, headers=headers)
    if r is None or getattr(r, "status_code", 0) != 200:
        return ""
    try:
        return str(r.text or "")[:max_chars]
    except Exception:
        return ""


def _readme_raw(kind: str, ident: str) -> str:
    """The README as RAW markdown — fetch_text strips tags, and the media live in
    <img>/<video> tags."""
    if kind == "github":
        t = _text(f"https://raw.githubusercontent.com/{ident}/HEAD/README.md")
        if not t:
            t = _text(f"https://api.github.com/repos/{ident}/readme", headers=_gh_headers(raw=True))
        return t
    return _text(f"https://huggingface.co/{ident}/raw/main/README.md")


def _space_info(sid: str) -> dict | None:
    """{"id","host","sdk","stage"} for a Space id or an hf.space host, or None."""
    if sid.endswith(".hf.space"):
        # a bare host has no id to ask the API about; it is checked by /config later
        return {"id": "", "host": f"https://{sid}", "sdk": "", "stage": "UNKNOWN"}
    d = _json(f"https://huggingface.co/api/spaces/{sid}")
    if not isinstance(d, dict):
        return None
    host = str(d.get("host") or "")
    if not host and d.get("subdomain"):
        host = f"https://{d['subdomain']}.hf.space"
    return {"id": sid, "host": host, "sdk": str(d.get("sdk") or ""),
            "stage": str((d.get("runtime") or {}).get("stage") or ""),
            "sha": str(d.get("sha") or "")}


def _space_ok(info: dict) -> bool:
    """Could this Space be driven now? Gradio (or a docker Space, which may serve
    Gradio — /config decides), not sleeping/paused/broken."""
    if not info or not str(info.get("host", "")).startswith("https://"):
        return False
    if info.get("stage") == "UNKNOWN":
        return True
    return info.get("stage") == "RUNNING" and info.get("sdk") in ("gradio", "docker")


# ============================================================ probe (cheap)
def probe(item: dict, readme: str | None = None) -> dict | None:
    """Which evidence source COULD exist for a candidate — no browser, no media
    download. Returns {"source": "hosted"|"author"|"none", "kind", "ident",
    "hosted": [space info], "author": [media], "rejected": [...], "license",
    "license_ok", "branch", "sha", "readme"} or None when it could not look (bad
    item, README unreachable). Never raises; v3-M.1 calls it inside a try."""
    try:
        if not isinstance(item, dict):
            return None
        rid = repo_of(item.get("url", ""))
        if not rid:
            return None
        kind, ident = rid
        # `readme` must be RAW markdown: ai_pipeline.fetch_text strips tags, and the
        # <img>/<video> tags are where most demo media live — callers pass None
        text = readme if (isinstance(readme, str) and readme.strip()) else _readme_raw(kind, ident)
        if not text:
            return None
        lic, branch, sha, extra_spaces = "", "", "", []
        if kind == "github":
            d = _json(f"https://api.github.com/repos/{ident}", headers=_gh_headers())
            if isinstance(d, dict):
                lic = str((d.get("license") or {}).get("spdx_id") or "")
                branch = str(d.get("default_branch") or "")
        else:
            d = _json(f"https://huggingface.co/api/models/{ident}")
            if isinstance(d, dict):
                card = d.get("cardData") if isinstance(d.get("cardData"), dict) else {}
                lic = str(card.get("license") or "")
                sha = str(d.get("sha") or "")
                owner = ident.split("/")[0].lower()
                # Spaces that use this model AND belong to its owner: the author's
                # own hosted demo even when the card does not link it
                extra_spaces = [s for s in (d.get("spaces") or [])
                                if isinstance(s, str) and s.split("/")[0].lower() == owner]
        accepted, rejected = readme_media(text, kind, ident)
        accepted = pick_media(accepted)
        hosted = []
        for sid in (readme_spaces(text) + extra_spaces):
            if len(hosted) >= MAX_SPACES:
                break
            if any(h.get("id") == sid for h in hosted):
                continue
            info = _space_info(sid)
            if info:
                hosted.append(info)
        lic_ok = _norm_spdx(lic) in AUTHOR_LICENSES
        source = ("hosted" if any(_space_ok(h) for h in hosted)
                  else "author" if (accepted and lic_ok) else "none")
        return {"source": source, "kind": kind, "ident": ident, "hosted": hosted,
                "author": accepted, "rejected": rejected, "license": lic,
                "license_ok": lic_ok, "branch": branch, "sha": sha, "readme": text}
    except Exception as e:
        print(f"     ⚠️ evidence probe failed ({type(e).__name__}: {e})")
        return None


# ============================================================ (c) author demo
def bounded_download(url: str, dest: Path, max_bytes: int = AUTHOR_MAX_BYTES,
                     seconds: float = AUTHOR_FETCH_SECONDS) -> int | None:
    """Stream `url` to `dest` under a WALL-CLOCK deadline and a byte cap (requests'
    timeout is a per-read gap, never a deadline — receipts.py). Bytes or None."""
    try:
        import requests
        deadline = time.monotonic() + seconds
        got = 0
        with requests.get(url, stream=True, timeout=HTTP_TIMEOUT,
                          headers={"User-Agent": "Mozilla/5.0 ToolDojo-evidence"}) as r:
            if r.status_code != 200:
                return None
            cl = r.headers.get("content-length")
            if cl and cl.isdigit() and int(cl) > max_bytes:
                return None
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    got += len(chunk)
                    if time.monotonic() > deadline or got > max_bytes:
                        f.close()
                        dest.unlink(missing_ok=True)
                        return None
                    f.write(chunk)
        return got if got > 0 else None
    except Exception:
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        return None


def _ffprobe_seconds(path: str) -> float:
    """Media duration in seconds, 0.0 when it is not decodable video. A GIF's
    container duration is what ffmpeg will play once (the demuxer ignores loops)."""
    try:
        r = subprocess.run([fv.FFPROBE or "ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=codec_type:format=duration",
                            "-of", "json", path], capture_output=True, text=True, timeout=60)
        d = json.loads(r.stdout or "{}")
        if not any(s.get("codec_type") == "video" for s in d.get("streams", [])):
            return 0.0
        return float((d.get("format") or {}).get("duration") or 0.0)
    except Exception:
        return 0.0


def _ffmpeg(args: list[str], timeout: int = 300) -> bool:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).returncode == 0
    except Exception as e:
        print(f"     ⚠️ ffmpeg step failed: {e}")
        return False


def _canvas_vf(hold: float, speed: float = 1.0) -> str:
    sp = f"setpts={1.0 / speed:.6f}*(PTS-STARTPTS)," if speed != 1.0 else "setpts=PTS-STARTPTS,"
    return (f"{sp}fps={FPS},scale={fv.VIDEO_W}:{fv.VIDEO_H}:force_original_aspect_ratio=decrease:"
            f"flags=lanczos,pad={fv.VIDEO_W}:{fv.VIDEO_H}:(ow-iw)/2:(oh-ih)/2:color={BG},"
            f"setsar=1,format=yuv420p,tpad=stop_mode=clone:stop_duration={max(0.0, hold):.3f}")


def master_args(src: str, dst: str, start: float, length: float, speed: float = 1.0) -> list[str]:
    """PURE: the evidence master clip — [start, start+length) of `src`, sped up by
    `speed`, letterboxed onto the 1920x1080 canvas, held on its last frame up to
    CLIP_MIN. Output = max(CLIP_MIN, length/speed) seconds."""
    shown = length / speed
    hold = max(0.0, CLIP_MIN - shown)
    return [fv.FFMPEG or "ffmpeg", "-y", "-ss", f"{max(0.0, start):.3f}", "-t", f"{length:.3f}",
            "-i", src, "-vf", _canvas_vf(hold, speed), "-t", f"{shown + hold:.3f}", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", dst]


AUTHOR_MAX_SPEED = 2.0   # an asset up to 2x CLIP_MAX is shown WHOLE, sped up (disclosed)


def author_plan(asset_seconds: float) -> dict | None:
    """PURE: which span of an author asset becomes the clip. An asset up to
    CLIP_MAX plays whole at 1x; up to AUTHOR_MAX_SPEED x CLIP_MAX it plays whole,
    sped up to CLIP_MAX (the sequence stays complete); anything longer is its
    first CLIP_MAX seconds at 1x (a known limit: may stop mid-action)."""
    try:
        d = float(asset_seconds)
    except (TypeError, ValueError):
        return None
    if not d == d or d < ASSET_MIN_SECONDS:          # NaN or decoration
        return None
    if d <= CLIP_MAX:
        length, speed = d, 1.0
    elif d <= CLIP_MAX * AUTHOR_MAX_SPEED:
        length, speed = d, d / CLIP_MAX
    else:
        length, speed = CLIP_MAX, 1.0
    shown = length / speed
    return {"start": 0.0, "length": round(length, 3), "speed": round(speed, 4),
            "seconds": round(max(CLIP_MIN, shown), 3), "whole": d <= CLIP_MAX * AUTHOR_MAX_SPEED}


def modification(plan: dict, asset_seconds: float) -> str:
    """PURE: the modification disclosure for the rights record (Apache-2.0 §4(b)
    asks modified files to say so; we say it for MIT too)."""
    what = []
    if not plan.get("whole"):
        what.append(f"first {plan['length']:.1f} s of {float(asset_seconds):.1f} s used")
    if plan.get("speed", 1.0) > 1.0:
        what.append(f"sped up {plan['speed']:.2f}x")
    if plan["seconds"] > plan["length"] / plan.get("speed", 1.0) + 0.05:
        what.append("last frame held")
    what.append(f"scaled to {fv.VIDEO_W}x{fv.VIDEO_H} and re-encoded")
    return (f"Modified by {fv.CHANNEL_NAME}: " + ", ".join(what)
            + "; a source label is shown over it.")


def attribution_line(ev) -> str:
    """The ONE description line an author demo must carry: pinned asset link,
    licence, copyright notice, NOTICE material, modification disclosure. "" for
    anything that is not an admissible-shaped author record. PURE.
    v3-R D4: a docs-route video carries its label as one line too."""
    if isinstance(ev, dict) and ev.get("source") == "docs":
        return (f"{DOCS_MARK} {LABELS['docs']}. Features and figures in this video are the "
                f"project's own claims.")
    if not isinstance(ev, dict) or ev.get("source") != "author":
        return ""
    r = ev.get("rights")
    if not isinstance(r, dict) or not r.get("license"):
        return ""
    parts = [f"{AUTHOR_MARK} {ev.get('url') or r.get('path', '')}", f"{r['license']} License"]
    if r.get("copyright"):
        parts.append(str(r["copyright"]))
    if r.get("notice"):
        parts.append(f"NOTICE: {r['notice']}")
    parts.append(str(r.get("modified") or ""))
    return " — ".join(p for p in parts if p).strip()


AUTHOR_MARK = "🎞️ Author demo footage:"


def _license_material(kind: str, ident: str, sha: str, spdx: str) -> tuple[str, str] | None:
    """(copyright, notice) at the pinned commit, or None when the provenance is
    unresolved: MIT needs its copyright notice found, and a NOTICE file longer than
    NOTICE_MAX_CHARS cannot be carried in one attribution line."""
    if kind == "github":
        lic = _json(f"https://api.github.com/repos/{ident}/license", headers=_gh_headers())
        lpath = str((lic or {}).get("path") or "LICENSE")
        ltext = _text(f"https://raw.githubusercontent.com/{ident}/{sha}/{lpath}")
        base = f"https://raw.githubusercontent.com/{ident}/{sha}/"
    else:
        base = f"https://huggingface.co/{ident}/raw/{sha}/"
        ltext = ""
        for name in ("LICENSE", "LICENSE.md", "LICENSE.txt"):
            ltext = _text(base + name)
            if ltext:
                break
    notice_text = ""
    for name in ("NOTICE", "NOTICE.md", "NOTICE.txt"):
        notice_text = _text(base + name)
        if notice_text:
            break
    notice = re.sub(r"\s+", " ", notice_text).strip()
    if len(notice) > NOTICE_MAX_CHARS:
        print(f"     ↻ author demo: NOTICE is {len(notice)} chars (> {NOTICE_MAX_CHARS}) — "
              f"cannot carry it in one line.")
        return None
    cr = copyright_line(notice_text) or copyright_line(ltext)
    if AUTHOR_LICENSES.get(_norm_spdx(spdx)) == "MIT" and not cr:
        print("     ↻ author demo: MIT licence with no copyright notice found — unresolved.")
        return None
    return cr, notice


def _pinned_sha(pr: dict) -> str:
    if pr.get("sha"):
        return str(pr["sha"])
    if pr.get("kind") != "github":
        return ""
    r = _http_get(f"https://api.github.com/repos/{pr['ident']}/commits/{pr.get('branch') or 'HEAD'}",
                  headers=dict(_gh_headers(), Accept="application/vnd.github.sha"))
    if r is None or getattr(r, "status_code", 0) != 200:
        return ""
    sha = str(r.text or "").strip()
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else ""


def try_author(pr: dict, out_dir: Path) -> dict | None:
    """The first README demo asset that downloads under the caps, decodes as video
    of at least ASSET_MIN_SECONDS and carries a resolved rights record → an author
    evidence dict with its master clip. None when no asset qualifies."""
    spdx = AUTHOR_LICENSES.get(_norm_spdx(pr.get("license")))
    if not spdx or not pr.get("author"):
        return None
    sha = _pinned_sha(pr)
    if not sha:
        print("     ↻ author demo: could not pin a commit — unresolved provenance.")
        return None
    material = _license_material(pr["kind"], pr["ident"], sha, spdx)
    if material is None:
        return None
    copyright_, notice = material
    for k, m in enumerate(pr["author"][:4]):
        path = m["path"]
        if pr["kind"] == "github":
            raw = f"https://raw.githubusercontent.com/{pr['ident']}/{sha}/{path}"
            public = f"https://github.com/{pr['ident']}/blob/{sha}/{path}"
        else:
            raw = f"https://huggingface.co/{pr['ident']}/resolve/{sha}/{path}"
            public = f"https://huggingface.co/{pr['ident']}/blob/{sha}/{path}"
        # an untrusted download lives in its own empty directory
        dl_dir = out_dir / f"asset_{k}"
        shutil.rmtree(dl_dir, ignore_errors=True)
        dl_dir.mkdir(parents=True, exist_ok=True)
        src = dl_dir / ("asset" + m["ext"])
        nbytes = bounded_download(raw, src)
        if not nbytes:
            print(f"     ↻ author demo {_basename(path)}: download failed or over the caps.")
            continue
        secs = _ffprobe_seconds(str(src))
        plan = author_plan(secs)
        if not plan:
            print(f"     ↻ author demo {_basename(path)}: {secs:.1f}s is not a sequence.")
            continue
        clip = str(out_dir / "evidence_author.mp4")
        if not (_ffmpeg(master_args(str(src), clip, plan["start"], plan["length"], plan["speed"]))
                and Path(clip).exists() and Path(clip).stat().st_size > 1000):
            continue
        what = m.get("alt") or ""
        where = m.get("heading") or ""
        observed = ("The README presents this demo"
                    + (f' as "{what}"' if what else "")
                    + (f' under "{where}"' if where else "") + ".")
        ev = empty()
        ev.update({
            "source": "author", "status": "NOT_RUN", "label": label("author"),
            "wording": wording("NOT_RUN"), "clip": clip, "clip_seconds": plan["seconds"],
            "url": public, "observed": observed, "version": sha,
            "rights": {"path": path, "commit": sha, "license": spdx, "copyright": copyright_,
                       "notice": notice,
                       "modified": modification(plan, secs)},
        })
        print(f"     🎞️ Author demo: {path} @ {sha[:7]} ({spdx}, {nbytes / 1e6:.1f} MB, "
              f"{secs:.1f}s → {plan['seconds']:.1f}s clip)")
        return ev
    return None


# ============================================================ (a) hosted demo
_ORDINAL = ("first", "second")


def _sample_text(samples, k: int) -> str:
    """PURE: the viewer-facing description of example k (file names, never paths)."""
    if not isinstance(samples, (list, tuple)):
        return f"the {_ORDINAL[k]} example in the Space's own example gallery"
    if k >= len(samples):
        return ""
    sample = samples[k]
    bits = []
    for v in (sample if isinstance(sample, (list, tuple)) else [sample]):
        if isinstance(v, dict):
            v = v.get("orig_name") or v.get("path") or v.get("url") or ""
            v = _basename(str(v)) if v else ""
        if isinstance(v, str) and v.strip():
            bits.append(v.strip()[:80])
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            bits.append(str(v))
    head = f"the Space's {_ORDINAL[k]} example"
    return (head + ": " + "; ".join(bits) if bits else head)[:240]


def gradio_plan(cfg) -> dict | None:
    """PURE: from a Gradio /config, the fixed-input plan — the example to click
    (the Space's OWN examples: a gr.Examples dataset, or a gallery whose select
    event fills the inputs), the primary button, and the declared output
    components the independent check watches. None = not drivable with a fixed
    input (no examples, no button, no result outputs)."""
    if not isinstance(cfg, dict):
        return None
    comps = {c.get("id"): c for c in (cfg.get("components") or []) if isinstance(c, dict)}
    deps = [d for d in (cfg.get("dependencies") or []) if isinstance(d, dict)]

    def sel(cid):
        c = comps.get(cid) or {}
        eid = str((c.get("props") or {}).get("elem_id") or "")
        return f"#{eid}" if re.fullmatch(r"[A-Za-z][\w-]*", eid) else f"#component-{cid}"

    def targets(d):
        out = []
        for t in d.get("targets") or []:
            if isinstance(t, (list, tuple)) and len(t) == 2:
                out.append((t[0], t[1]))
        return out

    # example sources: component id -> the inputs its click/select fills
    examples = []
    for d in deps:
        for cid, ev in targets(d):
            c = comps.get(cid) or {}
            props = c.get("props") or {}
            if c.get("type") == "dataset" and ev in ("click", "select") and props.get("samples"):
                examples.append({"id": cid, "type": "dataset", "fills": set(d.get("outputs") or []),
                                 "samples": list(props["samples"][:2])})
            elif c.get("type") == "gallery" and ev == "select" and d.get("outputs"):
                examples.append({"id": cid, "type": "gallery", "fills": set(d.get("outputs") or []),
                                 "samples": None})
    best = None
    for d in deps:
        for cid, ev in targets(d):
            c = comps.get(cid) or {}
            if c.get("type") != "button" or ev != "click":
                continue
            outs = [o for o in (d.get("outputs") or []) if (comps.get(o) or {}).get("type") in _RESULT_TYPES]
            ins = set(d.get("inputs") or [])
            if not outs or not ins:
                continue
            ex = next((e for e in examples if e["fills"] & ins), None)
            if not ex:
                continue
            rank = (0 if (c.get("props") or {}).get("variant") == "primary" else 1, cid)
            if best is None or rank < best[0]:
                best = (rank, cid, d, ex, outs)
    if not best:
        return None
    _rank, bid, dep, ex, outs = best
    inputs = [_sample_text(ex["samples"], 0), _sample_text(ex["samples"], 1)]
    def lab(cid):
        return str(((comps.get(cid) or {}).get("props") or {}).get("label") or "").strip()[:80]
    return {"button": sel(bid),
            "button_text": str(((comps.get(bid) or {}).get("props") or {}).get("value") or "").strip()[:60],
            "example": sel(ex["id"]), "example_type": ex["type"],
            "outputs": [sel(o) for o in outs], "output_labels": [lab(o) for o in outs],
            "output_types": [str((comps.get(o) or {}).get("type")) for o in outs],
            "input": inputs[0], "inputs": inputs, "api_prefix": str(cfg.get("api_prefix") or "")}


def classify(outcome: dict) -> str | None:
    """PURE: raw drive outcome → a status, or None for UNAVAILABLE evidence
    (sleeping, queued at the deadline, quota/log-in walls). Round 3: such a demo
    is unavailable evidence, never a fabricated result."""
    o = outcome if isinstance(outcome, dict) else {}
    if o.get("unavailable"):
        return None
    err = str(o.get("error") or "")
    if err:
        return None if _UNAVAILABLE_RX.search(err) else "FAILED_FIXED_TEST"
    if o.get("changed") and o.get("nonempty") and not o.get("pending"):
        # the DOM says the run finished; the pixels/text must agree, or we cannot
        # say what the viewer would see
        return "PASSED_FIXED_TEST" if o.get("visible") else "INCONCLUSIVE"
    if o.get("deadline"):
        return None if o.get("queued") else "TIMED_OUT"
    return "INCONCLUSIVE"


# the signature of the declared output components: what the independent check
# compares before and after the run. Status-tracker text, labels and timers are
# removed first — "processing | 3.2s" changes every frame and is not output.
_SIG_JS = r"""(els) => {
  const strip = '.wrap, .eta-bar, .progress-text, .progress-level, .timer, .meta-text, '
              + '.meta-text-center, [data-testid="status-tracker"], [data-testid="block-info"], '
              + 'label, .label-wrap, .icon-button-wrapper, .icon-buttons, svg';
  let sig = [], nonempty = false, pending = false, error = '';
  for (const el of els) {
    if (!el) { sig.push('?'); continue; }
    if (el.querySelector('.eta-bar, .progress-text, .progress-level, .generating, .pending'))
      pending = true;
    const e = el.querySelector('.error');
    if (e && e.innerText) error = error || e.innerText.slice(0, 200);
    const media = [];
    el.querySelectorAll('img[src], video[src], video source[src], audio[src], a[href]')
      .forEach(m => { const v = m.getAttribute('src') || m.getAttribute('href') || '';
                      if (v && !v.startsWith('data:image/svg')) media.push(v.slice(0, 300)); });
    const vals = [];
    el.querySelectorAll('textarea, input[type=text]').forEach(t => { if (t.value) vals.push(t.value.slice(0, 2000)); });
    const c = el.cloneNode(true);
    c.querySelectorAll(strip).forEach(x => x.remove());
    const txt = (c.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 2000);
    if (media.length || vals.length || txt) nonempty = true;
    sig.push(JSON.stringify([media, vals, txt]));
  }
  let toast = '';
  document.querySelectorAll('.toast-body').forEach(t => {
    const s = (t.innerText || '').trim();
    if (t.classList.contains('error') || /error/i.test(s)) toast = toast || s.slice(0, 200); });
  const body = document.body ? document.body.innerText : '';
  const q = /queue:\s*\d+\s*\/\s*\d+/i.test(body);
  let text = '';
  for (const el of els) {
    if (el) { el.querySelectorAll('textarea').forEach(t => { if (!text && t.value) text = t.value; });
              if (!text) { const c = el.cloneNode(true); c.querySelectorAll(strip).forEach(x => x.remove());
                           text = (c.innerText || '').replace(/\s+/g, ' ').trim(); } } }
  return {sig: sig.join('|'), nonempty, pending, error: toast || error, queued: q,
          text: text.slice(0, 300)};
}"""


_VISUAL = ("image", "video", "model3d", "gallery", "plot", "annotatedimage", "imageslider",
           "audio")
PIXEL_DIFF_MIN = 2.0      # mean abs RGB difference (0-255) the result region must change by
PIXEL_STD_MIN = 8.0       # and its post-run stdev: a uniform (blank) region is not a result


def result_slot(plan: dict) -> int:
    """PURE: index of the output the clip frames and the pixel check reads — the
    first visual output, else the first one."""
    types = plan.get("output_types") or []
    return next((i for i, t in enumerate(types) if t in _VISUAL), 0)


def pixel_change(before: bytes | None, after: bytes | None) -> tuple[float, float]:
    """(mean abs difference, post stdev) of two PNG screenshots of the same region;
    (0, 0) when either is missing or unreadable."""
    try:
        import io
        from PIL import Image, ImageChops, ImageStat
        a = Image.open(io.BytesIO(after)).convert("RGB")
        st = sum(ImageStat.Stat(a).stddev) / 3.0
        if not before:
            return 255.0, st
        b = Image.open(io.BytesIO(before)).convert("RGB")
        if b.size != a.size:
            b = b.resize(a.size)
        diff = sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3.0
        return diff, st
    except Exception:
        return 0.0, 0.0


def visible_result(otype: str, before: bytes | None, after: bytes | None, text: str = "") -> bool:
    """A visual result must change the region's pixels AND not be blank; a text
    result must be non-empty text."""
    if otype in _VISUAL:
        diff, st = pixel_change(before, after)
        return diff >= PIXEL_DIFF_MIN and st >= PIXEL_STD_MIN
    return bool(str(text or "").strip())


def _shot(locator) -> bytes | None:
    try:
        return locator.screenshot(timeout=5000, animations="disabled")
    except Exception:
        return None


def _center(locator) -> None:
    try:
        locator.evaluate("el => el.scrollIntoView({block: 'center', inline: 'nearest'})")
    except Exception:
        pass


_EXAMPLE_ITEMS = "button.gallery-item, tr.tr-body, .gallery-item, button.thumbnail-item, .thumbnail-item"


def _button_locator(page, plan: dict):
    """The primary button: its DOM id (Gradio 4/5 render `component-<id>`) or, for
    Gradio 6 which renders no ids, its own label text as a button role."""
    loc = page.locator(plan["button"])
    if plan.get("button_text"):
        loc = loc.or_(page.get_by_role("button", name=plan["button_text"], exact=True))
    return loc.first


def _example_locator(page, plan: dict, nth: int = 0):
    loc = page.locator(f"{plan['example']} :is({_EXAMPLE_ITEMS})")
    if loc.count():
        return loc.nth(nth)
    return page.locator(_EXAMPLE_ITEMS).nth(nth)


def _output_locator(page, plan: dict, k: int):
    """An output component: its DOM id, else (Gradio 6) the block carrying its label."""
    loc = page.locator(plan["outputs"][k])
    labels = plan.get("output_labels") or []
    lab = labels[k] if k < len(labels) else ""
    if lab:
        loc = loc.or_(page.locator(".block").filter(has=page.get_by_text(lab, exact=True)))
    return loc.first


def _drive(host: str, plan: dict, out_dir: Path, deadline: float) -> dict:
    """Drive one Gradio Space with its own example and record it. Returns the raw
    outcome for `classify` plus the recording and its time marks. Never raises."""
    from playwright.sync_api import sync_playwright

    o = {"recording": "", "t_input": 0.0, "t_done": 0.0}
    rec_dir = out_dir / "rec"
    shutil.rmtree(rec_dir, ignore_errors=True)
    rec_dir.mkdir(parents=True, exist_ok=True)

    def left_ms():
        return max(1, int((deadline - time.monotonic()) * 1000))

    try:
        with sync_playwright() as p:
            # software WebGL, so a 3D / canvas result can render on a GPU-less runner
            browser = p.chromium.launch(headless=True, args=["--enable-unsafe-swiftshader",
                                                             "--use-angle=swiftshader"])
            # a CLEAN context: no storage, no cookies, no log-in — what any viewer gets
            ctx = browser.new_context(viewport={"width": REC_W, "height": REC_H},
                                      record_video_dir=str(rec_dir),
                                      record_video_size={"width": REC_W, "height": REC_H},
                                      color_scheme="light")
            page = ctx.new_page()
            t_page = time.monotonic()
            try:
                resp = page.goto(host, wait_until="domcontentloaded", timeout=left_ms())
                if resp is not None and resp.status >= 400:
                    o["unavailable"] = True
                    raise RuntimeError(f"HTTP {resp.status}")
                btn = _button_locator(page, plan)
                btn.wait_for(state="visible", timeout=left_ms())
                item = _example_locator(page, plan)
                item.wait_for(state="visible", timeout=left_ms())
                page.wait_for_timeout(1200)          # the page settles: real content, kept
                outs = [_output_locator(page, plan, k) for k in range(len(plan["outputs"]))]
                handles = []
                for loc in outs:
                    try:
                        handles.append(loc.element_handle(timeout=3000))
                    except Exception:
                        handles.append(None)
                k_res = result_slot(plan)
                if handles[k_res] is None:
                    raise RuntimeError("result component not found on the page")
                region = outs[k_res]
                # the pixel baseline is the page as it LOADED, before the example:
                # a cached example fills the output on click, and a baseline taken
                # after it would make our own run look like "no change"
                shot0 = _shot(region)
                if (shot0 and pixel_change(None, shot0)[1] >= PIXEL_STD_MIN
                        and (plan.get("inputs") or ["", ""])[1]):
                    # the Space pre-loads a result (its first example's): run the
                    # SECOND example, or the result could never visibly change
                    second = _example_locator(page, plan, nth=1)
                    if second.count():
                        item, o["example_index"] = second, 1
                item.scroll_into_view_if_needed(timeout=left_ms())
                o["t_input"] = time.monotonic() - t_page
                item.click(timeout=left_ms())
                page.wait_for_timeout(1500)          # the example fills the inputs
                before = page.evaluate(_SIG_JS, handles)
                btn.click(timeout=left_ms())
                o["submitted"] = True
                shot_mid = None
                # the click scrolls to the button; the RESULT must be in frame
                _center(region)
                seen_pending = False
                while True:
                    if time.monotonic() >= deadline:
                        o["deadline"] = True
                        break
                    page.wait_for_timeout(250)
                    s = page.evaluate(_SIG_JS, handles)
                    if s["pending"] and not seen_pending:
                        # the in-progress region is the baseline the result must
                        # differ from: a Space that pre-loads its first example's
                        # output looks identical before and after (measured live)
                        shot_mid = _shot(region)
                    seen_pending = seen_pending or s["pending"]
                    o.update(pending=s["pending"], queued=s["queued"], nonempty=s["nonempty"],
                             text=s["text"])
                    if s["error"]:
                        # the output's own badge says only "Error"; the toast with
                        # the reason (a quota wall vs a real failure) lands a beat later
                        page.wait_for_timeout(1000)
                        s2 = page.evaluate(_SIG_JS, handles)
                        o["error"] = s2["error"] or s["error"]
                        break
                    changed = s["sig"] != before["sig"]
                    if s["nonempty"] and not s["pending"] and (changed or seen_pending):
                        # identical output after a run we watched happen (a cached
                        # example re-computed) is still a completed run
                        o["changed"] = True
                        break
                o["t_done"] = time.monotonic() - t_page
                o["seconds"] = round(o["t_done"] - o["t_input"], 1)
                if o.get("changed"):
                    _center(region)
                    page.wait_for_timeout(int(TAIL_HOLD * 1000))
                    # the independent check, part 2: the result region must LOOK
                    # different and not be blank. A DOM change alone passed a 3D
                    # viewer that rendered nothing in the first live run.
                    shot1 = _shot(region)
                    # the result must differ from the page as loaded OR from the
                    # in-progress region (whichever baseline shows the change: Gradio 6
                    # keeps the old output on screen while a run is pending)
                    bases = [b for b in (shot0, shot_mid) if b] or [None]
                    base = max(bases, key=lambda b: pixel_change(b, shot1)[0])
                    o["pixels"] = [round(x, 1) for x in pixel_change(base, shot1)]
                    o["visible"] = visible_result(
                        plan["output_types"][k_res], base, shot1, o.get("text", ""))
                    if shot1:
                        (out_dir / "result_region.png").write_bytes(shot1)
            except Exception as e:
                o.setdefault("inconclusive", f"{type(e).__name__}: {str(e)[:120]}")
                # only a run we SUBMITTED can time out; a page that never offered
                # its button or examples is inconclusive (could not drive it)
                if (o.get("submitted") and "Timeout" in type(e).__name__
                        and time.monotonic() >= deadline - 1):
                    o["deadline"] = True
            try:
                o["recording"] = str(page.video.path()) if page.video else ""
            except Exception:
                pass
            page.close()
            ctx.close()
            browser.close()
    except Exception as e:
        o.setdefault("inconclusive", f"{type(e).__name__}: {str(e)[:120]}")
    return o


def hosted_cut(t_input: float, t_done: float) -> dict | None:
    """PURE: the span of the recording that is the clip — from HEAD_PAD before the
    example click to TAIL_HOLD after the result — and the speed-up that fits it
    into CLIP_MAX (at most MAX_SPEEDUP; the wording then says it was sped up)."""
    start = max(0.0, float(t_input) - HEAD_PAD)
    length = float(t_done) + TAIL_HOLD - start
    if length <= 0:
        return None
    speed = 1.0 if length <= CLIP_MAX else min(MAX_SPEEDUP, length / CLIP_MAX)
    if length / speed > CLIP_MAX:            # still too long even at the cap: keep the END
        start = start + (length - CLIP_MAX * speed)
        length = CLIP_MAX * speed
    shown = length / speed
    return {"start": round(start, 3), "length": round(length, 3), "speed": round(speed, 3),
            "seconds": round(max(CLIP_MIN, shown), 3)}


def try_hosted(pr: dict, out_dir: Path, deadline: float) -> tuple[dict | None, list[str]]:
    """(evidence, log) for the first Space that produces a PASSED fixed test before
    the deadline. Failed / timed-out / inconclusive runs are logged and NOT
    published (round 4 row 4: skip on failure); None when no Space passed."""
    log = []
    for info in pr.get("hosted") or []:
        if time.monotonic() >= deadline - 10:
            log.append("deadline spent")
            break
        if not _space_ok(info):
            log.append(f"{info.get('id') or info.get('host')}: {info.get('stage') or '?'} — unavailable")
            continue
        host = info["host"].rstrip("/")
        cfg = _json(f"{host}/config")
        plan = gradio_plan(cfg)
        if not plan:
            log.append(f"{host}: no Gradio example + button + output — not drivable")
            continue
        o = _drive(host, plan, out_dir, deadline)
        status = classify(o)
        log.append(f"{host}: {status or 'UNAVAILABLE'} ({o.get('error') or o.get('inconclusive') or ''}"
                   f"{' pixels=' + str(o['pixels']) if o.get('pixels') else ''})"[:200])
        if status != "PASSED_FIXED_TEST" or not o.get("recording"):
            continue
        cut = hosted_cut(o["t_input"], o["t_done"])
        clip = str(out_dir / "evidence_hosted.mp4")
        if not cut or not (_ffmpeg(master_args(o["recording"], clip, cut["start"], cut["length"],
                                               cut["speed"]))
                           and Path(clip).exists() and Path(clip).stat().st_size > 1000):
            log.append(f"{host}: clip cut failed")
            continue
        kinds = sorted({t for t in plan["output_types"]})
        text = re.sub(r"\s+", " ", str(o.get("text") or "")).strip()
        observed = (f"In our hosted-demo run, this input produced {', '.join(kinds)} output "
                    f"in about {o.get('seconds', 0):.0f} seconds"
                    + (f': "{text[:120]}"' if text and set(kinds) & {"textbox", "markdown", "label",
                                                                       "json", "highlightedtext",
                                                                       "chatbot", "code"} else "")
                    + "." + (f" (Waiting shown at {cut['speed']:.1f}x speed.)" if cut["speed"] > 1 else ""))
        ev = empty()
        ev.update({"source": "hosted", "status": "PASSED_FIXED_TEST", "label": label("hosted"),
                   "wording": wording("PASSED_FIXED_TEST"), "clip": clip,
                   "clip_seconds": cut["seconds"], "url": host,
                   "input": (plan.get("inputs") or [plan["input"]] * 2)[o.get("example_index", 0)],
                   "observed": observed, "supported_claims": [observed],
                   "version": str(info.get("sha") or "")})
        return ev, log
    return None, log


# ============================================================ gather (expensive)
def gather(item: dict, readme: str | None = None, out_dir: str | Path | None = None,
           probe_result: dict | None = None) -> dict | None:
    """The evidence for one candidate: hosted first (120 s total capture
    deadline), then the author's demo. Returns an admissible evidence dict, the
    "none" record (looked, nothing admissible — see its `note`), or None when it
    could not look at all. Never raises."""
    try:
        pr = probe_result if isinstance(probe_result, dict) else probe(item, readme)
        if pr is None:
            return None
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", pr["ident"])[:60] or "tool"
        out = (Path(out_dir) if out_dir else fv.TEMP / "evidence" / slug).resolve()
        out.mkdir(parents=True, exist_ok=True)
        notes = []
        if any(_space_ok(h) for h in pr.get("hosted") or []):
            deadline = time.monotonic() + CAPTURE_DEADLINE
            ev, log = try_hosted(pr, out, deadline)
            for line in log:
                print(f"     🧪 hosted: {line}")
            if ev and admissible(ev):
                return ev
            notes.append("hosted: " + "; ".join(log)[:120])
        elif pr.get("hosted"):
            notes.append("hosted: no Space is running")
        if pr.get("author") and pr.get("license_ok"):
            ev = try_author(pr, out)
            if ev and admissible(ev):
                return ev
            notes.append("author: no asset qualified")
        elif pr.get("author"):
            notes.append(f"author: licence {pr.get('license') or 'unknown'} not admitted")
        elif pr.get("rejected"):
            whys = sorted({r["why"] for r in pr["rejected"]})
            notes.append("author: " + ", ".join(whys)[:100])
        return empty("; ".join(notes) or "no hosted demo, no committed demo media")
    except Exception as e:
        print(f"     ⚠️ evidence gather failed ({type(e).__name__}: {e})")
        return None


# ============================================================ writer hand-off
def writer_brief(ev) -> str:
    """The prompt block: what this evidence lets the writer claim and what it does
    not. "" for no admissible evidence (the caller skips the candidate). PURE."""
    if not admissible(ev):
        return ""
    ch = fv.CHANNEL_NAME
    if ev["source"] == "hosted":
        return (f"EVIDENCE (the video OPENS on this footage; these rules override STRUCTURE):\n"
                f"- Source label on screen: \"{label('hosted')}\" ({ev['captured_at']}). {ch}'s pipeline "
                f"opened the tool's own hosted demo ({ev['url']}) in a clean browser and ran it "
                f"with {ev['input']}.\n"
                f"- Observed: {ev['observed']}\n"
                f"- Status: {ev['wording']}\n"
                f"CLAIM RULES:\n"
                f"- Scene 1 must open by stating that observed result (\"In our hosted-demo run, "
                f"this input produced …\") in at most 16 words.\n"
                f"- Claim only what this run showed. Never say the installation works, that it "
                f"works offline, on the viewer's hardware, or how fast it is in general.\n"
                f"- Any speed, size or cost figure from the source is the authors' claim: "
                f"attribute it (\"the authors claim …\").\n\n")
    r = ev["rights"]
    return (f"EVIDENCE (the video OPENS on this footage; these rules override STRUCTURE):\n"
            f"- Source label on screen: \"{label('author')}\". The footage is the repository's own demo "
            f"media ({r['path']}), published by its authors. {ch} did NOT run this tool.\n"
            f"- What the source says the demo shows: {ev['observed']}\n"
            f"- Status: {ev['wording']}\n"
            f"CLAIM RULES:\n"
            f"- Scene 1 must begin with the words \"The author's demo shows\".\n"
            f"- Never write \"we tested\", \"we tried\", \"we ran\", \"in our test\" or anything that "
            f"says {ch} ran the tool. Say it is not independently tested by scene 2.\n"
            f"- Any speed, size or cost figure is the authors' claim: attribute it "
            f"(\"the authors claim …\").\n\n")


# ------------------------------------------------------------ v3-R D4: the docs route
DOCS_MARK = "📘"


def docs_record(prev=None) -> dict:
    """spec v3-R D4: the evidence record for a video built from the project's own
    documentation — what replaced row 17's skip while the recovery cohort is on.
    Not admissible (nothing was run, no clip): the label is burned as a chip, the
    writer is told it may not claim a test. `prev` is gather()'s answer, kept only
    for its log note. PURE."""
    note = prev.get("note", "") if isinstance(prev, dict) else ""
    ev = empty(note or "documentation route")
    ev.update(source="docs", label=LABELS["docs"])
    return ev


def docs_brief() -> str:
    """The writer's evidence block for a docs-route video. PURE."""
    ch = fv.CHANNEL_NAME
    return (f"EVIDENCE ROUTE: documentation only. On-screen label: \"{LABELS['docs']}\". "
            f"{ch} did NOT run, install or test this tool.\n"
            f"CLAIM RULES:\n"
            f"- Everything the tool does, supports or achieves is the authors' claim: attribute it "
            f"(\"the README says …\", \"the authors claim …\").\n"
            f"- Never write \"we tested\", \"we tried\", \"we ran\", \"in our test\", or that it "
            f"works on the viewer's machine.\n"
            f"- Say plainly, by scene 3, that {ch} has not tested it.\n\n")


def screen_label(ev) -> str:
    """The label a docs-route video carries as an on-screen chip from 0:00 (D4/D5);
    "" for every other record (an admissible clip burns its own label). PURE."""
    if isinstance(ev, dict) and ev.get("source") == "docs":
        return LABELS["docs"]
    return ""


_OVERCLAIM_AUTHOR = re.compile(
    r"\b(?:we|i)\s+(?:have\s+|just\s+|actually\s+)?(?:tested|tried|ran|run|benchmarked|measured|"
    r"installed|put it through)\b|\bour\s+(?:own\s+)?(?:test|tests|testing|benchmark|benchmarks|run)\b|"
    r"\bin\s+our\s+(?:tests?|testing|hands-on)\b|\bhands-on test\b|\bwe\s+put\s+\w+\s+to\s+the\s+test\b",
    re.I)
_OVERCLAIM_HOSTED = re.compile(
    r"\b(?:we|i)\s+(?:have\s+)?(?:installed|benchmarked)\b|\bworks\s+offline\b|"
    r"\b(?:runs|works)\s+on\s+your\s+(?:own\s+)?(?:machine|hardware|gpu|laptop|pc|computer)\b",
    re.I)


def overclaims(script) -> list[str]:
    """Narration phrases that claim more than the evidence allows: any first-person
    testing claim over an author demo; installation/offline/your-hardware claims
    over a hosted test. [] for no evidence dict. PURE, never raises."""
    if not isinstance(script, dict) or not isinstance(script.get("evidence"), dict):
        return []
    src = script["evidence"].get("source")
    # v3-R D4: a docs-route video ran nothing, so a first-person testing claim is an
    # over-claim — the author-demo rule. The hosted rule is NOT applied: it matches
    # attributed sentences ("the model card says it works offline"), which is exactly
    # the wording docs_brief asks for, and D8 lets only truth failures block.
    rxs = ([_OVERCLAIM_AUTHOR] if src in ("author", "docs") else [_OVERCLAIM_HOSTED] if src == "hosted"
           else [])
    hits = []
    for sc in script.get("scenes") or []:
        text = str((sc or {}).get("narration", "") if isinstance(sc, dict) else "")
        for rx in rxs:
            for m in rx.finditer(text):
                hits.append(m.group(0))
    return hits


def fact_lines(ev) -> str:
    """The evidence as fact_check source text (the checker reads what the writer
    was ordered to use — gates.fact_sources)."""
    if not admissible(ev):
        return ""
    lines = [f"- source: {ev['label']} ({ev['captured_at']})", f"- status: {ev['wording']}",
             f"- url: {ev['url']}"]
    if ev.get("input"):
        lines.append(f"- input: {ev['input']}")
    if ev.get("observed"):
        lines.append(f"- observed: {ev['observed']}")
    return "\n".join(lines)


# ============================================================ clip placement (v3-P.2 calls this)
def slot_plan(clip_seconds: float, share: float) -> dict | None:
    """PURE: fit a master clip of `clip_seconds` to a slot of `share` seconds.
    Shorter clip → play once, hold the last frame (the result). Longer → speed up
    to SLOT_MAX_SPEED, then drop the HEAD (the result at the end is what matters).
    Output is share + SLOT_PAD so step5_build never -stream_loops it."""
    try:
        c, s = float(clip_seconds), float(share)
    except (TypeError, ValueError):
        return None
    if c <= 0 or s <= 0:
        return None
    if c <= s:
        return {"start": 0.0, "speed": 1.0, "hold": round(s - c + SLOT_PAD, 3),
                "out": round(s + SLOT_PAD, 3)}
    speed = min(SLOT_MAX_SPEED, c / s)
    start = max(0.0, c - s * speed)
    return {"start": round(start, 3), "speed": round(speed, 4),
            "hold": SLOT_PAD, "out": round(s + SLOT_PAD, 3)}


def slot_args(clip: str, label_png: str, out: str, plan: dict) -> list[str]:
    """PURE: render the slot clip — the plan's span/speed, held, with the source
    label PNG overlaid top-left from frame 0 to the end."""
    sp = plan["speed"]
    chain = (f"[0:v]setpts={1.0 / sp:.6f}*(PTS-STARTPTS),fps={FPS},"
             f"scale={fv.VIDEO_W}:{fv.VIDEO_H}:force_original_aspect_ratio=decrease,"
             f"pad={fv.VIDEO_W}:{fv.VIDEO_H}:(ow-iw)/2:(oh-ih)/2:color={BG},setsar=1,"
             f"tpad=stop_mode=clone:stop_duration={plan['hold']:.3f}[b]")
    args = [fv.FFMPEG or "ffmpeg", "-y", "-ss", f"{plan['start']:.3f}", "-i", clip]
    if label_png:
        args += ["-loop", "1", "-i", label_png]
        graph = chain + ";[b][1:v]overlay=48:40:shortest=0,format=yuv420p[v]"
    else:
        graph = chain + ";[b]format=yuv420p[v]"
    return args + ["-filter_complex", graph, "-map", "[v]", "-t", f"{plan['out']:.3f}", "-an",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out]


def label_text(ev) -> str:
    """The on-screen source label: "Hosted test · <date>" or "Author demo · <repo>".
    "" when there is nothing admissible to label. PURE."""
    if not admissible(ev):
        return ""
    if ev["source"] == "hosted":
        return f"{ev['label']} · {ev.get('captured_at', '')}".strip(" ·")
    rid = repo_of(_repo_url_from(ev.get("url", "")))
    return f"{ev['label']} · {rid[1]}" if rid else ev["label"]


def _repo_url_from(url: str) -> str:
    m = re.match(r"(https?://(?:github\.com|huggingface\.co)/[\w.-]+/[\w.-]+)", str(url or ""))
    return m.group(1) if m else ""


def render_label_png(text: str, out_png: str) -> str | None:
    """The label as a PNG (white Inter Black on a dark pill), MEASURED with the font
    that is drawn — branding.fit_font, never a character count."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        from factverse import branding as _br

        def font_for(size):
            try:
                return ImageFont.truetype(str(fv.FONTS / "Inter-Black.ttf"), size)
            except Exception:
                return ImageFont.load_default()
        budget = int(fv.VIDEO_W * 0.6)
        size, f = _br.fit_font(font_for, [text], LABEL_PX, budget, floor=32, step=2)
        d = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
        bb = d.textbbox((0, 0), text, font=f)
        pad_x, pad_y = 22, 12
        w, h = int(bb[2] - bb[0] + 2 * pad_x), int(bb[3] - bb[1] + 2 * pad_y)
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        dd = ImageDraw.Draw(img)
        dd.rounded_rectangle([0, 0, w - 1, h - 1], radius=12, fill=(13, 17, 23, 225),
                             outline=(220, 38, 38, 255), width=3)
        dd.text((pad_x - bb[0], pad_y - bb[1]), text, font=f, fill=(255, 255, 255, 255))
        img.save(out_png)
        return out_png if Path(out_png).exists() else None
    except Exception as e:
        print(f"     ⚠️ evidence label failed: {e}")
        return None


def render_slot_clip(ev, share: float, out_mp4: str, with_label: bool = True) -> str | None:
    """The evidence clip rendered to EXACTLY its slot share (+SLOT_PAD), with the
    source label burned from frame 0. None on any failure."""
    plan = slot_plan((ev or {}).get("clip_seconds"), share)
    if not plan or not admissible(ev):
        return None
    png = ""
    if with_label:
        png = render_label_png(label_text(ev), str(Path(out_mp4).with_suffix(".label.png"))) or ""
        if not png:
            return None          # third-party footage never ships without its label
    if (_ffmpeg(slot_args(ev["clip"], png, out_mp4, plan))
            and Path(out_mp4).exists() and Path(out_mp4).stat().st_size > 1000):
        return out_mp4
    return None


_CARD_MARKS = ("statcard", "codecard", "receiptcard")


def lead_index(clips: list) -> int | None:
    """PURE: which clip of scene 1 the evidence REPLACES — the first one that is not
    a generated card (the recording or stock clip); a scene of only cards gives up
    its first. None for an empty scene (the clip is then the scene's only one)."""
    if not clips:
        return None
    for j, c in enumerate(clips):
        if not any(m in str(c) for m in _CARD_MARKS):
            return j
    return 0


def place_clip(script: dict, scene_clips: list, scene_durs: list | None,
               with_label: bool = True) -> float | None:
    """Lead scene 1 with the evidence clip, REPLACING a recording/stock clip (never
    stacking: a scene's time splits equally between its clips), rendered to its
    exact share after the narration timings exist (the C.3 law). Returns the slot
    seconds, or None when nothing was placed (then scene_clips is untouched).
    Call AFTER every inject_* and BEFORE screencap.recut."""
    try:
        ev = script.get("evidence") if isinstance(script, dict) else None
        if not admissible(ev) or not scene_clips or not scene_durs:
            return None
        sdur = float(scene_durs[0])
        if sdur <= 0:
            return None
        clips = scene_clips[0]
        idx = lead_index(clips)
        n = len(clips) if idx is not None else 1
        share = sdur / n
        out = render_slot_clip(ev, share, str(fv.TEMP / "evidence_slot.mp4"), with_label=with_label)
        if not out:
            return None
        if idx is None:
            clips.append(out)
        else:
            clips.pop(idx)
            clips.insert(0, out)
        print(f"  🎞️ Evidence ({ev['label']}) leads scene 1 ({share:.1f}s slot)")
        return round(share, 3)
    except Exception as e:
        print(f"  ⚠️ evidence clip placement failed ({type(e).__name__}: {e})")
        return None
