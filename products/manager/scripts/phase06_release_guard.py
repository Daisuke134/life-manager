#!/usr/bin/env python3
"""Stage precisely seven validated static files, preserving the rest of Pages.

This helper does NOT hold tokens, push git, change account settings, issue grants,
or enable Manager runtime writes. The owner-controlled CI release job supplies
its existing short-lived GitHub capability after full tests and source audit.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manager_core.digital_environment import PAGES, PUBLISH_PREFIX, verify_bundle, validate_catalog, permitted_publish_path

ROOT=Path(__file__).resolve().parents[1]


def stage_release(site,checkout,audit):
    site,checkout=Path(site),Path(checkout)
    if not checkout.is_dir() or checkout.is_symlink():
        raise ValueError('real existing owned Pages checkout required')
    manifest=json.loads((site/'manifest.json').read_text())
    verify_bundle(site,manifest)
    catalog=json.loads((ROOT/'public_goods/service/catalog.json').read_text())
    validate_catalog(catalog)
    expected={r['id']:r['url'] for r in catalog['resources']}
    if (not isinstance(audit,dict) or audit.get('content_rights')!='LINK_ONLY'
        or audit.get('human_outcome')!='NOT_MEASURED' or not isinstance(audit.get('sources'),list)
        or len(audit['sources'])!=len(expected)):
        raise ValueError('complete independently run source audit required')
    observed={}
    for row in audit['sources']:
        if (not isinstance(row,dict) or row.get('id') in observed
            or row.get('id') not in expected or row.get('url')!=expected[row['id']]
            or row.get('status')!='REACHABLE_NOT_OUTCOME' or row.get('http_status')!=200
            or not isinstance(row.get('sha256'),str) or re.fullmatch('[0-9a-f]{64}',row['sha256']) is None):
            raise ValueError('UNKNOWN, forged or incomplete official source audit: NO_ACTION')
        observed[row['id']]=row['url']
    if observed!=expected:
        raise ValueError('source identity mismatch')
    target=checkout/PUBLISH_PREFIX.rstrip('/')
    allowed=PAGES|{'manifest.json'}
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise ValueError('target is not an owned normal directory')
    if target.exists() and (set(p.name for p in target.iterdir())-allowed
                           or any(p.is_symlink() or not p.is_file() for p in target.iterdir())):
        raise ValueError('unexpected preexisting target content; preserve and refuse')
    changed=[]
    # Validate all bytes and paths before writing any file.
    data={name:(site/name).read_bytes() for name in allowed}
    for name in data:
        if not permitted_publish_path(PUBLISH_PREFIX+name):
            raise ValueError('outside release scope')
    target.mkdir(exist_ok=True)
    for name,content in sorted(data.items()):
        dest=target/name
        if not dest.exists() or dest.read_bytes()!=content:
            dest.write_bytes(content)
            changed.append(PUBLISH_PREFIX+name)
    verify_bundle(target,manifest)
    return {'status':'STAGED_MANAGER_ONLY' if changed else 'NO_ACTION',
            'changed_files':changed,'source_commit':manifest['source_commit'],
            'allowed_prefix':PUBLISH_PREFIX,'beneficiary_outcome':'NOT_MEASURED'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--site',type=Path,required=True)
    p.add_argument('--checkout',type=Path,required=True)
    p.add_argument('--audit',type=Path,required=True)
    args=p.parse_args()
    result=stage_release(args.site,args.checkout,json.loads(args.audit.read_text()))
    print(json.dumps(result,sort_keys=True,indent=2))

if __name__=='__main__': main()
