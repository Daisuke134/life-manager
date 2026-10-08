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
import io
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


def _build_plan_prompt(prior_facts: list[dict], market_items: list[dict] | None = None) -> str:
    market_items = market_items or []
    return f"""あなたはLINE Creators Marketで売れている「動くスタンプ」の企画者。

今日のLINE STORE上位（top_creators/new_creators、継続的に再取得される市場データ。古い場合は
null）。各項目は product_id/title/author/price_jpy/format/sticker_count/description/
text_or_no_text/theme/art_style/phrases/author_sets:
{json.dumps(market_items, ensure_ascii=False, indent=1)}

まず copy_target を1つ選ぶ: 上の市場データの中で、このキャラクターに当てはめて最も真似しやすい
勝ちパターンを1件選び、product_url・theme・phrases（真似する意図/フレーズ一覧）・
expression_style（表現スタイル）・text_or_no_text・title_pattern（タイトルの付け方）を記録する。
真似するのは「売れ筋の企画パターン」（テーマ・文字有無・タイトルの付け方・表現の意図）であり、
他者のキャラクター・絵・文字そのものを複製してはならない（LINEのAI/知的財産ガイドラインを守り、
キャラクターと絵はオリジナルにする）。
市場データが大半 static または文字入りの場合、このセットは動く・文字なしで作る（既存方針）ことを
踏まえ、format_gap に一言でそのギャップを記録する（例: "上位は静止画・文字入りが多いが今回は
動く・文字なしで作る"）。ギャップが無ければ null にする。

既存セットの傾向（上位作者は例外なく既存キャラクターのシリーズ（1キャラにつき5〜36セット）を
売っている。単発の新キャラクターは上位に一つも無い）: タイトルは「動く！」/「うごく」を先頭に付け
「<キャラ名>の<シーン>」の形、続編には vol./数字を付ける。テーマは頻度順に 汎用日常返事 → 敬語・
仕事 → 季節イベント（年末年始など） → 家族・推し活 を優先する。

既存セットの事実（新しいセットを計画する前に必ず読む。set=ディレクトリ名、
state_observed=LINE Creators Marketで最後に確認した公式状態、例: 販売中/審査待ち/リジェクト、
sales_jpy=LINE Creators Marketの公式売上・統計情報/送金申請ページで確認した累計売上（分配額の
速報値、円）。null は「まだ確認できていない」という意味で0円ではない）:
{json.dumps(prior_facts, ensure_ascii=False, indent=1)}

まず series_of を決める:
- sales_jpy が数値（nullでない）のセットが1つでもあれば、その中で売上が最も大きいキャラクターの
  続編を最優先する。実際に売れている実績は、state_observedだけの判断より優先する。
- sales_jpy がまだどのセットもnullの場合（売上データがまだ無い）は、既存キャラクター（できれば
  state_observed が「販売中」のもの）の続編を強く優先する。
- 続編にする場合: series_of にそのセットのset名（例: "set-003"）を入れ、character_id と
  character_prompt はそのキャラクターの説明（character_description）を引き継ぐ。続編では画像を
  再利用するため character_prompt は画像生成に使われないが、記録としてそのキャラクターの見た目を
  書く。motions とテーマはそのキャラクターの過去セット（theme/motions）と重複しない新しいシーンに
  する。キャラの日本語の名前はシリーズで1つに固定する: 同じキャラ（同じ series_of 元）の過去セットの
  タイトルに出てくる日本語の名前のうち最も古いセットのものをそのまま使い、新しい名前を作らない
  （上位作者は1キャラ1名で何十セットも出す。名前が毎回違うと同じシリーズに見えない）。
- 新キャラクターを立てる方が明らかに良い場合（例: 既存キャラクターが一つも販売中でない、過去の
  テーマを使い切った）だけ series_of を null にし、新しい character_id / character_prompt を
  企画する。

要件:
- series_of: 続編なら既存セットのset名の文字列、新キャラクターなら null。
- theme: 今回のセットのテーマを一言で（上の頻度順を優先）。
- character_id: このキャラクター固有の短い英数字スラッグ（例: char-foo-001）。続編なら既存のものを
  そのまま使う。
- character_prompt: 画像生成モデルに渡す英語プロンプト。新キャラクターの場合はオリジナルでシンプルな
  可愛いマスコット、背景は完全な単色クロマグリーン#00FF00で画面全体を埋める、キャラクター自体に
  緑色を一切使わない、文字・ロゴ・透かしなし、という条件を明記する。
- motions: ちょうど30個。毎日のチャットで使う意図（ありがとう・OK・ごめん・おやすみ・笑う・泣く・
  怒る・眠い・驚く・大好き・がんばる 等）を幅広くカバーし、各motionは一言はっきり分かる大きな動き。
  各要素は id（短い英数字スラッグ、重複不可）と prompt（Seedance画像to動画モデル向けの英語の動き指示、
  キャラクターが何をするか明確に）。表情のピークが遅いmotionは start を1.0程度にしてよい（省略可、
  省略時は0.0扱い）。
- listing: title/description を日本語・英語の両方で。タイトルは「動く！」/「うごく」+
  「<キャラ名>の<シーン>」パターンに従い、続編なら vol./数字を付ける。説明は「24種類、毎日使える、
  文字なしなので誰にでも送れる」という趣旨を含める。

JSON Schemaに厳密に従ったJSONだけを返す。"""


def planner(set_dir: Path, prior_facts: list[dict], market_items: list[dict] | None = None) -> dict:
    prompt = _build_plan_prompt(prior_facts, market_items)
    with tempfile.TemporaryDirectory(prefix=".plan-", dir=set_dir) as tmp:
        return _run_agent(prompt=prompt, schema=HERE / "schemas/plan.schema.json",
                           evidence_dir=Path(tmp) / "evidence", task_label=f"line-sticker-plan-{set_dir.name}")


IMAGE_MODEL = "gemini-3.1-flash-image"


def _sample_bg_color(png_path: Path) -> str:
    from PIL import Image
    rgb = Image.open(png_path).convert("RGB").getpixel((8, 8))
    return "0x%02X%02X%02X" % rgb


def _character_image_gemini(plan_draft: dict) -> tuple[bytes, dict]:
    # Gemini image: the OpenAI org ran out of credit on 2026-10-05 while this key stays funded.
    # Fallback only (Dais 2026-10-08: image generation must be cost-free via the ChatGPT
    # subscription first - see chatgpt_image_backend.py).
    body = {"contents": [{"parts": [{"text": plan_draft["character_prompt"]}]}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "1:1"}}}
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{IMAGE_MODEL}:generateContent?key="
        + os.environ["GEMINI_API_KEY"],
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.load(response)
    parts = result["candidates"][0]["content"]["parts"]
    image_b64 = next(part["inlineData"]["data"] for part in parts if "inlineData" in part)
    return base64.b64decode(image_b64), {"model": IMAGE_MODEL, "usage": result.get("usageMetadata", {})}


def character_image(set_dir: Path, plan_draft: dict) -> None:
    import chatgpt_image_backend as chatgpt

    char_ref = set_dir / "char-ref.png"
    from PIL import Image
    try:
        out_path = chatgpt.generate(plan_draft["character_prompt"] + " Flat 2D illustration, "
                                     "solid flat pure chroma green (#00FF00) background filling "
                                     "the entire frame, no text, no logo, no watermark.")
        try:
            Image.open(out_path).convert("RGB").save(char_ref)
        finally:
            out_path.unlink(missing_ok=True)
        receipt = {"backend": "chatgpt_imagegen", "prompt": plan_draft["character_prompt"], "cost_usd": "0"}
    except chatgpt.ChatGptImageGenUnavailable as exc:
        chatgpt.log_fallback(f"character_image:{set_dir.name}", exc)
        image_bytes, meta = _character_image_gemini(plan_draft)
        Image.open(io.BytesIO(image_bytes)).convert("RGB").save(char_ref)
        receipt = {"backend": "gemini_fallback", "prompt": plan_draft["character_prompt"], "cost_usd": "0.02", **meta}
    (set_dir / "char-ref.receipt.json").write_text(json.dumps(receipt, indent=1, ensure_ascii=False))
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
   タイトルは下書きの「動く！<キャラ名>の<シーン>」形を崩さない。<キャラ名>は下書きのものを変えない（シリーズで固定）。キャラ固有の名前とこのセットのテーマ（例: 敬語、仕事、季節）を必ず入れ、
   「かわいい〇〇の毎日スタンプ」のような誰とでも重なる汎用タイトルにしない（既存タイトルと重複すると申請できない）。
   長さは全角を2・半角を1と数えて38以内（日本語なら全角19文字程度まで）。続編は vol.2 などを付ける。
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
