#!/usr/bin/env python3
"""Explicit private CLI, under existing cumulative3600s/6GiB own-PGID watchdog.

The root starts the watchdog before this process. No retry/resume. Private audit
rows are written only to required0600 checkpoints; stdout is aggregate metadata.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.evaluate_xstest_refusal import _silence
from manager_core.xstest_binary_refusal_eval import UNAVAILABLE, run_local


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(UNAVAILABLE)


def main(argv=None):
    try:
        parser = _Parser(add_help=False, allow_abbrev=False)
        for name in ('protocol-path', 'expected-sha256', 'data-dir', 'model-dir', 'rights-path', 'code-version', 'output'):
            parser.add_argument('--' + name, required=True)
        configuration = vars(parser.parse_args(argv))
        path = Path(configuration.pop('output'))
        if (not path.is_absolute() or not path.parent.is_dir() or path.is_symlink()
                or any(p.is_symlink() for p in path.parents) or path.exists()):
            raise ValueError(UNAVAILABLE)

        def checkpoint(report):
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.xstest-binary-',
                                                  delete=False, encoding='utf-8') as stream:
                    temporary = Path(stream.name)
                    os.fchmod(stream.fileno(), 0o600)
                    json.dump(report, stream, sort_keys=True, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
                directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

        with _silence():
            report = run_local(**configuration, progress=checkpoint)
            checkpoint(report)
        public = {key: report[key] for key in ('lane_status', 'code_version', 'protocol_sha256', 'policies')}
        print(json.dumps(public, ensure_ascii=True, sort_keys=True, allow_nan=False))
        return 0
    except (Exception, KeyboardInterrupt):
        print(UNAVAILABLE)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
