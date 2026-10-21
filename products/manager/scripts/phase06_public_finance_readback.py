#!/usr/bin/env python3
"""Read a real, historically public ledger in CI. Observation only, no effect."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manager_core.adapters.public_finance import OpenCollectivePublicLedger,LedgerUnverified


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--collective",default="webpack")
    args=p.parse_args()
    try:
        result=OpenCollectivePublicLedger().read(args.collective,at=datetime.now(timezone.utc))
    except LedgerUnverified as exc:
        raise SystemExit(f"F003_PUBLIC_READBACK_UNKNOWN: {exc}")
    record={
        "source_url":result.source_url,
        "account_slug":result.account_slug,
        "retrieved_at":result.retrieved_at.isoformat(),
        "total_public_transactions":result.transaction_count,
        "sample_credit_cents":result.sample_credit_cents,
        "sample_debit_cents":result.sample_debit_cents,
        "sample_currency":list(result.currencies),
        "sample_sha256":result.snapshot_sha256,
        "proof_level":result.proof_level,
        "manager_caused_receipts":0,
        "beneficiary_welfare_improvement":"NOT_MEASURED",
        "domain":"historical_public_finance_observation_only",
    }
    print(json.dumps(record,sort_keys=True,indent=2))


if __name__=="__main__":
    main()
