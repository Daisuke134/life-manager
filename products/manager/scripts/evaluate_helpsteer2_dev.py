#!/usr/bin/env python3
"""Explicit local-only research entry; stdout is metadata or one static failure.

Run only under the separately reviewed root process-group watchdog. No default
paths or train/test modes. Raw data, model exceptions and paths are never printed.
"""
import argparse
from contextlib import redirect_stderr, redirect_stdout
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manager_core.helpsteer2_candidate_eval import UNAVAILABLE, run_local


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(UNAVAILABLE)


def main(argv=None):
    try:
        parser = _Parser(add_help=False, allow_abbrev=False)
        for name in ('protocol-path', 'expected-sha256', 'data-dir', 'model-dir', 'rights-path', 'code-version'):
            parser.add_argument('--' + name, required=True)
        parser.add_argument('--output')
        configuration = vars(parser.parse_args(argv))
        output = configuration.pop('output')
        def checkpoint(report):
            if output is None:
                return
            path = Path(output)
            if not path.is_absolute() or not path.parent.is_dir() or path.is_symlink():
                raise ValueError(UNAVAILABLE)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.helpsteer2-',
                                                  delete=False) as stream:
                    temporary = Path(stream.name)
                    json.dump(report, stream, sort_keys=True, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

        # Third-party diagnostics must never leak private source/error fragments.
        with open(os.devnull, 'w') as sink, redirect_stdout(sink), redirect_stderr(sink):
            report = run_local(**configuration, progress=checkpoint)
        print(json.dumps(report, ensure_ascii=True, sort_keys=True, allow_nan=False))
        return 0
    except Exception:
        print(UNAVAILABLE)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
