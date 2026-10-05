#!/usr/bin/env python3
"""Model judgment for the LINE sticker factory: theme/motion plan, character art, 24-of-30 selection.

Every creative or taxonomic decision (theme, motions, listing copy, which 24 candidates, tags,
taste/character category) goes through ``runtime/agent-runner/agent_runner.py`` so the judgment is
the model's, not a hardcoded rule. This module only shapes prompts, calls the runner, generates the
one deterministic asset (the character reference image via the OpenAI image API + ffmpeg padding)
and validates the runner's JSON against the schemas next to it.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
AGENT_RUNNER = REPO_ROOT / "runtime/agent-runner/agent_runner.py"
TAGS_FILE = Path(os.environ.get("LIFE_MANAGER_STATE_HOME", str(Path.home() / ".local/state/life-manager"))) / "line-sticker" / "tags-ja.json"
TASTE_OPTIONS = {
    "1": "カワイイ・キュート", "18": "ラブリー", "2": "かっこいい", "3": "シュール", "4": "ユニーク",
    "5": "ポップ", "6": "ナチュラル", "7": "シンプル", "8": "大人かわいい", "9": "ほのぼの",
}
CHARACTER_OPTIONS = {
    "10": "ネコ", "11": "ウサギ", "12": "イヌ", "13": "クマ", "14": "トリ", "19": "パンダ",
    "20": "アザラシ", "15": "食べ物", "21": "名前", "16": "その他",
}


def _run_agent(*, prompt: str, schema: Path, evidence_dir: Path, task_label: str, images: list[Path] | None = None) -> dict:
    cmd = [sys.executable, str(AGENT_RUNNER), "--task-class", "marketing-agent", "--prompt-stdin",
           "--schema", str(schema), "--evidence-dir", str(evidence_dir), "--task-label", task_label,
           "--loop", "line-sticker-factory", "--workdir", str(REPO_ROOT)]
    for image in images or []:
        cmd += ["--image", str(image)]
    done = subprocess.run(cmd, input=prompt, text=True, capture_output=True, timeout=1800, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"agent_runner_failed:{task_label}:{done.returncode}:{done.stderr[-500:]}")
    summary = json.loads((evidence_dir / "summary.json").read_text(encoding="utf-8"))
    result_path = Path(str(summary["result_path"])).resolve()
    result_path.relative_to(evidence_dir.resolve())
    return json.loads(result_path.read_text(encoding="utf-8"))


def planner(set_dir: Path, prior_listings: list[dict]) -> dict:
    prior_titles = [listing.get("title", {}) for listing in prior_listings]
    prompt = f"""あなたはLINE Creators Marketで売れている「動くスタンプ」の企画者。hoko525のような、
オリジナルの可愛いマスコットキャラクターが大きく動くアニメスタンプを1セット企画する。

要件:
- character_id: このキャラクター固有の短い英数字スラッグ（例: char-foo-001）。
- character_prompt: gpt-image-2に渡す英語プロンプト。オリジナルでシンプルな可愛いマスコット、
  背景は完全な単色クロマグリーン#00FF00で画面全体を埋める、キャラクター自体に緑色を一切使わない、
  文字・ロゴ・透かしなし、という条件を明記する。
- motions: ちょうど30個。毎日のチャットで使う意図（ありがとう・OK・ごめん・おやすみ・笑う・泣く・
  怒る・眠い・驚く・大好き・がんばる 等）を幅広くカバーし、各motionは一言はっきり分かる大きな動き。
  各要素は id（短い英数字スラッグ、重複不可）と prompt（Seedance画像to動画モデル向けの英語の動き指示、
  キャラクターが何をするか明確に）。表情のピークが遅いmotionは start を1.0程度にしてよい（省略可、
  省略時は0.0扱い）。
- listing: title/description を日本語・英語の両方で。説明は「24種類、毎日使える、文字なしなので
  誰にでも送れる」という趣旨を含める。

既存セットのタイトル（これらとテーマ・キャラクターを必ず変える）: {json.dumps(prior_titles, ensure_ascii=False)}

JSON Schemaに厳密に従ったJSONだけを返す。"""
    with tempfile.TemporaryDirectory(prefix=".plan-", dir=set_dir) as tmp:
        return _run_agent(prompt=prompt, schema=HERE / "schemas/plan.schema.json",
                           evidence_dir=Path(tmp) / "evidence", task_label=f"line-sticker-plan-{set_dir.name}")


def _sample_bg_color(png_path: Path) -> str:
    from PIL import Image
    rgb = Image.open(png_path).convert("RGB").getpixel((8, 8))
    return "0x%02X%02X%02X" % rgb


def character_image(set_dir: Path, plan_draft: dict) -> None:
    request = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=json.dumps({
            "model": "gpt-image-2", "prompt": plan_draft["character_prompt"],
            "size": "1024x1024", "background": "opaque",
        }).encode(),
        headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"], "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.load(response)
    image_b64 = result["data"][0]["b64_json"]
    char_ref = set_dir / "char-ref.png"
    char_ref.write_bytes(base64.b64decode(image_b64))
    (set_dir / "char-ref.receipt.json").write_text(json.dumps(
        {"model": "gpt-image-2", "prompt": plan_draft["character_prompt"], "usage": result.get("usage", {})},
        indent=1, ensure_ascii=False,
    ))
    bg = _sample_bg_color(char_ref)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(char_ref),
        "-vf", f"scale=640:640,pad=1024:1024:192:240:color={bg}",
        str(set_dir / "ref-padded.png"),
    ], check=True)


def selector(set_dir: Path, plan: dict) -> dict:
    motion_ids = [m["id"] for m in plan["motions"]]
    grid = [{"row": index // 6, "col": index % 6, "id": motion_id} for index, motion_id in enumerate(motion_ids)]
    tags = json.loads(TAGS_FILE.read_text()) if TAGS_FILE.exists() else []
    sheet = set_dir / "candidates-sheet.png"
    prompt = f"""添付の画像は候補スタンプの一覧シート（{set_dir / 'candidates-sheet.png'}）。6列グリッドで、
各セルは1候補の代表フレーム。セルの行・列とモーションidの対応は次の通り（row,col,id）:
{json.dumps(grid, ensure_ascii=False)}

タスク:
1. 明らかに壊れている候補（背景が緑以外に変色、キャラクターが欠けている・変形している等）を rejected に入れ、
   除外する。
2. 残りから24個を選び order に入れる（見た目のバリエーションと使いやすさを優先、文字なし）。
3. 24個のうち、メインアイコンにふさわしい1つを main、タブアイコンにふさわしい1つを tab として選ぶ。
4. listing.title / listing.description を日本語・英語で確定する（既存の下書き: {json.dumps(plan.get('listing', {}), ensure_ascii=False)}）。
5. tags: orderの1番目を"01"、2番目を"02"、...24番目を"24"として、各sticker_numberごとに日本語タグを
   以下の有効リストだけから4〜6個（最大9個）選ぶ。リストにない語は使わない。
   有効タグ一覧: {json.dumps(tags, ensure_ascii=False)}
6. taste_id: 次の候補からこのキャラクターに最も合うものを1つ選ぶ: {json.dumps(TASTE_OPTIONS, ensure_ascii=False)}
7. character_category_id: 次の候補から1つ選ぶ: {json.dumps(CHARACTER_OPTIONS, ensure_ascii=False)}
8. campaign_value は null にする（キャンペーン不参加）。

JSON Schemaに厳密に従ったJSONだけを返す。orderはちょうど24個の重複のないidにする。"""
    with tempfile.TemporaryDirectory(prefix=".select-", dir=set_dir) as tmp:
        return _run_agent(prompt=prompt, schema=HERE / "schemas/selection.schema.json",
                           evidence_dir=Path(tmp) / "evidence", task_label=f"line-sticker-select-{set_dir.name}",
                           images=[sheet])
