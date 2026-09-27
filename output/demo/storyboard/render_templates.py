"""Render every template at 3 moments (entering, mid-reveal, holding) + a contact sheet.
Run: py -3 output/demo/storyboard/render_templates.py"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE))
from factverse import storyboard as sb  # noqa: E402
from fixture import NARRATION, RAW, uniform_words  # noqa: E402

words, length = uniform_words(NARRATION)
board = sb.build_board(RAW, words, length, "arxiv.org")
for k, b in enumerate(board["beats"]):
    print(k, b["template"], b["start"], b["end"], [e.get("t") for e in b["els"]])

out = HERE / "templates"
out.mkdir(exist_ok=True)
from playwright.sync_api import sync_playwright  # noqa: E402
shots = []
with sync_playwright() as p:
    br = p.chromium.launch()
    page = br.new_page(viewport={"width": 1080, "height": 1920})
    page.goto(sb.PAGE.resolve().as_uri())
    page.wait_for_function("window.__ready === true")
    print("unfit:", page.evaluate("b => window.__load(b)", board))
    for k, b in enumerate(board["beats"]):
        reveals = sorted(e["t"] for e in b["els"] if e["t"] >= 0) or [b["start"]]
        mid = reveals[1] + 0.16 if len(reveals) > 1 else (b["start"] + b["end"]) / 2
        for tag, t in (("1-entering", max(0.0, reveals[0] + 0.16) if k else 0.0),
                       ("2-mid", min(mid, b["end"] - 0.1)), ("3-hold", b["end"] - 0.05)):
            page.evaluate("t => window.__seek(t)", t)
            path = out / f"{k}_{b['template']}_{tag}.png"
            page.screenshot(path=str(path))
            shots.append(path)
    br.close()

from PIL import Image  # noqa: E402
tw, th = 270, 480
sheet = Image.new("RGB", (tw * 3, th * len(board["beats"])), (40, 40, 40))
for i, pth in enumerate(shots):
    im = Image.open(pth).resize((tw, th))
    sheet.paste(im, ((i % 3) * tw, (i // 3) * th))
sheet.save(HERE / "templates_sheet.png")
print("sheet:", HERE / "templates_sheet.png", len(shots), "frames")
