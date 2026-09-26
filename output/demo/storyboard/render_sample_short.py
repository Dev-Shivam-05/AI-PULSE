"""v3-G.1 acceptance #2: one full storyboard Short through the PRODUCTION path.

Real: edge-tts voice (en-US-GuyNeural, config.json) with its word timings, shorts.make_shorts
with the storyboard branch, the Chromium render, the same mux/overlays as the control, and the
caption pass. Stubbed: the Shorts-moment LLM (one moment) and the storyboard model answer
(fixture.RAW) — no Gemini key exists locally.
Run: py -3 output/demo/storyboard/render_sample_short.py"""
import asyncio
import datetime as dt
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE))
from factverse import config as fv  # noqa: E402
from factverse import shorts as sh  # noqa: E402
from factverse import storyboard as sb  # noqa: E402
from fixture import NARRATION, RAW  # noqa: E402

import edge_tts  # noqa: E402

OUT = HERE / "sample"
OUT.mkdir(exist_ok=True)
audio = OUT / "voice.mp3"


async def tts():
    try:
        com = edge_tts.Communicate(NARRATION, "en-US-GuyNeural", rate="+12%", boundary="WordBoundary")
    except TypeError:
        com = edge_tts.Communicate(NARRATION, "en-US-GuyNeural", rate="+12%")
    words = []
    with open(audio, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                s = ch["offset"] / 1e7
                words.append((round(s, 3), round(s + ch["duration"] / 1e7, 3), ch["text"]))
    return words

words = asyncio.run(tts())
print(f"voice: {len(words)} timed words")

# the long-form "content video" the Short is cut from: here black 1280x720 + the voice
content = OUT / "content.mp4"
subprocess.run([fv.FFMPEG or "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=30",
                "-i", str(audio), "-shortest", "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac", str(content)], capture_output=True, check=True)

# stub only the two model calls
sh.eng.find_best_moments = lambda s: [{"scene_num": 1, "hook_text": "Your keyboard is a tiny AI"}]
sb.plan = lambda sub, length, dom: sb.build_board(RAW, sub, length, dom)
fv.CONFIG["storyboard_shorts"] = True
even_day = dt.date(2026, 10, 2)            # day-of-year 275 is odd -> use the 1st of Oct? check below
day = next(dt.date(2026, 10, d) for d in range(1, 8) if dt.date(2026, 10, d).timetuple().tm_yday % 2 == 0)
t0 = time.monotonic()
out = sh.make_shorts(str(content), {"scenes": [{"narration": NARRATION}]}, words,
                     scene_starts=[0.0], max_count=1, source_domain="arxiv.org", today=day)
print("shorts:", out, f"total {time.monotonic() - t0:.1f}s")
final = out[0]
assert "_sb_" in final, "the storyboard arm did not run"

# 12-frame contact sheet of the FINAL Short (overlays + captions included)
dur = float(subprocess.run([fv.FFPROBE or "ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", final], capture_output=True, text=True).stdout.strip())
frames = []
for i in range(12):
    t = dur * (i + 0.5) / 12
    fp = OUT / f"f{i:02d}.png"
    subprocess.run([fv.FFMPEG or "ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", final, "-frames:v", "1", str(fp)],
                   capture_output=True)
    frames.append((fp, t))
from PIL import Image, ImageDraw  # noqa: E402
tw, th = 270, 480
sheet = Image.new("RGB", (tw * 6, th * 2), (40, 40, 40))
for i, (fp, t) in enumerate(frames):
    im = Image.open(fp).resize((tw, th))
    ImageDraw.Draw(im).text((8, 8), f"{t:.1f}s", fill=(255, 255, 0))
    sheet.paste(im, ((i % 6) * tw, (i // 6) * th))
sheet.save(HERE / "sample_short_sheet.png")
Path(final).replace(OUT / "sample_short.mp4")
print("sheet:", HERE / "sample_short_sheet.png", f"duration {dur:.1f}s")
