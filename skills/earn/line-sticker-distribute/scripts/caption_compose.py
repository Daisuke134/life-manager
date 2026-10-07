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


def call_agent_runner(*, title_ja: str, use_cases: list[str], task_label: str, state_root: Path) -> str:
    prompt = (
        "LINEスタンプ販促の短尺動画につける、日本語のフック行を1つ作る。\n"
        "ルール: 絵文字は使わない。URLやハッシュタグは書かない（コード側で付与する）。\n"
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
    hook = result.get("hook") if isinstance(result, dict) else None
    if not isinstance(hook, str) or not hook.strip():
        raise RuntimeError("line_sticker_caption_contract_invalid")
    return hook.strip()


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
    parser.add_argument("--no-link", action="store_true", help="drop the store URL (new accounts)")
    args = parser.parse_args(argv)

    clip_order = [c for c in args.clip_order.split(",") if c]
    use_cases = use_cases_for(clip_order)
    hashtags = pick_hashtags(args.character_name, args.seed_index)
    hook = args.hook or call_agent_runner(
        title_ja=args.title_ja, use_cases=use_cases,
        task_label=args.task_label, state_root=Path(args.state_root).expanduser(),
    )
    caption = build_caption(
        hook=hook, title_ja=args.title_ja, use_cases=use_cases,
        store_url=args.store_url, hashtags=hashtags, include_link=not args.no_link,
    )
    print(json.dumps({"caption": caption, "hook": hook, "hashtags": hashtags}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
