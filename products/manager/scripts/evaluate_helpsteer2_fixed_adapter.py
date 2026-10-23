#!/usr/bin/env python3
"""Explicit private G7 research CLI. Stdout contains aggregates or a static error."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manager_core.helpsteer2_fixed_adapter_eval import UNAVAILABLE,run_local
from scripts.evaluate_xstest_refusal import _silence


class _Parser(argparse.ArgumentParser):
    def error(self,message):raise ValueError(UNAVAILABLE)


def main(argv=None):
    try:
        parser=_Parser(add_help=False,allow_abbrev=False)
        for name in ('protocol-path','expected-sha256','parent-protocol-path','manifest-path','data-dir','model-dir',
                     'rights-path','adapter-dir','code-version','execution-config-path','output'):
            parser.add_argument('--'+name,required=True)
        configuration=vars(parser.parse_args(argv));configuration['metadata_output_path']=configuration.pop('output')
        with _silence():report=run_local(**configuration)
        slices={name:dict(policies={p:{k:v for k,v in summary.items() if k not in ('groups',)}
            for p,summary in value['policies'].items()},paired={kind:{k:v for k,v in result.items() if k!='paired_ids'}
            for kind,result in value['paired'].items()}) for name,value in report['slices'].items()}
        print(json.dumps(dict(schema=report['schema'],status=report['status'],slices=slices,
            model_requests=report['model_requests'],can_execute=False),sort_keys=True,allow_nan=False))
        return 0
    except (Exception,KeyboardInterrupt):
        print(UNAVAILABLE);return 2


if __name__=='__main__':raise SystemExit(main())
