#!/usr/bin/env python3
"""Trusted main-workflow entry point for one owned digital cycle.

Preflight is read-only. ``run-once`` restores its private checkpoint before
constructing SQLite, then delegates one lifecycle to the existing cycle host.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manager_core.digital_handoff import MAIN_REF, REPOSITORY, WORKFLOW, PUBLIC_BASE
from manager_core.owned_checkpoint import CheckpointUnavailable, PrivateCheckpoint, SOURCE_ROOT
from manager_core.owned_cycle import CycleConfig, CycleStore, run_owned_cycle, _recover_owned_deliveries
from manager_core.owned_platform_host import (
    CatalogSelectionUnavailable, GitHubActionsCycleHost, is_canonical_remote,
)

WORKFLOW_NAME = 'Manager Phase06 Digital Environment'
STATE_OWNER = 'manager-owned-main-v2'
_SHA = re.compile(r'[0-9a-f]{40}\Z')
_POSITIVE = re.compile(r'[1-9][0-9]*\Z')


def _git(path, *args):
    try:
        done = subprocess.run(['git', '-C', str(path), *args], text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=10, check=False)
    except Exception:
        raise ValueError('repository context unavailable') from None
    if done.returncode:
        raise ValueError('repository context unavailable')
    return done.stdout.strip()


def _check_main_context(pages_checkout):
    """Verify actual checkout and workflow identity before requesting OIDC."""
    env = os.environ
    run_id, attempt = env.get('GITHUB_RUN_ID', ''), env.get('GITHUB_RUN_ATTEMPT', '')
    sha, workflow_sha = env.get('GITHUB_SHA', ''), env.get('GITHUB_WORKFLOW_SHA', '')
    if (env.get('GITHUB_REPOSITORY') != REPOSITORY or env.get('GITHUB_REF') != MAIN_REF or
            env.get('GITHUB_WORKFLOW_REF') != f'{REPOSITORY}/{WORKFLOW}@{MAIN_REF}' or
            env.get('GITHUB_WORKFLOW') != WORKFLOW_NAME or
            env.get('GITHUB_EVENT_NAME') not in ('schedule', 'workflow_dispatch') or
            env.get('RUNNER_ENVIRONMENT') != 'github-hosted' or
            not _POSITIVE.fullmatch(run_id) or not _POSITIVE.fullmatch(attempt) or
            not _SHA.fullmatch(sha) or workflow_sha != sha):
        raise PermissionError('trusted main workflow context required')
    from scripts import phase06_kernel_release
    actual_source = phase06_kernel_release.source_checkout_commit()
    source_root = SOURCE_ROOT.resolve()
    if (actual_source != sha or Path(phase06_kernel_release.ROOT.parents[1]).resolve() != source_root or
            not is_canonical_remote(_git(source_root, 'remote', 'get-url', 'origin'))):
        raise PermissionError('immutable source checkout mismatch')
    pages = Path(pages_checkout)
    if pages.is_symlink() or not pages.is_dir():
        raise PermissionError('existing Pages checkout required')
    pages_root = Path(_git(pages, 'rev-parse', '--show-toplevel')).resolve()
    if (pages_root != pages.resolve() or pages_root == source_root or
            pages_root in source_root.parents or source_root in pages_root.parents or
            _git(pages_root, 'symbolic-ref', '--quiet', 'HEAD') != 'refs/heads/gh-pages' or
            not is_canonical_remote(_git(pages_root, 'remote', 'get-url', 'origin')) or
            not is_canonical_remote(_git(pages_root, 'remote', 'get-url', '--push', 'origin')) or
            _git(pages_root, 'status', '--porcelain=v1', '--untracked-files=all')):
        raise PermissionError('clean canonical Pages checkout required')
    runner_temp = Path(env.get('RUNNER_TEMP', '')).resolve()
    if not runner_temp.is_dir():
        raise PermissionError('runner private temp unavailable')
    return {'run_id': run_id, 'attempt': attempt, 'source_sha': sha,
            'source_root': source_root, 'pages_root': pages_root, 'runner_temp': runner_temp}


def _private_fresh_root(path, runner_temp):
    target = Path(os.path.abspath(path))
    temp = Path(runner_temp).resolve()
    if (target.is_symlink() or target.parent.resolve() != temp or
            any(p.is_symlink() for p in (target.parent, *target.parents))):
        raise ValueError('fresh private runner-temp child required')
    if target.exists() and (not target.is_dir() or any(target.iterdir()) or target.stat().st_mode & 0o077):
        raise ValueError('state store must be fresh and private')
    return target


def _trusted_p2_observation(store, report):
    """Require the cycle journal binding and private native P2 row to agree."""
    if (type(store) is not CycleStore or not isinstance(report, dict) or
            report.get('status')!='VERIFIED_PUBLIC_ARTIFACT_ONLY' or
            report.get('proof_level')!='P2' or report.get('deployed') is not True):
        return False
    effect=report.get('effect_key');receipt=report.get('receipt_ref')
    if (type(effect) is not str or not re.fullmatch(r'[0-9a-f]{64}',effect) or
            type(receipt) is not str or not _SHA.fullmatch(receipt)):
        return False
    try:
        saved=store.journal.record(effect)
        if saved is None or saved.status!='PRESENT' or saved.receipt_ref!=receipt:
            return False
        packet=json.loads(saved.packet_json)
        return any(
            row.effect_key==effect and row.candidate_sha256==packet.get('candidate_sha256') and
            row.receipt_ref==receipt and row.measure_id=='owned.pages.served_bundle_bytes' and
            row.unit=='byte' and row.status=='VERIFIED' and row.proof_level=='P2' and
            type(row.native_value) is int and row.native_value>0 and
            row.missing_reason is None and row.human_outcome=='NOT_MEASURED' and
            f'https://github.com/{REPOSITORY}/commit/{receipt}' in row.provenance_refs and
            PUBLIC_BASE in row.provenance_refs
            for row in store.learning.native_technical_observations(effect_key=effect))
    except (AttributeError, KeyError, TypeError, ValueError, OSError):
        return False


def _select_current_noop_proof(store, host, report):
    """Select a fresh saved v2 current receipt for a no-op proof export.

    This private bridge never upgrades the cycle result or its canary. It asks
    the exact trusted platform host for a new default readback and binds that
    result to the immutable saved occurrence and its native P1/P2 facts.
    """
    from manager_core.digital_handoff import validate_intent
    from manager_core.learning import NativeTechnicalObservation
    from manager_core.owned_platform_host import GitHubActionsCycleHost

    if (type(store) is not CycleStore or type(host) is not GitHubActionsCycleHost or
            type(report) is not dict or report.get('status') not in ('NO_ACTION', 'NOT_DUE')):
        return None
    try:
        current = host.observe_current_delivery(store.journal)
        if (type(current) is not dict or current.get('kind') != 'candidate' or
                type(current.get('evidence')) is not dict):
            return None
        evidence = current['evidence']
        effect = current.get('effect_key')
        receipt = current.get('receipt_ref')
        if (evidence.get('status') != 'VERIFIED' or evidence.get('proof_level') != 'P2' or
                evidence.get('reason') != 'EXACT_DEPLOYED_CANDIDATE' or
                type(effect) is not str or not re.fullmatch(r'[0-9a-f]{64}', effect) or
                type(receipt) is not str or not _SHA.fullmatch(receipt) or
                evidence.get('effect_key') != effect or evidence.get('receipt_ref') != receipt):
            return None
        saved = store.journal.record(effect)
        if (saved is None or saved.status != 'PRESENT' or saved.receipt_ref != receipt):
            return None
        packet = json.loads(saved.packet_json)
        validate_intent(packet)
        if (packet.get('schema') != 'manager.digital-handoff.v2' or
                evidence.get('candidate_sha256') != packet.get('candidate_sha256')):
            return None
        receipt_url = f'https://github.com/{REPOSITORY}/commit/{receipt}'
        rows = store.learning.native_technical_observations(effect_key=effect)
        bound = [row for row in rows if type(row) is NativeTechnicalObservation and
                 row.effect_key == effect and
                 row.candidate_sha256 == packet['candidate_sha256'] and
                 row.receipt_ref == receipt and row.status == 'VERIFIED' and
                 row.missing_reason is None and row.human_outcome == 'NOT_MEASURED']
        if (not any(row.measure_id == 'owned.pages.commit_occurrence' and
                    row.unit == 'commit_occurrence' and row.proof_level == 'P1' and
                    row.native_value == 1 and receipt_url in row.provenance_refs
                    for row in bound) or
                not any(row.measure_id == 'owned.pages.served_bundle_bytes' and
                        row.unit == 'byte' and row.proof_level == 'P2' and
                        type(row.native_value) is int and row.native_value > 0 and
                        receipt_url in row.provenance_refs and PUBLIC_BASE in row.provenance_refs
                        for row in bound)):
            return None
        selected = dict(evidence, status='VERIFIED_PUBLIC_ARTIFACT_ONLY',
                        proof_level='P2', deployed=True, effect_key=effect,
                        receipt_ref=receipt)
        return selected if _trusted_p2_observation(store, selected) else None
    except Exception:
        return None


def _discard_kernel_proof(runner_temp):
    """Remove only this run's allowlisted proof directory after later failure."""
    try:
        root=Path(runner_temp).resolve()
        target=root/'manager-kernel-proof'
        if target.parent==root and not target.is_symlink() and target.is_dir():
            shutil.rmtree(target)
    except OSError:
        pass


def _export_current_kernel_proof(checkpoint, store, report, runner_temp, *, now=None):
    """Export proof only for the exact saved occurrence and native P1/P2 rows."""
    from manager_core.digital_handoff import validate_intent
    from manager_core.learning import NativeTechnicalObservation
    from scripts import phase06_kernel_release

    staging=None
    try:
        root=Path(runner_temp).resolve()
        state_db=Path(checkpoint.db).resolve()
        if (type(checkpoint) is not PrivateCheckpoint or checkpoint.broken or
                checkpoint.owner is None or type(checkpoint.revision) is not int or
                type(store) is not CycleStore or Path(store.db).resolve()!=state_db or
                not state_db.is_file() or root.is_symlink() or not root.is_dir() or
                state_db.parent.parent.resolve()!=root or
                not _trusted_p2_observation(store,report)):
            return False
        effect=report['effect_key'];receipt=report['receipt_ref']
        saved=store.journal.record(effect)
        if saved is None or saved.status!='PRESENT' or saved.receipt_ref!=receipt:
            return False
        packet=json.loads(saved.packet_json)
        validate_intent(packet)
        if packet.get('effect_key')!=effect:
            return False
        candidate_sha=packet.get('candidate_sha256')
        receipt_url=f'https://github.com/{REPOSITORY}/commit/{receipt}'
        rows=store.learning.native_technical_observations(effect_key=effect)
        observations=[row for row in rows if type(row) is NativeTechnicalObservation and
            row.effect_key==effect and row.candidate_sha256==candidate_sha and
            row.receipt_ref==receipt and row.status=='VERIFIED' and
            row.missing_reason is None and row.human_outcome=='NOT_MEASURED']
        if (not any(row.measure_id=='owned.pages.commit_occurrence' and
                    row.unit=='commit_occurrence' and row.proof_level=='P1' and
                    row.native_value==1 and receipt_url in row.provenance_refs
                    for row in observations) or
                not any(row.measure_id=='owned.pages.served_bundle_bytes' and
                        row.unit=='byte' and row.proof_level=='P2' and
                        type(row.native_value) is int and row.native_value>0 and
                        receipt_url in row.provenance_refs and PUBLIC_BASE in row.provenance_refs
                        for row in observations)):
            return False

        final=root/'manager-kernel-proof'
        if final.exists() or final.is_symlink():
            return False
        staging=Path(tempfile.mkdtemp(prefix='.manager-kernel-proof-',dir=root))
        private_parent=state_db.parent
        with tempfile.TemporaryDirectory(prefix='manager-proof-intent-',dir=private_parent) as intent_root:
            intent=Path(intent_root)/'saved-intent.json'
            fd=os.open(intent,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w',encoding='utf-8') as stream:
                json.dump(packet,stream,sort_keys=True,ensure_ascii=False,allow_nan=False)
                stream.write('\n')
            proved=phase06_kernel_release.prove(intent,receipt,staging,
                now or datetime.now(timezone.utc),learner=store.learning)

        proof_path=staging/'kernel-public-proof.json'
        explorer_path=staging/'proof-explorer.html'
        if (type(proved) is not dict or proved.get('status')!='VERIFIED_PUBLIC_ARTIFACT_ONLY' or
                proved.get('effect_key')!=effect or proved.get('pages_commit')!=receipt or
                proved.get('candidate_sha256')!=candidate_sha or
                type(proved.get('served_bundle_bytes')) is not int or
                proved['served_bundle_bytes']<=0 or
                not any(row.measure_id=='owned.pages.served_bundle_bytes' and
                        row.proof_level=='P2' and row.unit=='byte' and
                        row.native_value==proved['served_bundle_bytes'] for row in observations) or
                {path.name for path in staging.iterdir()}!=
                    {'kernel-public-proof.json','proof-explorer.html'} or
                any(path.is_symlink() or not path.is_file() for path in staging.iterdir())):
            raise ValueError('public proof files do not bind to saved native evidence')
        public_json=json.loads(proof_path.read_text(encoding='utf-8'))
        if (public_json.get('effect_key')!=effect or public_json.get('pages_commit')!=receipt or
                public_json.get('candidate_sha256')!=candidate_sha or
                public_json.get('served_bundle_bytes')!=proved['served_bundle_bytes']):
            raise ValueError('public proof JSON differs from validated proof')
        os.replace(staging,final)
        staging=None
        return True
    except Exception:
        if staging is not None:
            shutil.rmtree(staging,ignore_errors=True)
        return False


def public_summary(report, *, source_sha=None, receipt_sha=None, store=None):
    """Return only fields approved for public stdout/artifacts."""
    status = report.get('status') if isinstance(report, dict) else 'UNKNOWN'
    if status not in {'UNKNOWN', 'NO_ACTION', 'OWNER_BUSY', 'NOT_DUE', 'STOPPED_REGRESSION',
                      'STOPPED_BY_OWNER', 'CONTROL_STOP_REQUIRED', 'ROLLBACK_SUBMITTED',
                      'ROLLBACK_RECONCILED', 'ROLLBACK_BLOCKED', 'ROLLBACK_UNKNOWN',
                      'RESUMED_BY_OWNER',
                      'ROLLED_BACK_SANDBOX_REGRESSION', 'VERIFIED_PUBLIC_ARTIFACT_ONLY',
                      'VERIFIED_PLATFORM_CONTRACT_P0'}:
        status = 'UNKNOWN'
    reason = report.get('reason') if isinstance(report, dict) else 'RUNTIME_UNAVAILABLE'
    if not isinstance(reason, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', reason):
        reason = None
    writes = report.get('writes') if isinstance(report, dict) else None
    if status == 'UNKNOWN' or status not in ('NO_ACTION', 'VERIFIED_PUBLIC_ARTIFACT_ONLY',
                                             'VERIFIED_PLATFORM_CONTRACT_P0', 'STOPPED_REGRESSION',
                                             'OWNER_BUSY', 'NOT_DUE','STOPPED_BY_OWNER',
                                             'CONTROL_STOP_REQUIRED','ROLLBACK_SUBMITTED',
                                             'ROLLBACK_RECONCILED','RESUMED_BY_OWNER'):
        writes = None if status == 'UNKNOWN' else writes
    receipt = receipt_sha or (report.get('receipt_ref') if isinstance(report, dict) else None)
    summary = {
        'authentication': 'NOT_PROVEN',
        'status': status if isinstance(status, str) else 'UNKNOWN',
        'reason': reason if isinstance(reason, str) else None,
        'writes': writes if type(writes) is int and writes >= 0 else None,
        'proof_level': report.get('proof_level') if isinstance(report, dict) and report.get('proof_level') in ('P0', 'P2') else None,
        'receipt_sha': receipt if isinstance(receipt, str) and _SHA.fullmatch(receipt) else None,
        'source_sha': source_sha if isinstance(source_sha, str) and _SHA.fullmatch(source_sha) else None,
        'positive_canary': 'NOT_RUN',
        'E16_ACCEPTANCE': 'INCOMPLETE',
        'human_outcome': 'NOT_MEASURED',
        'rollback_delivery': (report.get('rollback_delivery_status')
                              if isinstance(report,dict) and
                              report.get('rollback_delivery_status') in ('VERIFIED','PENDING','UNKNOWN')
                              else None),
    }
    if summary['status'] in ('NO_ACTION', 'NOT_DUE', 'OWNER_BUSY'):
        summary['positive_canary'] = 'NOT_RUN'
    elif _trusted_p2_observation(store, report):
        summary['positive_canary'] = 'P2_ARTIFACT_VERIFIED'
    return summary


def _successful_cycle_exit(report):
    """Accept no-op/cadence outcomes and receipt-bound verified outcomes only.

    UNKNOWN, owner contention, and stopped regressions intentionally remain
    nonzero; this process result does not promote E16 or canary acceptance.
    """
    if not isinstance(report, dict):
        return False
    status = report.get('status')
    if status in ('NO_ACTION', 'NOT_DUE'):
        return True
    receipt_ref = report.get('receipt_ref')
    confirmed_receipt = isinstance(receipt_ref, str) and _SHA.fullmatch(receipt_ref)
    if (status == 'VERIFIED_PUBLIC_ARTIFACT_ONLY' and
            report.get('proof_level') == 'P2' and report.get('deployed') is True and
            confirmed_receipt):
        return True
    if (status == 'VERIFIED_PLATFORM_CONTRACT_P0' and
            report.get('proof_level') == 'P0' and confirmed_receipt):
        return True
    return False


def run_preflight(source_root=None, state_store=None):
    """Read-only diagnostics: no DB, lease, or state directory creation."""
    source = Path(source_root or SOURCE_ROOT).resolve()
    try:
        from scripts import phase06_kernel_release
        sha = phase06_kernel_release.source_checkout_commit()
        valid = (source == SOURCE_ROOT.resolve() and bool(_SHA.fullmatch(sha)) and
                 is_canonical_remote(_git(source, 'remote', 'get-url', 'origin')))
        if state_store is not None:
            path = Path(os.path.abspath(state_store))
            valid = (valid and not path.is_symlink() and
                     source not in path.parents and path != source)
        return (0 if valid else 2, {
            'status': 'PREFLIGHT_READY' if valid else 'PREFLIGHT_BLOCKED',
            'authentication': 'NOT_PROVEN', 'writes': 0,
            'source_sha': sha if valid else None,
            'state_store_created': False,
        })
    except Exception:
        return 2, {'status': 'PREFLIGHT_BLOCKED', 'authentication': 'NOT_PROVEN',
                    'writes': 0, 'source_sha': None, 'state_store_created': False}


def run_once(state_store, pages_checkout):
    checkpoint = None
    context = None
    proof_exported=False
    authentication = 'NOT_PROVEN'
    try:
        context = _check_main_context(pages_checkout)
        root = _private_fresh_root(state_store, context['runner_temp'])
        checkpoint = PrivateCheckpoint(run_id=context['run_id'], run_attempt=context['attempt'])
        checkpoint.acquire(root)
        authentication = 'GATEWAY_ACKNOWLEDGED'
        # CycleStore is permitted only after remote restore created the exact DB.
        store = CycleStore(Path(checkpoint.db).parent)
        planning = Path(checkpoint.db).parent / 'planning'
        if planning.exists():
            raise ValueError('fresh planning workspace required')
        audit_path = planning / 'source-audit.json'
        host = GitHubActionsCycleHost(checkpoint, context['pages_root'], audit_path,
                                      context=None, assessment=None, scope=None)
        try:
            report = run_owned_cycle(CycleConfig(STATE_OWNER, 3600), store, host=host)
        except CatalogSelectionUnavailable:
            # Prior recovery has completed; checkpoint the known journal/cadence
            # and release only this confirmed clean private session.
            checkpoint.save()
            checkpoint.release()
            summary = public_summary({'status': 'UNKNOWN', 'reason': 'SELECTOR_UNAVAILABLE', 'writes': None},
                                     source_sha=context['source_sha'])
            summary['writes'] = None
            summary['authentication'] = authentication
            return 2, summary
        if report.get('status') == 'UNKNOWN':
            # UNKNOWN describes the occurrence/delivery result. Persist its
            # journal evidence before ending this otherwise healthy session.
            checkpoint.save()
            checkpoint.release()
            summary = public_summary(report, source_sha=context['source_sha'],store=store)
            summary['writes'] = None
            summary['authentication'] = authentication
            return 2, summary
        current_proof_report = _select_current_noop_proof(
            store, host, report) if report.get('status') in ('NO_ACTION', 'NOT_DUE') else None
        # Persist the journal/cadence before relinquishing the remote session.
        checkpoint.save()
        export_report = (report if _trusted_p2_observation(store, report)
                         else current_proof_report)
        proof_exported = bool(export_report is not None and _export_current_kernel_proof(
            checkpoint, store, export_report, context['runner_temp']))
        checkpoint.release()
        summary = public_summary(report, source_sha=context['source_sha'],store=store)
        if not proof_exported:
            summary['positive_canary']='NOT_RUN'
        summary['current_proof_exported'] = bool(current_proof_report is not None and proof_exported)
        summary['current_proof_receipt_sha'] = (
            current_proof_report['receipt_ref'] if summary['current_proof_exported'] else None)
        summary['authentication'] = authentication
        return (0 if _successful_cycle_exit(report) else 2), summary
    except Exception as exc:
        # A broken checkpoint is fenced permanently. Never release it in finally.
        if proof_exported and context is not None:
            _discard_kernel_proof(context['runner_temp'])
        status = 'UNKNOWN'
        code = 2
        summary = public_summary({'status': status, 'reason': 'RUNTIME_UNAVAILABLE', 'writes': None},
                                 source_sha=context.get('source_sha') if context else None)
        summary['writes'] = None
        summary['authentication'] = authentication
        if isinstance(exc, CheckpointUnavailable) or (checkpoint is not None and checkpoint.broken):
            return code, summary
        # Failures before external effect may leave a known lease; still avoid
        # inferring a clean lifecycle from an exception or performing a retry.
        return code, summary


def run_control(control, state_store, pages_checkout):
    """Apply an explicit STOP or bounded rollback in the trusted main job.

    The action word is a request only. The workflow identity, OIDC-backed
    checkpoint lease and saved journal provide authority; callers supply no
    receipt SHA or release packet.
    """
    if control not in ('stop','rollback','resume'):
        return 2, public_summary({'status':'UNKNOWN','reason':'CONTROL_INVALID','writes':None})
    checkpoint=None; context=None; authentication='NOT_PROVEN'
    try:
        context=_check_main_context(pages_checkout)
        if os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch':
            raise PermissionError('owner control requires an official workflow dispatch')
        root=_private_fresh_root(state_store,context['runner_temp'])
        checkpoint=PrivateCheckpoint(run_id=context['run_id'],run_attempt=context['attempt'])
        checkpoint.acquire(root)
        authentication='GATEWAY_ACKNOWLEDGED'
        store=CycleStore(Path(checkpoint.db).parent)
        host=GitHubActionsCycleHost(checkpoint,context['pages_root'],None,
                                    context=None,assessment=None,scope=None)
        with store.owner_lock() as acquired:
            if not acquired:
                report={'status':'OWNER_BUSY','writes':0}
            else:
                host.assert_session(store)
                if control=='stop':
                    store.stop()
                    report={'status':'STOPPED_BY_OWNER','writes':0}
                elif control=='resume':
                    from manager_core.owned_cycle import _occurrence_reader
                    from manager_core.reconcile import reconcile_pending_owned
                    from datetime import datetime,timezone
                    if not store.stopped():
                        report={'status':'CONTROL_STOP_REQUIRED','writes':0}
                    else:
                        rollback=host.reconcile_pending_rollbacks(store)
                    if (store.stopped() and rollback is not None and
                            rollback.get('status')=='UNKNOWN'):
                        report={'status':'UNKNOWN','writes':None,
                                'reason':'ROLLBACK_RECONCILIATION_PENDING'}
                    elif store.stopped() and not (rollback is not None and
                            rollback.get('status')=='UNKNOWN'):
                        reader=_occurrence_reader(store,host)
                        reconcile_pending_owned(store.journal,reader,datetime.now(timezone.utc))
                        if store.journal.pending_records(limit=1):
                            report={'status':'UNKNOWN','writes':None,
                                    'reason':'OCCURRENCE_RECONCILIATION_PENDING'}
                        else:
                            delivery=_recover_owned_deliveries(store,host,host._now(),
                                                               allow_rollback=False)
                            if (delivery is not None or store.journal.pending_deliveries(limit=1) or
                                    store.journal.pending_rollbacks(limit=1)):
                                report={'status':'UNKNOWN','writes':None,
                                        'reason':'DELIVERY_RECONCILIATION_PENDING'}
                            else:
                                current=host.observe_current_delivery(store.journal)
                                valid=(type(current) is dict and
                                       current.get('kind') in ('candidate','rollback') and
                                       type(current.get('evidence')) is dict and
                                       current['evidence'].get('status')=='VERIFIED' and
                                       current['evidence'].get('proof_level')=='P2')
                                evidence=current.get('evidence') if type(current) is dict else None
                                if valid and current['kind']=='candidate':
                                    saved=store.journal.record(current.get('effect_key'))
                                    valid=(saved is not None and saved.status=='PRESENT' and
                                        saved.receipt_ref==current.get('receipt_ref') and
                                        evidence.get('effect_key')==saved.key and
                                        evidence.get('receipt_ref')==saved.receipt_ref and
                                        evidence.get('candidate_sha256')==
                                            json.loads(saved.packet_json).get('candidate_sha256'))
                                elif valid:
                                    saved=store.journal.rollback_record(current.get('effect_key'))
                                    valid=(saved is not None and saved.status=='PRESENT' and
                                        saved.receipt_ref==current.get('receipt_ref') and
                                        evidence.get('effect_key')==saved.key and
                                        evidence.get('receipt_ref')==saved.receipt_ref and
                                        evidence.get('baseline_sha256')==
                                            json.loads(saved.packet_json).get('baseline_sha256'))
                                if valid:
                                    store.resume()
                                    report={'status':'RESUMED_BY_OWNER','writes':0}
                                else:
                                    report={'status':'UNKNOWN','writes':None,
                                            'reason':'CURRENT_DELIVERY_NOT_VERIFIED_P2'}
                elif not store.stopped():
                    report={'status':'CONTROL_STOP_REQUIRED','writes':0}
                else:
                    report=host.rollback_latest_owned(store)
                checkpoint.save()
                checkpoint.release()
        summary=public_summary(report,source_sha=context['source_sha'],
                               receipt_sha=report.get('receipt_ref'))
        summary['authentication']=authentication
        return (0 if report.get('status') in ('STOPPED_BY_OWNER','CONTROL_STOP_REQUIRED',
                    'ROLLBACK_SUBMITTED','ROLLBACK_RECONCILED','RESUMED_BY_OWNER') else 2),summary
    except Exception:
        summary=public_summary({'status':'UNKNOWN','reason':'RUNTIME_UNAVAILABLE','writes':None},
                               source_sha=context.get('source_sha') if context else None)
        summary['writes']=None;summary['authentication']=authentication
        return 2,summary


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs='?', choices=('preflight', 'run-once', 'stop', 'rollback','resume'),
                        help='default is the read-only preflight')
    parser.add_argument('--state-store', type=Path,
                        help='preflight: inspected only; trusted commands: fresh private RUNNER_TEMP child')
    parser.add_argument('--pages-checkout', type=Path,
                        help='existing clean canonical gh-pages checkout (run-once only)')
    return parser


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command in (None, 'preflight'):
        if args.pages_checkout is not None:
            parser.error('--pages-checkout is valid only for run-once or owner control')
        code, summary = run_preflight(state_store=args.state_store)
    else:
        if args.state_store is None or args.pages_checkout is None:
            parser.error('trusted command requires --state-store and --pages-checkout')
        if args.command=='run-once':
            code, summary = run_once(args.state_store, args.pages_checkout)
        else:
            code, summary = run_control(args.command, args.state_store, args.pages_checkout)
    print(json.dumps(summary, ensure_ascii=False, separators=(',', ':'), sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
