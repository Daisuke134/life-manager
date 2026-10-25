#!/usr/bin/env python3
"""Connect the inert Manager planner to the existing owned CI publisher.

Only `admit` stages local files, using the original seven-path guard. It cannot
push, mint credentials or deploy. `plan` and `prove` make bounded public GETs.
The GitHub workflow owns admission, the non-force push and Pages dispatch.
"""
import argparse
from datetime import datetime, timezone, timedelta
from html import escape
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import Request, build_opener, HTTPRedirectHandler

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from manager_core.audit import AuditTrail
from manager_core.digital_environment import verify_bundle, verify_readback
from manager_core.digital_handoff import (
    REPOSITORY, SOURCE_REF, MAIN_SOURCE_REF, WORKFLOW, PUBLIC_BASE, PublisherContext,
    admit_release, validate_commit_receipt, validate_intent, commit_message,
)
from manager_core.kernel import ManagerKernel
from phase06_release_guard import stage_release

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'output/service'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('public evidence redirects are not permitted')


def public_get(url):
    """All URLs are constructed internally from fixed origins and checked SHAs."""
    req=Request(url,headers={'Cache-Control':'no-cache',
                'User-Agent':'Manager-Independent-Digital-Proof/1.0'},method='GET')
    with build_opener(NoRedirect()).open(req,timeout=20) as response:
        body=response.read(2*1024*1024+1)
        if response.status!=200 or len(body)>2*1024*1024:
            raise ValueError('unknown or oversized public evidence')
        return body


def served_snapshot(*,get=None):
    """Read a bounded current snapshot; mismatch is not itself a regression."""
    get=get or public_get
    manifest=json.loads(get(PUBLIC_BASE+'manifest.json'))
    # Validate the manifest before using even its page names to construct URLs.
    from manager_core.digital_handoff import _manifest
    _manifest(manifest)
    bodies={name:get(PUBLIC_BASE+name) for name in manifest['files']}
    return manifest,bodies


def live_snapshot(*,get=None):
    manifest,bodies=served_snapshot(get=get)
    verify_readback(manifest,bodies)
    return manifest,bodies


def immutable_snapshot(commit,*,get=None):
    """Read the exact seven-file bundle at one provider commit; no branch lookup."""
    if not isinstance(commit,str) or not re.fullmatch('[0-9a-f]{40}',commit):
        raise ValueError('immutable provider SHA required')
    base=f'https://raw.githubusercontent.com/{REPOSITORY}/{commit}/manager-support/'
    get=get or public_get
    raw=get(base+'manifest.json')
    manifest=json.loads(raw)
    from manager_core.digital_handoff import _manifest
    _manifest(manifest)
    bodies={'manifest.json':raw}
    bodies.update({name:get(base+name) for name in manifest['files']})
    return manifest,bodies


def fresh_audit(audit,now):
    if not isinstance(audit,dict) or not audit.get('sources'):
        raise ValueError('missing source audit')
    for row in audit['sources']:
        try:
            observed=datetime.fromisoformat(row['observed_at'])
            age=now-observed
        except (KeyError,TypeError,ValueError) as exc:
            raise ValueError('source audit needs an aware observation time') from exc
        if age<timedelta(0) or age>timedelta(hours=2):
            raise ValueError('stale or future source audit: NO_ACTION')


def write_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,sort_keys=True,ensure_ascii=False,indent=2)+'\n')


def prepare(site,output,now):
    candidate=json.loads((site/'manifest.json').read_text())
    verify_bundle(site,candidate)
    baseline,baseline_bodies=live_snapshot()
    output.mkdir(parents=True,exist_ok=True)
    # Keep the exact prior public bundle for bounded rollback/reproduction.
    rollback=output/'rollback-site';rollback.mkdir(exist_ok=True)
    for name,raw in baseline_bodies.items():(rollback/name).write_bytes(raw)
    write_json(rollback/'manifest.json',baseline)
    verify_bundle(rollback,baseline)
    kernel=ManagerKernel(None,None,AuditTrail(output/'digital-trace.sqlite'))
    source_ref=MAIN_SOURCE_REF if os.environ.get('GITHUB_REF')==MAIN_SOURCE_REF else SOURCE_REF
    packet=kernel.prepare_digital_release('release-'+candidate['source_commit'],baseline,candidate,now,
                                         source_ref=source_ref)
    write_json(output/'release-intent.json',packet)
    write_json(output/'kernel-trace.json',kernel.audit.trace('release-'+candidate['source_commit']))
    return packet


def _checkout_parent(checkout):
    try:
        return subprocess.check_output(
            ['git','-C',str(checkout),'rev-parse','HEAD'],stderr=subprocess.DEVNULL,
            text=True,timeout=10).strip()
    except (OSError,subprocess.SubprocessError) as exc:
        raise PermissionError('publisher target must be an immutable Git checkout') from exc


def admit(site,checkout,audit_path,intent_path,output,now,*,owned_request=None):
    packet=json.loads(intent_path.read_text())
    validate_intent(packet)
    source_ref=packet['ref']
    expected_workflow=f'{REPOSITORY}/{WORKFLOW}@{source_ref}'
    if os.environ.get('GITHUB_WORKFLOW_REF')!=expected_workflow:
        raise PermissionError('publisher workflow identity mismatch')
    if source_ref==MAIN_SOURCE_REF:
        if (os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch' or owned_request is None
                or not os.environ.get('MANAGER_OWNER_ID')):
            raise PermissionError('main publisher requires the owner-bound workflow request')
        from manager_core.owned_platform_host import validate_owned_workflow_request
        bound_request=validate_owned_workflow_request(
            owned_request,packet=packet,expected_owner_id=os.environ['MANAGER_OWNER_ID'],
            current_parent=_checkout_parent(checkout))
        if os.environ.get('MANAGER_REQUEST_ID')!=bound_request.request_id:
            raise PermissionError('workflow run does not match the stable owner request ID')
    elif owned_request is not None:
        raise PermissionError('owned workflow requests are accepted only by the versioned main publisher')
    context=PublisherContext(os.environ.get('GITHUB_REPOSITORY'),os.environ.get('GITHUB_REF'),
                             WORKFLOW,os.environ.get('GITHUB_SHA'),os.environ.get('GITHUB_RUN_ID'))
    # Verify both actual directories; caller-provided hashes never suffice.
    current_dir=checkout/'manager-support'
    current=json.loads((current_dir/'manifest.json').read_text())
    candidate=json.loads((site/'manifest.json').read_text())
    verify_bundle(current_dir,current);verify_bundle(site,candidate)
    result=admit_release(packet,context,current,candidate,now,
                         revoked=os.environ.get('MANAGER_RELEASE_ENABLED')!='true')
    audit=json.loads(audit_path.read_text());fresh_audit(audit,now)
    if result['dispatch_deployment']:
        staged=stage_release(site,checkout,audit)
        if staged['status']!='STAGED_MANAGER_ONLY':
            raise ValueError('expected change disappeared: reconcile only')
    else:
        staged={'status':'NO_ACTION','changed_files':[]}
    result.update(changed_files=staged['changed_files'],commit_message=commit_message(packet))
    write_json(output,result)
    return result


def admit_owned(context,assessment,standing_scope,prepared,checkout,audit_path,output,now,*,owned_request=None):
    """Host bridge: revalidate scope/source/artifact immediately before original admission.

    No CLI/model input creates a scope. The separately privileged owner must
    supply these typed host objects and the original GitHub workflow identity.
    This function only stages; the platform still owns CAS commit/push.
    """
    from manager_core.digital_handoff import prepare_owned_change
    validate_intent(prepared.packet)
    if not datetime.fromisoformat(prepared.packet['created_at'])<=now<datetime.fromisoformat(prepared.packet['expires_at']):
        raise PermissionError('original owned intent expired')
    check=prepare_owned_change(context,assessment,standing_scope,now)
    # Packet timestamps may differ; compare immutable bindings, then use fresh intent.
    if (prepared.status!='PREPARED_PLATFORM_AUTHORITY_REQUIRED'
            or check.status!=prepared.status or check.context_hash!=prepared.context_hash
            or check.packet['effect_key']!=prepared.packet['effect_key']):
        raise PermissionError('owned scope/context/artifact no longer eligible')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        intent=Path(tmp)/'intent.json';write_json(intent,check.packet)
        return admit(Path(context.candidate_bundle),Path(checkout),Path(audit_path),intent,output,now,
                     owned_request=owned_request)


def render_explorer(report):
    """Static view of an independently collected report; no trackers/forms."""
    details=[('Technical evidence',report['technical_proof']),
             ('Human outcomes',report['human_outcome']),('Effect key',report['effect_key']),
             ('Source commit',report['source_commit']),('Pages commit',report['pages_commit']),
             ('Parent Pages commit',report['parent_pages_commit']),
             ('Original release at',report['committed_at']),('Observed at',report['observed_at']),
             ('Observation decision',report['observation_decision']),
             ('Reconciled existing occurrence',report['reconciled_existing_occurrence']),
             ('Original release changed pages',', '.join(report['changed_pages']))]
    rows=''.join('<tr><th scope="row">'+escape(k)+'</th><td>'+escape(str(v))+'</td></tr>' for k,v in details)
    links=''.join('<li><a href="'+escape(url,quote=True)+'">'+escape(label)+'</a></li>'
                  for label,url in [('Public service',PUBLIC_BASE),('Exact provider receipt',report['receipt_url']),
                                    ('Immutable source','https://github.com/'+REPOSITORY+'/tree/'+report['source_commit']+'/products/manager')])
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Manager — digital release proof</title><style>body{font:18px/1.6 system-ui;max-width:75ch;margin:3rem auto;padding:1rem;color:#18352a}td,th{border-bottom:1px solid #ccc;text-align:left;padding:.7rem;overflow-wrap:anywhere}a{color:#175d49}</style><main><h1>Manager digital release proof</h1><p>Public Git commit and independently served bytes. This report does not establish beneficiary improvement or a causal welfare effect.</p><table><caption>Observed evidence</caption>'+rows+'</table><h2>Check the sources</h2><ul>'+links+'</ul><h2>What remains unknown</h2><p>Mental, physical and financial outcomes: NOT_MEASURED. No experiment participants, claimed medical effects or confirmed benefit payments.</p></main></html>\n'


def prove(intent_path,pages_commit,output,now):
    if not re.fullmatch('[0-9a-f]{40}',pages_commit or ''):
        raise ValueError('exact provider commit required')
    packet=json.loads(intent_path.read_text());validate_intent(packet)
    # No caller-supplied receipt or observation is promoted into public proof.
    receipt=json.loads(public_get(f'https://api.github.com/repos/{REPOSITORY}/commits/{pages_commit}'))
    if (not isinstance(receipt,dict) or receipt.get('sha')!=pages_commit or
        not isinstance(receipt.get('parents'),list) or len(receipt['parents'])!=1 or
        not isinstance(receipt['parents'][0],dict)):
        raise ValueError('provider receipt does not identify the requested single-parent occurrence')
    parent_commit=receipt['parents'][0].get('sha')
    committed,committed_bodies=immutable_snapshot(pages_commit)
    parent,parent_bodies=immutable_snapshot(parent_commit)
    live,bodies=live_snapshot()
    observed_at=datetime.now(timezone.utc)
    data=validate_commit_receipt(packet,receipt,committed,observed_at,
                                committed_bodies=committed_bodies,parent_commit=parent_commit,
                                parent_manifest=parent,parent_bodies=parent_bodies)
    if live!=packet['candidate']:
        raise ValueError('public live version differs: UNKNOWN_EFFECT; do not resend')
    technical=verify_readback(packet['candidate'],bodies)
    report={**data,**technical,'status':'VERIFIED_PUBLIC_ARTIFACT_ONLY',
            'source_commit':packet['candidate']['source_commit'],
            'candidate_sha256':packet['candidate_sha256'],'public_url':PUBLIC_BASE,
            'measurement_unit':'exact_public_artifact_bytes',
            'human_outcome':'NOT_MEASURED','causal_effect_verified':False,
            'candidate':packet['candidate']}
    write_json(output/'kernel-public-proof.json',report)
    (output/'proof-explorer.html').write_text(render_explorer(report))
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['plan','admit','prove'])
    p.add_argument('--site',type=Path,default=OUT/'site')
    p.add_argument('--output',type=Path,default=OUT)
    p.add_argument('--intent',type=Path,default=OUT/'release-intent.json')
    p.add_argument('--checkout',type=Path);p.add_argument('--audit',type=Path)
    p.add_argument('--pages-commit')
    p.add_argument('--owned-request',type=Path,
                   help='exact owner-bound request passed to the versioned main publisher')
    args=p.parse_args();now=datetime.now(timezone.utc)
    if args.command=='plan':result=prepare(args.site,args.output,now)
    elif args.command=='admit':
        if args.checkout is None or args.audit is None:p.error('admit needs --checkout and --audit')
        request=args.owned_request.read_text() if args.owned_request is not None else None
        result=admit(args.site,args.checkout,args.audit,args.intent,args.output,now,
                     owned_request=request)
    else:result=prove(args.intent,args.pages_commit,args.output,now)
    print(json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
