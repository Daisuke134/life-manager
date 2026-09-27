#!/usr/bin/env python3
"""Render one Larry/native-carousel slide as a JPEG.

Native-tool choice (ponytail rung 5): Pillow is already an installed
dependency on this host and, unlike this machine's ImageMagick build, its
freetype support actually rasterizes CJK glyphs from system .ttc fonts --
verified by hand before wiring this in (blank/tofu boxes would silently
defeat the "no blank slides" gate check).

usage: render-slide-image.py <out_file> <width> <height> <text>
Reads background/foreground/font/pointsize from env so the caller (Node)
never has to shell-escape a text argument through extra flags.
"""
import os
import sys
import textwrap

from PIL import Image, ImageDraw, ImageFont

FALLBACK_FONTS = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
]


def load_font(point_size):
    candidates = [os.environ.get("SLIDE_FONT_PATH", "")] + FALLBACK_FONTS
    for path in candidates:
        if path and os.path.isfile(path):
            try:
                return ImageFont.truetype(path, point_size)
            except OSError:
                continue
    return ImageFont.load_default()


def wrap_text(draw, text, font, max_width):
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for ch in paragraph:
            trial = current + ch
            box = draw.textbbox((0, 0), trial, font=font)
            if box[2] - box[0] > max_width and current:
                lines.append(current)
                current = ch
            else:
                current = trial
        lines.append(current)
    return lines


def main():
    out_file, width, height, text = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    background = os.environ.get("SLIDE_BACKGROUND", "#141b2d")
    foreground = os.environ.get("SLIDE_FOREGROUND", "#f5f5f0")
    point_size = int(os.environ.get("SLIDE_POINT_SIZE", "56"))

    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    font = load_font(point_size)
    margin = int(width * 0.12)
    max_text_width = width - 2 * margin
    lines = wrap_text(draw, text, font, max_text_width)
    line_heights = [draw.textbbox((0, 0), line or " ", font=font)[3] for line in lines]
    line_gap = int(point_size * 0.35)
    total_height = sum(line_heights) + line_gap * (len(lines) - 1 if lines else 0)
    y = (height - total_height) / 2
    for line, line_height in zip(lines, line_heights):
        box = draw.textbbox((0, 0), line, font=font)
        line_width = box[2] - box[0]
        x = (width - line_width) / 2
        draw.text((x, y), line, font=font, fill=foreground)
        y += line_height + line_gap

    image.save(out_file, format="JPEG", quality=92)


if __name__ == "__main__":
    main()
