"""
Render SAMPLE outputs without uploading anything:
  * one long-form YouTube video (with the person-first thumbnail)
  * one YouTube Short
  * one Instagram Reel (IG-native CTA) + its ready-to-paste caption

Run:  python scripts/make_samples.py [news|evergreen|roundup]

Everything lands in output/samples/ for easy review. No YouTube/IG calls happen.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factverse import config as fv                      # noqa: E402
from factverse import ai_pipeline as ap                 # noqa: E402


def main() -> int:
    forced = next((a for a in sys.argv[1:] if a in ("news", "evergreen", "roundup")), None)
    report = ap.run(publish=False, force_format=forced)
    if not report:
        print("❌ Sample run failed — see messages above.")
        return 1

    samples = fv.OUTPUT / "samples"
    samples.mkdir(parents=True, exist_ok=True)

    def _abs(p):
        return str(p) if not p or Path(p).is_absolute() else str(fv.BASE / p)

    long_video = _abs(report.get("video"))
    shorts = [_abs(s) for s in (report.get("shorts") or [])]
    thumb = _abs(report.get("thumbnail"))
    meta = report.get("shorts_meta") or []

    out = {}
    if long_video and Path(long_video).exists():
        out["long_video"] = str(shutil.copy2(long_video, samples / f"SAMPLE_LONG_{Path(long_video).name}"))
    if thumb and Path(thumb).exists():
        out["thumbnail"] = str(shutil.copy2(thumb, samples / f"SAMPLE_THUMB_{Path(thumb).name}"))
    if shorts:
        out["youtube_short"] = str(shutil.copy2(shorts[0], samples / f"SAMPLE_SHORT_{Path(shorts[0]).name}"))
        # The Reel is the same vertical format; give it the IG caption for a true sample.
        reel_src = shorts[1] if len(shorts) > 1 else shorts[0]
        out["instagram_reel"] = str(shutil.copy2(reel_src, samples / f"SAMPLE_REEL_{Path(reel_src).name}"))
        cap = (meta[1] if len(meta) > 1 else (meta[0] if meta else {})).get("instagram_caption", "")
        cap_file = samples / "SAMPLE_REEL_caption.txt"
        cap_file.write_text(cap + "\n\n(Reminder: IG links go in the bio, not the caption.)",
                            encoding="utf-8")
        out["instagram_reel_caption"] = str(cap_file)

    (samples / "SAMPLES.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n" + "=" * 60)
    print("  📦 SAMPLES READY")
    for k, v in out.items():
        print(f"  {k:24s} {v}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
