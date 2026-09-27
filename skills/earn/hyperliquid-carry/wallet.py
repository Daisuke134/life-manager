"""Agent-owned Hyperliquid wallet, persisted only in the credential SSOT."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from eth_account import Account

SERVICE = "hyperliquid-carry-agent-wallet"
DEFAULT_SSOT = Path.home() / ".local/share/anicca/credentials.json"


def _read(ssot: Path) -> dict:
    if not ssot.exists():
        return {"credentials": []}
    doc = json.loads(ssot.read_text(encoding="utf-8"))
    if isinstance(doc, list):
        doc = {"credentials": doc}
    doc.setdefault("credentials", [])
    return doc


def load_or_create(ssot: Path = DEFAULT_SSOT):
    doc = _read(ssot)
    for row in doc["credentials"]:
        if isinstance(row, dict) and row.get("service") == SERVICE and row.get("private_key"):
            return Account.from_key(row["private_key"])
    acct = Account.create()
    doc["credentials"].append({
        "service": SERVICE,
        "url": "https://app.hyperliquid.xyz",
        "username": acct.address,
        "private_key": acct.key.hex(),
        "note": "agent-created EVM key for Hyperliquid carry loop; fund with Arbitrum USDC",
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    })
    ssot.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(ssot.parent, 0o700)
    tmp = ssot.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ssot)
    return acct
