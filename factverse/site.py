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
from factverse import tasks

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
    # fv.flag, not fv.setting: setting() returns an env var as a STRING and
    # bool("false") is True — the switch would be un-flippable from Actions.
    return fv.flag("site_pages", True)


# --------------------------------------------------------------- catalog (pure)
def _as_list(v) -> list[str]:
    """Raw LLM output is never type-safe (the repo-wide rule): coerce, never assume."""
    if isinstance(v, str):
        v = [ln for ln in v.splitlines()] or [v]
    elif not isinstance(v, (list, tuple)):
        return []
    return [str(x).strip() for x in v if str(x).strip()]


def safe_link(url: str) -> str:
    """An href we are willing to put on our own origin. `deliverable.url` is written
    by a model grounded in a third-party README, and html.escape cannot help with a
    scheme — `javascript:` is not a metacharacter. screencap.py already refuses this
    same field before handing it to a browser; the site refuses it before linking it."""
    u = str(url or "").strip()
    return u if u.lower().startswith(("http://", "https://")) else ""


def entry_for(script: dict, sheet: dict | None = None, video_url: str = "",
              date: _dt.date | None = None, pdf: str | None = None) -> dict:
    """The catalog row for one tool video. Pure — no I/O, no LLM."""
    script = script if isinstance(script, dict) else {}
    sheet = sheet if isinstance(sheet, dict) else {}
    dl = script.get("deliverable") if isinstance(script.get("deliverable"), dict) else {}
    # `pdf` is the file make_cheat_sheet actually wrote (None when that seam failed) —
    # the page must not offer a download that does not exist. Falling back to the
    # script's name keeps entry_for usable on its own.
    name = pdf if pdf is not None else script.get("cheat_sheet")
    pdf_file = deliverable.safe_name(name or "")     # never an un-sanitized href
    d = date or _dt.date.today()
    out = {
        "page": (page_name(script.get("cheat_sheet") or "")
                 or f"{d.isoformat()}-{deliverable.slug(script.get('title', ''))}.html"),
        "pdf": pdf_file,
        "title": str(script.get("title", "")).strip(),
        "slug": deliverable.slug(script.get("title", "")),
        "date": d.isoformat(),
        # the repo/model name the signal carried; `deliverable` holds only kind/text/url
        "tool": str(script.get("signal_title") or "").strip(),
        "command": str(dl.get("text", "")).strip(),
        "source_url": safe_link(dl.get("url") or script.get("source_url") or ""),
        "video_url": str(video_url or "").strip(),
        "video_id": video_id(video_url),
        "what": str(sheet.get("what", "")).strip(),
        "uses": _as_list(sheet.get("uses"))[:3],
        "skip_if": str(sheet.get("skip_if", "")).strip(),
    }
    # v3-K.1: the "Before you start" list (the sheet's own setup steps), the
    # shared-interface evidence WITHOUT its runner-local clip, and the task family.
    out["steps"] = _as_list(sheet.get("steps"))[:5]
    out["evidence"] = tasks.clean_evidence(script.get("evidence"))
    out["task_family"] = tasks.task_family(out)
    return out


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
.decision{{background:{BOX};border:1px solid {LINE};border-left:4px solid {ACCENT};
border-radius:8px;padding:16px 18px;margin:20px 0 0}}
.decision p{{margin:8px 0 0}}
.badge{{display:inline-block;font-size:12px;font-weight:700;letter-spacing:.06em;
text-transform:uppercase;border:1px solid {LINE};border-radius:999px;padding:3px 10px;
color:{FG};background:{BG}}}
.verdict{{font-weight:600;font-size:17px}}
.state{{border:1px solid {ACCENT};border-radius:8px;padding:12px 16px;margin:16px 0 0;
font-size:15px}}
.state b{{color:{ACCENT}}}
.res{{border:1px solid {LINE};border-radius:8px;padding:14px 16px;margin:10px 0 0;
background:{BOX}}}
.res .n{{font-weight:700;font-size:17px}}
.res .s{{margin:4px 0 0}}
.res .l{{color:{MUTED};font-size:14px;margin:6px 0 0;word-break:break-word}}
.res .l a{{color:{MUTED}}}
.note{{color:{MUTED};font-size:14px}}
.follow{{border:1px dashed {LINE};border-radius:8px;padding:14px 16px;margin:12px 0 0}}
.hist li{{margin:8px 0}}
@media(max-width:520px){{body{{font-size:15px}}h1{{font-size:25px}}
.cmd{{flex-direction:column}}.copy{{align-self:flex-start}}}}"""

_JS = """(function(){var b=document.getElementById('c'),t=document.getElementById('cmd');
if(!b||!t)return;b.addEventListener('click',function(){var s=t.textContent;
function ok(){b.textContent='Copied';setTimeout(function(){b.textContent='Copy'},1500)}
function sel(){var r=document.createRange();r.selectNodeContents(t);
var g=window.getSelection();g.removeAllRanges();g.addRange(r)}
try{navigator.clipboard.writeText(s).then(ok,sel)}catch(e){sel()}})})();"""


def verification_token() -> str:
    """K.1 row 15: Search Console's HTML-tag method, from config. Google's token is
    URL-safe base64; anything else is dropped rather than written into our <head>."""
    tok = str(fv.setting("google_site_verification", "") or "").strip()
    return tok if re.fullmatch(r"[A-Za-z0-9_-]{10,100}", tok) else ""


def _head(title: str, desc: str, canonical: str, image: str, verify: bool = False) -> str:
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
    tok = verification_token() if verify else ""
    if tok:
        tags.append(f'<meta name="google-site-verification" content="{_esc(tok)}">')
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


def entry_name(entry: dict) -> str:
    """The one file name for a catalog row: the file written, the canonical URL, the
    index href and the sitemap <loc> must all be THIS. rebuild() sanitized only the
    file, so the other three could advertise a URL the generator had refused to write
    — and the catalog is merged state read back off origin/main, not our own output."""
    name = deliverable.safe_name((entry or {}).get("page") if isinstance(entry, dict) else "")
    return name if name.endswith(".html") else ""


# v3-K.1 row 14: what each evidence source does NOT establish. Review round 3's
# "What ToolDojo may claim" column, turned into the reader's limitation line.
NOT_ESTABLISHED = {
    "hosted": ("A hosted-demo run does not establish that installation works, that it "
               "works offline, or that it works on your hardware."),
    "sandbox": ("A fixed test in our environment does not establish that the package is "
                "safe or that the tool works generally."),
    "author": ("This is the author's demonstration, not our test. It does not show how "
               "the tool behaves on your inputs or your hardware."),
    "none": ("We have not run this tool. Everything on this page comes from its own "
             "documentation."),
}
NO_SPEED_RANKING = ("No speed ranking: hosted demos run on hardware and queues we do not "
                    "control, so only the result on the fixed input is compared.")


def rights_line(rights) -> str:
    """The attribution line an author demo must carry (review row 4: asset path,
    commit, licence, copyright notice, NOTICE material, modification)."""
    if not isinstance(rights, dict):
        return ""
    parts = []
    if rights.get("path"):
        parts.append(f"Asset: {rights['path']}")
    if rights.get("commit"):
        parts.append(f"commit {str(rights['commit'])[:12]}")
    if rights.get("license"):
        parts.append(f"Licence: {rights['license']}")
    if rights.get("copyright"):
        parts.append(str(rights["copyright"]))
    if rights.get("notice"):
        parts.append(f"Notice: {rights['notice']}")
    if rights.get("modified"):
        parts.append(f"Modified: {rights['modified']}")
    return " · ".join(parts)


def _ev(entry: dict) -> dict:
    """The entry's evidence, re-coerced (merged state is data, not trusted output);
    an entry without any is honestly "Not independently tested"."""
    ev = tasks.clean_evidence((entry or {}).get("evidence") if isinstance(entry, dict) else None)
    return ev or tasks.clean_evidence({"source": "none"})


def _evidence_block(ev: dict, today: _dt.date, links: list[tuple[str, str]] = ()) -> str:
    """One evidence card: label, verbatim status wording, then only what is true."""
    src = ev.get("source", "none")
    out = [f'<span class="badge">{_esc(ev.get("label") or "Not tested")}</span>',
           f'<p class="s"><b>{_esc(ev.get("wording"))}</b></p>']
    if tasks.is_outdated(ev, today):
        out.append(f'<p class="s"><b>Outdated:</b> tested {_esc(ev["captured_at"])}, more '
                   f'than {tasks.OUTDATED_DAYS} days ago. It may no longer hold.</p>')
    if ev.get("input"):
        out.append(f'<p class="s">Our fixed input: {_esc(ev["input"])}</p>')
    if ev.get("observed"):
        lead = "What the author's demo shows" if src == "author" else "What we saw"
        out.append(f'<p class="s">{lead}: {_esc(ev["observed"])}</p>')
    claims = ev.get("supported_claims") or []
    if claims:
        out.append('<ul class="s">' + "".join(f"<li>{_esc(c)}</li>" for c in claims) + "</ul>")
    meta = []
    if ev.get("captured_at"):
        meta.append(("Captured " if src == "author" else "Tested ") + _esc(ev["captured_at"]))
    if ev.get("url"):                     # already scheme-checked by clean_evidence
        meta.append(f'<a href="{_esc(ev["url"])}" rel="noopener nofollow">'
                    + ("Author's asset" if src == "author" else "The demo") + "</a>")
    for text, href in links or ():
        if href:
            meta.append(f'<a href="{_esc(href)}">{_esc(text)}</a>')
    if meta:
        out.append('<p class="l">' + " · ".join(meta) + "</p>")
    rl = rights_line(ev.get("rights"))
    if rl:
        out.append(f'<p class="l">{_esc(rl)}</p>')
    return "".join(out)


def render_page(entry: dict, hub: str = "", today: _dt.date | None = None) -> str:
    """One tool page. Pure: same entry in, same bytes out (spec acceptance #2).

    v3-K.1 row 14 (useful HTML, not a download wrapper): the video first, then the
    decision with its evidence label, then evidence, prerequisites and limits."""
    e = entry if isinstance(entry, dict) else {}
    today = today or _dt.date.today()
    title, what = str(e.get("title", "")), str(e.get("what", ""))
    canonical = public_url(entry_name(e))
    vid = str(e.get("video_id") or video_id(e.get("video_url", "")))
    img = f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg" if vid else ""
    ev = _ev(e)
    out = [f"<!doctype html><html lang=\"en\"><head>{_head(title, what, canonical, img)}"
           f"</head><body><div class=\"wrap\">{_brand()}",
           f"<h1>{_esc(title)}</h1>"]
    meta = " · ".join(_esc(x) for x in (str(e.get("date", "")), str(e.get("tool", ""))) if x)
    hub = deliverable.safe_name(hub or "")
    if hub.endswith(".html"):
        fam = tasks.family_of(e)
        meta += (" · " if meta else "") + (f'<a href="../tasks/{_esc(hub)}">Compare '
                                           f'{_esc(tasks.label(fam).lower())} tools</a>')
    if meta:
        out.append(f'<p class="meta">{meta}</p>')
    if vid:
        out.append('<div class="embed"><iframe loading="lazy" '
                   f'src="https://www.youtube-nocookie.com/embed/{_esc(vid)}" '
                   f'title="{_esc(title)}" allowfullscreen '
                   'allow="accelerometer;clipboard-write;encrypted-media;picture-in-picture">'
                   "</iframe></div>")
    out.append(f'<div class="decision"><span class="badge">'
               f'{_esc(ev.get("label") or "Not tested")}</span>'
               f'<p class="verdict">{_esc(ev.get("wording"))}</p>'
               + (f'<p><b>Skip it if:</b> {_esc(e["skip_if"])}</p>' if e.get("skip_if") else "")
               + "</div>")
    if e.get("command"):
        out.append('<h2>The exact command</h2><div class="cmd">'
                   f'<code id="cmd">{_esc(e["command"])}</code>'
                   '<button class="copy" id="c" type="button">Copy</button></div>')
    if what:
        out.append(f"<h2>What it is</h2><p>{_esc(what)}</p>")
    steps = [s for s in _steps(e.get("steps")) if s]
    if steps:
        out.append("<h2>Before you start</h2><ol>"
                   + "".join(f"<li>{_esc(s)}</li>" for s in steps) + "</ol>")
    uses = [u for u in (e.get("uses") or []) if str(u).strip()]
    if uses:
        out.append("<h2>What to make with it</h2><ul>"
                   + "".join(f"<li>{_esc(u)}</li>" for u in uses) + "</ul>")
    out.append(f'<h2>Evidence</h2><div class="res">{_evidence_block(ev, today)}</div>')
    # the reader's own "skip it if" already sits in the decision box above
    out.append("<h2>Limitations</h2>"
               + f'<p>{_esc(NOT_ESTABLISHED.get(ev["source"], ""))}</p>')
    if e.get("pdf"):
        out.append(f'<h2>Take it with you</h2><a class="btn" href="{_esc(e["pdf"])}">'
                   "⬇ Download the 1-page PDF</a>")
    # Guarded AGAIN at render: entry_for checks it on write, but the catalog is
    # merged state read back off origin/main, and a row written by any other path
    # (an older version, a hand edit, a bad merge) reached this href unchecked.
    src = safe_link(e.get("source_url"))
    if src:
        out.append(f'<h2>Source</h2><p class="src"><a href="{_esc(src)}" '
                   f'rel="noopener">{_esc(src)}</a></p>')
    out.append(_footer() + f"</div><script>{_JS}</script></body></html>")
    return "".join(out)


def _steps(v) -> list[str]:
    """`steps` is merged state: a list of strings, or coerced into one."""
    return _as_list(v)[:5]


def _footer() -> str:
    handle = str(fv.setting("channel_handle", "aipulse") or "aipulse")
    return (f'<footer>{_esc(fv.CHANNEL_NAME)} · '
            f'<a href="https://youtube.com/@{_esc(handle)}">youtube.com/@{_esc(handle)}</a>'
            "</footer>")


_STATE_NOTE = {
    "outdated": ("Outdated", "the newest test here is from {newest}, more than {days} days "
                 "ago. The answer may no longer hold until we test again."),
    "inconclusive": ("Inconclusive", "none of the tested options passed this input, so "
                     "there is no recommendation yet."),
    "withdrawn": ("Withdrawn", "we no longer stand behind this comparison, so it makes no "
                  "recommendation. The results are kept below for the record."),
}
_KIND_TEXT = {
    "first_answer": "First comparison published.",
    "checked_again": "Checked again — recommendation unchanged.",
    "recommendation_changed": "Recommendation changed.",
    "now_passes": "Recommendation changed — an input that failed before now passes.",
}


def _names(xs) -> str:
    xs = [str(x) for x in xs or []]
    return ", ".join(xs) if xs else "none"


def hub_url(name: str) -> str:
    return site_url(f"tasks/{name}")


def render_hub(h: dict, today: _dt.date | None = None) -> str:
    """One task hub (K.1 rows 4-9). Pure. Every value is escaped for HTML and every
    href is either ours (relative) or passed the scheme guard."""
    h = h if isinstance(h, dict) else {}
    today = today or _dt.date.today()
    lab, name, state = str(h.get("label", "")), str(h.get("name", "")), str(h.get("state", ""))
    title = f"{lab}: tested options compared"
    tested = h.get("tested") or []
    answer = str(h.get("answer", ""))
    out = [f"<!doctype html><html lang=\"en\"><head>"
           f"{_head(title, answer, hub_url(name), '')}</head><body><div class=\"wrap\">"
           f"{_brand()}<h1>{_esc(title)}</h1>",
           f'<p class="meta">Last tested {_esc(h.get("newest", ""))} · {len(tested)} options '
           f'on the same input · {_esc(h.get("hashtag", ""))}</p>']
    if state in _STATE_NOTE:
        word, text = _STATE_NOTE[state]
        out.append(f'<div class="state"><b>{_esc(word)}:</b> '
                   + _esc(text.format(newest=h.get("newest", ""), days=tasks.OUTDATED_DAYS))
                   + "</div>")
    shown = (_STATE_NOTE["withdrawn"][1][0].upper() + _STATE_NOTE["withdrawn"][1][1:]
             if state == "withdrawn" else answer)
    out.append('<h2>The current answer</h2><div class="decision">'
               f'<p class="verdict">{_esc(shown)}</p>'
               '<p class="note">This answer is conditional: it holds for the fixed input '
               "below and the test dates listed. It does not say any tool is the best "
               "in general.</p></div>")
    if h.get("input"):
        out.append(f'<h2>Our fixed input</h2><p>{_esc(h["input"])}</p>')
    out.append("<h2>Tested options</h2>")
    for r in tested:
        e, ev = r.get("entry") or {}, r.get("ev") or {}
        out.append(f'<div class="res"><div class="n">{_esc(r.get("name", ""))}</div>'
                   + _evidence_block(ev, today, _links(e)) + "</div>")
    out.append(f'<p class="note">{_esc(NO_SPEED_RANKING)}</p>')
    cands = h.get("candidates") or []
    if cands:
        out.append("<h2>Candidate profiles — not tested by us</h2>"
                   '<p class="note">An author demo shows what the author recorded. It never '
                   "earns a tested position on this page.</p>")
        for r in cands:
            e, ev = r.get("entry") or {}, r.get("ev") or {}
            out.append(f'<div class="res"><div class="n">{_esc(r.get("name", ""))}</div>'
                       + _evidence_block(ev, today, _links(e)) + "</div>")
    out.append(f"<h2>What these tests do not establish</h2>"
               f'<p>{_esc(NOT_ESTABLISHED["hosted"])}</p>')
    hist = list(reversed(h.get("history") or []))
    if hist:
        items = []
        for ev in hist:
            line = f'<b>{_esc(ev.get("date", ""))}</b> — {_esc(_KIND_TEXT.get(ev.get("kind"), ""))}'
            if ev.get("kind") in ("recommendation_changed", "now_passes"):
                line += (f' Passed now: {_esc(_names(ev.get("answer")))}. '
                         f'Before: {_esc(_names(ev.get("previous")))}.')
            elif ev.get("kind") == "first_answer":
                line += f' Passed: {_esc(_names(ev.get("answer")))}.'
            items.append(f"<li>{line}</li>")
        out.append('<h2>Change history</h2><ul class="hist">' + "".join(items) + "</ul>")
    ch = tasks.follow_channel()
    if ch and state != "withdrawn" and fv.flag("task_alerts", True):
        out.append("<h2>Follow changes to this task</h2><div class=\"follow\">"
                   "<p>One message only when this answer materially changes: the "
                   "recommendation changes, or an input that failed now passes. Never for a "
                   "new star count or a new repo.</p>"
                   f'<p><a class="btn" href="https://t.me/{_esc(ch)}" rel="noopener">'
                   f"Follow on Telegram</a> "
                   f'<span class="note">posts tagged {_esc(h.get("hashtag", ""))}</span></p></div>')
    out.append(_footer() + "</div></body></html>")
    return "".join(out)


def _links(e: dict) -> list[tuple[str, str]]:
    """Tool page, cheat sheet and video for one catalog row, relative to tasks/."""
    name = entry_name(e)
    pdf = deliverable.safe_name(str(e.get("pdf") or ""))
    return [("Tool page", f"../tools/{name}" if name else ""),
            ("Cheat sheet", f"../tools/{pdf}" if pdf.lower().endswith(".pdf") else ""),
            ("Video", safe_link(e.get("video_url")))]


def render_index(entries: list[dict], hubs: list[dict] | None = None) -> str:
    """Newest-first list of every catalog entry (spec #11). Pure."""
    rows = sorted([e for e in entries if entry_name(e)],
                  key=lambda e: (str(e.get("date", "")), str(e.get("page", ""))), reverse=True)
    name = str(fv.CHANNEL_NAME or "ToolDojo")
    pitch = "One free AI tool a day, actually run and checked before it ships."
    handle = str(fv.setting("channel_handle", "aipulse") or "aipulse")
    out = [f"<!doctype html><html lang=\"en\"><head>"
           f"{_head(name, pitch, site_url(), '', verify=True)}</head><body><div class=\"wrap\">",
           f"<h1>{_esc(_wordmark(name)[0])}<span>{_esc(_wordmark(name)[1])}</span></h1>"
           f"<p class=\"meta\">{_esc(pitch)} · "
           f'<a href="https://youtube.com/@{_esc(handle)}">youtube.com/@{_esc(handle)}</a></p>']
    hub_rows = [h for h in (hubs or []) if isinstance(h, dict) and h.get("name")]
    if hub_rows:
        out.append("<h2>Compare by task</h2>")
        for h in hub_rows:
            word = _STATE_NOTE.get(h.get("state"), ("Current", ""))[0]
            out.append(f'<a class="row" href="tasks/{_esc(h["name"])}">'
                       f'<div class="d">{_esc(word)} · last tested {_esc(h.get("newest", ""))}</div>'
                       f'<div class="t">{_esc(h.get("label", ""))} →</div>'
                       f'<div class="w">{_esc(h.get("answer", ""))}</div></a>')
    if rows:
        out.append(f"<h2>{len(rows)} tool{'s' if len(rows) != 1 else ''}</h2>")
        for e in rows:
            out.append(f'<a class="row" href="tools/{_esc(entry_name(e))}">'
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


def render_sitemap(entries: list[dict], hubs: list[dict] | None = None) -> str:
    rows = [e for e in entries if entry_name(e)]
    hub_rows = [h for h in (hubs or []) if isinstance(h, dict) and h.get("name")]
    dates = [str(e.get("date", "")) for e in rows] + [str(h.get("newest", "")) for h in hub_rows]
    urls = [(site_url(), max(dates, default=""))]
    urls += [(hub_url(h["name"]), str(h.get("newest", ""))) for h in hub_rows]
    urls += [(public_url(entry_name(e)), str(e.get("date", "")))
             for e in sorted(rows, key=lambda e: str(e.get("date", "")), reverse=True)]
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
        today = _dt.date.today()
        try:
            hubs = tasks.hubs(entries, today)  # v3-K.1: [] until the supply exists
        except Exception as ex:
            print(f"   ⚠️ task hubs skipped: {type(ex).__name__}: {ex}")
            hubs = []
        hub_for = {h["family"]: h["name"] for h in hubs if h.get("state") != "withdrawn"}
        n = 0
        for e in recent:
            name = entry_name(e)               # a catalog row is data, not a path
            if not name:
                continue
            try:
                n += int(_write(TOOLS_DIR / name,
                                render_page(e, hub=hub_for.get(tasks.family_of(e), ""))))
            except Exception as ex:
                # One unreadable page file used to abort the loop, which skipped the
                # index and sitemap writes BELOW it — the site then froze at its
                # pre-corruption state on every future run, while publish_page still
                # returned a URL and the ledger still said tool_page=True.
                print(f"   ⚠️ page skipped ({name}): {type(ex).__name__}: {ex}")
        written = []
        for h in hubs:
            # per-item isolation (the F.1 freeze): one bad hub never costs the index
            try:
                name = tasks.hub_name(h.get("family", ""))
                if name:
                    n += int(_write(DOCS / "tasks" / name, render_hub(h, today)))
                    written.append(h)
            except Exception as ex:
                print(f"   ⚠️ hub skipped ({h.get('family', '?')}): {type(ex).__name__}: {ex}")
        n += int(_write(DOCS / "index.html", render_index(entries, written)))
        n += int(_write(DOCS / "sitemap.xml", render_sitemap(entries, written)))
        print(f"  🌐 Site: {len(recent)} page(s), {len(written)} hub(s), {n} file(s) written")
        return n
    except Exception as e:                                     # never fatal
        print(f"   ⚠️ site rebuild failed ({type(e).__name__}: {e})")
        return -1


def publish_page(script: dict, sheet: dict | None = None, video_url: str = "",
                 pdf: str | None = None) -> str | None:
    """Add this video to the catalog and rebuild the site. Returns the page URL.

    Called in the post-upload zone, so EVERY path returns instead of raising:
    a raise between yt_upload and record_run costs a duplicate publish.
    """
    if not enabled():
        return None
    try:
        entry = entry_for(script, sheet, video_url, pdf=pdf)
        # v3-P.1 shared interface: the catalog row carries the evidence (without the
        # local clip path). Inside this try: post-upload zone.
        from factverse import evidence as _ev
        view = _ev.catalog_view(script.get("evidence") if isinstance(script, dict) else None)
        if view:
            entry["evidence"] = view
        if not entry_name(entry):
            return None
        entries = upsert(load_catalog(), entry)
        save_catalog(entries)
        rebuild(entries)
        url = public_url(entry_name(entry))
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
