#!/usr/bin/env python3
"""Inspect permitted local INTIMA bytes; emit metadata, never prompt content."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from manager_core.intima_benchmark import intima_intake_manifest, load_intima


class _StaticParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('INTIMA_INTAKE_UNAVAILABLE')


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('INTIMA_INTAKE_UNAVAILABLE')
        result[key] = value
    return result


def main(argv=None):
    try:
        parser = _StaticParser(description=__doc__)
        parser.add_argument('data_path', type=Path)
        parser.add_argument('--code-version', required=True)
        parser.add_argument('--rights-manifest', type=Path, default=ROOT / 'docs/research/source-rights.json')
        args = parser.parse_args(argv)
        rights = json.loads(args.rights_manifest.read_text(encoding='utf-8'), object_pairs_hook=_object)
        dataset = load_intima(args.data_path.read_bytes(), rights)
        manifest = intima_intake_manifest(dataset, code_version=args.code_version)
        output = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    except (OSError, ValueError, TypeError, RecursionError):
        print('INTIMA_INTAKE_UNAVAILABLE', file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
