#!/usr/bin/env python3
"""Read-only deployment preflight; never installs an owner or pushes a release.

The deterministic reference cycle is tested through manager_core.owned_cycle.
Production remains blocked until an existing immutable owner, persistent volume,
platform authority and official occurrence/readback have been verified.
"""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manager_core.owned_cycle import CycleConfig,CycleStore,run_owned_cycle


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-store',type=Path,required=True,help='private persistent owner state, outside source')
    args=p.parse_args()
    report=run_owned_cycle(CycleConfig('unverified-production-owner',3600),CycleStore(args.state_store))
    report['required_evidence']=['merged immutable release and loaded existing owner identity',
        'verified persistent volume and single-owner lock semantics',
        'standing owner scope, original platform/artifact admission and source/browser checks',
        'one target-CAS canary, exact official occurrence, independent served-byte readback and replay-zero']
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 2 if report['status'] in ('DEPLOYMENT_HOST_REQUIRED','RESTORE_RECONCILIATION_REQUIRED') else 0


if __name__=='__main__':raise SystemExit(main())
