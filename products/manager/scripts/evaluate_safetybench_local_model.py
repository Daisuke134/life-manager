#!/usr/bin/env python3
"""Accepted private infer or terminal-only no-model finalize; static failures."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manager_core.safetybench_local_model import UNAVAILABLE, validate_configuration, run_local, finalize_run
from scripts.evaluate_xstest_refusal import _silence


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(UNAVAILABLE)


def main(argv=None):
    try:
        parser = _Parser(add_help=False, allow_abbrev=False)
        parser.add_argument('--mode', required=True, choices=('infer', 'finalize'))
        parser.add_argument('--execution-config-path', required=True)
        parser.add_argument('--code-version', required=True)
        parser.add_argument('--terminal-receipt-path')
        args = parser.parse_args(argv)
        if (args.mode == 'finalize') != (args.terminal_receipt_path is not None):
            raise ValueError(UNAVAILABLE)
        with _silence():
            config = validate_configuration(Path(args.execution_config_path), mode=args.mode, code_version=args.code_version)
            report = run_local(configuration=config) if args.mode == 'infer' else finalize_run(
                configuration=config, terminal_receipt_path=Path(args.terminal_receipt_path))
        if args.mode == 'infer' and report.get('status') in ('LOAD_FAILED', 'COMPUTE_FAILED'):
            raise ValueError(UNAVAILABLE)
        print(json.dumps(report, ensure_ascii=True, sort_keys=True, allow_nan=False))
        return 0
    except (Exception, KeyboardInterrupt):
        print(UNAVAILABLE)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
