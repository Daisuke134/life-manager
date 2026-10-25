#!/usr/bin/env python3
"""Run one bounded Railway cycle for the fixed Manager public-support bundle.

After host and durable-state preflight, the cycle reconciles older effects,
checks the current main and Pages baseline, and may reserve and submit at most
one exact request through the existing protected GitHub publisher. It never
claims that workflow acceptance is publication or human benefit.
"""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manager_core.owned_cycle import run_owned_workflow_bridge_once


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-store',type=Path,required=True,help='private persistent owner state, outside source')
    args=p.parse_args()
    report=run_owned_workflow_bridge_once(args.state_store)
    report['required_evidence']=[
        'reviewed immutable main release deployed to the exact configured Railway worker and mounted volume',
        'Railway dispatch credential plus protected GitHub MANAGER_OWNER_ID and MANAGER_RELEASE_ENABLED settings',
        'one real request traced through exact workflow run, gh-pages commit and parent, all seven bytes, and independent served-byte readback',
        'real-host restart/restore/stop/catch-up evidence with no duplicate dispatch or publication',
    ]
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 2 if report['status'] in (
        'DEPLOYMENT_HOST_REQUIRED','RESTORE_RECONCILIATION_REQUIRED','OWNER_BUSY',
        'RECONCILIATION_REQUIRED','UNKNOWN') else 0


if __name__=='__main__':raise SystemExit(main())
