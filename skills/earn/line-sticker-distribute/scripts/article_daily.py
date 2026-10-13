"""article_daily.py -- slot-gated free Japanese aniccaai.com articles for on-sale sticker sets.

aniccaai.com is the shared site for everything Life Manager ships (Dais 2026-10-08), so the sticker
sell loop publishes there through the same free-article publisher capafy-distribute-daily uses
(skills/earn/capafy-marketing/scripts/capafy_free_article.py). Top sticker creators announce each
new set with a short post of the character, the everyday scenes it fits and the store link; the
model writes that copy, code owns the slug, the single store link, the PII gate and the ledger.

Slot-gated and best-effort like engagement_daily.py: one article per PUBLISH_HOURS slot (JST, 15 a day; not
10/13, when Capafy publishes to the same landing checkout), at most MAX_ATTEMPTS per slot, never
blocking the reel pass that follows it. Sets that have no article yet are written first (Dais
2026-10-11: distribute beyond Instagram/Threads; each on-sale set gets its own searchable page).
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
PUBLISH_HOURS = (7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23)  # not 10/13: Capafy's slots
ROTATION_HOUR = 12  # once every set has an article, one a day
MAX_ATTEMPTS = 2


def slot_key(now: dt.datetime) -> str:
    local = now.astimezone(JST)
    return f"{local.date().isoformat()}@{local.hour:02d}"


def due(now: dt.datetime, ledger: dict) -> bool:
    entry = ledger.get(slot_key(now), {})
    return now.astimezone(JST).hour in PUBLISH_HOURS and entry.get("status") != "published" \
        and entry.get("attempts", 0) < MAX_ATTEMPTS


def pick(sets: list[dict], ledger: dict, seed_key: str, *, hour: int) -> dict | None:
    """An on-sale set without a published article first (every slot); once all have one, only the
    ROTATION_HOUR slot writes, so the site is not flooded with repeats of the same sets."""
    covered = {e.get("set_id") for e in ledger.values() if isinstance(e, dict) and e.get("status") == "published"}
    fresh = [s for s in sets if s["set_id"] not in covered]
    if fresh:
        return choose_set(fresh, seed_key)
    return choose_set(sets, seed_key) if hour == ROTATION_HOUR else None


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


def _compose_failure_class(evidence: Path) -> str:
    try:
        summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "diagnostic_unavailable"
    if not isinstance(summary, dict):
        return "diagnostic_unavailable"

    def safe_class(value: object) -> str | None:
        if isinstance(value, str) and 0 < len(value) <= 80 and all(
            char.isalnum() or char in "_:.-" for char in value
        ):
            return value
        return None

    reason = safe_class(summary.get("reason"))
    if reason:
        return reason
    attempts_path = summary.get("attempts_path")
    if isinstance(attempts_path, str):
        path = Path(attempts_path)
        try:
            if path.resolve().is_relative_to(evidence.resolve()) and path.is_file():
                for line in path.read_text(encoding="utf-8").splitlines():
                    attempt = json.loads(line)
                    if isinstance(attempt, dict):
                        error_class = safe_class(attempt.get("error_class"))
                        if error_class:
                            return error_class
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
    return "agent_runner_failed"


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
            raise RuntimeError(
                f"line_sticker_article_compose_failed:{done.returncode}:"
                f"{_compose_failure_class(evidence)}"
            )
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
    key = slot_key(now)
    chosen = pick(load_on_sale_sets(sticker_root, require_clips=False), ledger, f"article:{key}", hour=now.astimezone(JST).hour)
    if chosen is None:
        return {"state": "no_set_for_this_slot"}
    entry = {"attempts": ledger.get(key, {}).get("attempts", 0) + 1, "set_id": chosen["set_id"]}
    ledger[key] = entry
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=1))
    run_dir = state_root / "articles" / key.replace("@", "-")
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        article = compose(chosen, state_root, f"line-sticker-article-{key.replace('@', '-')}")
        draft = run_dir / "article-ja.md"
        draft.write_text(build_markdown(article["title"], article["body"], chosen["store_url"]))
        gate = subprocess.run([sys.executable, str(PII_GATE), str(draft)], capture_output=True, text=True)
        if gate.returncode != 0:
            raise RuntimeError(f"pii_gate_blocked: {gate.stdout[-200:]}{gate.stderr[-200:]}")
        result = _publisher().publish(
            draft_path=draft, slug=f"line-sticker-{chosen['set_id']}-{key.replace('@', '-')}", cta_url=chosen["store_url"],
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
