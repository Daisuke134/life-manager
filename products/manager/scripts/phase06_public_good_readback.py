#!/usr/bin/env python3
"""Prove public README artifact appeared since the frozen previous HEAD.

Evidence is P2_ARTIFACT_ONLY, NOT beneficiary P3/P4.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manager_core.public_good_readback import read_public_artifact,PublicArtifactUnverified


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--baseline-sha",required=True)
    args=p.parse_args()
    sha=os.environ.get("GITHUB_SHA") or subprocess.check_output(
        ["git","rev-parse","HEAD"],text=True).strip()
    try:
        result=read_public_artifact(head_sha=sha,baseline_sha=args.baseline_sha)
    except (ValueError,PublicArtifactUnverified) as err:
        raise SystemExit(f"PUBLIC_ARTIFACT_READBACK_UNKNOWN: {err}") from None
    print(json.dumps(asdict(result),sort_keys=True,indent=2))
    print("Welfare P3/P4 NOT_MEASURED; independent GitHub public readback is artifact only.")


if __name__=="__main__":
    main()
