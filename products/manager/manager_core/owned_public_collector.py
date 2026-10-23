"""Bounded fixed-origin public GET collectors; supplied transport is P0 only.

Provider occurrence and current delivery are separate observations. No function
here issues a write, infers absence or authorizes a retry/rollback.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import re

from .digital_handoff import (REPOSITORY, PUBLIC_BASE, commit_message,
                              validate_commit_receipt, verify_readback)
from .models.source import _aware
from .reconcile import OwnedOccurrenceEvidence


PAGES_WORKFLOW_ID = '307239134'
PAGES_WORKFLOW_PATH = '.github/workflows/pages.yml'
_HEX_SHA = re.compile(r'[0-9a-f]{40}\Z')


class _CurrentPageCue(HTMLParser):
    """Read the one fixed primary-navigation current-page cue."""
    def __init__(self, page):
        super().__init__(convert_charrefs=True)
        self.page = page
        self.nav_depth = 0
        self.primary_navs = 0
        self.self_links = []
        self.current_links = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'nav' and values.get('aria-label') == '主な案内':
            self.nav_depth += 1
            self.primary_navs += 1
        elif tag == 'a' and self.nav_depth:
            current = values.get('aria-current')
            href = values.get('href')
            if href == self.page:
                self.self_links.append(current)
            if current is not None:
                self.current_links.append((href, current))

    def handle_endtag(self, tag):
        if tag == 'nav' and self.nav_depth:
            self.nav_depth -= 1

    def valid(self):
        return (self.primary_navs == 1 and self.nav_depth == 0 and
                self.self_links == ['page'] and
                self.current_links == [(self.page, 'page')])


def _fixed_cue_ok(body, page, *, require_csp=True):
    try:
        from .candidate_verification import _Safety
        text = body.decode('utf-8')
        safety = _Safety(); safety.feed(text); safety.close()
        cue = _CurrentPageCue(page); cue.feed(text); cue.close()
        return safety.safe and (safety.csp or not require_csp) and cue.valid()
    except (UnicodeError, ValueError, TypeError):
        return False


def _workflow_bound_to_candidate(value, candidate_sha, committed_at):
    """Accept only the current fixed Pages workflow's completed exact run."""
    if type(value) is not dict or type(value.get('workflow_runs')) is not list:
        return False
    runs = value['workflow_runs']
    if len(runs) > 100:
        return False
    for run in runs:
        if type(run) is not dict:
            continue
        repository = run.get('head_repository')
        try:
            created = datetime.fromisoformat(run['created_at'].replace('Z', '+00:00'))
            _aware(created)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if (run.get('workflow_id') == int(PAGES_WORKFLOW_ID) and
                run.get('path') == PAGES_WORKFLOW_PATH and
                run.get('event') == 'workflow_dispatch' and
                run.get('head_branch') == 'gh-pages' and
                type(repository) is dict and repository.get('full_name') == REPOSITORY and
                run.get('head_sha') == candidate_sha and
                run.get('status') == 'completed' and run.get('conclusion') == 'success' and
                created >= committed_at):
            return True
    return False


def _record_native_observation(journal, packet, receipt_ref, observed_at, measure_id,
                               unit, native_value, proof_level, provenance_refs,
                               status='VERIFIED', missing_reason=None):
    """Append an already validated provider fact to the existing private DB."""
    from .learning import NativeTechnicalObservation, PolicyLearner
    observation = NativeTechnicalObservation(
        effect_key=packet['effect_key'], candidate_sha256=packet['candidate_sha256'],
        receipt_ref=receipt_ref, observed_at=observed_at, measure_id=measure_id,
        unit=unit, status=status, proof_level=proof_level,
        native_value=native_value, missing_reason=missing_reason, human_outcome='NOT_MEASURED',
        provenance_refs=tuple(provenance_refs))
    return PolicyLearner(journal.path).record_native_technical_observation(observation)


@dataclass(frozen=True)
class DeliveryObservation:
    status: str
    reason: str
    proof_ref: str

    def __post_init__(self):
        if self.status not in ('VERIFIED', 'PENDING', 'REGRESSION', 'UNKNOWN'):
            raise ValueError('typed delivery status required')


def collect_owned_occurrence(key, journal, observed_at=None, *, get=None, max_pages=5):
    """Find the exact saved effect across bounded gh-pages commit pages.

    A missing result/page limit/network error is UNKNOWN, never proven absence.
    An injected transport exercises the validator, not authenticated collection.
    """
    from scripts.phase06_kernel_release import public_get, immutable_snapshot
    observed_at=observed_at or datetime.now(timezone.utc); _aware(observed_at)
    if type(max_pages) is not int or not 1<=max_pages<=10:
        raise ValueError('bounded provider pagination required')
    record=journal.record(key)
    if record is None: raise ValueError('saved owned intent required')
    packet=json.loads(record.packet_json); message=commit_message(packet)
    read=get or public_get
    try:
        for page in range(1,max_pages+1):
            rows=json.loads(read(f'https://api.github.com/repos/{REPOSITORY}/commits?sha=gh-pages&per_page=100&page={page}'))
            if type(rows) is not list or len(rows)>100: return None
            for row in rows:
                if not isinstance(row,dict) or row.get('commit',{}).get('message','').strip()!=message:
                    continue
                sha=row.get('sha')
                if type(sha) is not str or not re.fullmatch('[0-9a-f]{40}',sha): continue
                try:
                    receipt=json.loads(read(f'https://api.github.com/repos/{REPOSITORY}/commits/{sha}'))
                    if receipt.get('sha')!=sha: continue
                    if receipt['parents']!=[{'sha':record.expected_parent}]:
                        # GitHub parent objects contain additional public fields.
                        if len(receipt['parents'])!=1 or receipt['parents'][0].get('sha')!=record.expected_parent:
                            continue
                    manifest,bodies=immutable_snapshot(sha,get=read)
                    parent,old_bodies=immutable_snapshot(record.expected_parent,get=read)
                    validate_commit_receipt(packet,receipt,manifest,observed_at,
                        committed_bodies=bodies,parent_commit=record.expected_parent,
                        parent_manifest=parent,parent_bodies=old_bodies)
                    if get is None:
                        committed_at=datetime.fromisoformat(
                            receipt['commit']['committer']['date'].replace('Z','+00:00'))
                        _aware(committed_at)
                        _record_native_observation(journal,packet,sha,committed_at,
                            'owned.pages.commit_occurrence','commit_occurrence',1,'P1',
                            (receipt['html_url'],))
                    return OwnedOccurrenceEvidence(receipt,manifest,bodies,
                                                    record.expected_parent,parent,old_bodies)
                except (ValueError,KeyError,TypeError,OSError):
                    continue
            if len(rows)<100: break
    except (ValueError,KeyError,TypeError,OSError):
        return None
    return None


@dataclass(frozen=True)
class OwnedRollbackEvidence:
    receipt: dict
    restored_manifest: dict
    restored_bodies: dict
    parent_commit: str
    parent_manifest: dict
    parent_bodies: dict


def collect_owned_rollback(key, journal, observed_at=None, *, get=None, max_pages=5):
    """Reconcile a saved rollback intent from exact candidate and rollback commits."""
    from .outbox import owned_rollback_commit_message, validate_owned_rollback
    from scripts.phase06_kernel_release import public_get, immutable_snapshot
    observed_at=observed_at or datetime.now(timezone.utc);_aware(observed_at)
    if type(max_pages) is not int or not 1<=max_pages<=10:
        raise ValueError('bounded rollback pagination required')
    row=journal.rollback_record(key)
    if row is None:
        raise ValueError('saved rollback intent required')
    packet=json.loads(row.packet_json);validate_owned_rollback(packet)
    original=journal.record(packet['candidate_effect_key'])
    if (original is None or original.status!='PRESENT' or
            original.receipt_ref!=packet['candidate_commit'] or
            original.expected_parent!=packet['parent_commit']):
        return None
    read=get or public_get
    try:
        candidate=collect_owned_occurrence(packet['candidate_effect_key'],journal,
                                           observed_at,get=read,max_pages=max_pages)
        if (type(candidate) is not OwnedOccurrenceEvidence or
                candidate.receipt.get('sha')!=packet['candidate_commit'] or
                candidate.parent_commit!=packet['parent_commit'] or
                candidate.committed_manifest!=packet['candidate'] or
                candidate.parent_manifest!=packet['baseline']):
            return None
        message=owned_rollback_commit_message(packet)
        for page in range(1,max_pages+1):
            rows=json.loads(read(f'https://api.github.com/repos/{REPOSITORY}/commits?sha=gh-pages&per_page=100&page={page}'))
            if type(rows) is not list or len(rows)>100:return None
            for item in rows:
                if (type(item) is not dict or
                        item.get('commit',{}).get('message','').strip()!=message):
                    continue
                sha=item.get('sha')
                if type(sha) is not str or not _HEX_SHA.fullmatch(sha):continue
                receipt=json.loads(read(f'https://api.github.com/repos/{REPOSITORY}/commits/{sha}'))
                if (type(receipt) is not dict or receipt.get('sha')!=sha or
                        receipt.get('html_url')!=f'https://github.com/{REPOSITORY}/commit/{sha}' or
                        receipt.get('commit',{}).get('message','').strip()!=message or
                        type(receipt.get('parents')) is not list or len(receipt['parents'])!=1 or
                        receipt['parents'][0].get('sha')!=packet['candidate_commit']):
                    continue
                timestamp=datetime.fromisoformat(
                    receipt['commit']['committer']['date'].replace('Z','+00:00'))
                _aware(timestamp)
                created=datetime.fromisoformat(packet['created_at']);_aware(created)
                if timestamp<created or timestamp>observed_at:continue
                restored_manifest,restored_bodies=immutable_snapshot(sha,get=read)
                if restored_manifest!=packet['baseline'] or restored_bodies!=candidate.parent_bodies:
                    continue
                if (candidate.parent_manifest!=packet['baseline'] or
                        candidate.committed_manifest!=packet['candidate'] or
                        candidate.parent_bodies.keys()!=restored_bodies.keys()):
                    continue
                changed=sorted(path for path in restored_bodies
                               if restored_bodies[path]!=candidate.committed_bodies[path])
                # immutable_snapshot returns canonical repository-relative
                # keys; GitHub's commit receipt names repository paths.
                changed=[f'manager-support/{path}' for path in changed]
                files=receipt.get('files')
                if (not changed or type(files) is not list or
                        sorted(entry.get('filename') for entry in files if type(entry) is dict)!=changed or
                        any(type(entry) is not dict or entry.get('status')!='modified' or
                            entry.get('filename') not in packet['allowed_paths'] for entry in files)):
                    continue
                # Verify every restored raw page byte against the exact saved
                # parent manifest; no partial bundle or hash-only receipt closes.
                try:
                    verify_readback(packet['baseline'],
                        {name:raw
                         for name,raw in restored_bodies.items()
                         if name!='manifest.json'})
                except ValueError:
                    continue
                return OwnedRollbackEvidence(receipt,restored_manifest,restored_bodies,
                    packet['candidate_commit'],packet['candidate'],candidate.committed_bodies)
            if len(rows)<100:break
    except (ValueError,KeyError,TypeError,OSError,AttributeError):
        return None
    return None


def collect_owned_rollback_delivery(key, journal, observed_at=None, *, get=None):
    """Read P2 only after the exact restored commit is deployed and served."""
    from .outbox import validate_owned_rollback
    from scripts.phase06_kernel_release import public_get, served_snapshot
    observed_at=observed_at or datetime.now(timezone.utc);_aware(observed_at)
    row=journal.rollback_record(key)
    if row is None or row.status!='PRESENT':
        raise ValueError('official rollback receipt required before delivery')
    packet=json.loads(row.packet_json);validate_owned_rollback(packet)
    result=dict(status='UNKNOWN',effect_key=key,receipt_ref=row.receipt_ref,
                baseline_sha256=packet['baseline_sha256'],observed_at=observed_at.isoformat(),
                proof_ref=PUBLIC_BASE,proof_level='P0',reason='ROLLBACK_DELIVERY_UNCONFIRMED',
                human_outcome='NOT_MEASURED')
    read=get or public_get
    try:
        evidence=collect_owned_rollback(key,journal,observed_at,get=read)
        if (type(evidence) is not OwnedRollbackEvidence or
                evidence.receipt.get('sha')!=row.receipt_ref):
            return result
        committed_at=datetime.fromisoformat(
            evidence.receipt['commit']['committer']['date'].replace('Z','+00:00'))
        _aware(committed_at)
        target=json.loads(read(
            f'https://api.github.com/repos/{REPOSITORY}/git/ref/heads/gh-pages'))
        if (type(target) is not dict or target.get('ref')!='refs/heads/gh-pages' or
                type(target.get('object')) is not dict or target['object'].get('type')!='commit' or
                type(target['object'].get('sha')) is not str or
                not _HEX_SHA.fullmatch(target['object']['sha'])):
            return result
        if target['object']['sha']!=row.receipt_ref:
            return dict(result,status='PENDING',reason='ROLLBACK_NOT_CURRENT_TARGET')
        runs=json.loads(read(
            f'https://api.github.com/repos/{REPOSITORY}/actions/workflows/{PAGES_WORKFLOW_ID}/runs'
            '?branch=gh-pages&per_page=100'))
        if not _workflow_bound_to_candidate(runs,row.receipt_ref,committed_at):
            return dict(result,status='PENDING',reason='ROLLBACK_DEPLOYMENT_NOT_BOUND_SUCCESS')
        manifest,bodies=served_snapshot(get=read)
        if manifest!=packet['baseline']:
            return dict(result,status='PENDING',reason='ROLLBACK_BASELINE_NOT_CURRENT')
        try:
            verify_readback(packet['baseline'],bodies)
        except ValueError:
            return dict(result,reason='ROLLBACK_BASELINE_BYTES_UNCONFIRMED')
        return dict(result,status='VERIFIED',proof_level='P2',
                    reason='EXACT_DEPLOYED_PARENT_BASELINE')
    except (ValueError,KeyError,TypeError,OSError,AttributeError):
        return result


def collect_owned_delivery(key, journal, observed_at=None, *, get=None,
                           _served_bytes_capture=None):
    """Verify currently served candidate bytes independently of provider success.

    Public mismatch cannot bind corrupted bytes to a completed deployment, so
    this collector alone never reports REGRESSION or requests rollback.
    """
    from scripts.phase06_kernel_release import public_get, served_snapshot
    observed_at=observed_at or datetime.now(timezone.utc); _aware(observed_at)
    record=journal.record(key)
    if record is None or record.status!='PRESENT':
        raise ValueError('validated provider occurrence required before delivery')
    packet=json.loads(record.packet_json)
    result=dict(status='UNKNOWN',effect_key=key,receipt_ref=record.receipt_ref,
                candidate_sha256=packet['candidate_sha256'],observed_at=observed_at.isoformat(),
                proof_ref=PUBLIC_BASE,proof_level='P0',reason='DELIVERY_UNCONFIRMED',
                human_outcome='NOT_MEASURED')
    native_binding=None

    def record_missing(reason):
        if get is None and native_binding is not None:
            _record_native_observation(journal,packet,record.receipt_ref,observed_at,
                'owned.pages.served_bundle_bytes','byte',None,'P2',
                (native_binding.receipt['html_url'],PUBLIC_BASE),status='UNKNOWN',
                missing_reason=reason)

    if packet.get('schema') == 'manager.digital-handoff.v2':
        read=get or public_get
        try:
            # Rebind this read to the exact immutable provider commit and its
            # parent; a journal receipt or current branch name alone is not proof.
            evidence=collect_owned_occurrence(key,journal,observed_at,get=get)
            if (type(evidence) is not OwnedOccurrenceEvidence or
                    evidence.receipt.get('sha') != record.receipt_ref or
                    evidence.parent_commit != record.expected_parent or
                    evidence.committed_manifest != packet['candidate'] or
                    evidence.parent_manifest != packet['baseline']):
                return dict(result,reason='EXACT_CANDIDATE_RECEIPT_UNAVAILABLE')
            native_binding=evidence
            committed_at=datetime.fromisoformat(
                evidence.receipt['commit']['committer']['date'].replace('Z','+00:00'))
            _aware(committed_at)

            target=json.loads(read(
                f'https://api.github.com/repos/{REPOSITORY}/git/ref/heads/gh-pages'))
            if (type(target) is not dict or target.get('ref')!='refs/heads/gh-pages' or
                    type(target.get('object')) is not dict or
                    target['object'].get('type')!='commit' or
                    type(target['object'].get('sha')) is not str or
                    not _HEX_SHA.fullmatch(target['object']['sha'])):
                record_missing('CURRENT_TARGET_UNAVAILABLE')
                return dict(result,reason='CURRENT_TARGET_UNAVAILABLE')
            if target['object']['sha'] != record.receipt_ref:
                record_missing('CURRENT_TARGET_NOT_CANDIDATE')
                return dict(result,reason='CURRENT_TARGET_NOT_CANDIDATE')

            runs=json.loads(read(
                f'https://api.github.com/repos/{REPOSITORY}/actions/workflows/{PAGES_WORKFLOW_ID}/runs'
                '?branch=gh-pages&per_page=100'))
            if not _workflow_bound_to_candidate(runs,record.receipt_ref,committed_at):
                record_missing('PAGES_DEPLOYMENT_NOT_BOUND_SUCCESS')
                return dict(result,reason='PAGES_DEPLOYMENT_NOT_BOUND_SUCCESS')

            manifest,bodies=served_snapshot(get=read)
            if manifest != packet['candidate']:
                record_missing('SERVED_CANDIDATE_NOT_CURRENT')
                return dict(result,reason='SERVED_CANDIDATE_NOT_CURRENT')
            try:
                verify_readback(packet['candidate'],bodies)
                if get is None:
                    _record_native_observation(journal,packet,record.receipt_ref,observed_at,
                        'owned.pages.served_bundle_bytes','byte',
                        sum(len(body) for body in bodies.values()),'P2',
                        (evidence.receipt['html_url'],PUBLIC_BASE))
                return dict(result,status='VERIFIED',reason='EXACT_DEPLOYED_CANDIDATE',proof_level='P2')
            except ValueError:
                pass

            changed=packet.get('changed_pages')
            if type(changed) is not list or not changed or any(
                    type(page) is not str or page not in packet['candidate']['files']
                    for page in changed):
                record_missing('HASH_MISMATCH_ONLY')
                return dict(result,reason='HASH_MISMATCH_ONLY')
            from .candidate_verification import _Safety
            for page in changed:
                expected=evidence.committed_bodies.get('manager-support/'+page)
                served=bodies.get(page)
                if not isinstance(expected,bytes) or not isinstance(served,bytes):
                    record_missing('SERVED_BYTES_UNAVAILABLE')
                    return dict(result,reason='SERVED_BYTES_UNAVAILABLE')
                for body in (served,):
                    try:
                        safety=_Safety();safety.feed(body.decode('utf-8'));safety.close()
                    except (UnicodeError,ValueError,TypeError):
                        return dict(result,status='REGRESSION',proof_level='P2',
                                   reason='BOUND_FIXED_HTML_CSP_FAILURE')
                    if not safety.safe or not safety.csp:
                        if get is None:
                            _record_native_observation(journal,packet,record.receipt_ref,
                                observed_at,'owned.pages.served_bundle_bytes','byte',
                                sum(len(raw) for raw in bodies.values()),'P2',
                                (evidence.receipt['html_url'],PUBLIC_BASE),status='REGRESSION')
                        return dict(result,status='REGRESSION',proof_level='P2',
                                   reason='BOUND_FIXED_HTML_CSP_FAILURE')
                if _fixed_cue_ok(expected,page) and not _fixed_cue_ok(served,page):
                    if get is None:
                        _record_native_observation(journal,packet,record.receipt_ref,
                            observed_at,'owned.pages.served_bundle_bytes','byte',
                            sum(len(raw) for raw in bodies.values()),'P2',
                            (evidence.receipt['html_url'],PUBLIC_BASE),status='REGRESSION')
                    return dict(result,status='REGRESSION',proof_level='P2',
                               reason='BOUND_CURRENT_PAGE_CUE_FAILURE')
            record_missing('HASH_MISMATCH_ONLY')
            return dict(result,reason='HASH_MISMATCH_ONLY')
        except (ValueError,KeyError,TypeError,OSError,AttributeError):
            record_missing('DELIVERY_UNCONFIRMED')
            return dict(result,reason='DELIVERY_UNCONFIRMED')

    # Preserve the original P0 fixture contract for v1 offline cycles.
    try:
        manifest,bodies=served_snapshot(get=get)
        if manifest!=packet['candidate']:
            if _served_bytes_capture is not None and type(_served_bytes_capture) is list:
                _served_bytes_capture.append(None)
            return dict(result,status='PENDING',reason='DIFFERENT_SERVED_VERSION')
        verify_readback(packet['candidate'],bodies)
        if _served_bytes_capture is not None:
            if type(_served_bytes_capture) is not list:
                raise TypeError('private served-byte capture list required')
            _served_bytes_capture.append(sum(len(body) for body in bodies.values()))
    except (ValueError,KeyError,TypeError,OSError):
        if _served_bytes_capture is not None and type(_served_bytes_capture) is list:
            _served_bytes_capture.append(None)
        return result
    return dict(result,status='VERIFIED',reason='EXACT_SERVED_CANDIDATE',
                proof_level='P0' if get is not None else 'P2')


def collect_current_owned_delivery(journal, observed_at=None, *, get=None):
    """Observe only the saved occurrence named by the current Pages target SHA.

    Historical delivery rows remain immutable facts. This bounded current-SHA
    lookup is the monitoring cursor; it never scans or reopens older releases.
    """
    from scripts.phase06_kernel_release import public_get
    observed_at=observed_at or datetime.now(timezone.utc);_aware(observed_at)
    if not journal.has_owned_history():
        return None
    read=get or public_get
    target_url=f'https://api.github.com/repos/{REPOSITORY}/git/ref/heads/gh-pages'
    unknown={'status':'UNKNOWN','observed_at':observed_at.isoformat(),
        'proof_ref':PUBLIC_BASE,'proof_level':'P0','reason':'CURRENT_TARGET_UNAVAILABLE',
        'human_outcome':'NOT_MEASURED'}
    try:
        target=json.loads(read(target_url))
        if (type(target) is not dict or target.get('ref')!='refs/heads/gh-pages' or
                type(target.get('object')) is not dict or target['object'].get('type')!='commit' or
                type(target['object'].get('sha')) is not str or
                not _HEX_SHA.fullmatch(target['object']['sha'])):
            return {'kind':'unmatched','evidence':dict(unknown,reason='CURRENT_TARGET_UNAVAILABLE')}
        current_sha=target['object']['sha']
        candidate=journal.record_for_receipt(current_sha)
        if candidate is not None:
            packet=json.loads(candidate.packet_json)
            if packet.get('schema')=='manager.digital-handoff.v1':
                # The frozen seed predates the v2 deployment-run binding. Its
                # saved receipt is usable only for read-only continuity after
                # revalidating the exact provider commit, parent and both
                # immutable seven-file bundles, then independently serving the
                # same saved candidate. It grants no v1 send or rollback path.
                unknown={'status':'UNKNOWN','effect_key':candidate.key,
                    'receipt_ref':candidate.receipt_ref,
                    'candidate_sha256':packet['candidate_sha256'],
                    'observed_at':observed_at.isoformat(),'proof_ref':PUBLIC_BASE,
                    'proof_level':'P0','reason':'EXACT_V1_RECEIPT_UNAVAILABLE',
                    'human_outcome':'NOT_MEASURED'}
                occurrence=collect_owned_occurrence(candidate.key,journal,observed_at,get=get)
                if (type(occurrence) is not OwnedOccurrenceEvidence or
                        occurrence.receipt.get('sha')!=candidate.receipt_ref or
                        occurrence.parent_commit!=candidate.expected_parent or
                        occurrence.committed_manifest!=packet['candidate'] or
                        occurrence.parent_manifest!=packet['baseline']):
                    evidence=unknown
                else:
                    served_bytes=[]
                    evidence=collect_owned_delivery(candidate.key,journal,observed_at,get=get,
                                                    _served_bytes_capture=served_bytes)

                    def record_v1_missing(reason):
                        if get is None:
                            _record_native_observation(journal,packet,candidate.receipt_ref,
                                observed_at,'owned.pages.served_bundle_bytes','byte',None,'P2',
                                (occurrence.receipt['html_url'],PUBLIC_BASE),status='UNKNOWN',
                                missing_reason=reason)

                    if (evidence.get('status')=='VERIFIED' and
                            evidence.get('effect_key')==candidate.key and
                            evidence.get('receipt_ref')==candidate.receipt_ref and
                            evidence.get('candidate_sha256')==packet['candidate_sha256']):
                        try:
                            target_again=json.loads(read(target_url))
                        except (ValueError,UnicodeError,KeyError,TypeError,OSError,AttributeError):
                            evidence=dict(unknown,reason='CURRENT_TARGET_UNAVAILABLE')
                            record_v1_missing('CURRENT_TARGET_UNAVAILABLE')
                        else:
                            if (type(target_again) is dict and
                                    target_again.get('ref')=='refs/heads/gh-pages' and
                                    type(target_again.get('object')) is dict and
                                    target_again['object'].get('type')=='commit' and
                                    target_again['object'].get('sha')==current_sha):
                                evidence=dict(evidence,reason='EXACT_CURRENT_V1_SERVED_BUNDLE')
                                if (get is None and evidence.get('status')=='VERIFIED' and
                                        evidence.get('proof_level')=='P2' and len(served_bytes)==1 and
                                        type(served_bytes[0]) is int):
                                    _record_native_observation(journal,packet,candidate.receipt_ref,
                                        observed_at,'owned.pages.served_bundle_bytes','byte',
                                        served_bytes[0],'P2',(occurrence.receipt['html_url'],PUBLIC_BASE))
                                elif (get is None and evidence.get('status')=='VERIFIED' and
                                      evidence.get('proof_level')=='P2'):
                                    record_v1_missing('SERVED_BYTES_UNAVAILABLE')
                            else:
                                evidence=dict(unknown,
                                    reason='CURRENT_TARGET_CHANGED_DURING_READBACK')
                                record_v1_missing('CURRENT_TARGET_CHANGED_DURING_READBACK')
                    else:
                        evidence=dict(unknown,reason=evidence.get(
                            'reason','EXACT_V1_SERVED_BUNDLE_UNCONFIRMED'))
                        record_v1_missing(evidence['reason'])
            else:
                evidence=collect_owned_delivery(candidate.key,journal,observed_at,get=get)
            return {'kind':'candidate','effect_key':candidate.key,
                    'receipt_ref':candidate.receipt_ref,'evidence':evidence}
        rollback=journal.rollback_for_receipt(current_sha)
        if rollback is not None:
            evidence=collect_owned_rollback_delivery(rollback.key,journal,observed_at,get=read)
            return {'kind':'rollback','effect_key':rollback.key,
                    'receipt_ref':rollback.receipt_ref,'evidence':evidence}
        return {'kind':'unmatched','evidence':dict(unknown,reason='CURRENT_TARGET_NOT_SAVED_RECEIPT')}
    except (ValueError,KeyError,TypeError,OSError,AttributeError):
        return {'kind':'unmatched','evidence':unknown}
