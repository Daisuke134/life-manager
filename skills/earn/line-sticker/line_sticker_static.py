#!/usr/bin/env python3
"""Static-sticker counterpart to the animated line (seedance_set.py / line_sticker_planner.py).

LINE STORE top_creators are 60% static stickers (no video, cheaper to make) and the animated
line is stalled on fal's 403 (balance). This module makes a static set through the SAME
character art (reused via ``series_of``, zero new character cost) with one Gemini image call per
sticker instead of a Seedance video call, and packages/validates it against LINE's official
static-sticker guideline (https://creator.line.me/en/guideline/sticker/, read 2026-10-08):
main 240x240, tab 96x74, sticker max 370x320 (even px), each file <=1MB, PNG, transparent, count
in {8,16,24,32,40}.

Kept in its own file (not line_sticker_planner.py / line_sticker.py) so it never collides with the
animated line's campaign/selector/copy_target edits happening in parallel.
"""
from __future__ import annotations

import base64
import datetime
import io
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import seedance_set  # noqa: E402 - reuse _key()/_fill_pinholes(), zero duplication
from line_sticker_planner import AGENT_RUNNER, TAGS_FILE, _run_agent  # noqa: E402

POLICY_PATH = HERE / "static_policy.json"
IMAGE_MODEL = "gemini-3.1-flash-image"
# ponytail: flat per-call estimate (Gemini does not return token/cost usage the way fal does);
# upgrade to metered cost if Gemini billing exposes it to this key.
STATIC_IMAGE_COST_USD = Decimal("0.02")
CANVAS = (320, 280)  # inside the 370x320 max, even dimensions, ~10px margin applied below
MARGIN_PX = 10
# 文字入り variant (SSOT 5.L row 5): lettering rendered deterministically with a macOS-bundled
# Japanese font referenced by path (never copied into git), so every sticker's text is legible and
# identical in style - image models garble Japanese glyphs.
FONT_CANDIDATES = (
    "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
)
TEXT_BAND_PX = 72  # bottom band reserved for the phrase; art shrinks into the rest
TEXT_STROKE_PX = 6
TEXT_MARK = {"ja": "【文字入り】", "en": " (with text)"}
GENERIC_TITLE_SUFFIXES = ("スタンプ", " Stickers", " stickers", " Sticker")


def _policy() -> dict:
    return json.loads(POLICY_PATH.read_text())


# --------------------------------------------------------------------------------------
# Plan: pick an existing character (series_of mandatory), N phrases copied from top-seller
# coverage, judgment delegated to the model via agent_runner (same mechanism as the animated
# planner's planner()).
# --------------------------------------------------------------------------------------

def _build_static_plan_prompt(prior_facts: list[dict], market_items: list[dict] | None = None) -> str:
    market_items = market_items or []
    return f"""あなたはLINE Creators Marketで売れている「静止画スタンプ」の企画者。

今日のLINE STORE上位（top_creators/new_creators、継続的に再取得される市場データ。古い場合は
null）。各項目は product_id/title/author/price_jpy/format/sticker_count/description/
text_or_no_text/theme/art_style/phrases/author_sets:
{json.dumps(market_items, ensure_ascii=False, indent=1)}

市場調査（2026-10-08の集計: 上位40件中24件が静止画スタンプ、15件が動くスタンプ、1件がポップアップ）:
上位作者の約6割は動かない静止画スタンプ（価格帯は¥190が中心）であり、動く系（¥250）は少数派。
静止画は生成コストが低いので数を作って広く展開するのに向く。既存のアニメ系シリーズと同じ
キャラクターを使い、1キャラにつき静止画・動くスタンプの両方を展開するのが上位作者の型。

まず copy_target を1つ選ぶ: 上の市場データの中から、できれば format が静止画のものを優先して、
このキャラクターに当てはめて最も真似しやすい勝ちパターンを1件選び、product_url・theme・
phrases（真似する意図/フレーズ一覧）・expression_style（表現スタイル）・text_or_no_text・
title_pattern（タイトルの付け方）を記録する。真似するのは「売れ筋の企画パターン」（テーマ・
文字有無・タイトルの付け方・表現の意図）であり、他者のキャラクター・絵・文字そのものを複製しては
ならない（LINEのAI/知的財産ガイドラインを守り、キャラクターと絵はオリジナルにする）。
copy_targetが動く系しか無い場合など、このセット（静止画・文字なし、既存方針）とズレがあれば
format_gap に一言で記録する（無ければ null）。

既存セットの事実（character_id・character_prompt・theme・state_observed・sales_jpy、set=ディレクトリ名）:
{json.dumps(prior_facts, ensure_ascii=False, indent=1)}

要件:
- series_of: 必ず既存セットのset名（例: "set-003"）を入れる。静止画セットは新キャラクターを作らず、
  既存キャラクターの絵を再利用する（画像コストを増やさない）。sales_jpy が数値のセットがあれば売上最大の
  キャラクターを選ぶ。どれもnullならstate_observedが「販売中」のキャラクターを選ぶ。
- character_id / character_prompt: 選んだキャラクターのものをそのまま引き継ぐ（画像は再利用、
  character_promptは記録用）。
- theme: 今回の静止画セットのテーマ（そのキャラクターの過去セットと重複しない）。
- text_mode: "no_text"（文字なし、既定）か "with_text"（文字入り）。上位作者は同じキャラで文字なし版と
  文字入り版（「了解」「ありがとう」「おつかれさま」等の短い文字で、場面に合うスタンプを選びやすい）の
  両方を売る。選んだキャラクターに文字なしセットが既にあり、copy_target が text_or_no_text="text" の
  売れ筋なら "with_text" を選ぶ（市場データの文字入り売れ筋を優先して copy_target にする）。
- stickers: ちょうど16個（LINEの静止画は8/16/24/32/40のいずれか、上位作者に多い16を使う）。毎日の
  チャットで使う意図（ありがとう・OK・ごめん・おやすみ・笑う・泣く・怒る・眠い・驚く・大好き・
  がんばる・はい・了解・お疲れ様・おはよう・こんにちは 等、上位作者の網羅パターンを参考に）を幅広く
  カバーし、各要素は id（短い英数字スラッグ、重複不可）、prompt（画像生成モデル向けの英語指示。
  キャラクターがそのポーズ・表情を1枚の静止画ではっきり表す。背景は完全な単色クロマグリーン
  #00FF00で画面全体を埋める、文字・ロゴ・透かしなし、という条件を明記する）、tags（LINEの有効タグ
  一覧から2〜4個、下の一覧だけから選ぶ）、text を持つ。画像そのものには文字を描かせない（prompt に
  文字を書かない）。text_mode が "with_text" なら text に上位作者の網羅パターンから写した短い日本語
  フレーズ（目安8文字以内、例: 了解・ありがとう・おつかれさま）を入れる（文字は後から決まった書体で
  描き込む）。"no_text" なら text は null。
- main_id / tab_id: stickersの中からメインアイコン・タブアイコンにふさわしいidを選ぶ。
- listing: title/descriptionを日本語・英語の両方で。キャラ名と「スタンプ」を含め、動く系と
  重複しないタイトルにする（既存タイトルと重複すると申請できない）。with_text なら
  「<キャラ名>の毎日返事」のような売れ筋の付け方にする（【文字入り】の表記は自動で付く）。

有効タグ一覧: {json.dumps(json.loads(TAGS_FILE.read_text()) if TAGS_FILE.exists() else [], ensure_ascii=False)}

JSON Schemaに厳密に従ったJSONだけを返す。stickersはちょうど16個の重複のないidにする。"""


def static_planner(set_dir: Path, prior_facts: list[dict], market_items: list[dict] | None = None) -> dict:
    prompt = _build_static_plan_prompt(prior_facts, market_items)
    with tempfile.TemporaryDirectory(prefix=".static-plan-", dir=set_dir) as tmp:
        plan = _run_agent(prompt=prompt, schema=HERE / "schemas/static-plan.schema.json",
                          evidence_dir=Path(tmp) / "evidence", task_label=f"line-sticker-static-plan-{set_dir.name}")
    if plan.get("text_mode") == "with_text":
        plan["listing"] = mark_text_listing(plan["listing"])
    return plan


def mark_text_listing(listing: dict) -> dict:
    """Title says it is the 文字入り version (market pattern), clamped so the mark survives
    line_sticker_submit._fit_listing's width-counted limit. Idempotent."""
    from line_sticker_submit import TITLE_MAX, _clean, _fit, _title_units  # lazy: submit imports playwright
    titles = {}
    for lang, title in listing["title"].items():
        mark = TEXT_MARK.get(lang, TEXT_MARK["en"])
        base = _clean(title)
        if base.endswith(mark.strip()):
            titles[lang] = title
            continue
        limit = TITLE_MAX - _title_units(mark)
        # Drop the generic "スタンプ"/"Stickers" tail before cutting mid-word
        # (48156132 was filed as "...毎日返事ス【文字入り】", 2026-10-08).
        for suffix in GENERIC_TITLE_SUFFIXES:
            if _title_units(base) > limit and base.endswith(suffix):
                base = base[: -len(suffix)].rstrip()
        titles[lang] = _fit(base, limit) + mark
    return dict(listing, title=titles)


# --------------------------------------------------------------------------------------
# Images: one Gemini image call per sticker, keyed off the green screen the same way the
# animated line keys its video frames (seedance_set._key / _fill_pinholes), fit to the static
# canvas with a margin.
# --------------------------------------------------------------------------------------

def _gemini_sticker_image(ref_path: Path, prompt: str):
    ref_b64 = base64.b64encode(ref_path.read_bytes()).decode()
    body = {
        "contents": [{"parts": [
            {"inlineData": {"mimeType": "image/png", "data": ref_b64}},
            {"text": prompt},
        ]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "1:1"}},
    }
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{IMAGE_MODEL}:generateContent?key="
        + os.environ["GEMINI_API_KEY"],
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.load(response)
    parts = result["candidates"][0]["content"]["parts"]
    image_b64 = next(part["inlineData"]["data"] for part in parts if "inlineData" in part)
    from PIL import Image
    image = Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB")
    return image, result.get("usageMetadata", {})


def _font(size: int):
    from PIL import ImageFont
    for path in FONT_CANDIDATES:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise FileNotFoundError("no bundled Japanese font in " + ", ".join(FONT_CANDIDATES))


def _draw_text(canvas, text: str) -> None:
    """Dark rounded-gothic lettering with a thick white outline, centred in the bottom band."""
    from PIL import ImageDraw
    draw = ImageDraw.Draw(canvas)
    max_width = CANVAS[0] - 2 * MARGIN_PX
    size = TEXT_BAND_PX - 2 * TEXT_STROKE_PX
    while True:
        font = _font(size)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font, stroke_width=TEXT_STROKE_PX)
        if right - left <= max_width or size <= 12:
            break
        size -= 2
    band_top = CANVAS[1] - MARGIN_PX - TEXT_BAND_PX
    x = (CANVAS[0] - (right - left)) // 2 - left
    y = band_top + (TEXT_BAND_PX - (bottom - top)) // 2 - top
    draw.text((x, y), text, font=font, fill=(60, 40, 40, 255), stroke_width=TEXT_STROKE_PX,
              stroke_fill=(255, 255, 255, 255))


def _fit_sticker(rgb_image, text: str | None = None) -> "object":
    import numpy as np
    from PIL import Image
    keyed = seedance_set._key(np.array(rgb_image))
    ys, xs = np.nonzero(keyed[..., 3] > 16)
    if ys.size == 0:
        top, bottom, left, right = 0, keyed.shape[0], 0, keyed.shape[1]
    else:
        top, bottom, left, right = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    art_height = CANVAS[1] - (TEXT_BAND_PX if text else 0)
    scale = min((CANVAS[0] - 2 * MARGIN_PX) / (right - left), (art_height - 2 * MARGIN_PX) / (bottom - top))
    size = (max(1, round((right - left) * scale)), max(1, round((bottom - top) * scale)))
    offset = ((CANVAS[0] - size[0]) // 2, (art_height - size[1]) // 2)
    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    canvas.paste(Image.fromarray(keyed[top:bottom, left:right], "RGBA").resize(size, Image.LANCZOS), offset)
    canvas = seedance_set._fill_pinholes(canvas)
    if text:
        _draw_text(canvas, text)
    return canvas


def _generate_sticker_image(ref_path: Path, character_prompt: str, sticker_prompt: str, task_label: str):
    """Cost-free ChatGPT subscription image first (Dais 2026-10-08); Gemini (image-conditioned on
    the character reference, paid) only when the CLI is unavailable or fails. ChatGPT-imagegen is
    generate-only (no reference-image input), so the character description is folded into the
    prompt text each time to keep the look consistent across stickers."""
    import chatgpt_image_backend as chatgpt
    from PIL import Image

    full_prompt = (f"{character_prompt} {sticker_prompt} Flat 2D illustration, solid flat pure "
                   "chroma green (#00FF00) background filling the entire frame, no text, no logo, "
                   "no watermark.")
    try:
        out_path = chatgpt.generate(full_prompt)
        try:
            image = Image.open(out_path).convert("RGB")
            image.load()
        finally:
            out_path.unlink(missing_ok=True)
        return image, "chatgpt_imagegen", Decimal("0")
    except chatgpt.ChatGptImageGenUnavailable as exc:
        chatgpt.log_fallback(task_label, exc)
        image, usage = _gemini_sticker_image(ref_path, sticker_prompt)
        return image, "gemini_fallback", STATIC_IMAGE_COST_USD


def static_images(set_dir: Path, plan: dict) -> None:
    """Generate every sticker in plan['stickers'] that is not already on disk (idempotent/resumable:
    a crash mid-set redoes only the missing ones, like seedance_set.clips())."""
    out = set_dir / "candidates"
    out.mkdir(exist_ok=True)
    ref = set_dir / plan.get("reference", "ref-padded.png")
    character_prompt = plan.get("character_prompt", "")
    with_text = plan.get("text_mode") == "with_text"
    for sticker in plan["stickers"]:
        png_path = out / f"{sticker['id']}.png"
        if png_path.exists():
            continue
        image, backend, cost = _generate_sticker_image(
            ref, character_prompt, sticker["prompt"], f"line-sticker-static-image-{set_dir.name}-{sticker['id']}")
        _fit_sticker(image, sticker.get("text") if with_text else None).save(png_path)
        (out / f"{sticker['id']}.cost.json").write_text(json.dumps(
            {"backend": backend, "estimated_usd": str(cost)}))


# --------------------------------------------------------------------------------------
# Package: numbered PNGs + main.png (240x240) + tab.png (96x74), plain PNG (no APNG chunks -
# static main/tab must NOT be animated, unlike the animated line's main.png).
# --------------------------------------------------------------------------------------

def static_package(set_dir: Path, order: list[str], main_id: str, tab_id: str) -> None:
    from PIL import Image
    policy = _policy()
    if len(order) not in policy["sticker_counts"] or len(set(order)) != len(order):
        sys.exit(f"order must name a distinct set of {policy['sticker_counts']} stickers")
    out = set_dir / "package"
    out.mkdir(exist_ok=True)
    candidates = set_dir / "candidates"
    names = [f"{number:02d}.png" for number in range(1, len(order) + 1)]
    for name, sticker_id in zip(names, order):
        Image.open(candidates / f"{sticker_id}.png").convert("RGBA").save(out / name)
    main = Image.open(candidates / f"{main_id}.png").convert("RGBA")
    main_fit = main.copy()
    main_fit.thumbnail((policy["main"]["width"], policy["main"]["height"]), Image.LANCZOS)
    main_canvas = Image.new("RGBA", (policy["main"]["width"], policy["main"]["height"]), (0, 0, 0, 0))
    main_canvas.paste(main_fit, ((policy["main"]["width"] - main_fit.width) // 2, (policy["main"]["height"] - main_fit.height) // 2))
    main_canvas.save(out / "main.png")
    tab = Image.open(candidates / f"{tab_id}.png").convert("RGBA")
    tab.thumbnail((policy["tab"]["width"], policy["tab"]["height"]), Image.LANCZOS)
    tab_canvas = Image.new("RGBA", (policy["tab"]["width"], policy["tab"]["height"]), (0, 0, 0, 0))
    tab_canvas.paste(tab, ((policy["tab"]["width"] - tab.width) // 2, (policy["tab"]["height"] - tab.height) // 2))
    tab_canvas.save(out / "tab.png")
    all_names = sorted(["main.png", "tab.png"] + names)
    with zipfile.ZipFile(out / "submission.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in all_names:
            archive.write(out / name, name)


def validate_static_package(root: Path, policy_path: Path = POLICY_PATH) -> dict:
    """Byte-verified acceptance record for one static package directory; reuses line_sticker.py's
    parse_png (same PNG-chunk parser the animated validator trusts) instead of a decoder."""
    from line_sticker import parse_png, PngError  # local import: keeps this module import-light for tests

    root = Path(root)
    policy = json.loads(Path(policy_path).read_text())
    errors: set[str] = set()
    counts = policy["sticker_counts"]
    try:
        actual = sorted(p.name for p in root.glob("*.png") if p.name not in ("main.png", "tab.png"))
    except OSError:
        actual = []
    count = len(actual)
    if count not in counts or actual != [f"{n:02d}.png" for n in range(1, count + 1)]:
        errors.add("sticker_count_invalid")
        count = max((c for c in counts if c <= count), default=counts[0])
    names = ["main.png", "tab.png"] + [f"{n:02d}.png" for n in range(1, count + 1)]
    max_file_bytes = int(policy["max_file_bytes"])
    for name in names:
        path = root / name
        if not path.is_file():
            errors.add(f"file_missing:{name}")
            continue
        if path.stat().st_size >= max_file_bytes:
            errors.add(f"file_too_large:{name}")
            continue
        try:
            parsed = parse_png(path)
        except PngError as exc:
            errors.add(f"{exc.code}:{name}")
            continue
        if parsed["animated"]:
            errors.add(f"animation_forbidden:{name}")
        if name == "main.png":
            expect = (policy["main"]["width"], policy["main"]["height"])
            if (parsed["width"], parsed["height"]) != expect:
                errors.add("dimensions_invalid:main.png")
        elif name == "tab.png":
            expect = (policy["tab"]["width"], policy["tab"]["height"])
            if (parsed["width"], parsed["height"]) != expect:
                errors.add("dimensions_invalid:tab.png")
        else:
            width, height = parsed["width"], parsed["height"]
            sticker_policy = policy["sticker"]
            if width > sticker_policy["max_width"] or height > sticker_policy["max_height"] or width % 2 or height % 2:
                errors.add(f"dimensions_invalid:{name}")
        if int(parsed["color_type"]) not in policy["required_color_types"]:
            errors.add(f"color_type_invalid:{name}")
    zip_path = root / "submission.zip"
    if not zip_path.is_file():
        errors.add("zip_missing")
    elif zip_path.stat().st_size >= int(policy["max_zip_bytes"]):
        errors.add("zip_too_large")
    else:
        try:
            with zipfile.ZipFile(zip_path) as archive:
                if set(archive.namelist()) != set(names):
                    errors.add("zip_membership_mismatch")
        except (OSError, zipfile.BadZipFile):
            errors.add("zip_invalid")
    errors_list = sorted(errors)
    return {"status": "ready" if not errors_list else "invalid", "sticker_count": count, "errors": errors_list}


# --------------------------------------------------------------------------------------
# Factory scheduling: static when fal is known-unavailable (marker written by factory's
# clips_runner wrapper on an observed HTTP 403), otherwise a simple rule that tracks the
# observed 60% static / 40% animated top-seller mix (deterministic bookkeeping, no model call -
# the model's judgment already went into planner vs static_planner's own content choices).
# --------------------------------------------------------------------------------------

# Market sweep 2026-10-08 (~/.local/state/life-manager/line-sticker/market.json, top 40 creators):
# 24 static / 15 animated / 1 popup -> target the static share among the two sticker formats.
TOP_SELLER_STATIC_SHARE = 24 / (24 + 15)


def choose_line_type(state_root: Path, recent_types: list[str], fal_unavailable_marker: dict | None,
                      *, stale_after: datetime.timedelta = datetime.timedelta(hours=24)) -> str:
    if fal_unavailable_marker:
        try:
            marked_at = datetime.datetime.fromisoformat(fal_unavailable_marker["at"])
            if datetime.datetime.now(datetime.timezone.utc) - marked_at < stale_after:
                return "static"
        except (KeyError, ValueError):
            return "static"
    if not recent_types:
        return "static"  # SSOT L19: most of the market is static; start there
    static_ratio = recent_types.count("static") / len(recent_types)
    return "static" if static_ratio < TOP_SELLER_STATIC_SHARE else "animated"


def fal_balance_marker(state_root: Path) -> Path:
    return state_root / "fal-unavailable.json"
