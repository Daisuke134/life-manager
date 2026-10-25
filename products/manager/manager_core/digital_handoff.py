"""Inert kernel-to-publisher contract for the existing owned static site.

Nothing here holds a token, signs a live grant, sends a request or enables the
fixture runtime. PublisherContext must be supplied by the separately privileged
GitHub Actions job. Constructing this dataclass is not authentication. The job
checks its platform context, exact verified artifact and current target before
calling the existing seven-path release guard.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
import re

from .digital_environment import PAGES, PUBLISH_PREFIX, _valid_manifest, verify_readback
from .models.source import _aware

REPOSITORY = 'Daisuke134/life-manager'
SOURCE_REF = 'refs/heads/research/manager-product-r006-20261020'
MAIN_SOURCE_REF = 'refs/heads/main'
_INTENT_SCHEMAS = {
    SOURCE_REF: 'manager.digital-handoff.v1',
    MAIN_SOURCE_REF: 'manager.digital-handoff.v2',
}
WORKFLOW = '.github/workflows/manager-phase06-service.yml'
PUBLIC_BASE = 'https://daisuke134.github.io/life-manager/manager-support/'
ALLOWED_PATHS = tuple(sorted(PUBLISH_PREFIX+n for n in PAGES | {'manifest.json'}))
LEASE = timedelta(hours=6)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return sha256(canonical_bytes(value)).hexdigest()


def _manifest(value):
    _valid_manifest(value)
    if set(value) != {'schema','source_commit','files','beneficiary_outcome',
                      'real_participants','clinical_claim','experiment_enabled'}:
        raise ValueError('unknown manifest field')
    return deepcopy(value)


@dataclass(frozen=True)
class PublisherContext:
    repository: str
    ref: str
    workflow: str
    source_commit: str
    run_id: str


def plan_release(baseline, candidate, now: datetime, *, source_ref=SOURCE_REF):
    """Compare actual public baseline with tested candidate; produce no effect."""
    _aware(now)
    if type(source_ref) is not str or source_ref not in _INTENT_SCHEMAS:
        raise ValueError('unsupported immutable publisher source ref')
    baseline, candidate = _manifest(baseline), _manifest(candidate)
    identity = {'repository':REPOSITORY, 'ref':source_ref, 'workflow':WORKFLOW,
                'target':PUBLIC_BASE, 'candidate':candidate,
                'allowed_paths':list(ALLOWED_PATHS)}
    changed = sorted(n for n in PAGES if baseline['files'][n] != candidate['files'][n])
    same = baseline == candidate
    packet = {'schema':_INTENT_SCHEMAS[source_ref], **identity,
              'effect_key':digest(identity), 'baseline':baseline,
              'baseline_sha256':digest(baseline), 'candidate_sha256':digest(candidate),
              'created_at':now.isoformat(), 'expires_at':(now+LEASE).isoformat(),
              'decision':'NO_ACTION' if same else 'PROPOSE_TECHNICAL_RELEASE',
              'changed_pages':changed, 'money_budget':0,
              'max_changed_files':len(ALLOWED_PATHS),
              'external_authority':'REQUIRED_PLATFORM_CONTEXT',
              'revocation_control':WORKFLOW+'#publish-owned-prefix',
              'human_outcome':'NOT_MEASURED', 'causal_effect_verified':False}
    packet['packet_sha256'] = digest(packet)
    return packet


def validate_intent(packet):
    if not isinstance(packet,dict):
        raise ValueError('typed release intent required')
    try:
        created = datetime.fromisoformat(packet['created_at'])
        source_ref = packet['ref']
        if packet.get('schema') != _INTENT_SCHEMAS.get(source_ref):
            raise ValueError('intent schema does not match its immutable source ref')
        expected = plan_release(packet['baseline'],packet['candidate'],created,
                                source_ref=source_ref)
    except (KeyError,TypeError,ValueError) as exc:
        raise ValueError('invalid release intent') from exc
    if packet != expected:
        raise ValueError('changed, widened or unknown release intent')
    return created


def admit_release(packet, context: PublisherContext, current, candidate,
                  now: datetime, *, revoked=False):
    """Pure admission check; authority is the job, never the packet or agent."""
    created = validate_intent(packet)
    _aware(now)
    if revoked is not False or not created <= now < created+LEASE:
        raise PermissionError('revoked, future or expired release intent')
    if (not isinstance(context,PublisherContext) or
        (context.repository,context.ref,context.workflow,context.source_commit) !=
        (REPOSITORY,packet['ref'],WORKFLOW,packet['candidate']['source_commit']) or
        not isinstance(context.run_id,str) or not re.fullmatch(r'[1-9][0-9]*',context.run_id)):
        raise PermissionError('not the separately authorized publisher context')
    candidate, current = _manifest(candidate), _manifest(current)
    if candidate != packet['candidate']:
        raise PermissionError('candidate differs from verified intent')
    if current == candidate:
        return {'status':'NO_ACTION_ALREADY_PRESENT','effect_key':packet['effect_key'],
                'dispatch_deployment':False,'human_outcome':'NOT_MEASURED'}
    if current != packet['baseline']:
        raise PermissionError('target moved since independent baseline: reconcile only')
    return {'status':'ADMITTED_MANAGER_PREFIX_ONLY','effect_key':packet['effect_key'],
            'dispatch_deployment':True,'human_outcome':'NOT_MEASURED'}


def commit_message(packet):
    validate_intent(packet)
    return ('Manager release: effect '+packet['effect_key']+
            ' source '+packet['candidate']['source_commit'])


def _immutable_bundle(manifest, bodies):
    """Bind all seven fetched files, including raw manifest bytes, to their hashes."""
    manifest = _manifest(manifest)
    if (not isinstance(bodies, dict) or set(bodies) != PAGES | {'manifest.json'} or
        any(not isinstance(raw, bytes) for raw in bodies.values())):
        raise ValueError('complete immutable bundle bytes required')
    try:
        decoded = json.loads(bodies['manifest.json'])
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError('invalid immutable manifest bytes') from exc
    if decoded != manifest:
        raise ValueError('immutable manifest body differs')
    verify_readback(manifest, {name: bodies[name] for name in PAGES})
    return manifest


def validate_commit_receipt(packet, receipt, committed_manifest, observed_at, *,
                            committed_bodies, parent_commit, parent_manifest, parent_bodies):
    """Validate publicly collected data; this function alone authenticates nothing.

    The read-only collector must GET the commit and every file in both immutable
    bundles from the exact public GitHub endpoints. Supplied data authenticates
    nothing. A retry can reconcile an older occurrence of the same stable effect;
    the original provider transition stays separate from the new observation.
    """
    created = validate_intent(packet)
    _aware(observed_at)
    try:
        commit_sha = receipt['sha']
        timestamp = datetime.fromisoformat(receipt['commit']['committer']['date'].replace('Z','+00:00'))
        _aware(timestamp)
        files = receipt['files']
        message = receipt['commit']['message'].strip()
    except (KeyError,TypeError,AttributeError,ValueError) as exc:
        raise ValueError('incomplete provider receipt') from exc
    if (not isinstance(commit_sha,str) or not re.fullmatch('[0-9a-f]{40}',commit_sha) or
        receipt.get('html_url') != f'https://github.com/{REPOSITORY}/commit/{commit_sha}' or
        message != commit_message(packet) or
        not isinstance(receipt.get('parents'),list) or len(receipt['parents'])!=1 or
        not isinstance(receipt['parents'][0],dict) or
        not isinstance(parent_commit,str) or not re.fullmatch('[0-9a-f]{40}',parent_commit) or
        parent_commit == commit_sha or receipt['parents'][0].get('sha') != parent_commit or
        not isinstance(files,list) or not files or
        any(not isinstance(f,dict) or f.get('filename') not in ALLOWED_PATHS or
            f.get('status') != 'modified' for f in files) or
        len({f['filename'] for f in files}) != len(files) or
        timestamp > observed_at):
        raise ValueError('receipt is not the exact scoped release occurrence')
    committed_manifest = _immutable_bundle(committed_manifest, committed_bodies)
    parent_manifest = _immutable_bundle(parent_manifest, parent_bodies)
    if (committed_manifest != packet['candidate'] or parent_manifest == committed_manifest or
        (parent_manifest != packet['baseline'] and packet['baseline'] != committed_manifest)):
        raise ValueError('immutable parent is not the proposed or reconciled baseline')
    changed_files = sorted(PUBLISH_PREFIX + name for name in committed_bodies
                           if committed_bodies[name] != parent_bodies[name])
    if sorted(f['filename'] for f in files) != changed_files:
        raise ValueError('receipt paths differ from the complete immutable parent transition')
    changed_pages = sorted(name for name in PAGES if committed_bodies[name] != parent_bodies[name])
    return {'status':'MATCHED_PUBLIC_COMMIT_DATA','effect_key':packet['effect_key'],
            'pages_commit':commit_sha,'receipt_url':receipt['html_url'],
            'parent_pages_commit':parent_commit,'baseline':parent_manifest,
            'baseline_sha256':digest(parent_manifest),'changed_files':changed_files,
            'changed_pages':changed_pages,
            'observation_baseline':packet['baseline'],
            'observation_baseline_sha256':packet['baseline_sha256'],
            'observation_changed_pages':packet['changed_pages'],
            'observation_decision':packet['decision'],
            'reconciled_existing_occurrence':timestamp < created or packet['decision']=='NO_ACTION',
            'committed_at':timestamp.isoformat(),'observed_at':observed_at.isoformat(),
            'human_outcome':'NOT_MEASURED','causal_effect_verified':False}


@dataclass(frozen=True)
class OwnedChangeContext:
    """Host-owned source/bundle bindings; never parsed from model advice."""
    run_id: str
    planner: object
    baseline_bundle: object
    candidate_bundle: object
    criteria: object


@dataclass(frozen=True)
class OwnedReleaseIntent:
    status: str
    run_id: str
    reason: str
    packet: dict | None = None
    context_hash: str | None = None
    scope_id: str | None = None
    scope_expires_at: str | None = None
    # Construction is not authority; privileged platform checks remain required.
    @property
    def authorized_execution(self):return False


def prepare_owned_change(context,assessment,standing_scope,now,*,source_ref=SOURCE_REF):
    """Recompute static verification; emit an inert intent, never a write grant."""
    from dataclasses import asdict
    from .authority import OwnedDigitalScope
    from .collaboration import PlannerContext
    from .candidate_verification import TechnicalCriteria,TechnicalAssessment,verify_candidate,_load
    _aware(now)
    if type(context) is not OwnedChangeContext:raise ValueError('host-owned context required')
    run=context.run_id
    if type(run) is not str or not run.strip() or len(run)>256:raise ValueError('bounded run ID required')
    def no(reason):return OwnedReleaseIntent('NO_ACTION',run,reason)
    if type(standing_scope) is not OwnedDigitalScope:return no('MISSING_HOST_SCOPE')
    if type(context.planner) is not PlannerContext or type(context.criteria) is not TechnicalCriteria:
        return no('INVALID_HOST_CONTEXT')
    scope=standing_scope;c=context.criteria
    if c.at>now or context.planner.observed_at>now:return no('FUTURE_CONTEXT')
    if type(assessment) is not TechnicalAssessment:return no('UNVERIFIED_ASSESSMENT')
    facts={f.source.source_id:f.source for f in context.planner.facts}
    try:
        for ref in c.candidate.source_refs:
            facts[ref].require_fresh(now,48)
            if facts[ref] not in c.official_sources:return no('CONTEXT_SOURCE_CHANGED')
    except (KeyError,ValueError):return no('INVALID_SOURCE_BINDING')
    recomputed=verify_candidate(context.baseline_bundle,context.candidate_bundle,c)
    if recomputed!=assessment or assessment.status!='VERIFIED_TECHNICAL':return no('UNVERIFIED_OR_UNCHANGED')
    if (not scope.allows(c.candidate.target,now) or len(assessment.changed_paths)>scope.max_changed_files
            or not set(assessment.changed_paths)<=scope.allowed_paths):return no('OUTSIDE_HOST_SCOPE')
    before,_=_load(context.baseline_bundle);after,_=_load(context.candidate_bundle)
    packet=plan_release(before,after,now,source_ref=source_ref)
    bindings={'run_id':run,'goal':context.planner.goal,'observed_at':context.planner.observed_at.isoformat(),
              'facts':[{'source':{**asdict(f.source),'retrieved_at':f.source.retrieved_at.isoformat()},'summary':f.summary}
                       for f in context.planner.facts],
              'assessment':asdict(assessment),'scope_id':scope.scope_id,
              'scope_expires_at':scope.expires_at.isoformat()}
    return OwnedReleaseIntent('PREPARED_PLATFORM_AUTHORITY_REQUIRED',run,'ORIGINAL_PUBLISHER_GATES_REQUIRED',
                              packet,digest(bindings),scope.scope_id,scope.expires_at.isoformat())
