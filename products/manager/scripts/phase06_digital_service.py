#!/usr/bin/env python3
"""Build/audit/read back owned static environment; never creates an efficacy claim."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
from urllib.request import Request,build_opener,HTTPRedirectHandler
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manager_core.digital_environment import build_site,audit_sources,assess_outcomes,verify_readback,verify_bundle

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/service'
PUBLIC_BASE='https://daisuke134.github.io/life-manager/manager-support/'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('public service readback cannot change origin or path')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['build','audit','outcomes','readback'])
    p.add_argument('--commit')
    args=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    catalog=json.loads((ROOT/'public_goods/service/catalog.json').read_text())
    if args.command=='build':
        result=build_site(catalog,OUT/'site',args.commit)
    elif args.command=='audit':
        result=audit_sources(catalog)
        (OUT/'source-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    elif args.command=='outcomes':
        result=assess_outcomes(None)
        (OUT/'outcomes.json').write_text(json.dumps(result,indent=2)+'\n')
    else:
        manifest=json.loads((OUT/'site/manifest.json').read_text())
        verify_bundle(OUT/'site',manifest)
        bodies={}
        for name in manifest['files']:
            req=Request(PUBLIC_BASE+name,headers={'Cache-Control':'no-cache','User-Agent':'Manager-Independent-Readback/0.1'},method='GET')
            with build_opener(NoRedirect()).open(req,timeout=15) as response:
                if response.status!=200: raise SystemExit('PUBLIC_READBACK_UNKNOWN')
                bodies[name]=response.read(131073)
        result=verify_readback(manifest,bodies)
        result.update(url=PUBLIC_BASE,source_commit=manifest['source_commit'],observed_at=datetime.now(timezone.utc).isoformat())
        (OUT/'public-readback.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
