"""Independent execution/source evidence; never a billing or net-P&L calculator."""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import stat
import sys
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from effect_store import _append_once
from risk_policy import parse_instant


CATALOG_PATH = Path('apps/life-manager/config/product-loop-catalog.json')


MAX_RELEASE_METADATA_BYTES = 16 * 1024 * 1024


def _release_bytes(root,relative):
    relative=Path(relative)
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('source_release_invalid')
    flags=os.O_RDONLY|os.O_DIRECTORY|getattr(os,'O_NOFOLLOW',0)
    directory=os.open(root,flags)
    try:
        for part in relative.parts[:-1]:
            child=os.open(part,flags,dir_fd=directory)
            os.close(directory);directory=child
        descriptor=os.open(relative.name,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|os.O_NONBLOCK,dir_fd=directory)
        try:
            info=os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>MAX_RELEASE_METADATA_BYTES:
                raise ValueError('source_release_invalid')
            with os.fdopen(descriptor,'rb') as handle:
                descriptor=-1;value=handle.read(MAX_RELEASE_METADATA_BYTES+1)
            if len(value)>MAX_RELEASE_METADATA_BYTES:raise ValueError('source_release_invalid')
            return value
        finally:
            if descriptor>=0:os.close(descriptor)
    finally:os.close(directory)


def _gap(reason):
    return {'coverage_state': 'gap', 'reason': reason, 'appended': False}


def record_source_inventory(ledger: Path, *, release_root: Path, owner_id: str,
                            run_id: str | None, occurrence_id: str | None) -> dict:
    """Capture this execution release's declaration without inferring costs.

    Physical run and claimed occurrence are distinct host identities. Missing
    identity or release evidence produces no invented snapshot or zero cost.
    """
    if (not isinstance(owner_id, str) or not owner_id
            or not isinstance(run_id, str) or not run_id
            or not isinstance(occurrence_id, str) or not occurrence_id.startswith(owner_id + ':')):
        return _gap('source_execution_identity_missing')
    try:
        manifest = json.loads(_release_bytes(Path(release_root),'RELEASE.json'))
        catalog_bytes = _release_bytes(Path(release_root),CATALOG_PATH)
        catalog = json.loads(catalog_bytes)
        sha = manifest.get('sha')
        if (not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{40}', sha)
                or manifest.get('release_paths') != 'ALL'):
            return _gap('source_release_invalid')
        loops = [row for row in catalog['loops'] if row.get('id') == 'investment']
        if len(loops) != 1 or owner_id not in loops[0].get('job_ids', []):
            return _gap('source_owner_invalid')
        declaration = loops[0].get('cost_source_inventory')
        if (not isinstance(declaration, dict) or declaration.get('schema_version') != 1
                or declaration.get('status') not in ('unverified', 'verified')
                or not isinstance(declaration.get('sources'), list)):
            return _gap('source_declaration_unavailable')
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return _gap('source_declaration_unavailable')
    digest = hashlib.sha256(catalog_bytes).hexdigest()
    identity = {'owner_id': owner_id, 'release_sha': sha}
    prepared = {}
    def prepare(existing):
        previous = [row for row in existing if row.get('receipt_type') == 'cost_source_inventory'
                    and all(row.get(key) == value for key, value in identity.items())]
        conflict = any(row.get('catalog_sha256') != digest for row in previous)
        prepared['conflict'] = conflict
        row = {**identity, 'receipt_type': ('cost_source_inventory_conflict' if conflict else 'cost_source_inventory'),
               'schema_version': 1, 'catalog_sha256': digest, 'run_id': run_id, 'occurrence_id': occurrence_id,
               'recorded_at': datetime.now(timezone.utc).isoformat(),
               'evidence_refs': [f'lm-release://{sha}/{CATALOG_PATH.as_posix()}']}
        if not conflict:
            row['source_declaration'] = declaration
            row['execution_owner_ids'] = loops[0]['job_ids']
        return row
    try:
        appended = _append_once(Path(ledger), prepare, ('receipt_type', 'owner_id', 'release_sha', 'catalog_sha256'))
    except (OSError, ValueError) as error:
        return {'coverage_state': 'gap', 'reason': 'source_inventory_write_failed', 'appended': None,
                'error_class': type(error).__name__, 'retryable': True, 'next_action': 'inspect_owner_ledger',
                'release_sha': sha, 'catalog_sha256': digest}
    return {'coverage_state': 'gap', 'reason': ('source_declaration_conflict' if prepared['conflict']
            else 'source_inventory_not_evaluated' if declaration['status'] == 'verified'
            else 'source_declaration_unverified'), 'appended': appended,
            'release_sha': sha, 'catalog_sha256': digest}


_COST_CATEGORIES = frozenset({'model_cost', 'tool_cost', 'browser_cost', 'infra_cost'})
_OWNER_MODES = {'alpaca-investment-paper': 'paper', 'alpaca-investment-live': 'live'}


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _ids(value, *, nonempty=True):
    return isinstance(value, list) and (bool(value) or not nonempty) and all(_text(x) for x in value)


def _hex(value, length):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{' + str(length) + '}', value) is not None


def _census_scope(trip, owner, observed):
    mode = _OWNER_MODES[owner]
    kind = trip.get('scope_kind', 'order_pair')
    ids = trip.get('order_ids')
    if (kind not in {'order_pair', 'owner_period'} or not _ids(ids, nonempty=False)
            or (kind == 'order_pair' and (not ids or len(set(ids)) != len(ids)))
            or (kind == 'owner_period' and ids != [])
            or trip.get('owner_id', owner) != owner or trip.get('mode', mode) != mode
            or trip.get('paper', mode == 'paper') is not (mode == 'paper')
            or (kind == 'owner_period' and not {'owner_id', 'mode', 'paper', 'period_end'} <= trip.keys())):
        raise ValueError
    start = parse_instant(trip.get('period_start'))
    end = parse_instant(trip.get('closed_at') if kind == 'order_pair' else trip.get('period_end'))
    if (not start < end <= observed or not _ids(trip.get('source_receipt_ids'), nonempty=False)
            or ('period_end' in trip and parse_instant(trip['period_end']) != end)):
        raise ValueError
    return {'scope_kind': kind, 'owner_id': owner, 'mode': mode, 'paper': mode == 'paper',
            'order_ids': list(ids), 'period_start': start.isoformat(), 'period_end': end.isoformat(),
            'source_receipt_ids': sorted(set(trip['source_receipt_ids'])),
            'required_sources': [], 'execution_refs': [], 'known_paid_bindings': [],
            'evidence_refs': [], 'gaps': []}


def build_expected_inventory(trips, *, beneficiary_owner_id, observed_at,
                             runtime_rows_by_owner, occurrence_rows_by_owner,
                             release_inputs, paid_bindings):
    """Census independent execution declarations; never evaluate billed costs.

    Inputs are read-only snapshots prepared by the caller. Their retrieval and
    historical coverage are not proved by rows alone, so this stage never emits
    complete cost coverage, money, a synthetic occurrence, or a provider query.
    """
    result = {'schema_version': 1, 'beneficiary_owner_id': beneficiary_owner_id,
              'observed_at': observed_at, 'coverage_state': 'gap',
              'reason': 'cost_coverage_not_evaluated', 'scopes': [], 'gaps': []}
    def gap(target, reason, **context):
        value = {'reason': reason, **context}
        if value not in target['gaps']:
            target['gaps'].append(value)
    try:
        observed = parse_instant(observed_at)
        if (beneficiary_owner_id not in _OWNER_MODES or not isinstance(trips, list)
                or not isinstance(runtime_rows_by_owner, dict) or not isinstance(occurrence_rows_by_owner, dict)
                or not isinstance(release_inputs, dict) or not isinstance(paid_bindings, list)):
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        gap(result, 'census_input_invalid')
        return result
    if not trips:
        gap(result, 'scope_missing')
    for index, trip in enumerate(trips):
        try:
            scope = _census_scope(trip, beneficiary_owner_id, observed)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            gap(result, 'scope_invalid', scope_index=index)
            continue
        result['scopes'].append(scope)
        gap(scope, 'history_coverage_unverified')
        if not scope['source_receipt_ids'] and scope['scope_kind']!='owner_period':
            gap(scope, 'scope_evidence_missing')
        start, end = parse_instant(scope['period_start']), parse_instant(scope['period_end'])
        sources, evidence, visited, pending = {}, set(), set(), [beneficiary_owner_id]

        def add_source(provider, account, category, *, owners=(), releases=(), refs=()):
            key = (provider, account, category)
            row = sources.setdefault(key, {'provider': provider, 'billing_account_ref': account,
                'category': category, 'execution_owner_ids': set(), 'release_refs': set(), 'evidence_refs': set()})
            row['execution_owner_ids'].update(owners)
            row['release_refs'].update(releases)
            row['evidence_refs'].update(refs)
            evidence.update(refs)

        def declarations(sha, execution_owner):
            snapshots = release_inputs.get(sha)
            if not isinstance(snapshots, list) or not snapshots:
                gap(scope, 'source_release_missing', release_sha=sha)
                return
            signatures = set()
            for snapshot in snapshots:
                if not isinstance(snapshot, dict) or snapshot.get('release_sha') != sha:
                    gap(scope, 'source_release_invalid', release_sha=sha)
                    continue
                if snapshot.get('receipt_type') == 'cost_source_inventory_conflict':
                    gap(scope, 'source_declaration_conflict', release_sha=sha)
                    continue
                declaration = snapshot.get('source_declaration')
                jobs, refs = snapshot.get('execution_owner_ids'), snapshot.get('evidence_refs')
                if (snapshot.get('receipt_type') != 'cost_source_inventory'
                        or not _hex(snapshot.get('catalog_sha256'), 64)
                        or not isinstance(declaration, dict) or not _ids(jobs) or not _ids(refs)
                        or type(declaration.get('schema_version')) is not int or declaration['schema_version'] != 1
                        or not isinstance(declaration.get('sources'), list)):
                    gap(scope, 'source_release_invalid', release_sha=sha)
                    continue
                try:
                    signatures.add(json.dumps([snapshot['catalog_sha256'], declaration, sorted(jobs)], sort_keys=True))
                except (TypeError, ValueError):
                    gap(scope, 'source_release_invalid', release_sha=sha)
                    continue
                if len(signatures) > 1:
                    gap(scope, 'source_declaration_conflict', release_sha=sha)
                if execution_owner not in jobs:
                    gap(scope, 'source_owner_invalid', execution_owner_id=execution_owner, release_sha=sha)
                if declaration.get('status') != 'verified':
                    gap(scope, 'source_declaration_unverified', release_sha=sha)
                if not declaration['sources']:
                    gap(scope, 'source_declaration_empty', release_sha=sha)
                evidence.update(refs)
                for source in declaration['sources']:
                    if not isinstance(source, dict):
                        gap(scope, 'source_invalid', release_sha=sha)
                        continue
                    beneficiary, mode = source.get('beneficiary_owner_id'), source.get('beneficiary_mode')
                    if (not _text(beneficiary) or beneficiary not in jobs or not _text(mode)
                            or mode not in {'paper', 'live', 'shadow'}
                            or beneficiary in _OWNER_MODES and mode != _OWNER_MODES[beneficiary]):
                        gap(scope, 'source_invalid', release_sha=sha)
                        continue
                    if beneficiary != beneficiary_owner_id:
                        continue
                    executor = source.get('execution_owner_id')
                    categories, source_refs = source.get('covered_categories'), source.get('evidence_refs')
                    if (source.get('beneficiary_mode') != scope['mode'] or not _text(source.get('provider'))
                            or not _text(executor) or executor not in jobs or not _ids(categories)
                            or any(category not in _COST_CATEGORIES for category in categories)
                            or source.get('attribution') != 'exact_evidence_required' or not _ids(source_refs)):
                        gap(scope, 'source_invalid', release_sha=sha)
                        continue
                    account = source.get('billing_account_ref')
                    if not _text(account):
                        account = None
                        gap(scope, 'source_account_missing', provider=source['provider'], release_sha=sha)
                    for category in categories:
                        add_source(source['provider'], account, category, owners=[executor], releases=[sha],
                                   refs=[*refs, *source_refs])
                    if executor != beneficiary_owner_id:
                        gap(scope, 'shared_attribution_unproven', execution_owner_id=executor)
                    if executor not in visited and executor not in pending:
                        pending.append(executor)

        while pending:
            owner = pending.pop(0)
            visited.add(owner)
            rows = runtime_rows_by_owner.get(owner)
            if not isinstance(rows, list):
                gap(scope, 'runtime_owner_missing', execution_owner_id=owner)
                continue
            events, groups, invalid, conflicts = {}, {}, {}, set()
            for row in rows:
                if not isinstance(row, dict):
                    gap(scope, 'runtime_event_invalid', execution_owner_id=owner)
                    continue
                try:
                    stamp = parse_instant(row.get('timestamp'))
                    if (row.get('owner_id') != owner or row.get('job_id') != owner
                            or not _text(row.get('run_id'))):
                        raise ValueError
                except (ValueError, TypeError, OverflowError):
                    gap(scope, 'runtime_event_invalid', execution_owner_id=owner)
                    continue
                valid_phase = (_text(row.get('phase')) and _text(row.get('status'))
                    and row['phase'] in {'plan', 'execute', 'reconcile', 'verify', 'report'}
                    and row['status'] in {'running', 'pass', 'fail', 'blocked'})
                if valid_phase and not (row['phase'] == 'execute' and row['status'] == 'running'
                        or row['phase'] == 'report' and row['status'] in {'pass', 'fail', 'blocked'}):
                    continue
                if (not valid_phase or not _text(row.get('event_id')) or not _hex(row.get('release_sha'), 40)
                        or not _ids(row.get('evidence_refs'))):
                    invalid.setdefault(row['run_id'], []).append((stamp, row))
                    continue
                event_id = row['event_id']
                if event_id in events:
                    if events[event_id] != row:
                        conflicts.add(event_id)
                    else:
                        continue
                events[event_id] = row
                groups.setdefault(row['run_id'], []).append((stamp, row))
            selected = 0
            for run_id in sorted(groups.keys() | invalid.keys()):
                valid = groups.get(run_id, [])
                run = [*valid, *invalid.get(run_id, [])]
                starts = [(t, r) for t, r in valid if r['phase'] == 'execute']
                terminals = [(t, r) for t, r in valid if r['phase'] == 'report']
                earliest=min(t for t,_ in run)
                if (earliest>=end if scope['scope_kind']=='owner_period' else earliest>end) or terminals and max(t for t,_ in run)<start:
                    continue
                selected += 1
                for event_id in sorted(conflicts & {row['event_id'] for _, row in valid}):
                    gap(scope, 'runtime_event_conflict', execution_owner_id=owner, event_id=event_id)
                for sha in sorted({r['release_sha'] for _, r in run if _hex(r.get('release_sha'), 40)}):
                    declarations(sha, owner)
                evidence.update(ref for _, row in run if _ids(row.get('evidence_refs')) for ref in row['evidence_refs'])
                if run_id in invalid:
                    gap(scope, 'runtime_event_invalid', execution_owner_id=owner, run_id=run_id)
                    continue
                if len(starts) != 1 or len(terminals) != 1:
                    gap(scope, 'runtime_start_missing' if not starts else 'runtime_terminal_missing'
                        if not terminals else 'runtime_event_cardinality', execution_owner_id=owner, run_id=run_id)
                    continue
                (started_at, first), (finished_at, terminal) = starts[0], terminals[0]
                identity_fields = ('release_sha', 'loaded_argv_sha256', 'loaded_env_sha256')
                if (started_at > finished_at or finished_at > observed
                        or any(first.get(k) != terminal.get(k) for k in identity_fields)
                        or not all(_hex(terminal.get(k), 64) for k in identity_fields[1:])
                        or any(row['event_id'] in conflicts for _, row in run)):
                    gap(scope, 'runtime_identity_mismatch', execution_owner_id=owner, run_id=run_id)
                    continue
                occurrence = terminal.get('occurrence_id')
                if not isinstance(occurrence, str) or not occurrence.startswith(owner + ':'):
                    gap(scope, 'runtime_occurrence_missing', execution_owner_id=owner, run_id=run_id)
                    continue
                admission_rows = occurrence_rows_by_owner.get(owner)
                matches = []
                for row in admission_rows if isinstance(admission_rows, list) else []:
                    if isinstance(row, dict) and row.get('owner_id') == owner and row.get('occurrence_id') == occurrence:
                        if row not in matches:
                            matches.append(row)
                if len(matches) != 1:
                    gap(scope, 'admission_missing' if not matches else 'admission_conflict',
                        execution_owner_id=owner, run_id=run_id, occurrence_id=occurrence)
                    continue
                admission = matches[0]
                try:
                    if (parse_instant(admission.get('queued_at')) > started_at or admission.get('state') != 'released'
                            or type(admission.get('effect_unknown')) not in (int, bool)
                            or admission['effect_unknown'] != 0):
                        raise ValueError
                except (ValueError, TypeError, OverflowError):
                    gap(scope, 'admission_unresolved', execution_owner_id=owner, run_id=run_id, occurrence_id=occurrence)
                scope['execution_refs'].append({'execution_owner_id': owner, 'run_id': run_id,
                    'occurrence_id': occurrence, 'release_sha': terminal['release_sha'],
                    'loaded_argv_sha256': terminal['loaded_argv_sha256'], 'loaded_env_sha256': terminal['loaded_env_sha256'],
                    'start_event_id': first['event_id'], 'terminal_event_id': terminal['event_id'],
                    'started_at':started_at.isoformat(),'finished_at':finished_at.isoformat()})
            if not selected:
                gap(scope, 'source_execution_missing', execution_owner_id=owner)

        if scope['scope_kind']=='owner_period' and not scope['source_receipt_ids']:
            scope['source_receipt_ids']=sorted({ref[key] for ref in scope['execution_refs']
                for key in ('start_event_id','terminal_event_id')})
            if not scope['source_receipt_ids']:gap(scope,'scope_evidence_missing')

        for binding in paid_bindings:
            try:
                if not isinstance(binding, dict):
                    raise ValueError
                if (binding.get('order_ids') != scope['order_ids']
                        or parse_instant(binding.get('period_start')) != start
                        or parse_instant(binding.get('period_end')) != end):
                    continue
                if (any(key in binding and binding[key] != scope[key] for key in ('owner_id', 'mode'))
                        or 'paper' in binding and binding['paper'] is not scope['paper']):
                    gap(scope, 'paid_binding_scope_invalid')
                    continue
                if not {'owner_id', 'mode', 'paper'} <= binding.keys():
                    gap(scope, 'paid_binding_owner_unverified')
                if (not _text(binding.get('receipt_id')) or not _text(binding.get('provider'))
                        or binding.get('category') not in _COST_CATEGORIES or not _ids(binding.get('evidence_refs'))):
                    raise ValueError
                # Same identity contract as the existing paid binding writer.
                from paper_performance import _operating_identity_keys
                _operating_identity_keys(binding)
                account = binding.get('billing_account_ref')
                if not _text(account):
                    account = None
                    gap(scope, 'paid_account_missing', receipt_id=binding['receipt_id'])
                add_source(binding['provider'], account, binding['category'], refs=binding['evidence_refs'])
                scope['known_paid_bindings'].append(deepcopy({key: binding[key] for key in
                    ('receipt_id', 'provider', 'billing_account_ref', 'category',
                    'owner_id', 'mode', 'paper', 'order_ids', 'period_start', 'period_end',
                    'charge_identity', 'identity_aliases', 'evidence_refs') if key in binding}))
            except (ValueError, TypeError, OverflowError):
                gap(scope, 'paid_binding_invalid')
        for key in sorted(sources, key=repr):
            scope['required_sources'].append({k: sorted(v) if isinstance(v, set) else v
                                              for k, v in sources[key].items()})
        for category in sorted(_COST_CATEGORIES - {key[2] for key in sources}):
            gap(scope, 'source_category_uncovered', category=category)
        scope['execution_refs'].sort(key=lambda row: (row['execution_owner_id'], row['run_id']))
        scope['evidence_refs'] = sorted(evidence)
    return result


MAX_INVENTORY_OWNERS = 16
MAX_INVENTORY_ADMISSIONS = 50_000


def _release_snapshot(root,sha):
    manifest=json.loads(_release_bytes(root,'RELEASE.json'))
    if manifest.get('sha')!=sha or manifest.get('release_paths')!='ALL':return None
    raw=_release_bytes(root,CATALOG_PATH)
    loops=[r for r in json.loads(raw)['loops'] if r.get('id')=='investment']
    if len(loops)!=1:raise ValueError('source_release_invalid')
    return {'receipt_type':'cost_source_inventory','release_sha':sha,
        'catalog_sha256':hashlib.sha256(raw).hexdigest(),'source_declaration':loops[0].get('cost_source_inventory'),
        'execution_owner_ids':loops[0].get('job_ids'),
        'evidence_refs':[f'lm-release://{sha}/{CATALOG_PATH.as_posix()}']}


def _private_cost_object(path,max_bytes):
    descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        info=os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1
                or stat.S_IMODE(info.st_mode)!=0o600 or info.st_size>max_bytes):raise ValueError
        with os.fdopen(descriptor,'r') as handle:
            descriptor=-1;value=json.load(handle)
        if not isinstance(value,dict):raise ValueError
        return value
    finally:
        if descriptor>=0:os.close(descriptor)


def select_expected_inventory(inventory,trips):
    if inventory is None:return None
    ids={tuple(trip['order_ids']) for trip in trips}
    return {**inventory,'scopes':[scope for scope in inventory['scopes'] if tuple(scope['order_ids']) in ids]}


def read_expected_inventory(state,trips,*,observed_at,owner_id='alpaca-investment-paper',release_root=None):
    """Read independent local inputs; no provider call, DB creation or coverage promotion."""
    code_root=Path(__file__).resolve().parents[2]
    if str(code_root) not in sys.path:sys.path.append(str(code_root))
    from runtime.loop import lm_loop
    root=Path(release_root) if release_root is not None else code_root
    runtime={};admissions={};releases={};reads={};errors=[];paid_bindings=[]
    def error(reason,owner=None):
        item={'reason':reason}
        if owner is not None:item['execution_owner_id']=owner
        if item not in errors:errors.append(item)
    def finish():
        result=build_expected_inventory(trips,beneficiary_owner_id=owner_id,observed_at=observed_at,
            runtime_rows_by_owner=runtime,occurrence_rows_by_owner=admissions,release_inputs=releases,paid_bindings=paid_bindings)
        result['gaps'].extend(errors);result['input_reads']=reads
        result['read_limits']={'owners':MAX_INVENTORY_OWNERS,'admission_rows_per_owner':MAX_INVENTORY_ADMISSIONS,
            'runtime_archives_per_owner':lm_loop.MAX_PRE_EFFECT_ARCHIVES}
        return result
    try:
        if owner_id not in _OWNER_MODES:raise ValueError
        observed=parse_instant(observed_at)
        if not isinstance(trips,list):raise ValueError
        if not trips:return finish()
        entries=json.loads(_release_bytes(root,'config/loop-registry.json'))['loops']
        entry=entries.get(owner_id)
        if not isinstance(entry,dict) or Path(entry['state_root']).expanduser().resolve()!=Path(state).resolve():
            error('inventory_state_owner_mismatch',owner_id);return finish()
    except (OSError,ValueError,KeyError,TypeError,AttributeError):
        error('inventory_registry_unavailable',owner_id);return finish()
    pending=[owner_id]
    while pending:
        owner=pending.pop(0)
        if owner in reads:continue
        if len(reads)>=MAX_INVENTORY_OWNERS:
            error('inventory_owner_read_limit',owner);continue
        detail=reads[owner]={}
        entry=entries.get(owner)
        if not isinstance(entry,dict) or not _text(entry.get('state_root')):
            error('inventory_owner_unregistered',owner);continue
        directory=Path(entry['state_root']).expanduser()
        rows,reason=lm_loop._owner_runtime_rows(entry)
        try:
            if rows is None:raise ValueError
            stamps=[parse_instant(r['timestamp']) for r in rows]
            archives=len(list(directory.glob('events-*.jsonl.gz')))
            detail['runtime']={'status':'ok','row_count':len(rows),'archives_available':archives,
                'first_event_at':min(stamps).isoformat() if stamps else None,
                'last_event_at':max(stamps).isoformat() if stamps else None}
            if archives>lm_loop.MAX_PRE_EFFECT_ARCHIVES:error('runtime_archive_read_limit',owner)
            runtime[owner]=rows
        except (OSError,ValueError,KeyError,TypeError):
            detail['runtime']={'status':'unavailable'};error('runtime_read_unavailable',owner)
        try:ledger=lm_loop._private_jsonl_rows(directory/'receipts.jsonl',strict=True)
        except (OSError,ValueError,TypeError,RecursionError):ledger=[]
        detail['ledger']={'status':'ok' if ledger else 'unavailable','row_count':len(ledger)}
        if not ledger:error('source_ledger_unavailable',owner)
        for row in ledger:
            kind=row.get('receipt_type')
            if kind is not None and not isinstance(kind,str):
                error('source_snapshot_invalid',owner);continue
            if kind not in {'cost_source_inventory','cost_source_inventory_conflict'}:
                if 'source_declaration' in row or 'catalog_sha256' in row:error('source_snapshot_invalid',owner)
                continue
            if row.get('owner_id')!=owner:
                error('source_snapshot_owner_mismatch',owner);continue
            sha=row.get('release_sha')
            if not _hex(sha,40):
                error('source_snapshot_invalid',owner);continue
            releases.setdefault(sha,[]).append(row)
        try:
            database=lm_loop.admission_root()/'admission-v2.sqlite3'
            values=lm_loop._read_admission_rows(database,
                'SELECT occurrence_id,state,queued_at,effect_unknown FROM occurrences WHERE owner_id=? AND queued_at<=? ORDER BY queued_at DESC,occurrence_id LIMIT ?',
                (owner,observed.timestamp(),MAX_INVENTORY_ADMISSIONS+1))
            if len(values)>MAX_INVENTORY_ADMISSIONS:error('admission_read_limit',owner)
            normalized=[]
            for occurrence,status,queued,unknown in values[:MAX_INVENTORY_ADMISSIONS]:
                if type(queued) not in (int,float) or not math.isfinite(queued):raise ValueError
                normalized.append({'owner_id':owner,'occurrence_id':occurrence,'state':status,
                    'queued_at':datetime.fromtimestamp(queued,timezone.utc).isoformat(),'effect_unknown':unknown})
            admissions[owner]=normalized;detail['admission']={'status':'ok','row_count':len(normalized)}
        except (OSError,sqlite3.Error,ValueError,OverflowError,TypeError):
            detail['admission']={'status':'unavailable'};error('admission_read_unavailable',owner)
        for sha in {r.get('release_sha') for r in runtime.get(owner,[]) if _hex(r.get('release_sha'),40)}:
            if sha in releases:continue
            parent=root.parent if (root/'RELEASE.json').exists() else Path.home()/'loops/releases'
            candidates=[root,*sorted(parent.glob('*-'+sha[:8]))]
            for candidate in candidates:
                try:
                    if candidate.is_symlink():continue
                    captured=_release_snapshot(candidate,sha)
                    if captured is not None:releases.setdefault(sha,[]).append(captured)
                except (OSError,ValueError,KeyError,TypeError,AttributeError):continue
        if owner==owner_id:
            mode=_OWNER_MODES[owner_id];detail['paid_cache']={}
            for name in ('performance-crypto-latest.json','performance-latest.json'):
                path=directory/name
                if not path.exists() and not path.is_symlink():continue
                try:
                    cached=_private_cost_object(path,lm_loop.MAX_HARNESS_FAILURE_BYTES)
                    legacy=name=='performance-latest.json' and mode=='paper' and cached.get('owner_id') is None
                    if (cached.get('mode')!=mode or cached.get('paper') is not (mode=='paper')
                            or not legacy and cached.get('owner_id')!=owner_id):
                        error('paid_cache_scope_invalid',owner);continue
                    components=cached.get('known_operating_cost_components',cached.get('operating_cost_components',[]))
                    if not isinstance(components,list):raise ValueError
                    for component in components:
                        if not isinstance(component,dict):raise ValueError
                        context={'mode':mode,'paper':mode=='paper'}
                        if not legacy:context['owner_id']=owner_id
                        if any(k in component and component[k]!=v for k,v in context.items()):
                            error('paid_cache_scope_invalid',owner);continue
                        paid_bindings.append({**deepcopy(component),**context})
                    detail['paid_cache'][name]={'status':'ok','component_count':len(components)}
                except (OSError,ValueError,TypeError,KeyError,RecursionError):
                    detail['paid_cache'][name]={'status':'unavailable'};error('paid_cache_unavailable',owner)
        for snapshots in releases.values():
            for captured in snapshots:
                declaration=captured.get('source_declaration')
                sources=declaration.get('sources') if isinstance(declaration,dict) else None
                for source in sources if isinstance(sources,list) else []:
                    if (isinstance(source,dict) and source.get('beneficiary_owner_id')==owner_id
                            and source.get('beneficiary_mode')==_OWNER_MODES[owner_id]):
                        executor=source.get('execution_owner_id')
                        if (_text(executor) and isinstance(captured.get('execution_owner_ids'),list)
                                and executor in captured['execution_owner_ids'] and executor not in reads and executor not in pending):pending.append(executor)
    return finish()
