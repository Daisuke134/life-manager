"""article_daily.py -- one free Japanese article per day on aniccaai.com for an on-sale sticker set.

aniccaai.com is the shared site for everything Life Manager ships (Dais 2026-10-08), so the sticker
sell loop publishes there through the same free-article publisher capafy-distribute-daily uses
(skills/earn/capafy-marketing/scripts/capafy_free_article.py). Top sticker creators announce each
new set with a short post of the character, the everyday scenes it fits and the store link; the
model writes that copy, code owns the slug, the single store link, the PII gate and the ledger.

Date-gated and best-effort like engagement_daily.py: runs in the JST 12:00 hour only (between the
11:15 and 13:15 reel slots and Capafy's 10:15/13:15 article slots on the same landing checkout),
at most MAX_ATTEMPTS per day, and never blocks the reel pass that follows it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
from pick_set import choose_set, load_on_sale_sets  # noqa: E402

AGENT_RUNNER = REPO_ROOT / "runtime/agent-runner/agent_runner.py"
SCHEMA = HERE.parent / "schemas" / "sticker_article.schema.json"
PUBLISHER = REPO_ROOT / "skills/earn/capafy-marketing/scripts/capafy_free_article.py"
PII_GATE = REPO_ROOT / "skills/writer-agent/scripts/pii-gate.py"
JST = ZoneInfo("Asia/Tokyo")
PUBLISH_HOUR = 12
MAX_ATTEMPTS = 2


def due(now: dt.datetime, ledger: dict) -> bool:
    local = now.astimezone(JST)
    entry = ledger.get(local.date().isoformat(), {})
    return local.hour == PUBLISH_HOUR and entry.get("status") != "published" \
        and entry.get("attempts", 0) < MAX_ATTEMPTS


def build_markdown(title: str, body: str, store_url: str) -> str:
    """The store link is bookkeeping: appended once by code, never left to the model."""
    return f"# {title.strip()}\n\n{body.strip()}\n\n[LINE STOREでスタンプを見る]({store_url})\n"


def _prompt(chosen: dict) -> str:
    return (
        "LINEスタンプの新作紹介記事を日本語で1本書く。売れているスタンプ作者が新作を出したときの"
        "ブログ投稿と同じ形にする: キャラクターの紹介、どんな場面で使えるか（具体的な会話の例を3〜5個）、"
        "このスタンプならではの良さ。600〜1000文字、見出しは「## 」で2〜4個、絵文字なし、誇張しない。"
        "URLは書かない（リンクはコード側で付ける）。AIであることや運営者名は書かない。\n"
        f"スタンプ名: {chosen['title_ja']}\n"
        f"キャラクター名: {chosen.get('character_name') or '（タイトル参照）'}\n"
        "title は記事タイトル（32文字以内、スタンプ名を含める）、body は本文のMarkdown（H1なし）。"
    )


def compose(chosen: dict, state_root: Path, task_label: str) -> dict:
    with tempfile.TemporaryDirectory(prefix=".article-compose-", dir=state_root) as temporary:
        evidence = Path(temporary) / "evidence"
        done = subprocess.run(
            [sys.executable, str(AGENT_RUNNER), "--task-class", "composition-agent",
             "--prompt-stdin", "--schema", str(SCHEMA), "--evidence-dir", str(evidence),
             "--task-label", task_label, "--loop", task_label, "--workdir", str(REPO_ROOT)],
            input=_prompt(chosen), text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=300, check=False,
        )
        if done.returncode != 0:
            raise RuntimeError("line_sticker_article_compose_failed")
        summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
        result = json.loads(Path(summary["result_path"]).read_text(encoding="utf-8"))
    if not result.get("title", "").strip() or len(result.get("body", "")) < 200:
        raise RuntimeError("line_sticker_article_contract_invalid")
    return result


def _publisher():
    spec = importlib.util.spec_from_file_location("capafy_free_article", PUBLISHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(now: dt.datetime, sticker_root: Path, state_root: Path) -> dict:
    ledger_path = state_root / "article-ledger.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    if not due(now, ledger):
        return {"state": "not_due"}
    date = now.astimezone(JST).date().isoformat()
    chosen = choose_set(load_on_sale_sets(sticker_root), f"article:{date}")
    if chosen is None:
        return {"state": "no_on_sale_set"}
    entry = {"attempts": ledger.get(date, {}).get("attempts", 0) + 1, "set_id": chosen["set_id"]}
    ledger[date] = entry
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=1))
    run_dir = state_root / "articles" / date
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        article = compose(chosen, state_root, f"line-sticker-article-{date}")
        draft = run_dir / "article-ja.md"
        draft.write_text(build_markdown(article["title"], article["body"], chosen["store_url"]))
        gate = subprocess.run([sys.executable, str(PII_GATE), str(draft)], capture_output=True, text=True)
        if gate.returncode != 0:
            raise RuntimeError(f"pii_gate_blocked: {gate.stdout[-200:]}{gate.stderr[-200:]}")
        result = _publisher().publish(
            draft_path=draft, slug=f"line-sticker-{chosen['set_id']}-{date}", cta_url=chosen["store_url"],
            landing_root=Path(os.environ["ARTICLE_SELF_OWNED_LANDING_ROOT"]),
            remote=os.environ.get("ARTICLE_SELF_OWNED_REMOTE", "origin"),
            branch=os.environ.get("ARTICLE_SELF_OWNED_BRANCH", "main"),
            base_url=os.environ["ARTICLE_SELF_OWNED_BASE_URL"], date=date, retries=40,
        )
        entry.update(status="published", url=result["url"], title=result["title"], commit=result["commit"])
    except (Exception, SystemExit) as error:  # best-effort: record, never block the reel pass
        entry.update(status="failed", error=f"{type(error).__name__}: {str(error)[:300]}")
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=1))
    return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--line-sticker-state-root", required=True)
    parser.add_argument("--state-root", required=True)
    args, _ = parser.parse_known_args(argv)
    state_root = Path(args.state_root).expanduser()
    state_root.mkdir(parents=True, exist_ok=True)
    result = run(dt.datetime.now(dt.timezone.utc), Path(args.line_sticker_state_root).expanduser(), state_root)
    print(json.dumps({"article_daily": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
