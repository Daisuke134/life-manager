#!/usr/bin/env python3
"""Explicit private train27 research entry, under a separately accepted watchdog."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manager_core.helpsteer2_candidate_sft import UNAVAILABLE, run_local
from scripts.evaluate_xstest_refusal import _silence


class _Parser(argparse.ArgumentParser):
    def error(self,message):
        raise ValueError(UNAVAILABLE)


def main(argv=None):
    try:
        parser = _Parser(add_help=False,allow_abbrev=False)
        for name in ('protocol-path','expected-sha256','manifest-path','data-dir','model-dir',
                     'rights-path','code-version','execution-config-path','adapter-dir','output'):
            parser.add_argument('--'+name,required=True)
        configuration = vars(parser.parse_args(argv))
        configuration['metadata_output_path'] = configuration.pop('output')
        with _silence():
            report = run_local(**configuration)
        # Receipt paths, prompts, completions, labels and raw exceptions never go to stdout.
        print(json.dumps({k:report[k] for k in ('schema','status','event','global_step',
            'optimizer_opportunities_observed','changed_adapter_tensors','parameter_change','can_execute')},
            sort_keys=True,allow_nan=False))
        return 0
    except (Exception,KeyboardInterrupt):
        print(UNAVAILABLE)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
