"""
L2 batch synthesis — human-AUTHORED, machine-VOICED editorial blocks.

Eliminates manual voice recording while preserving the thing the monetization
policy actually requires: the take itself must be the operator's. The workflow:

    1. python scripts/make_l2_batch.py --draft
         Generates l2_store/takes.md with LLM-drafted takes based on the week's
         topics. Every draft carries an EDIT-ME marker.
    2. The operator EDITS the file — rewrites, sharpens, deletes, adds. This is
         the human-authorship step and it is enforced: the script refuses to
         synthesize any file still carrying the marker.
    3. python scripts/make_l2_batch.py
         Synthesizes every take into l2_store/{cold_opens,insight_blocks}/ and
         logs authorship metadata to state/l2_takes.jsonl (originality dossier).

Voice backends (config: l2_voice_backend):
    kokoro (default) — a dedicated "operator" voice, distinct from the two
        narrators. Fully licensed (Apache). Zero setup.
    xtts — clones the operator's real voice from assets/voice_sample.wav.
        ⚠ Coqui XTTS ships under the CPML NON-COMMERCIAL license: do NOT use
        this backend for videos on a monetized channel. It exists for local
        preview only. A commercially-licensed cloning backend (OpenVoice V2,
        MIT) is the planned upgrade — see the backlog.

Recorded audio always wins: if you drop real recordings into the store, they
are used before generated ones (l2.py picks clips in name order).
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factverse import config as fv        # noqa: E402
from factverse import llm                 # noqa: E402
from factverse import tts_kokoro          # noqa: E402

TAKES = fv.BASE / "l2_store" / "takes.md"
MARKER = "<!-- DRAFT: edit every take, then delete this line to unlock synthesis -->"
LOG = fv.STATE / "l2_takes.jsonl"


def draft() -> int:
    topics = []
    runs = fv.STATE / "runs.jsonl"
    if runs.exists():
        for line in runs.read_text(encoding="utf-8").splitlines()[-14:]:
            try:
                t = json.loads(line).get("title")
                if t:
                    topics.append(t)
            except json.JSONDecodeError:
                continue
    d = llm.generate_json(
        "Draft editorial takes for an AI-news channel operator to EDIT (they will rewrite "
        "these in their own words — make them opinionated starting points, not filler). "
        f"Recent topics: {'; '.join(topics[-8:]) or 'AI news broadly'}\n"
        "Return ONLY JSON {\"cold_opens\":[5 x 2-sentence energetic video openers (generic "
        "enough to fit any AI story)], \"insights\":[5 x 3-5 sentence PERSONAL takes — what "
        "most coverage gets wrong, what it means for people building things, a position]}")
    co = (d or {}).get("cold_opens") or ["Big move in AI today — and it matters more than the headline suggests. Let me show you why."] * 5
    ins = (d or {}).get("insights") or ["Here's my take: most people will ignore this until it's everywhere. The builders who move early on shifts like this are the ones who end up owning the category."] * 5
    lines = [MARKER, "", "# L2 takes — EDIT THESE. They ship in your voice, under your name.", "",
             "## COLD OPENS", ""]
    lines += [f"- {t}" for t in co[:5]]
    lines += ["", "## INSIGHTS", ""]
    lines += [f"- {t}" for t in ins[:5]]
    TAKES.parent.mkdir(parents=True, exist_ok=True)
    TAKES.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Drafted {TAKES} — edit every take, delete the marker line, then rerun without --draft.")
    return 0


def _parse() -> dict:
    text = TAKES.read_text(encoding="utf-8")
    if MARKER.split(":")[0] in text:
        print("REFUSING: takes.md still carries the DRAFT marker.")
        print("Edit the takes (that edit is the human-authorship requirement), delete the "
              "marker line, and rerun. Unedited LLM takes would reopen the originality gap "
              "this system exists to close.")
        raise SystemExit(2)
    out, section = {"cold_opens": [], "insights": []}, None
    for line in text.splitlines():
        u = line.strip()
        if u.upper().startswith("## COLD"):
            section = "cold_opens"
        elif u.upper().startswith("## INSIGHT"):
            section = "insights"
        elif u.startswith("- ") and section:
            out[section].append(u[2:].strip())
    return out


def synthesize() -> int:
    takes = _parse()
    backend = str(fv.setting("l2_voice_backend", "kokoro")).lower()
    op_voice = str(fv.setting("l2_kokoro_voice", "bm_george"))
    if backend == "xtts":
        print("⚠ XTTS backend: Coqui CPML is NON-COMMERCIAL. Local preview only —")
        print("  do not publish monetized videos with this backend.")
    stamp = dt.datetime.now().strftime("%Y%m%d")
    made = 0
    for kind, folder in (("cold_opens", "cold_opens"), ("insights", "insight_blocks")):
        dest = fv.BASE / "l2_store" / folder
        dest.mkdir(parents=True, exist_ok=True)
        for i, text in enumerate(takes[kind], 1):
            out = dest / f"gen_{stamp}_{i:02d}.wav"
            ok = None
            if backend == "xtts":
                from factverse import voice as vc
                ok = vc.synth_clone(text, str(out)) if vc.available() else None
            if ok is None and tts_kokoro.available():
                ok = tts_kokoro.synth(text, str(out), voice=op_voice)
            if ok:
                made += 1
                with open(LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"date": stamp, "kind": kind, "file": out.name,
                                        "text": text, "author": "human-edited",
                                        "backend": backend}, ensure_ascii=False) + "\n")
                print(f"  ✅ {out.name}  ({len(text.split())} words)")
            else:
                print(f"  ❌ synthesis failed for {kind} #{i}")
    print(f"\n{made} take(s) synthesized into l2_store/. Recorded audio, when present, "
          f"is still preferred automatically.")
    return 0 if made else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", action="store_true", help="generate takes.md for editing")
    args = ap.parse_args()
    if args.draft or not TAKES.exists():
        sys.exit(draft())
    sys.exit(synthesize())
