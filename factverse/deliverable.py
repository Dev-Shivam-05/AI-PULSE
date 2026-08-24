"""v3-C: the free 1-page cheat sheet every tool video ships with.

One A4 PDF per tool video, written to docs/tools/<date>-<slug>.pdf and served by
GitHub Pages at <deliverable_base_url>/tools/<file>. The file name is decided
BEFORE upload (so the description can link it) and the PDF is written AFTER
upload (so it can carry the video link). Sections come from one LLM extraction
over the script; if that fails the sheet still ships with title + deliverable.
Spec: docs/spec/ai-pulse-v3c.md. reportlab is imported lazily (test job installs it;
the publish job too) so importing this module never needs it.
"""
from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

from factverse import config as fv
from factverse import llm

TOOLS_DIR = fv.BASE / "docs" / "tools"
DEFAULT_BASE_URL = "https://dev-shivam-05.github.io/AI-PULSE"
RED = "#DC2626"
INK = "#0D1117"
_MONO_COLS = 68        # JetBrains Mono 11pt inside the code box, A4 minus margins


# ------------------------------------------------------------- naming (pure)
def slug(title: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(title).lower()).strip("-")
    return s[:max_len].rstrip("-") or "tool"


def pdf_name(title: str, date: _dt.date | None = None) -> str:
    date = date or _dt.date.today()
    return f"{date.isoformat()}-{slug(title)}.pdf"


def public_url(name: str) -> str:
    base = str(fv.setting("deliverable_base_url", DEFAULT_BASE_URL) or DEFAULT_BASE_URL)
    return f"{base.rstrip('/')}/tools/{name}"


# ------------------------------------------------------------- content
def fallback_sheet(script: dict) -> dict:
    """The sheet we can always build without an LLM: the deliverable itself."""
    dl = script.get("deliverable") or {}
    return {"what": "", "steps": [str(dl.get("text", "")).strip()] if dl.get("text") else [],
            "uses": [], "skip_if": ""}


def _as_list(v) -> list[str]:
    """The LLM returns a JSON list most of the time and a plain string the rest of
    the time. Iterating a string yields CHARACTERS, so coerce before filtering."""
    if isinstance(v, str):
        v = [ln for ln in v.splitlines()] or [v]
    elif not isinstance(v, (list, tuple)):
        return []
    return [str(x).strip() for x in v if str(x).strip()]


def extract_sheet(script: dict) -> dict | None:
    """One LLM call -> {what, steps[2-5], uses[3], skip_if}. None on any failure."""
    dl = script.get("deliverable") or {}
    scenes = "\n".join(f"- {sc.get('narration', '')}" for sc in script.get("scenes") or [])
    prompt = f"""From this video script about a free AI tool, extract a 1-page cheat sheet.
Commands must be copied EXACTLY from the deliverable/script — never invent flags or URLs.

TITLE: {script.get('title', '')}
DELIVERABLE: {dl.get('text', '')}  ({dl.get('url', '')})
SCRIPT:
{scenes}

Return ONLY JSON:
{{"what": "<=40 words: what it is and who built it",
 "steps": ["2-5 strings: the exact commands/steps to get it running, first one = the deliverable"],
 "uses": ["exactly 3 concrete things to make with it, most impressive first"],
 "skip_if": "<=30 words: who should NOT bother / what it cannot do yet"}}"""
    try:
        d = llm.generate_json(prompt, max_tokens=1024, temperature=0.2)
        if not isinstance(d, dict):
            return None
        steps = _as_list(d.get("steps"))[:5]
        uses = _as_list(d.get("uses"))[:3]
        if len(steps) < 1:
            steps = fallback_sheet(script)["steps"]
        return {"what": " ".join(str(d.get("what", "")).split())[:400],
                "steps": steps, "uses": uses,
                "skip_if": " ".join(str(d.get("skip_if", "")).split())[:300]}
    except Exception as e:
        print(f"   ⚠️ cheat-sheet extraction failed: {e}")
        return None


# ------------------------------------------------------------- rendering
def _fonts() -> dict:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    fonts = {"title": "Helvetica-Bold", "mono": "Courier", "body": "Helvetica", "unicode": False}
    for key, name, paths in (
        ("title", "InterBlack", [fv.FONTS / "Inter-Black.ttf"]),
        ("mono", "JBMono", [fv.FONTS / "JetBrainsMono-Regular.ttf"]),
        ("body", "BodySans", ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                              "C:/Windows/Fonts/segoeui.ttf"]),
    ):
        for p in paths:
            try:
                if Path(p).exists():
                    pdfmetrics.registerFont(TTFont(name, str(p)))
                    fonts[key] = name
                    if key == "body":
                        fonts["unicode"] = True
                    break
            except Exception:
                continue
    return fonts


def _clean(text: str, unicode_ok: bool) -> str:
    t = " ".join(str(text or "").split())
    return t if unicode_ok else t.encode("latin-1", "ignore").decode("latin-1")


def meta_line(script: dict) -> str:
    """spec v3-E #8: the receipts stamp — stars/downloads, license, checked-on date —
    exactly the per-item line HAL's field guide carries. Empty when no facts exist."""
    vf = script.get("verified_facts") or {}
    if not vf:
        return ""
    parts = []
    if vf.get("stars") is not None:
        # "stars" as a WORD: JetBrainsMono has no ★ glyph — it rendered as tofu.
        parts.append(f"{vf['stars']:,} stars")
    if vf.get("downloads") is not None:
        parts.append(f"{vf['downloads']:,} downloads")
    if vf.get("license"):
        parts.append(str(vf["license"]))
    parts.append("checked " + _dt.date.today().isoformat())
    return " · ".join(parts)


def build_pdf(script: dict, sheet: dict, out: str, video_url: str = "") -> str | None:
    """A4 portrait, exactly one page (sections are line-capped, never overflow)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfgen import canvas

    f = _fonts()
    uni = f["unicode"]
    W, H = A4
    M = 48                                   # page margin
    c = canvas.Canvas(out, pagesize=A4)
    c.setTitle(_clean(script.get("title", ""), True))

    # top bar
    c.setFillColor(RED)
    c.rect(0, H - 40, W, 40, stroke=0, fill=1)
    c.setFillColor("white")
    c.setFont(f["title"], 11)
    c.drawString(M, H - 26, _clean(f"{fv.CHANNEL_NAME.upper()}  ·  FREE CHEAT SHEET", uni))
    c.drawRightString(W - M, H - 26, _dt.date.today().strftime("%d %b %Y"))

    y = H - 80
    title = _clean(script.get("title", "Tool"), uni)
    lines = simpleSplit(title, f["title"], 26, W - 2 * M)
    size = 26 if len(lines) <= 2 else 20
    lines = simpleSplit(title, f["title"], size, W - 2 * M)[:2]
    c.setFillColor(INK)
    for ln in lines:
        c.setFont(f["title"], size)
        c.drawString(M, y, ln)
        y -= size + 6
    # spec v3-E #8: the receipts stamp directly under the title — stars/downloads,
    # license, checked-on date. Skipped cleanly when no verified facts exist.
    ml = meta_line(script)
    if ml:
        c.setFillColor(RED)
        c.setFont(f["mono"], 10)
        c.drawString(M, y, _clean(ml, uni))
        y -= 18
    y -= 10

    def label(text):
        nonlocal y
        c.setFillColor(RED)
        c.setFont(f["title"], 10)
        c.drawString(M, y, text)
        y -= 16

    def body(text, max_lines):
        nonlocal y
        c.setFillColor(INK)
        c.setFont(f["body"], 11)
        for ln in simpleSplit(_clean(text, uni), f["body"], 11, W - 2 * M)[:max_lines]:
            c.drawString(M, y, ln)
            y -= 15
        y -= 8

    if sheet.get("what"):
        label("WHAT IT IS")
        body(sheet["what"], 4)

    steps = [s for s in (sheet.get("steps") or []) if s]
    if steps:
        label("GET IT RUNNING")
        rows = []
        for s in steps[:5]:
            # simpleSplit never breaks a long unbroken token (a git+https:// install
            # URL is one), so hard-wrap on character count as well. Never slice the
            # wrapped lines: a deliverable may be 300 chars (ai_pipeline._validate_script)
            # and keeping only the first two rendered a command that still looks
            # copy-pasteable and is cut mid-flag — worse than no command at all.
            for row in simpleSplit(_clean(s, uni), f["mono"], 11, W - 2 * M - 40):
                while len(row) > _MONO_COLS:
                    rows.append(row[:_MONO_COLS])
                    row = row[_MONO_COLS:]
                rows.append(row)
        if len(rows) > 8:            # one page is the contract; say so rather than cut silently
            rows = rows[:7] + ["... full command in the video description"]
        box_h = 18 * len(rows) + 22
        c.setFillColor(INK)
        c.roundRect(M, y - box_h + 12, W - 2 * M, box_h, 6, stroke=0, fill=1)
        c.setFillColor("#E6EDF3")
        c.setFont(f["mono"], 11)
        ty = y - 8
        for r in rows:
            c.drawString(M + 16, ty, r)
            ty -= 18
        y -= box_h + 6

    uses = [u for u in (sheet.get("uses") or []) if u][:3]
    if uses:
        label("MAKE THESE 3 THINGS")
        c.setFillColor(INK)
        c.setFont(f["body"], 11)
        for u in uses:
            for j, ln in enumerate(simpleSplit(_clean(u, uni), f["body"], 11, W - 2 * M - 16)[:2]):
                c.drawString(M + (0 if j == 0 else 16), y, ("•  " if j == 0 else "") + ln)
                y -= 15
        y -= 8

    if sheet.get("skip_if"):
        label("SKIP IT IF")
        body(sheet["skip_if"], 2)

    # footer
    dl = script.get("deliverable") or {}
    c.setStrokeColor(RED)
    c.setLineWidth(2)
    c.line(M, 70, W - M, 70)
    c.setFillColor("#57606A")
    c.setFont(f["body"], 9)
    fy = 56
    src = str(dl.get("url") or script.get("source_url") or "")
    if src:
        c.drawString(M, fy, _clean(f"Source: {src}", uni)[:110])
        fy -= 12
    if video_url:
        c.drawString(M, fy, _clean(f"Video: {video_url}", uni)[:110])
        fy -= 12
    handle = str(fv.setting("channel_handle", "aipulse") or "aipulse")
    c.drawString(M, fy, _clean(f"youtube.com/@{handle}  ·  {fv.CHANNEL_NAME}", uni))
    c.showPage()
    c.save()
    p = Path(out)
    return str(p) if p.exists() and p.stat().st_size > 1000 else None


def make_cheat_sheet(script: dict, video_url: str = "") -> str | None:
    """Write docs/tools/<name>.pdf for this tool video. Fail-soft (None)."""
    try:
        name = script.get("cheat_sheet") or pdf_name(script.get("title", ""))
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        out = TOOLS_DIR / name
        sheet = extract_sheet(script) or fallback_sheet(script)
        path = build_pdf(script, sheet, str(out), video_url)
        if path:
            print(f"  📄 Cheat sheet: {name} → {public_url(name)}")
        return path
    except Exception as e:
        print(f"   ⚠️ cheat sheet failed: {e}")
        return None
