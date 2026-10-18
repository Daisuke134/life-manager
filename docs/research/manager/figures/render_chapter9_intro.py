"""Render chapter 9 teaching assets using the established research slide layout."""
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "content/2026-10-18-chapter9-intro"
FONT = FontProperties(fname="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
BOLD = FontProperties(fname="/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")


def main():
    data = json.loads((OUT / "slides.json").read_text())
    for aspect, size in [("landscape", (12, 6.75)), ("portrait", (6.75, 12))]:
        for index, slide in enumerate(data, 1):
            wide = aspect == "landscape"
            fig = plt.figure(figsize=size, facecolor="#f5f2eb")
            fig.text(.075, .925, "Ninja / マネージャー 第9単元", fontproperties=FONT,
                     fontsize=12, color="#b4452c")
            fig.text(.075, .81, slide["title"], fontproperties=BOLD,
                     fontsize=30 if wide else 25, va="top", color="#172823")
            fig.text(.075, .53, slide["body"], fontproperties=FONT,
                     fontsize=19 if wide else 16.5, va="top", linespacing=1.7,
                     color="#172823")
            fig.text(.075, .16, slide["note"], fontproperties=FONT,
                     fontsize=9 if wide else 8, color="#b4452c")
            fig.text(.075, .09, "出典・発表者ノート：slides.jsonと解説記事\n確認日：2026-10-18",
                     fontproperties=FONT, fontsize=8, color="#637069")
            fig.text(.93, .07, f"{index:02}/{len(data):02}", fontproperties=FONT,
                     fontsize=10, ha="right", color="#637069")
            fig.savefig(OUT / f"{aspect}-{index:02}.png", dpi=160)
            plt.close(fig)
    sections = []
    for index, slide in enumerate(data, 1):
        sources = " ".join(f'<a href="{html.escape(url, quote=True)}">出典{n}</a>'
                           for n, url in enumerate(slide["sources"], 1))
        sections.append(f'<section><small>Ninja / マネージャー {index}/{len(data)}</small>'
                        f'<h1>{html.escape(slide["title"])}</h1>'
                        f'<p>{html.escape(slide["body"])}</p>'
                        f'<aside>{html.escape(slide["note"])}</aside>{sources}'
                        f'<details><summary>発表者ノート</summary>'
                        f'<p>{html.escape(slide["speaker_notes"])}</p></details></section>')
    page = ('<!doctype html><html lang="ja"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>マネージャー 第9単元の導入</title><style>'
            'body{margin:0;background:#e2e5df;color:#172823;font-family:sans-serif}'
            'section{box-sizing:border-box;max-width:1100px;min-height:70vh;margin:24px auto;'
            'padding:6vw;background:#f5f2eb;break-after:page}h1{font-size:clamp(28px,4vw,52px)}'
            'h1,p{white-space:pre-line}p{font-size:clamp(18px,2.2vw,28px);line-height:1.8}'
            'small,aside{color:#b4452c}a{margin-right:1em}details p{font-size:18px}'
            '@media print{body{background:white}section{margin:0;min-height:95vh;max-width:none}'
            'details{display:none}}</style>' + "".join(sections) + '</html>')
    (OUT / "deck.html").write_text(page)
    print(f"Rendered {len(data) * 2} PNGs and editable HTML")


if __name__ == "__main__":
    main()
