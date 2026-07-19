"""
The Intelligence Brain — turn free signal feeds into a ranked content shortlist.

Pipeline:
    gather  -> pull candidates from primary AI sources (sources.py)
    filter  -> keep AI/tech-relevant items, drop already-covered topics
    score   -> blend (per-source) strength + niche relevance + recency -> 0..100 fit
    rank    -> return the strongest items
    brief   -> (optional, LLM) turn the chosen item into a format + angle + hook

Ranking is pure Python (no LLM, no API key) so it is cheap, deterministic, and
testable on its own. The LLM is only used in brief() to craft the angle.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from factverse import config as fv
from factverse.intelligence import sources

# Words that mark an item as on-niche for an AI/tech channel.
KEYWORDS = (
    "ai", "a.i", "llm", "gpt", "claude", "gemini", "llama", "mistral", "qwen",
    "model", "benchmark", "agent", "openai", "anthropic", "deepmind", "hugging face",
    "neural", "transformer", "inference", "fine-tune", "finetune", "rag", "diffusion",
    "robot", "chip", "gpu", "nvidia", "dataset", "open source", "open-source",
    "multimodal", "reasoning", "training", "prompt", "embedding", "vision", "voice",
    "machine learning", "deep learning", "generative",
)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())


def _relevance(item: dict) -> float:
    t = " " + _norm(item.get("title", "")) + " "
    hits = sum(1 for k in KEYWORDS if k in t)
    rel = min(hits, 5) / 5.0
    if item.get("niche"):           # AI-native source: never gate it out
        rel = max(rel, 0.6)
    return rel


def _parse_dt(s: str):
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except Exception:
            continue
    try:  # RFC-822 (RSS pubDate)
        dt = parsedate_to_datetime(s)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None


def _recency_boost(published: str) -> float:
    dt = _parse_dt(published)
    if not dt:
        return 0.5
    age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    return max(0.05, math.exp(-age_h / 72.0))  # ~3-day decay


def _used_topics() -> set[str]:
    f = fv.BASE / "used_topics.json"
    if f.exists():
        try:
            return {_norm(x) for x in json.loads(f.read_text(encoding="utf-8"))}
        except Exception:
            return set()
    return set()


def _used_urls() -> set[str]:
    f = fv.BASE / "used_urls.json"
    if f.exists():
        try:
            return {str(x).strip().rstrip("/") for x in json.loads(f.read_text(encoding="utf-8"))}
        except Exception:
            return set()
    return set()


def _is_used(title: str, used: set[str]) -> bool:
    nt = _norm(title)
    for u in used:
        if not u:
            continue
        # substring matching only for real titles; short strings would over-block
        if len(u) >= 12 and (u in nt or nt in u):
            return True
        if u == nt:
            return True
    return False


# The same story published as a paper reads worse on video than as news; weight kinds.
_KIND_WEIGHT = {"news": 1.0, "discussion": 0.9, "research": 0.75}


def rank(limit: int = 10) -> list[dict]:
    """Return the top `limit` content candidates, each with a 0..100 fit_score."""
    candidates = sources.gather_all()
    used = _used_topics()
    used_urls = _used_urls()

    # Normalize source strength WITHIN each feed so a 300-point HN story doesn't
    # bury every arXiv paper and blog post (different scales per source).
    feed_max: dict[str, float] = {}
    feed_min: dict[str, float] = {}
    for c in candidates:
        s = c.get("source", "?")
        sc = c.get("score", 0.0)
        feed_max[s] = max(feed_max.get(s, 0.0), sc)
        feed_min[s] = min(feed_min.get(s, sc), sc)

    scored: list[dict] = []
    seen: set[str] = set()
    for c in candidates:
        title = (c.get("title") or "").strip()
        if not title:
            continue
        key = _norm(title)
        if key in seen:
            continue
        rel = _relevance(c)
        if rel <= 0:
            continue                       # off-niche (HN noise)
        if _is_used(title, used):
            continue                       # already covered (title match)
        if (c.get("url") or "").strip().rstrip("/") in used_urls:
            continue                       # already covered (same article, new headline)
        seen.add(key)

        src = c.get("source", "?")
        fm = feed_max.get(src, 0.0) or 1.0
        if feed_max.get(src, 0.0) == feed_min.get(src, 0.0):
            # uniform-score feed (RSS/arXiv): no ranking signal, so stay neutral
            # instead of letting every item claim a perfect score
            src_norm = 0.5
        else:
            src_norm = c.get("score", 0.0) / fm
        rec = _recency_boost(c.get("published", ""))
        fit = 100 * (0.35 * src_norm + 0.30 * rel + 0.35 * rec)
        fit *= _KIND_WEIGHT.get(c.get("kind", "news"), 1.0)
        item = dict(c)
        item["fit_score"] = round(fit, 1)
        item["relevance"] = round(rel, 2)
        item["recency"] = round(rec, 2)
        scored.append(item)

    scored.sort(key=lambda x: x["fit_score"], reverse=True)
    return scored[:limit]


def brief(item: dict) -> dict:
    """Optionally enrich the chosen item with an LLM-generated format + angle + hook."""
    from factverse import llm

    prompt = f"""You are the editor of a faceless but authoritative AI/tech YouTube channel.
Trending item: "{item['title']}" (source: {item['source']}).

Pick the best FORMAT (one of: explainer, news_roundup, tool_howto, short_take) and write a
curiosity-driven angle. Be accurate; do NOT invent facts not implied by the title.
Return ONLY JSON:
{{"format":"...","title_idea":"<=60 chars","angle":"1-2 sentences","hook":"first 2 spoken lines"}}"""
    data = llm.generate_json(prompt)
    return {**item, "brief": data} if data else item


if __name__ == "__main__":
    print("=" * 78)
    print("  FactVerse Intelligence Brain - live AI signal ranking")
    print("=" * 78)
    top = rank(limit=10)
    if not top:
        print("\n  No candidates returned. Check internet / that 'requests' is installed.")
    for i, c in enumerate(top, 1):
        print(f"\n{i:2d}. [{c['fit_score']:5.1f}]  {c['title'][:84]}")
        print(f"     {c['source']:18s} rel={c['relevance']} rec={c['recency']}  {c['url'][:64]}")
    print()
