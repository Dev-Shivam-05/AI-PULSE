"""
Free, PRIMARY-source signal feeds for the AI Intelligence niche.

Why primary sources: lab blogs / arXiv / Hacker News / ML subreddits are
accurate, citable, and low-copyright — exactly what keeps a channel monetizable
(vs. rehashing other outlets' news footage).

Every fetcher is defensive: any network/parse failure returns [] (never raises),
so the brain degrades gracefully instead of dying. Each item is a dict:
    {"title", "url", "source", "score", "published", "kind", "niche"}
`niche=True` marks AI-native feeds (arXiv, ML subreddits, lab blogs) so the
ranker doesn't keyword-gate them.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests

# Reddit-style descriptive UA (plain bot UAs get 403'd more often).
UA = {"User-Agent": "python:factverse.aiintel:v1.0 (research bot)"}
TIMEOUT = 20


def _get(url: str, params: dict | None = None, headers: dict | None = None):
    h = dict(UA)
    if headers:
        h.update(headers)
    return requests.get(url, params=params, headers=h, timeout=TIMEOUT)


def hacker_news(min_points: int = 50, days: int = 21, max_items: int = 40) -> list[dict]:
    """Fresh AI/LLM stories from Hacker News (Algolia API), last `days` days only."""
    out: list[dict] = []
    try:
        cutoff = int(time.time()) - days * 86400
        r = _get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={
                "query": "AI LLM GPT model agent",
                "tags": "story",
                "numericFilters": f"points>{min_points},created_at_i>{cutoff}",
                "hitsPerPage": max_items,
            },
        )
        for h in r.json().get("hits", []):
            title = (h.get("title") or "").strip()
            if not title:
                continue
            out.append(
                {
                    "title": title,
                    "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                    "source": "hackernews",
                    "score": float(h.get("points", 0)) + float(h.get("num_comments", 0)) * 0.5,
                    "published": h.get("created_at", ""),
                    "kind": "news",
                    "niche": False,
                }
            )
    except Exception:
        pass
    return out


def reddit(
    subs: tuple[str, ...] = ("MachineLearning", "LocalLLaMA", "artificial", "singularity", "OpenAI"),
    per_sub: int = 12,
) -> list[dict]:
    """Hot posts from the AI/ML subreddits (public JSON). Often 403s without auth — degrades."""
    out: list[dict] = []
    for sub in subs:
        try:
            r = _get(f"https://www.reddit.com/r/{sub}/hot.json", params={"limit": per_sub})
            if r.status_code != 200:
                continue
            for child in r.json().get("data", {}).get("children", []):
                d = child.get("data", {})
                if d.get("stickied"):
                    continue
                title = (d.get("title") or "").strip()
                if not title:
                    continue
                pub = ""
                cu = d.get("created_utc")
                if cu:
                    pub = datetime.fromtimestamp(cu, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                out.append(
                    {
                        "title": title,
                        "url": "https://reddit.com" + d.get("permalink", ""),
                        "source": f"reddit/{sub}",
                        "score": float(d.get("ups", 0)) + float(d.get("num_comments", 0)) * 0.5,
                        "published": pub,
                        "kind": "discussion",
                        "niche": True,
                    }
                )
            time.sleep(0.4)
        except Exception:
            continue
    return out


def arxiv(categories: tuple[str, ...] = ("cs.AI", "cs.CL", "cs.LG"), max_items: int = 25) -> list[dict]:
    """Newest papers from arXiv (Atom API). All inherently on-niche (niche=True)."""
    out: list[dict] = []
    try:
        query = "+OR+".join(f"cat:{c}" for c in categories)
        r = _get(
            "https://export.arxiv.org/api/query",
            params={
                "search_query": query,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": max_items,
            },
        )
        ns = {"a": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(r.text)
        for e in root.findall("a:entry", ns):
            title = (e.findtext("a:title", default="", namespaces=ns) or "").strip()
            title = " ".join(title.split())
            link = e.findtext("a:id", default="", namespaces=ns)
            pub = e.findtext("a:published", default="", namespaces=ns)
            if title:
                out.append(
                    {
                        "title": title,
                        "url": link,
                        "source": "arxiv",
                        "score": 1.0,
                        "published": pub,
                        "kind": "research",
                        "niche": True,
                    }
                )
    except Exception:
        pass
    return out


# Primary AI lab/news RSS feeds — highest credibility, lowest copyright risk.
# Third field: niche=True only for AI-NATIVE sources (never keyword-gated);
# general tech outlets stay keyword-gated so off-topic items can't slip through.
AI_FEEDS = (
    ("https://huggingface.co/blog/feed.xml", "blog/huggingface", True),
    ("https://openai.com/news/rss.xml", "blog/openai", True),
    ("https://www.anthropic.com/rss.xml", "blog/anthropic", True),
    ("https://blog.google/technology/ai/rss/", "blog/google-ai", False),
    ("https://bair.berkeley.edu/blog/feed.xml", "blog/bair", True),
    ("https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "news/theverge", False),
    ("https://venturebeat.com/category/ai/feed/", "news/venturebeat", False),
    ("https://techcrunch.com/category/artificial-intelligence/feed/", "news/techcrunch", False),
)


def rss(url: str, source: str, max_items: int = 12, niche: bool = True,
        kind: str = "news") -> list[dict]:
    """Parse an RSS 2.0 or Atom feed defensively."""
    out: list[dict] = []
    try:
        r = _get(url)
        root = ET.fromstring(r.text)
        items = root.findall(".//item")  # RSS 2.0
        if items:
            for it in items[:max_items]:
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                pub = (it.findtext("pubDate") or "").strip()
                if title:
                    out.append({"title": title, "url": link, "source": source,
                                "score": 1.0, "published": pub, "kind": kind, "niche": niche})
        else:  # Atom
            ns = {"a": "http://www.w3.org/2005/Atom"}
            for e in root.findall("a:entry", ns)[:max_items]:
                title = (e.findtext("a:title", default="", namespaces=ns) or "").strip()
                link_el = e.find("a:link", ns)
                link = link_el.get("href") if link_el is not None else ""
                pub = (e.findtext("a:updated", default="", namespaces=ns)
                       or e.findtext("a:published", default="", namespaces=ns) or "")
                if title:
                    out.append({"title": title, "url": link, "source": source,
                                "score": 1.0, "published": pub, "kind": kind, "niche": niche})
    except Exception:
        pass
    return out


def ai_blogs() -> list[dict]:
    out: list[dict] = []
    for url, src, niche in AI_FEEDS:
        out += rss(url, src, niche=niche)
    return out


def github_trending(days: int = 14, min_stars: int = 120, max_items: int = 15) -> list[dict]:
    """Hot NEW AI repos via the official GitHub search API (free, no key needed).

    'Created recently + already heavily starred' is the closest key-free proxy for
    github.com/trending (which has no official API). kind='tool' marks these as
    candidates for the v3 hands-on utility format."""
    out: list[dict] = []
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        r = _get(
            "https://api.github.com/search/repositories",
            params={"q": f"ai OR llm OR agent OR diffusion created:>{since} stars:>{min_stars}",
                    "sort": "stars", "order": "desc", "per_page": max_items},
            headers={"Accept": "application/vnd.github+json"},
        )
        if r.status_code != 200:
            return []
        for it in r.json().get("items", []):
            name = (it.get("full_name") or "").strip()
            if not name:
                continue
            desc = (it.get("description") or "").strip()
            out.append(
                {
                    "title": f"{name}: {desc[:90]}" if desc else name,
                    "url": it.get("html_url") or f"https://github.com/{name}",
                    "source": "github/trending",
                    "score": float(it.get("stargazers_count", 0)),
                    "published": it.get("created_at", ""),
                    "kind": "tool",
                    "niche": True,
                }
            )
    except Exception:
        pass
    return out


def huggingface_trending(max_items: int = 12) -> list[dict]:
    """Trending models from the Hugging Face Hub API (free, no key needed)."""
    out: list[dict] = []
    try:
        r = _get("https://huggingface.co/api/models",
                 params={"sort": "trendingScore", "direction": "-1", "limit": max_items})
        if r.status_code != 200:
            return []
        for m in r.json():
            mid = (m.get("modelId") or m.get("id") or "").strip()
            if not mid:
                continue
            tag = str(m.get("pipeline_tag") or "model").replace("-", " ")
            out.append(
                {
                    "title": f"{mid} — trending {tag} on Hugging Face",
                    "url": f"https://huggingface.co/{mid}",
                    "source": "huggingface/trending",
                    "score": float(m.get("trendingScore") or m.get("likes") or 0),
                    "published": m.get("createdAt", ""),
                    "kind": "tool",
                    "niche": True,
                }
            )
    except Exception:
        pass
    return out


def product_hunt() -> list[dict]:
    """Product Hunt's public feed (free, no key). It lists ALL products, so
    niche=False on purpose: the ranker's keyword gate keeps only the AI ones."""
    return rss("https://www.producthunt.com/feed", "producthunt",
               max_items=20, niche=False, kind="tool")


def gather_all() -> list[dict]:
    """Pull every source. A dead source just contributes nothing."""
    candidates: list[dict] = []
    candidates += hacker_news()
    candidates += ai_blogs()
    candidates += arxiv()
    candidates += reddit()
    # v3 utility-lane signals: things a viewer can USE today (kind="tool")
    candidates += github_trending()
    candidates += huggingface_trending()
    candidates += product_hunt()
    return candidates
