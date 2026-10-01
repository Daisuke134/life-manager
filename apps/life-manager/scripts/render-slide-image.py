#!/usr/bin/env python3
"""Compose one Larry/native-carousel slide: a photorealistic background
(already fetched/cached by marketing-slide-background-image.js -- this
script does no network calls and needs no API key) plus big bold outlined
title text, upper/middle third, max 2 lines.

Native-tool choice (ponytail rung 5): Pillow is already an installed
dependency and, unlike this machine's ImageMagick build, its freetype
support actually rasterizes CJK glyphs from system .ttc fonts -- verified by
hand before wiring this in.

usage: render-slide-image.py <bg_file> <out_file> <width> <height> <text>
Prints exactly one JSON line to stdout on success:
  {"luminance_std": 41.2, "text_contrast_ok": true}
so the Node-side gate can verify text legibility without re-decoding the
JPEG itself.
"""
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

BOLD_FONT = "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc"
FALLBACK_FONTS = [BOLD_FONT, "/System/Library/Fonts/Helvetica.ttc"]
MIN_POINT_SIZE_AT_1080 = 72
MAX_LINES = 2
# Text band: upper/middle third of the slide.
BAND_TOP_FRACTION = 0.12
BAND_BOTTOM_FRACTION = 0.55


def load_font(point_size):
    for path in FALLBACK_FONTS:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, point_size)
            except OSError:
                continue
    return ImageFont.load_default()


def wrap_to_lines(draw, text, font, max_width, max_lines):
    """Greedy char-wrap (correct for CJK, degrades gracefully for Latin)."""
    paragraphs = [p for p in text.split("\n") if p != ""] or [text]
    lines = []
    for paragraph in paragraphs:
        current = ""
        for ch in paragraph:
            trial = current + ch
            box = draw.textbbox((0, 0), trial, font=font)
            if box[2] - box[0] > max_width and current:
                lines.append(current)
                current = ch
            else:
                current = trial
        if current:
            lines.append(current)
    if len(lines) <= max_lines:
        return lines
    # Too long for max_lines at this size -- caller shrinks font and retries.
    return None


def fit_text(draw, text, width, max_lines, min_point_size):
    max_text_width = int(width * 0.86)
    point_size = int(min_point_size * (width / 1080))
    lines = None
    font = load_font(point_size)
    for _ in range(30):
        font = load_font(point_size)
        lines = wrap_to_lines(draw, text, font, max_text_width, max_lines)
        if lines is not None:
            break
        point_size = max(int(min_point_size * (width / 1080) * 0.6), int(point_size * 0.9))
        if point_size < 24:
            lines = wrap_to_lines(draw, text, load_font(point_size), max_text_width, 99) or [text]
            break
    return lines, font


def draw_scrim(image, top, bottom):
    """Dark gradient band behind the text so it reads on any background."""
    width, height = image.size
    scrim = Image.new("L", (1, height), 0)
    for y in range(height):
        if top <= y <= bottom:
            mid = (top + bottom) / 2
            dist = abs(y - mid) / max((bottom - top) / 2, 1)
            alpha = int(150 * max(0, 1 - dist ** 1.5))
        else:
            alpha = 0
        scrim.putpixel((0, y), alpha)
    scrim = scrim.resize((width, height))
    overlay = Image.new("RGBA", image.size, (10, 10, 15, 0))
    overlay.putalpha(scrim)
    image.alpha_composite(overlay)


def luminance(rgb):
    r, g, b = rgb[:3]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def measure_contrast(image, box):
    region = image.crop(box).convert("RGB")
    count = 0
    mean = 0.0
    m2 = 0.0
    bright_count = 0
    dark_count = 0
    for pixel in region.get_flattened_data():
        value = luminance(pixel)
        count += 1
        delta = value - mean
        mean += delta / count
        m2 += delta * (value - mean)
        bright_count += value > 200
        dark_count += value < 90
    if count == 0:
        return 0.0, False
    std = math.sqrt(m2 / count)
    bright = bright_count / count
    dark = dark_count / count
    # A legible white-fill/dark-outline title on any photo produces both a
    # meaningful bright cluster (the glyph fill) and a dark cluster (the
    # outline/scrim) with real separation -- a flat/blank slide never does.
    ok = std > 35 and bright > 0.03 and dark > 0.10
    return std, ok


def main():
    bg_file, out_file, width, height, text = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]

    background = Image.open(bg_file).convert("RGB").resize((width, height), Image.LANCZOS)
    canvas = background.convert("RGBA")

    band_top = int(height * BAND_TOP_FRACTION)
    band_bottom = int(height * BAND_BOTTOM_FRACTION)
    draw_scrim(canvas, band_top, band_bottom)

    draw = ImageDraw.Draw(canvas)
    lines, font = fit_text(draw, text, width, MAX_LINES, MIN_POINT_SIZE_AT_1080)

    line_boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    line_heights = [box[3] - box[1] for box in line_boxes]
    line_gap = int(font.size * 0.3)
    total_height = sum(line_heights) + line_gap * (len(lines) - 1)
    y = band_top + max(0, ((band_bottom - band_top) - total_height) // 2)
    stroke_width = max(3, font.size // 14)

    text_top, text_bottom = y, y
    for line, box, line_height in zip(lines, line_boxes, line_heights):
        line_width = box[2] - box[0]
        x = (width - line_width) / 2
        draw.text((x, y), line, font=font, fill="white", stroke_width=stroke_width, stroke_fill=(10, 10, 15, 255))
        text_bottom = y + line_height
        y += line_height + line_gap

    luminance_std, contrast_ok = measure_contrast(canvas, (0, text_top - 10, width, text_bottom + 10))

    canvas.convert("RGB").save(out_file, format="JPEG", quality=92)
    print(json.dumps({"luminance_std": round(luminance_std, 2), "text_contrast_ok": contrast_ok}))


if __name__ == "__main__":
    main()
