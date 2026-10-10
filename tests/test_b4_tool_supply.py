"""v3-B.4: tool-lane supply fix (docs/spec/ai-pulse-v3b4.md).

From 10-07 the tool lane failed 3/3 candidates a day. 6 of 9 were Product Hunt pages
(stripped HTML, never a code fence) and two real repos/models had their first fenced
block just past the 5,000-char grounding cut, so the copy-paste containment check
rejected every one of them. Network, LLM and ffmpeg are never touched here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factverse import ai_pipeline as ap

_B4_HF = "https://huggingface.co/google/embeddinggemma-2"
_B4_GH = "https://github.com/CopilotKit/OpenDots"
_B4_PH = "https://www.producthunt.com/products/devally"
_B4_PIP = "pip install -U sentence-transformers transformers"
_B4_CLONE = "git clone https://github.com/CopilotKit/OpenDots.git"


def _b4_prose(n: int, word: str = "The model embeds sentences for semantic search. ") -> str:
    """Exactly n chars of harmless README prose (no fences, no screen terms)."""
    return (word * (n // len(word) + 1))[:n]


def _b4_readme_with_fence_at(at: int, cmd: str, total: int) -> str:
    head = _b4_prose(at - 1) + "\n"
    block = f"```bash\n{cmd}\n```\n"
    return head + block + _b4_prose(max(0, total - len(head) - len(block)))


def _b4_answer(cmd: str, url: str) -> dict:
    """A well-formed writer answer: 5 scenes plus a deliverable."""
    return {"title": "T",
            "scenes": [{"narration": f"scene {i} words", "visual_query": "person using laptop"}
                       for i in range(5)],
            "deliverable": {"kind": "command", "text": cmd, "url": url}}


def _b4_stub(monkeypatch, pages: dict, answer=None):
    """Stub every seam script_tool reaches, as the consumer sees it (ap.*)."""
    fetched, prompts = [], []

    def fake_fetch(u, limit=4000):
        fetched.append((u, limit))
        body = pages.get(u) or ""
        # the real fetch_text slices AFTER its 400-char floor; mirror that
        return body[:limit] if len(body) > 400 else ""

    monkeypatch.setattr(ap, "fetch_text", fake_fetch)
    monkeypatch.setattr(ap, "_verified_facts", lambda u: {})
    monkeypatch.setattr(ap, "_top_issues", lambda u: [])
    monkeypatch.setattr(ap.llm, "generate_json",
                        lambda p, **k: prompts.append(p) or answer)
    return fetched, prompts


# ------------------------------------------------------------ (a) eligibility
def test_b4_eligibility_is_github_repo_or_hf_model_only():
    assert ap.tool_source_eligible(_B4_GH)
    assert ap.tool_source_eligible(_B4_HF)
    assert not ap.tool_source_eligible(_B4_PH)
    assert not ap.tool_source_eligible("https://github.com/CopilotKit")          # an owner
    assert not ap.tool_source_eligible("https://github.com/o/r/issues/3")        # not a repo
    assert not ap.tool_source_eligible("")
    assert not ap.tool_source_eligible(None)


def test_b4_build_script_never_writes_a_product_hunt_candidate(monkeypatch):
    tried = []
    monkeypatch.setattr(ap, "script_tool", lambda c: tried.append(c["url"]) or None)
    monkeypatch.setattr(ap, "mark_failed", lambda t: None)
    monkeypatch.setattr(ap, "pick_evergreen_topic", lambda r: None)
    monkeypatch.setattr(ap, "script_news", lambda *a, **k: None)
    ap.build_script("tool", [{"title": "DevAlly AI Agent", "kind": "tool", "url": _B4_PH},
                             {"title": "CopilotKit/OpenDots", "kind": "tool", "url": _B4_GH}])
    assert tried == [_B4_GH], "a Product Hunt page must never cost a writer call"


def test_b4_skipped_candidates_do_not_consume_the_three_slots(monkeypatch):
    """"3 candidates tried" means 3 that CAN ground a tool video."""
    tried = []
    monkeypatch.setattr(ap, "script_tool", lambda c: tried.append(c["url"]) or None)
    monkeypatch.setattr(ap, "mark_failed", lambda t: None)
    monkeypatch.setattr(ap, "pick_evergreen_topic", lambda r: None)
    monkeypatch.setattr(ap, "script_news", lambda *a, **k: None)
    ph = [{"title": f"PH {i}", "kind": "tool", "url": f"https://www.producthunt.com/products/p{i}"}
          for i in range(3)]
    real = [{"title": f"repo {i}", "kind": "tool", "url": f"https://github.com/o/r{i}"}
            for i in range(2)] + [{"title": "hf", "kind": "tool", "url": _B4_HF},
                                  {"title": "repo 9", "kind": "tool", "url": "https://github.com/o/r9"}]
    ap.build_script("tool", ph + real)
    assert tried == ["https://github.com/o/r0", "https://github.com/o/r1", _B4_HF]


# ------------------------------------------------------------ (b) grounding window
def test_b4_fence_past_the_cut_reaches_the_writer_and_passes_containment(monkeypatch):
    """embeddinggemma-2: the card's first fence was at char 5,190."""
    card = _b4_readme_with_fence_at(5190, _B4_PIP, 6000)
    assert card.index("```") == 5190 and len(card) == 6000
    assert ap._first_fenced(card[:5000]) == "", "the old 5,000-char window had no fence"
    raw = ap._hf_readme_url(_B4_HF)
    fetched, prompts = _b4_stub(monkeypatch, {raw: card}, _b4_answer(_B4_PIP, _B4_HF))

    s = ap.script_tool({"title": "google/embeddinggemma-2 — trending feature extraction",
                        "source": "huggingface/trending", "url": _B4_HF})
    assert fetched == [(raw, ap.TOOL_README_FETCH)]
    assert ap.TOOL_README_FETCH == 20000
    assert f"```bash\n{_B4_PIP}\n```" in prompts[0], "the writer must see the fence"
    assert s is not None, "a command the card really shows must not be rejected"
    assert s["deliverable"]["text"] == _B4_PIP
    assert s["grounding"].startswith(card[:5000])
    assert ap.command_grounded(_B4_PIP, s["grounding"])
    assert ap._first_fenced(s["grounding"]) == _B4_PIP


def test_b4_appended_fence_also_repairs_an_invented_command(monkeypatch):
    """_first_fenced must see the appended block too: an invented flag is replaced by
    the source's own command instead of rejecting the candidate."""
    card = _b4_readme_with_fence_at(5190, _B4_PIP, 6000)
    _b4_stub(monkeypatch, {ap._hf_readme_url(_B4_HF): card},
             _b4_answer(_B4_PIP + " --invented-flag", _B4_HF))
    s = ap.script_tool({"title": "embeddinggemma-2", "source": "hf", "url": _B4_HF})
    assert s["deliverable"]["text"] == _B4_PIP


def test_b4_github_readme_fence_past_the_cut_and_screen_reads_it(monkeypatch):
    """OpenDots: the README's first fence (git clone) was at char 7,227. The page is
    still read for SCREENING only, never handed to the writer."""
    readme = _b4_readme_with_fence_at(7227, _B4_CLONE, 9000)
    raw = ap._gh_readme_url(_B4_GH)
    chrome = "You signed in with another tab or window. " * 40
    fetched, prompts = _b4_stub(monkeypatch, {raw: readme, _B4_GH: chrome},
                                _b4_answer(_B4_CLONE, _B4_GH))
    screened = []
    real_gate = ap.gates.tool_unsuitable
    monkeypatch.setattr(ap.gates, "tool_unsuitable",
                        lambda t, text="": screened.append(text) or real_gate(t, text))
    s = ap.script_tool({"title": "CopilotKit/OpenDots", "source": "github/trending",
                        "url": _B4_GH})
    assert fetched == [(raw, ap.TOOL_README_FETCH), (_B4_GH, 5000)]
    assert _B4_CLONE in prompts[0] and "You signed in" not in prompts[0]
    assert s and s["deliverable"]["text"] == _B4_CLONE
    assert _B4_CLONE in screened[0] and "You signed in" in screened[0], \
        "the screen reads README (with the appended block) AND page"


def test_b4_fence_cut_by_the_window_is_replaced_not_duplicated(monkeypatch):
    """A block that opens at 4,980 and closes past 5,000 is cut. Left in, its dangling
    opening fence pairs with the appended block's and _first_fenced returns a
    truncated command."""
    cmd = "pip install some-really-long-package-name another-package"
    card = _b4_readme_with_fence_at(4980, cmd, 6000)
    assert ap._first_fenced(card[:5000]) == ""
    _b4_stub(monkeypatch, {ap._hf_readme_url(_B4_HF): card},
             _b4_answer(cmd + " --invented", _B4_HF))
    s = ap.script_tool({"title": "embeddinggemma-2", "source": "hf", "url": _B4_HF})
    assert s["deliverable"]["text"] == cmd
    assert s["grounding"].count("```bash") == 1


def test_b4_fence_inside_the_window_leaves_grounding_byte_identical(monkeypatch):
    card = _b4_readme_with_fence_at(100, _B4_PIP, 8000) + "TAILMARKER"
    _, prompts = _b4_stub(monkeypatch, {ap._hf_readme_url(_B4_HF): card},
                          _b4_answer(_B4_PIP, _B4_HF))
    s = ap.script_tool({"title": "embeddinggemma-2", "source": "hf", "url": _B4_HF})
    assert s["grounding"] == card[:5000], "today's 5,000-char window, byte for byte"
    assert "TAILMARKER" not in prompts[0]


def test_b4_no_fence_anywhere_is_still_rejected(monkeypatch):
    card = _b4_prose(9000)
    _b4_stub(monkeypatch, {ap._hf_readme_url(_B4_HF): card},
             _b4_answer("pip install invented", _B4_HF))
    assert ap.script_tool({"title": "embeddinggemma-2", "source": "hf",
                           "url": _B4_HF}) is None


def test_b4_github_page_fallback_never_appends(monkeypatch):
    """A repo with no raw README grounds on the page as before; nothing is appended."""
    page = _b4_prose(3000)
    _, prompts = _b4_stub(monkeypatch, {ap._gh_readme_url(_B4_GH): "", _B4_GH: page},
                          _b4_answer("pip install invented", _B4_GH))
    assert ap.script_tool({"title": "o/r", "source": "gh", "url": _B4_GH}) is None
    assert page in prompts[0] and "```" not in prompts[0]


def test_b4_fetch_failure_still_fails_soft(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(ap.llm, "generate_json", lambda *a, **k: calls.append(1))
    for answer in ("", None):
        monkeypatch.setattr(ap, "fetch_text", lambda u, limit=4000, a=answer: a)
        assert ap.script_tool({"title": "t", "source": "hf", "url": _B4_HF}) is None
        assert ap.script_tool({"title": "t", "source": "gh", "url": _B4_GH}) is None
    assert calls == [], "a failed fetch must never cost a writer call"
    assert "grounding too thin" in capsys.readouterr().out


# ------------------------------------------------------------ (c) visible rejection
def test_b4_writer_with_no_valid_script_says_so(monkeypatch, capsys):
    card = _b4_readme_with_fence_at(100, _B4_PIP, 6000)
    _b4_stub(monkeypatch, {ap._hf_readme_url(_B4_HF): card}, {"scenes": []})
    assert ap.script_tool({"title": "embeddinggemma-2", "source": "hf",
                           "url": _B4_HF}) is None
    assert "writer returned no valid tool script — rejected." in capsys.readouterr().out
