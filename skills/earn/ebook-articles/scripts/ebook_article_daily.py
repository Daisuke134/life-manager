"""ebook_article_daily.py -- slot-gated free aniccaai.com articles that sell The Anicca Reset.

2026-10-16: both eBook Instagram lanes need a human to post (English Monk Instagram has no Postiz
integration and Postiz refuses a new channel with 402; the Japanese lane's owner is fenced). Indie
authors get free buyers from search with useful posts on the book's theme and one link to the
book, so this lane copies line-sticker-articles (same publisher, PII gate, agent_runner compose,
ledger and fence shape) and needs no social account at all. aniccaai.com is the umbrella site for
every Life Manager product (Dais 2026-10-08).

The model writes the article; code owns the slot, slug, the single checkout link (the product's
destination_url from the marketing registry), the PII gate and the ledger. Best-effort: a failure
is recorded and the next slot tries again, at most MAX_ATTEMPTS per slot.
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
AGENT_RUNNER = REPO_ROOT / "runtime/agent-runner/agent_runner.py"
# Same {title, body} contract as the sticker articles.
SCHEMA = REPO_ROOT / "skills/earn/line-sticker-distribute/schemas/sticker_article.schema.json"
PUBLISHER = REPO_ROOT / "skills/earn/capafy-marketing/scripts/capafy_free_article.py"
PII_GATE = REPO_ROOT / "skills/writer-agent/scripts/pii-gate.py"
PRODUCTS = REPO_ROOT / "skills/earn/marketing-engine/registry/products"
JST = ZoneInfo("Asia/Tokyo")
# Hours no other aniccaai.com landing writer uses (stickers 7-9,11,12,14-23; writer 6-23).
SLOT_PRODUCTS = {1: "ebook-en", 2: "ebook-ja", 4: "ebook-en", 5: "ebook-ja"}
LANGUAGE = {"ebook-en": "en", "ebook-ja": "ja"}
MAX_ATTEMPTS = 2
RECENT_TITLES = 20


def product_for_hour(hour: int) -> str | None:
    return SLOT_PRODUCTS.get(hour)


def slot_key(now: dt.datetime) -> str:
    local = now.astimezone(JST)
    return f"{local.date().isoformat()}@{local.hour:02d}"


def slug_for(product_id: str, key: str) -> str:
    return f"{product_id}-{key.replace('@', '-')}"


def due(now: dt.datetime, ledger: dict) -> bool:
    entry = ledger.get(slot_key(now), {})
    return product_for_hour(now.astimezone(JST).hour) is not None \
        and entry.get("status") != "published" and entry.get("attempts", 0) < MAX_ATTEMPTS


def load_product(product_id: str) -> dict:
    product = json.loads((PRODUCTS / f"{product_id}.json").read_text(encoding="utf-8"))
    return {**product, "language": LANGUAGE[product_id]}


def build_markdown(title: str, body: str, url: str, cta: str) -> str:
    """The checkout link is bookkeeping: appended once by code, never left to the model."""
    return f"# {title.strip()}\n\n{body.strip()}\n\n[{cta}]({url})\n"


def prompt_for(product: dict, recent_titles: list[str]) -> str:
    claims = "; ".join(product["approved_claims"])
    avoid = "\n".join(f"- {title}" for title in recent_titles) or "- (none yet)"
    if product["language"] == "ja":
        return (
            "日本語で無料のブログ記事を1本書く。読者は「" + "、".join(product["audiences"]) + "」。"
            "売れている個人作家と同じ形にする: 本のテーマ（無常・内省・心を整える日々の問い）から、読者が今日"
            "そのまま試せる具体的な内省の方法や問いを1つ選び、手順と例で役に立つ記事にする。"
            "800〜1200文字、見出しは「## 」で2〜4個、絵文字なし、誇張や効果の約束はしない。"
            "URLは書かない（リンクはコード側で付ける）。AIであることや運営者名は書かない。"
            f"本について書いてよい事実はこれだけ: {claims}。\n"
            f"次のタイトルと同じテーマは避ける:\n{avoid}\n"
            "title は記事タイトル（32文字以内）、body は本文のMarkdown（H1なし）。"
        )
    return (
        "Write one free blog article in English for: " + "; ".join(product["audiences"]) + ". "
        "Copy what selling indie authors do: pick one concrete reflection practice or question from "
        "the book's theme (impermanence, everyday self-reflection, calming the mind) that the reader "
        "can try today, and make the article useful on its own with steps and an example. "
        "700-1100 words, 2-4 headings with '## ', no emoji, no hype or promised outcomes. "
        "Write no URL (code adds the link). Never mention AI or the operator. "
        f"The only facts you may state about the book: {claims}.\n"
        f"Avoid the topics of these earlier titles:\n{avoid}\n"
        "title is the article title (max 70 characters); body is the Markdown body (no H1)."
    )


def compose(product: dict, recent_titles: list[str], state_root: Path, task_label: str) -> dict:
    with tempfile.TemporaryDirectory(prefix=".article-compose-", dir=state_root) as temporary:
        evidence = Path(temporary) / "evidence"
        done = subprocess.run(
            [sys.executable, str(AGENT_RUNNER), "--task-class", "composition-agent",
             "--prompt-stdin", "--schema", str(SCHEMA), "--evidence-dir", str(evidence),
             "--task-label", task_label, "--loop", task_label, "--workdir", str(REPO_ROOT)],
            input=prompt_for(product, recent_titles), text=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300, check=False,
        )
        if done.returncode != 0:
            raise RuntimeError(f"ebook_article_compose_failed:{done.returncode}")
        summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
        result = json.loads(Path(summary["result_path"]).read_text(encoding="utf-8"))
    if not result.get("title", "").strip() or len(result.get("body", "")) < 400:
        raise RuntimeError("ebook_article_contract_invalid")
    return result


def _publisher():
    spec = importlib.util.spec_from_file_location("capafy_free_article", PUBLISHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(now: dt.datetime, state_root: Path) -> dict:
    ledger_path = state_root / "article-ledger.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    if not due(now, ledger):
        return {"state": "not_due"}
    key = slot_key(now)
    product_id = product_for_hour(now.astimezone(JST).hour)
    product = load_product(product_id)
    recent = [e["title"] for e in ledger.values() if isinstance(e, dict) and e.get("status") == "published"
              and e.get("product_id") == product_id and e.get("title")][-RECENT_TITLES:]
    entry = {"attempts": ledger.get(key, {}).get("attempts", 0) + 1, "product_id": product_id}
    ledger[key] = entry
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=1))
    run_dir = state_root / "articles" / key.replace("@", "-")
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        article = compose(product, recent, state_root, f"ebook-article-{key.replace('@', '-')}")
        draft = run_dir / f"article-{product['language']}.md"
        draft.write_text(build_markdown(article["title"], article["body"], product["destination_url"], product["cta"]))
        gate = subprocess.run([sys.executable, str(PII_GATE), str(draft)], capture_output=True, text=True)
        if gate.returncode != 0:
            raise RuntimeError(f"pii_gate_blocked: {gate.stdout[-200:]}{gate.stderr[-200:]}")
        result = _publisher().publish(
            draft_path=draft, slug=slug_for(product_id, key), cta_url=product["destination_url"],
            landing_root=Path(os.environ["ARTICLE_SELF_OWNED_LANDING_ROOT"]),
            remote=os.environ.get("ARTICLE_SELF_OWNED_REMOTE", "origin"),
            branch=os.environ.get("ARTICLE_SELF_OWNED_BRANCH", "main"),
            base_url=os.environ["ARTICLE_SELF_OWNED_BASE_URL"],
            date=now.astimezone(JST).date().isoformat(), retries=40,
        )
        entry.update(status="published", url=result["url"], title=result["title"], commit=result["commit"])
    except (Exception, SystemExit) as error:  # best-effort: record, the next slot tries again
        entry.update(status="failed", error=f"{type(error).__name__}: {str(error)[:300]}")
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=1))
    return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", required=True)
    args, _ = parser.parse_known_args(argv)
    state_root = Path(args.state_root).expanduser()
    state_root.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"ebook_article_daily": run(dt.datetime.now(dt.timezone.utc), state_root)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
