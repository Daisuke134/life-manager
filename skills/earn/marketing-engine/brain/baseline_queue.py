#!/usr/bin/env python3
"""Materialize the first seven-day, product-isolated ebook script baselines."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from script_ledger import ScriptLedger


JA = [
    ("スマホを置きたい夜", "通知を見るたびに画面を開いてしまう", "反応する前に一息おける", "スマホを伏せて息を一回吐く"),
    ("返事を急いでしまう時", "まだ考えたいのにすぐ返してしまう", "返事は一度読んでから決めてよい", "返事を書いたら一度読み返す"),
    ("予定が重なる朝", "やることが多くて最初の一つを選べない", "今できる一つから始めてよい", "今日最初にする用事を一つ紙に書く"),
    ("会話の後で気になる夜", "言えなかったことを何度も考えてしまう", "今の気持ちは短い言葉で確かめられる", "気になっていることを一文だけ書く"),
    ("作業が進まない午後", "別の作業へ何度も手を伸ばしてしまう", "いま取り組む一つを決めてよい", "机の上で今使う道具を一つ選ぶ"),
    ("頼みを断れない時", "予定があってもすぐ引き受けてしまう", "確認する時間を取ってから答えてよい", "予定を確かめてから返すと一言伝える"),
    ("一日を振り返る夜", "できなかったことばかり数えてしまう", "できた小さな行動も一日の一部", "今日終えたことを一つ書く"),
]
EN = [
    ("When the room feels too loud", "your thoughts keep asking for an answer", "a thought is a visitor, not a command", "name one sound you can hear"),
    ("When enough never arrives", "each win creates another demand", "wanting changes; it does not define you", "write down one thing already here"),
    ("When you compare your life", "someone else's pace makes yours feel small", "no path stays fixed for long", "feel both feet on the floor"),
    ("When a mistake follows you", "you replay one moment as if it is the whole story", "the past cannot be held in this breath", "lower your shoulders once"),
    ("When you rush to prove yourself", "rest feels like losing", "urgency also rises and passes", "choose only the next kind step"),
    ("When you feel alone", "you assume no one could understand", "loneliness moves like weather", "make a warm drink for yourself"),
    ("When change scares you", "letting go feels like disappearing", "breath continues inside every change", "open a window and breathe slowly"),
]


def row(product: str, day: int, slot: int, parts: tuple[str, str, str, str]) -> dict:
    ja = product == "ebook-ja"
    hook, pain, teaching, action = parts
    suffixes = ("。静かに続ける。", "。急がず一度だけする。", "。終えたら今へ戻る。") if ja else (". Stay with it for one moment", ". Do it once without rushing", ". Then return to this moment")
    action += suffixes[slot - 1]
    cta = "アニッチャ・リセットを読む" if ja else "Read The Anicca Reset"
    body = (f"{hook}。{pain}。{teaching}。{action}{cta}。" if ja else
            f"{hook}. {pain.capitalize()}. {teaching.capitalize()}. {action[:1].upper() + action[1:]}. {cta}.")
    return {
        "schema_version": "marketing.ebook-script.v1", "product_id": product,
        "account_id": f"product:{product}", "language": "ja" if ja else "en",
        "version": "2" if ja else "1", "parent_script_id": None,
        "source_mechanism_ids": [f"baseline.owner-authored.{product}.{'avatar-v2.' if ja else ''}{day}.{slot}"],
        "hook": hook, "pain_angle": pain, "teaching": teaching, "action": action,
        "cta": cta, "hypothesis": "structured baseline: compare one culturally authored pain angle",
        "declared_mutation": "action", "baseline": True,
        "campaign_id": f"baseline.{product}.{'avatar-v2.' if ja else ''}d{day}.s{slot}",
        "creative_id": f"baseline.{product}.{'avatar-v2.' if ja else ''}d{day}.s{slot}",
        "renderer_id": "heygen-avatar-iv",
        "primary_metric": "contribution_margin", "maturity_window": "72h",
        "stop_rule": "three comparable mature losses", "body": body,
    }


def materialize(ledger: ScriptLedger, product: str) -> list[dict]:
    themes = JA if product == "ebook-ja" else EN
    output = []
    for day, theme in enumerate(themes, start=1):
        for slot in range(1, 4):
            script = row(product, day, slot, theme)
            receipt = ledger.register(script)
            output.append({**script, "script_id": receipt["script_id"], "semantic_signature": receipt["semantic_signature"]})
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    ledger = ScriptLedger(args.ledger)
    for product in ("ebook-ja", "ebook-en"):
        rows = materialize(ledger, product)
        (args.output_dir / f"{product}.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        print(f"{product}={len(rows)}")


if __name__ == "__main__":
    main()
