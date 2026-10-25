#!/usr/bin/env python3
"""Explicit private local-only research CLI, default OFF.

Run under the root-owned cumulative900s/6GiB own-process-group watchdog starting
before this process. No retry/resume. Only metadata or a static failure is printed.
"""
import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manager_core.xstest_refusal_eval import UNAVAILABLE, run_local


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(UNAVAILABLE)


@contextmanager
def _silence():
    # Native libraries can write directly to file descriptors, bypassing Python
    # redirects. Preserve both forms; leave only our final metadata on stdout.
    stdout_fd, stderr_fd = os.dup(1), os.dup(2)
    try:
        with open(os.devnull, 'w') as sink:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
            with redirect_stdout(sink), redirect_stderr(sink):
                yield
    finally:
        os.dup2(stdout_fd, 1)
        os.dup2(stderr_fd, 2)
        os.close(stdout_fd)
        os.close(stderr_fd)


def main(argv=None):
    try:
        parser = _Parser(add_help=False, allow_abbrev=False)
        for name in ('protocol-path', 'expected-sha256', 'data-dir', 'model-dir', 'rights-path', 'code-version'):
            parser.add_argument('--' + name, required=True)
        parser.add_argument('--output')
        configuration = vars(parser.parse_args(argv))
        output = configuration.pop('output')
        path = None
        if output is not None:
            path = Path(output)
            if (not path.is_absolute() or not path.parent.is_dir() or path.is_symlink()
                    or any(p.is_symlink() for p in path.parents) or path.exists()):
                raise ValueError(UNAVAILABLE)

        def checkpoint(report):
            if path is None:
                return
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.xstest-',
                                                  delete=False, encoding='utf-8') as stream:
                    temporary = Path(stream.name)
                    os.fchmod(stream.fileno(), 0o600)
                    json.dump(report, stream, sort_keys=True, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

        with _silence():
            report = run_local(**configuration, progress=checkpoint)
            checkpoint(report)
        print(json.dumps(report, ensure_ascii=True, sort_keys=True, allow_nan=False))
        return 0
    except (Exception, KeyboardInterrupt):
        print(UNAVAILABLE)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
