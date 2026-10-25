#!/usr/bin/env python3
"""Reproduce the frozen offline v2 comparison without provider calls."""
import argparse
import json
from pathlib import Path
from manager_core.collaboration_comparison import load_suite, evaluate_suite, RecordedProviderRun


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--recorded-provider',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    provider=None
    if args.recorded_provider:
        provider=RecordedProviderRun(**json.loads(args.recorded_provider.read_text()))
    report=evaluate_suite(load_suite(root/'evaluation/collaboration-v2'),provider=provider)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:report[k] for k in ('evaluation_cases','actual_provider_calls','provider_status','conclusion')}))


if __name__=='__main__':main()
