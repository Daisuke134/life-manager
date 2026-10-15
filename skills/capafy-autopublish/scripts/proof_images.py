#!/usr/bin/env python3
"""Render up to 4 listing proof images from a catalog item's real output ($0, Pillow only).

Winners show output proof in the listing description (HookAce embeds 6 images). This takes
the "Actual output" part of the item's evidence/ or test/ markdown, splits it at "## "
headings, and draws one 1080x1350 card per section. CP1 inserts them into the description
editor (CP1_AGENTIC.md, Basic Info). Usage: proof_images.py <catalog_item_dir> <out_dir>
"""
from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path

MAX_CARDS = 4
META = re.compile(r"boundary|diagnosis|honesty|verification|notes|evidence|input|constraint", re.I)
MAX_BODY = 700
W, H = 1080, 1350
BG, INK, ACCENT, MUTED = (244, 237, 223), (26, 22, 18), (255, 90, 31), (110, 100, 90)
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def sections(markdown: str) -> list[tuple[str, str]]:
    """(heading, body) for the first sections of the real output, input excluded."""
    if "## Actual output" not in markdown:  # inputs/expectations are not proof of output
        return []
    text = markdown.split("## Actual output", 1)[1]
    out = []
    for block in re.split(r"(?m)^## ", text)[1:]:
        heading, _, body = block.partition("\n")
        if META.search(heading):  # explanatory notes, not the deliverable a buyer gets
            continue
        body = re.sub(r"```[a-z]*\n?|```", "", body)
        lines = []
        for line in body.splitlines():
            if re.fullmatch(r"\s*\|?[\s:|-]+\|?\s*", line) and "-" in line:
                continue  # table rule row
            if line.strip().startswith("|"):
                line = " · ".join(c.strip() for c in line.strip().strip("|").split("|"))
            lines.append(line.replace("**", "").replace("`", ""))
        body = "\n".join(lines).strip()
        if body:
            out.append((heading.strip(), body[:MAX_BODY].rstrip()))
        if len(out) == MAX_CARDS:
            break
    return out


def _source(item_dir: Path) -> Path | None:
    for pattern in ("evidence/*.md", "test/*.md"):
        found = sorted(item_dir.glob(pattern))
        if found:
            return found[0]
    return None


def render(item_dir: Path, out_dir: Path) -> list[Path]:
    from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415

    src = _source(item_dir)
    if src is None:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    title_font, head_font, body_font, small = (ImageFont.truetype(BOLD, 40), ImageFont.truetype(BOLD, 52),
                                               ImageFont.truetype(FONT, 34), ImageFont.truetype(BOLD, 28))
    name = re.search(r"^# (.+)$", src.read_text(), re.M)
    product = (name.group(1) if name else item_dir.name).split("—")[0].replace("Verified offline demonstration", "").strip(" -—")
    paths = []
    for i, (heading, body) in enumerate(sections(src.read_text()), 1):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((60, 60, 330, 112), radius=26, fill=ACCENT)
        d.text((84, 70), "REAL OUTPUT", font=small, fill=(255, 255, 255))
        d.text((60, 150), product[:40], font=title_font, fill=MUTED)
        y = 220
        for line in textwrap.wrap(heading, 30)[:2]:
            d.text((60, y), line, font=head_font, fill=INK)
            y += 66
        y += 30
        for para in body.splitlines():
            for line in textwrap.wrap(para.strip(), 50) or [""]:
                if y > H - 120:
                    break
                d.text((60, y), line, font=body_font, fill=INK)
                y += 46
        d.text((60, H - 80), f"{i} / {MAX_CARDS if len(sections(src.read_text())) >= MAX_CARDS else len(sections(src.read_text()))}",
               font=small, fill=MUTED)
        path = out_dir / f"proof-{i:02d}.png"
        img.save(path)
        paths.append(path)
    return paths


if __name__ == "__main__":
    for p in render(Path(sys.argv[1]), Path(sys.argv[2])):
        print(p)
