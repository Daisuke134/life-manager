#!/usr/bin/env python3
"""Score pinned local SafetyBench MCQ bytes; emit aggregate metadata only."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from manager_core import safetybench_mcq as contract


class _StaticParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('SAFETYBENCH_MCQ_UNAVAILABLE')


def main(argv=None) -> int:
    try:
        parser = _StaticParser(description=__doc__, allow_abbrev=False)
        parser.add_argument('--questions-path', type=Path, required=True)
        parser.add_argument('--answers-path', type=Path, required=True)
        parser.add_argument('--code-version', required=True)
        parser.add_argument('--predictions-path', type=Path)
        parser.add_argument('--protocol-path', type=Path, default=ROOT / 'experiments/behavior-model/safetybench-mcq-protocol-v1.json')
        parser.add_argument('--rights-path', type=Path, default=ROOT / 'docs/research/source-rights.json')
        parser.add_argument('--expected-sha256', default=contract.PROTOCOL_SHA256)
        args = parser.parse_args(argv)
        questions, answers = args.questions_path.read_bytes(), args.answers_path.read_bytes()
        protocol = args.protocol_path.read_bytes()
        rights_payload = args.rights_path.read_bytes()
        rights = contract._parse(rights_payload)
        predictions = None if args.predictions_path is None else args.predictions_path.read_bytes()
        dataset = contract.load_safetybench(questions, answers, protocol_payload=protocol, expected_sha256=args.expected_sha256,
                                           rights_manifest=rights, retrieved_at=datetime.now(timezone.utc))
        result = contract.evaluate_recorded(dataset, predictions, code_version=args.code_version)
        result['rights_manifest_sha256'] = sha256(rights_payload).hexdigest()
        output = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        print('SAFETYBENCH_MCQ_UNAVAILABLE', file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
