#!/usr/bin/env python3
"""Explicit one-attempt train128 entry; config admission precedes ML imports."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manager_core.costello_forecast_train import run_train
from scripts.evaluate_xstest_refusal import _silence


class _Parser(argparse.ArgumentParser):
    def error(self,message):
        raise ValueError('COSTELLO_FORECAST_UNAVAILABLE')


def main(argv=None):
    try:
        parser=_Parser(add_help=False,allow_abbrev=False)
        parser.add_argument('--execution-config',required=True)
        args=parser.parse_args(argv)
        with _silence():report=run_train(args.execution_config)
        print(json.dumps({k:report[k] for k in ('schema','status','rows','global_step',
            'optimizer_opportunities','model_adoption','can_execute')}))
        return 0
    except (Exception,KeyboardInterrupt):
        print('COSTELLO_FORECAST_UNAVAILABLE')
        return 2


if __name__=='__main__':raise SystemExit(main())
