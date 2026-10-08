#!/usr/bin/env python3
"""caption_compose.py -- build the short-video caption for one post.

Creative judgment (the hook line's wording) goes through the shared
runtime/agent-runner/agent_runner.py the same way
skills/_shared/marketplace-core/scripts/reply_composer.py asks for a reply:
one schema-validated model call, read back from its evidence/summary.json.
Everything else -- which use-case words to mention, which hashtags, the
store URL -- is deterministic bookkeeping and stays in code (building-agents:
judgment belongs to the model, bookkeeping belongs to code).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[4]
AGENT_RUNNER = REPO_ROOT / "runtime/agent-runner/agent_runner.py"
SCHEMA = Path(__file__).resolve().parent.parent / "schemas" / "caption_hook.schema.json"

# Use-case label per clip id slug. The slug names already carry the motion's
# meaning (see set-*/plan.json "id" + "prompt"); this is a bookkeeping lookup,
# not a creative decision. An id missing from this table still works -- it
# just contributes no extra use-case word (falls back to the character name).
USE_CASE_BY_SLUG_SUBSTRING = {
    "thanks": "感謝",
    "ok-thumb": "了解",
    "sorry": "ごめんね",
    "goodnight": "おやすみ",
    "laugh": "笑い",
    "tears": "悲しい",
    "angry": "怒り",
    "sleepy": "眠い",
    "surprise": "驚き",
    "love": "大好き",
    "doit": "応援",
    "hello": "こんにちは",
    "bye": "バイバイ",
    "clap": "拍手",
    "cold": "寒い",
    "congrat": "おめでとう",
    "embarrass": "恥ずかしい",
    "morning": "おはよう",
}

DEFAULT_HASHTAGS = ["#LINEスタンプ", "#動くスタンプ", "#スタンプ"]

# Formats copied from top LINE creators' social accounts (docs/superpowers/specs/
# 2026-08-28-line-sticker-loop-design.md, "Social formats copied from top creators"):
# a daily-life/seasonal/reaction mini-story beats the clips with a short text overlay each,
# instead of only ever showing the sticker-sample "showcase" format.
CONTENT_TYPES = ("daily_life", "seasonal_hook", "reaction_pick", "showcase")
BEAT_CONTENT_TYPES = ("daily_life", "seasonal_hook", "reaction_pick")


def use_cases_for(clip_order: list[str]) -> list[str]:
    seen: list[str] = []
    for clip_id in clip_order:
        for needle, label in USE_CASE_BY_SLUG_SUBSTRING.items():
            if needle in clip_id and label not in seen:
                seen.append(label)
                break
    return seen


def pick_hashtags(character_name: str, seed_index: int) -> list[str]:
    tag_name = character_name.replace(" ", "")
    extra = [f"#{tag_name}"] if tag_name else []
    pool = DEFAULT_HASHTAGS + extra
    # rotate deterministically so consecutive posts don't read identically
    rotated = pool[seed_index % len(pool):] + pool[: seed_index % len(pool)]
    return rotated[: max(3, min(6, len(rotated)))]


def validate_content_plan(result: object, clip_count: int) -> dict:
    """Pure validation of the agent's {hook, content_type, beat_texts} contract.

    building-agents: the MODEL decides the hook wording AND which format (content_type)
    this slot uses, plus the per-beat text for a daily_life/seasonal_hook/reaction_pick
    mini-story; this function only enforces the bookkeeping contract (enum membership,
    beat count matching the clips actually chosen for this slot), it makes no creative
    choice itself.
    """
    if not isinstance(result, dict):
        raise RuntimeError("line_sticker_caption_contract_invalid")
    hook = result.get("hook")
    if not isinstance(hook, str) or not hook.strip():
        raise RuntimeError("line_sticker_caption_contract_invalid")
    content_type = result.get("content_type")
    if content_type not in CONTENT_TYPES:
        raise RuntimeError("line_sticker_content_type_invalid")
    beat_texts_raw = result.get("beat_texts") or []
    if not isinstance(beat_texts_raw, list):
        raise RuntimeError("line_sticker_beat_texts_invalid")
    beat_texts = [b.strip() for b in beat_texts_raw if isinstance(b, str) and b.strip()]
    if content_type in BEAT_CONTENT_TYPES:
        if not beat_texts:
            raise RuntimeError("line_sticker_beat_texts_invalid")
        # Reuse/trim deterministically to match the clips actually on screen -- the
        # model sees clip_count in the prompt, but a mismatch must not crash the slot.
        if len(beat_texts) < clip_count:
            beat_texts = (beat_texts * clip_count)[:clip_count]
        else:
            beat_texts = beat_texts[:clip_count]
    else:
        beat_texts = []
    return {"hook": hook.strip(), "content_type": content_type, "beat_texts": beat_texts}


def call_agent_runner(
    *, title_ja: str, use_cases: list[str], clip_count: int, recent_content_types: list[str],
    task_label: str, state_root: Path,
) -> dict:
    avoid = ", ".join(recent_content_types) if recent_content_types else "（直近の投稿なし）"
    prompt = (
        "LINEスタンプ販促の短尺動画を1本作る。フォーマットとフック行をあなたが選ぶ。\n"
        "まず content_type を次の4つから1つ選ぶ（直近の投稿形式と同じものは避けて、"
        "上位のLINEスタンプ作者のSNS運用を真似る）:\n"
        "  daily_life: キャラクターの日常のワンシーン（共感できる一コマ）\n"
        "  seasonal_hook: 今の季節・行事に絡めたワンシーン\n"
        "  reaction_pick: 「どれ送る？」のようにこのクリップ群から選ばせるリアクション企画\n"
        "  showcase: スタンプの見本紹介（通常フォーマット）\n"
        f"直近の投稿で使った content_type: {avoid}\n"
        "daily_life/seasonal_hook/reaction_pick を選んだ場合は beat_texts も書く: "
        f"このスロットのクリップは{clip_count}個あるので、各クリップに合わせた短い日本語の一言を"
        f"{clip_count}個、配列で順番通りに書く（各18文字以内、絵文字なし、2〜4コマのミニストーリーになるように）。"
        "showcase を選んだ場合は beat_texts は空配列でよい。\n"
        "hook はキャプション冒頭の一文。絵文字は使わない。URLやハッシュタグは書かない（コード側で付与する）。"
        "40文字以内、煽りすぎない、使いたくなる一言。\n"
        f"スタンプ名: {title_ja}\n"
        f"このクリップで映す用途の例: {', '.join(use_cases) if use_cases else '（指定なし）'}\n"
    )
    state_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".caption-compose-", dir=state_root) as temporary:
        evidence = Path(temporary) / "evidence"
        done = subprocess.run(
            [sys.executable, str(AGENT_RUNNER), "--task-class", "composition-agent",
             "--prompt-stdin", "--schema", str(SCHEMA), "--evidence-dir", str(evidence),
             "--task-label", task_label, "--loop", task_label, "--workdir", str(REPO_ROOT)],
            input=prompt, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=90, check=False,
        )
        if done.returncode != 0:
            raise RuntimeError("line_sticker_caption_compose_failed")
        try:
            summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
            result_path = Path(str(summary["result_path"])).resolve()
            result_path.relative_to(evidence.resolve())
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, KeyError, TypeError, ValueError):
            raise RuntimeError("line_sticker_caption_compose_failed") from None
    return validate_content_plan(result, clip_count)


def build_caption(
    *,
    hook: str,
    title_ja: str,
    use_cases: list[str],
    store_url: str,
    hashtags: list[str],
    include_link: bool = True,
) -> str:
    """include_link=False drops the store URL line entirely (Dais 2026-10-07:
    a brand-new account's first days carry no outbound link, only
    "LINEスタンプで『<title>』と検索")."""
    if include_link and not store_url.startswith("https://"):
        raise ValueError("store_url must be an https URL")
    if include_link:
        lines = [hook, f"「{title_ja}」をLINEスタンプで検索"]
    else:
        lines = [hook, f"LINEスタンプで『{title_ja}』と検索"]
    if use_cases:
        lines.append("・".join(use_cases))
    if include_link:
        lines.append(store_url)
    lines.append(" ".join(hashtags))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title-ja", required=True)
    parser.add_argument("--character-name", default="")
    parser.add_argument("--store-url", required=True)
    parser.add_argument("--clip-order", required=True, help="comma-separated clip ids")
    parser.add_argument("--seed-index", type=int, default=0)
    parser.add_argument("--task-label", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--hook", default=None, help="skip the agent_runner call (tests / dry-run)")
    parser.add_argument("--content-type", default="showcase", choices=CONTENT_TYPES)
    parser.add_argument("--no-link", action="store_true", help="drop the store URL (new accounts)")
    args = parser.parse_args(argv)

    clip_order = [c for c in args.clip_order.split(",") if c]
    use_cases = use_cases_for(clip_order)
    hashtags = pick_hashtags(args.character_name, args.seed_index)
    if args.hook:
        hook, content_type = args.hook, args.content_type
    else:
        plan = call_agent_runner(
            title_ja=args.title_ja, use_cases=use_cases, clip_count=len(clip_order) or 1,
            recent_content_types=[], task_label=args.task_label,
            state_root=Path(args.state_root).expanduser(),
        )
        hook, content_type = plan["hook"], plan["content_type"]
    caption = build_caption(
        hook=hook, title_ja=args.title_ja, use_cases=use_cases,
        store_url=args.store_url, hashtags=hashtags, include_link=not args.no_link,
    )
    print(json.dumps(
        {"caption": caption, "hook": hook, "content_type": content_type, "hashtags": hashtags},
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
