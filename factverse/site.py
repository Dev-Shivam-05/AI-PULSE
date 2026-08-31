"""v3-F.1: the docs/ directory becomes a real website.

One HTML page per tool video (docs/tools/<date>-<slug>.html), a regenerated
docs/index.html and docs/sitemap.xml, served by GitHub Pages at
<deliverable_base_url>. `docs/.nojekyll` is committed, so Pages serves this
directory VERBATIM — there is no Jekyll, no plugin allowlist and no build step.
Markdown would be served as raw text; that is why this module emits HTML.

The single source of truth is the catalog `state/tools_index.json` (a list of
entries). Every HTML file is 100% derived from it, so CI can throw the HTML away
and regenerate it after `state_merge` instead of stashing it — unlike the PDFs,
which an LLM wrote once and cannot reproduce.

Spec: docs/spec/ai-pulse-v3f1.md. Every public function fails soft (returns
None / no-op): the page is written in the post-upload zone, where a raise would
cost a duplicate publish.
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import re
import sys
from pathlib import Path

from factverse import config as fv
from factverse import deliverable

CATALOG = fv.BASE / "state" / "tools_index.json"
DOCS = fv.BASE / "docs"
TOOLS_DIR = DOCS / "tools"
MAX_PAGES = 500          # spec v3-F.1 note: newest N entries are regenerated

# spec v3-F.1 #8 — the committed dark theme (INK/RED already exist in deliverable.py)
BG = "#0D1117"
FG = "#E6EDF3"
MUTED = "#8B949E"
ACCENT = "#DC2626"
BOX = "#161B22"
LINE = "#30363D"


# --------------------------------------------------------------- naming (pure)
def page_name(pdf: str) -> str:
    """The page shares the PDF's <date>-<slug> stem (spec #6): one slug, no drift."""
    stem = deliverable.safe_name(pdf)      # never join an LLM-supplied path onto DOCS
    return (stem[:-4] if stem.lower().endswith(".pdf") else stem) + ".html" if stem else ""


def public_url(name: str) -> str:
    """<deliverable_base_url>/tools/<name> — the same host the PDF is served from."""
    return deliverable.public_url(name)


def site_url(rel: str = "") -> str:
    base = str(fv.setting("deliverable_base_url", deliverable.DEFAULT_BASE_URL)
               or deliverable.DEFAULT_BASE_URL).rstrip("/")
    return f"{base}/{rel.lstrip('/')}" if rel else base + "/"


def video_id(url: str) -> str:
    """The 11-char id out of watch?v= / youtu.be / embed forms. '' when absent."""
    m = re.search(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})", str(url or ""))
    return m.group(1) if m else ""


def enabled() -> bool:
    return bool(fv.setting("site_pages", True))


# --------------------------------------------------------------- catalog (pure)
def _as_list(v) -> list[str]:
    """Raw LLM output is never type-safe (the repo-wide rule): coerce, never assume."""
    if isinstance(v, str):
        v = [ln for ln in v.splitlines()] or [v]
    elif not isinstance(v, (list, tuple)):
        return []
    return [str(x).strip() for x in v if str(x).strip()]


def entry_for(script: dict, sheet: dict | None = None, video_url: str = "",
              date: _dt.date | None = None) -> dict:
    """The catalog row for one tool video. Pure — no I/O, no LLM."""
    script = script if isinstance(script, dict) else {}
    sheet = sheet if isinstance(sheet, dict) else {}
    dl = script.get("deliverable") if isinstance(script.get("deliverable"), dict) else {}
    pdf = str(script.get("cheat_sheet") or "")
    d = date or _dt.date.today()
    return {
        "page": page_name(pdf) or f"{d.isoformat()}-{deliverable.slug(script.get('title', ''))}.html",
        "pdf": pdf,
        "title": str(script.get("title", "")).strip(),
        "slug": deliverable.slug(script.get("title", "")),
        "date": d.isoformat(),
        # the repo/model name the signal carried; `deliverable` holds only kind/text/url
        "tool": str(script.get("signal_title") or "").strip(),
        "command": str(dl.get("text", "")).strip(),
        "source_url": str(dl.get("url") or script.get("source_url") or "").strip(),
        "video_url": str(video_url or "").strip(),
        "video_id": video_id(video_url),
        "what": str(sheet.get("what", "")).strip(),
        "uses": _as_list(sheet.get("uses"))[:3],
        "skip_if": str(sheet.get("skip_if", "")).strip(),
    }


def load_catalog(path: Path | None = None) -> list[dict]:
    """The catalog, or [] — a missing or corrupt file must never stop a run."""
    p = Path(path or CATALOG)
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    except (OSError, json.JSONDecodeError):
        return []
    return [e for e in data if isinstance(e, dict) and e.get("page")] if isinstance(data, list) else []


def upsert(entries: list[dict], entry: dict) -> list[dict]:
    """Replace the row with this `page`, else append. Pure — same key as _merge_index."""
    out = [e for e in entries if e.get("page") != entry.get("page")]
    out.append(entry)
    out.sort(key=lambda e: (str(e.get("date", "")), str(e.get("page", ""))))
    return out


def save_catalog(entries: list[dict], path: Path | None = None) -> bool:
    p = Path(path or CATALOG)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
        return True
    except OSError as e:
        print(f"   ⚠️ catalog write failed: {e}")
        return False


# --------------------------------------------------------------- render (pure)
def _esc(v) -> str:
    return html.escape(str(v or ""), quote=True)


_CSS = f"""*{{box-sizing:border-box}}
body{{margin:0;background:{BG};color:{FG};font:16px/1.6 -apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-text-size-adjust:100%}}
.wrap{{max-width:720px;margin:0 auto;padding:32px 20px 64px}}
a{{color:{FG}}}
.brand{{display:inline-block;font-weight:700;letter-spacing:.02em;text-decoration:none;
font-size:15px;margin-bottom:28px}}
.brand span{{color:{ACCENT}}}
h1{{font-size:30px;line-height:1.25;margin:0 0 8px}}
h1 span{{color:{ACCENT}}}
h2{{font-size:13px;letter-spacing:.10em;text-transform:uppercase;color:{MUTED};
margin:36px 0 10px;font-weight:600}}
.meta{{color:{MUTED};font-size:14px;margin:0 0 28px}}
.cmd{{background:{BOX};border:1px solid {LINE};border-radius:8px;padding:14px 16px;
display:flex;gap:12px;align-items:flex-start}}
.cmd code{{font:14px/1.55 ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace;
white-space:pre-wrap;word-break:break-word;flex:1;color:{FG}}}
.copy{{flex:none;background:{ACCENT};color:#fff;border:0;border-radius:6px;padding:7px 13px;
font:600 13px/1 inherit;cursor:pointer}}
ul{{margin:0;padding-left:20px}} li{{margin:6px 0}}
.embed{{position:relative;padding-top:56.25%;margin:12px 0 0;border-radius:8px;
overflow:hidden;background:{BOX}}}
.embed iframe{{position:absolute;inset:0;width:100%;height:100%;border:0}}
.btn{{display:inline-block;border:1px solid {LINE};border-radius:8px;padding:12px 18px;
text-decoration:none;font-weight:600;background:{BOX}}}
.src{{color:{MUTED};font-size:14px;word-break:break-word}}
.src a{{color:{MUTED}}}
footer{{margin-top:44px;padding-top:18px;border-top:1px solid {LINE};color:{MUTED};font-size:13px}}
.row{{display:block;text-decoration:none;padding:16px 0;border-bottom:1px solid {LINE}}}
.row .d{{color:{MUTED};font-size:13px}}
.row .t{{font-weight:600;font-size:18px;margin:2px 0 4px}}
.row .w{{color:{MUTED};font-size:14px}}
.row:last-of-type{{border-bottom:0}}
@media(max-width:520px){{body{{font-size:15px}}h1{{font-size:25px}}
.cmd{{flex-direction:column}}.copy{{align-self:flex-start}}}}"""

_JS = """(function(){var b=document.getElementById('c'),t=document.getElementById('cmd');
if(!b||!t)return;b.addEventListener('click',function(){var s=t.textContent;
function ok(){b.textContent='Copied';setTimeout(function(){b.textContent='Copy'},1500)}
function sel(){var r=document.createRange();r.selectNodeContents(t);
var g=window.getSelection();g.removeAllRanges();g.addRange(r)}
try{navigator.clipboard.writeText(s).then(ok,sel)}catch(e){sel()}})})();"""


def _head(title: str, desc: str, canonical: str, image: str) -> str:
    """<head> incl. the OG/Twitter card F.2/F.3 will rely on (spec #10)."""
    d = _esc(desc[:160])
    tags = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>{_esc(title)}</title>",
        f'<meta name="description" content="{d}">',
        f'<link rel="canonical" href="{_esc(canonical)}">',
        f'<meta property="og:title" content="{_esc(title)}">',
        f'<meta property="og:description" content="{d}">',
        f'<meta property="og:url" content="{_esc(canonical)}">',
        '<meta property="og:type" content="article">',
        f'<meta property="og:site_name" content="{_esc(fv.CHANNEL_NAME)}">',
        f'<meta name="twitter:card" content="{"summary_large_image" if image else "summary"}">',
    ]
    if image:
        tags.append(f'<meta property="og:image" content="{_esc(image)}">')
    tags.append(f"<style>{_CSS}</style>")
    return "".join(tags)


def _wordmark(name: str) -> tuple[str, str]:
    """Split the channel name for the two-tone wordmark: "Tool" + "Dojo"."""
    name = str(name or "ToolDojo").strip()
    parts = name.split()
    if len(parts) > 1:
        return " ".join(parts[:-1]) + " ", parts[-1]
    m = re.match(r"^([A-Z][a-z0-9]+)([A-Z].*)$", name)      # "ToolDojo" -> Tool + Dojo
    return (m.group(1), m.group(2)) if m else (name, "")


def _brand() -> str:
    """The wordmark, two-tone like branding.wordmark: last word in the accent."""
    head, tail = _wordmark(fv.CHANNEL_NAME)
    return f'<a class="brand" href="../index.html">{_esc(head)}<span>{_esc(tail)}</span></a>'


def render_page(entry: dict) -> str:
    """One tool page. Pure: same entry in, same bytes out (spec acceptance #2)."""
    e = entry if isinstance(entry, dict) else {}
    title, what = str(e.get("title", "")), str(e.get("what", ""))
    canonical = public_url(str(e.get("page", "")))
    vid = str(e.get("video_id") or video_id(e.get("video_url", "")))
    img = f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg" if vid else ""
    out = [f"<!doctype html><html lang=\"en\"><head>{_head(title, what, canonical, img)}"
           f"</head><body><div class=\"wrap\">{_brand()}",
           f"<h1>{_esc(title)}</h1>"]
    meta = " · ".join(x for x in (str(e.get("date", "")), str(e.get("tool", ""))) if x)
    if meta:
        out.append(f'<p class="meta">{_esc(meta)}</p>')
    if e.get("command"):
        out.append('<h2>The exact command</h2><div class="cmd">'
                   f'<code id="cmd">{_esc(e["command"])}</code>'
                   '<button class="copy" id="c" type="button">Copy</button></div>')
    if what:
        out.append(f"<h2>What it is</h2><p>{_esc(what)}</p>")
    uses = [u for u in (e.get("uses") or []) if str(u).strip()]
    if uses:
        out.append("<h2>What to make with it</h2><ul>"
                   + "".join(f"<li>{_esc(u)}</li>" for u in uses) + "</ul>")
    if e.get("skip_if"):
        out.append(f'<h2>Skip it if</h2><p>{_esc(e["skip_if"])}</p>')
    if vid:
        out.append('<h2>The video</h2><div class="embed"><iframe loading="lazy" '
                   f'src="https://www.youtube-nocookie.com/embed/{_esc(vid)}" '
                   f'title="{_esc(title)}" allowfullscreen '
                   'allow="accelerometer;clipboard-write;encrypted-media;picture-in-picture">'
                   "</iframe></div>")
    if e.get("pdf"):
        out.append(f'<h2>Take it with you</h2><a class="btn" href="{_esc(e["pdf"])}">'
                   "⬇ Download the 1-page PDF</a>")
    if e.get("source_url"):
        out.append(f'<h2>Source</h2><p class="src"><a href="{_esc(e["source_url"])}" '
                   f'rel="noopener">{_esc(e["source_url"])}</a></p>')
    handle = str(fv.setting("channel_handle", "aipulse") or "aipulse")
    out.append(f'<footer>{_esc(fv.CHANNEL_NAME)} · '
               f'<a href="https://youtube.com/@{_esc(handle)}">youtube.com/@{_esc(handle)}</a>'
               f"</footer></div><script>{_JS}</script></body></html>")
    return "".join(out)


def render_index(entries: list[dict]) -> str:
    """Newest-first list of every catalog entry (spec #11). Pure."""
    rows = sorted([e for e in entries if isinstance(e, dict) and e.get("page")],
                  key=lambda e: (str(e.get("date", "")), str(e.get("page", ""))), reverse=True)
    name = str(fv.CHANNEL_NAME or "ToolDojo")
    pitch = "One free AI tool a day, actually run and checked before it ships."
    handle = str(fv.setting("channel_handle", "aipulse") or "aipulse")
    out = [f"<!doctype html><html lang=\"en\"><head>"
           f"{_head(name, pitch, site_url(), '')}</head><body><div class=\"wrap\">",
           f"<h1>{_esc(_wordmark(name)[0])}<span>{_esc(_wordmark(name)[1])}</span></h1>"
           f"<p class=\"meta\">{_esc(pitch)} · "
           f'<a href="https://youtube.com/@{_esc(handle)}">youtube.com/@{_esc(handle)}</a></p>']
    if rows:
        out.append(f"<h2>{len(rows)} tool{'s' if len(rows) != 1 else ''}</h2>")
        for e in rows:
            out.append(f'<a class="row" href="tools/{_esc(e["page"])}">'
                       f'<div class="d">{_esc(e.get("date", ""))}</div>'
                       f'<div class="t">{_esc(e.get("title", ""))} →</div>'
                       + (f'<div class="w">{_esc(str(e.get("what", ""))[:150])}</div>'
                          if e.get("what") else "") + "</a>")
    else:
        out.append('<p class="meta">The first tool page lands here after the next run.</p>')
    out.append(f'<footer>{_esc(name)} · '
               f'<a href="https://youtube.com/@{_esc(handle)}">youtube.com/@{_esc(handle)}</a>'
               "</footer></div></body></html>")
    return "".join(out)


def render_sitemap(entries: list[dict]) -> str:
    urls = [(site_url(), max((str(e.get("date", "")) for e in entries), default=""))]
    urls += [(public_url(str(e["page"])), str(e.get("date", "")))
             for e in sorted(entries, key=lambda e: str(e.get("date", "")), reverse=True)
             if isinstance(e, dict) and e.get("page")]
    body = "".join(
        f"<url><loc>{_esc(u)}</loc>" + (f"<lastmod>{_esc(d)}</lastmod>" if d else "") + "</url>"
        for u, d in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + body + "</urlset>")


# --------------------------------------------------------------- write (I/O)
def _write(path: Path, text: str) -> bool:
    """Write only on change, so an unchanged rebuild leaves git clean."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return False
        path.write_text(text, encoding="utf-8")
        return True
    except OSError as e:
        print(f"   ⚠️ site write failed ({path.name}): {e}")
        return False


def rebuild(entries: list[dict] | None = None) -> int:
    """Regenerate index + sitemap + the newest MAX_PAGES pages. Returns files written.

    CI calls this AFTER state_merge, so the merged catalog — not this run's local
    copy — is what the site is built from. Fail-soft: -1 on an unexpected error.
    """
    try:
        entries = load_catalog() if entries is None else entries
        recent = sorted(entries, key=lambda e: (str(e.get("date", "")), str(e.get("page", ""))),
                        reverse=True)[:MAX_PAGES]
        n = 0
        for e in recent:
            name = deliverable.safe_name(e.get("page"))
            if not name.endswith(".html"):     # a catalog row is data, not a path
                continue
            n += int(_write(TOOLS_DIR / name, render_page(e)))
        n += int(_write(DOCS / "index.html", render_index(entries)))
        n += int(_write(DOCS / "sitemap.xml", render_sitemap(entries)))
        print(f"  🌐 Site: {len(recent)} page(s), {n} file(s) written")
        return n
    except Exception as e:                                     # never fatal
        print(f"   ⚠️ site rebuild failed ({type(e).__name__}: {e})")
        return -1


def publish_page(script: dict, sheet: dict | None = None, video_url: str = "") -> str | None:
    """Add this video to the catalog and rebuild the site. Returns the page URL.

    Called in the post-upload zone, so EVERY path returns instead of raising:
    a raise between yt_upload and record_run costs a duplicate publish.
    """
    if not enabled():
        return None
    try:
        entry = entry_for(script, sheet, video_url)
        if not entry.get("page"):
            return None
        entries = upsert(load_catalog(), entry)
        save_catalog(entries)
        rebuild(entries)
        url = public_url(entry["page"])
        print(f"  🌐 Page: {url}")
        return url
    except Exception as e:
        print(f"   ⚠️ site page failed ({type(e).__name__}: {e})")
        return None


def main(argv: list[str] | None = None) -> int:
    """`python -m factverse.site` — regenerate everything from the catalog."""
    return 0 if rebuild() >= 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
