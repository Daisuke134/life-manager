#!/usr/bin/env python3
"""Render one deterministic Japanese eBook baseline for an exact product slot."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import datetime as dt
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "brain"), str(HERE / "gates"),
                str(HERE / "render_eval"), str(HERE / "measure"),
                str(HERE.parents[2])]

from baseline_queue import materialize  # noqa: E402
from ebook_packs import load_ebook_packs  # noqa: E402
from ebook_runner import run as run_ebook  # noqa: E402
from script_ledger import ScriptLedger  # noqa: E402
from attribution import campaign_token  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")


@contextmanager
def exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def render_slot(*, product: str, slot_at: str, state_root: Path) -> dict:
    if product not in {"ebook-en", "ebook-ja"}:
        raise ValueError("unsupported eBook product")
    timestamp = dt.datetime.fromisoformat(slot_at.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("slot timestamp timezone required")
    pack = next((row for row in load_ebook_packs(HERE).values()
                 if row.get("product_id") == product), None)
    if pack is None:
        raise ValueError("Japanese eBook pack is missing")
    local = timestamp.astimezone(JST)
    wall_slot = local.strftime("%H:%M")
    if wall_slot not in pack["slots_jst"]:
        raise ValueError("slot is outside the Japanese eBook schedule")

    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state_root, 0o700)
    ledger_path = state_root / "script-ledger.sqlite3"
    with exclusive_lock(state_root / "locks" / "script-ledger.lock"):
        ledger = ScriptLedger(ledger_path)
        scripts = materialize(ledger, product)
        if ledger_path.exists():
            os.chmod(ledger_path, 0o600)

    day_index = (local.date().toordinal() - 1) % 7
    slot_index = pack["slots_jst"].index(wall_slot)
    script = scripts[day_index * len(pack["slots_jst"]) + slot_index]
    if script.get("baseline") is not True or script.get("product_id") != product:
        raise ValueError("selected eBook script is outside the baseline policy")

    key = hashlib.sha256(f"{product}|{slot_at}".encode()).hexdigest()[:24]
    run_id = f"ebook-run.{key}"
    receipt_root = state_root / "runs"
    output = state_root / "renders" / f"{run_id}.mp4"
    lock_name = "heygen-avatar-iv-account.lock" if product == "ebook-en" else f"{run_id}.lock"
    with exclusive_lock(state_root / "locks" / lock_name):
        receipt = run_ebook(
            engine=HERE,
            product=product,
            slot_at=slot_at,
            script_id=script["script_id"],
            ledger_path=ledger_path,
            state_root=receipt_root,
            render_output=output,
        )

    slot_id = "".join(character for character in slot_at if character.isalnum())
    publication_id = f"{script['creative_id']}-{slot_id}"
    if len(publication_id) > 120 or any(
        not (character.isalnum() or character in "._-") for character in publication_id
    ):
        raise ValueError("eBook publication ID is too long")
    return {
        "schema_version": "marketing.ebook-owner-input.v1",
        "receipt": receipt,
        "script": {key: script[key] for key in (
            "script_id", "creative_id", "product_id", "language", "baseline",
            "renderer_id", "body", "cta", "source_mechanism_ids",
        )},
        "publication_id": publication_id,
        "attribution_token": campaign_token(product, publication_id),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", required=True)
    parser.add_argument("--slot-at", required=True)
    parser.add_argument("--state-root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = render_slot(product=args.product, slot_at=args.slot_at,
                             state_root=args.state_root)
    except Exception as exc:
        print(json.dumps({
            "schema_version": "marketing.ebook-render-failure.v1",
            "error_class": type(exc).__name__,
        }, ensure_ascii=False, separators=(",", ":")))
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
