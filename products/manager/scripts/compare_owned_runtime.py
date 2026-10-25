#!/usr/bin/env python3
"""Offline E16 current/DBOS crash probe. Only scratch state and local Git effects.

Run --backend current with stdlib only; DBOS is an isolated optional install. This development-only probe imports the
repository's local Git fixture; it is not a production adapter or scheduler.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True
SCRIPT = Path(__file__).resolve()
PRODUCT = SCRIPT.parents[1]
REPO = PRODUCT.parents[1]
PIN = 'e63ee714e031287c9b3447a173be835d6eaf1f95'
CASES = ('slot_claim', 'reserved_before_send', 'response_loss', 'checkpoint_loss',
         'cached_step_replay', 'before_delivery_read', 'fresh_engine_metadata',
         'readonly_multistage_wait')
CRASH_CODE = 81
WAIT_SECONDS = 2.0


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def load(path):
    return json.loads(Path(path).read_text())


def source_imports():
    sys.path[:0] = [str(PRODUCT), str(PRODUCT / 'tests')]
    from manager_core.owned_cycle import CycleConfig, CycleStore, LocalGitCycleSandbox
    from manager_core.digital_handoff import OwnedChangeContext, prepare_owned_change
    from manager_core.models.source import Source
    from manager_core.models.intervention import Candidate
    from manager_core.candidate_verification import TechnicalCriteria, verify_candidate
    from manager_core.collaboration import PublicFact, PlannerContext
    from manager_core.authority import OwnedDigitalScope
    return locals()


def event(root, kind, **payload):
    root = Path(root)
    with sqlite3.connect(root / 'probe-events.sqlite', timeout=15) as db:
        db.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL)')
        db.execute('INSERT INTO events(kind,payload) VALUES(?,?)',
                   (kind, json.dumps(dict(pid=os.getpid(), at=time.time(), **payload), sort_keys=True)))


def events(root):
    with sqlite3.connect(Path(root) / 'probe-events.sqlite') as db:
        return [dict(id=row[0], kind=row[1], **json.loads(row[2]))
                for row in db.execute('SELECT id,kind,payload FROM events ORDER BY id')]


def crash_once(root, point, **detail):
    root = Path(root)
    if load(root / 'fixture.json')['case'] != point:
        return
    marker = root / 'crash.json'
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    with os.fdopen(fd, 'w') as stream:
        json.dump(dict(point=point, at=time.time(), pid=os.getpid(), **detail), stream)
        stream.flush()
        os.fsync(stream.fileno())
    event(root, 'crash', point=point)
    os._exit(CRASH_CODE)


def setup_fixture(root, backend, case):
    ns = source_imports()
    import test_digital_cycle_acceptance as fixtures
    from test_candidate_verification import NOW
    fixture_root = root / 'fixture'
    fixture_root.mkdir()
    config, store, host, git = fixtures.CycleAcceptanceTests().prepare(fixture_root)
    criteria = host.context.criteria
    source = asdict(criteria.official_sources[0])
    source['retrieved_at'] = criteria.official_sources[0].retrieved_at.isoformat()
    candidate = criteria.candidate
    packet = ns['prepare_owned_change'](host.context, host.assessment, host.scope, NOW).packet
    metadata = dict(schema='e16-offline-runtime-probe.v1', backend=backend, case=case,
        now=NOW.isoformat(), config=asdict(config), state=str(store.root),
        paths=dict(checkout=str(host.checkout), served=str(host.served),
                   baseline=str(host.context.baseline_bundle), candidate=str(host.context.candidate_bundle)),
        criteria=dict(candidate={key: getattr(candidate, key) for key in
                      ('candidate_id', 'action', 'target', 'source_refs', 'technical_criterion')},
                      old_link_url=criteria.old_link_url, expected_link_url=criteria.expected_link_url,
                      required_label=criteria.required_label, official_sources=[source],
                      at=criteria.at.isoformat(), version=criteria.version),
        planner=dict(goal=host.context.planner.goal,
                     summary=host.context.planner.facts[0].summary,
                     observed_at=host.context.planner.observed_at.isoformat()),
        scope=dict(scope_id=host.scope.scope_id, allowed_paths=sorted(host.scope.allowed_paths),
                   not_before=host.scope.not_before.isoformat(), expires_at=host.scope.expires_at.isoformat(),
                   max_changed_files=host.scope.max_changed_files, revoked=host.scope.revoked),
        run_id=host.context.run_id, source_audit=host.source_audit,
        expected_parent=git.parent, packet=packet)
    dump(root / 'fixture.json', metadata)
    event(root, 'fixture_created', backend=backend, case=case)


def reconstruct(root, instrument=True):
    root = Path(root).resolve()
    if root == REPO or REPO in root.parents:
        raise ValueError('probe state must be outside source')
    m = load(root / 'fixture.json')
    if m['schema'] != 'e16-offline-runtime-probe.v1':
        raise ValueError('unsupported explicit fixture schema')
    ns = source_imports()
    sources = []
    for item in m['criteria']['official_sources']:
        data = dict(item)
        data['retrieved_at'] = datetime.fromisoformat(data['retrieved_at'])
        sources.append(ns['Source'](**data))
    candidate_fields = dict(m['criteria']['candidate'])
    candidate_fields['source_refs'] = tuple(candidate_fields['source_refs'])
    criteria = ns['TechnicalCriteria'](ns['Candidate'](**candidate_fields),
        m['criteria']['old_link_url'], m['criteria']['expected_link_url'],
        m['criteria']['required_label'], tuple(sources), datetime.fromisoformat(m['criteria']['at']),
        m['criteria']['version'])
    planner = ns['PlannerContext'](m['planner']['goal'],
        (ns['PublicFact'](sources[0], m['planner']['summary']),),
        datetime.fromisoformat(m['planner']['observed_at']))
    paths = {key: Path(value).resolve() for key, value in m['paths'].items()}
    if any(root not in path.parents for path in paths.values()):
        raise ValueError('all fixture paths must belong to this isolated case')
    context = ns['OwnedChangeContext'](m['run_id'], planner, paths['baseline'], paths['candidate'], criteria)
    scope = ns['OwnedDigitalScope'](m['scope']['scope_id'], frozenset(m['scope']['allowed_paths']),
        datetime.fromisoformat(m['scope']['not_before']), datetime.fromisoformat(m['scope']['expires_at']),
        m['scope']['max_changed_files'], m['scope']['revoked'])
    assessment = ns['verify_candidate'](paths['baseline'], paths['candidate'], criteria)
    host = ns['LocalGitCycleSandbox'](paths['checkout'], paths['served'], context, assessment, scope, m['source_audit'])
    state = Path(m['state']).resolve()
    if root not in state.parents:
        raise ValueError('fixture state must belong to this isolated case')
    store = ns['CycleStore'](state)
    if instrument:
        send = host.send
        def counted_send(packet, parent, now):
            event(root, 'send_attempt', key=packet['effect_key'], expected_parent=parent)
            sha = send(packet, parent, now)
            event(root, 'target_advanced', sha=sha)
            crash_once(root, 'response_loss', receipt=sha)
            return sha
        host.send = counted_send
        reserve = store.journal.reserve
        def reserved(*args, **kwargs):
            record = reserve(*args, **kwargs)
            if record.dispatch:
                crash_once(root, 'reserved_before_send', key=record.key)
            return record
        store.journal.reserve = reserved
    return ns['CycleConfig'](**m['config']), store, host, m['packet'], datetime.fromisoformat(m['now'])


def slot_stage(root):
    config, store, host, packet, now = reconstruct(root)
    event(root, 'stage_body', stage='slot')
    with store.owner_lock() as acquired:
        if not acquired:
            return dict(status='OWNER_BUSY', writes=0)
        claimed = store.due(config, now)
        crash_once(root, 'slot_claim', claimed=claimed)
    return dict(status='SLOT_CLAIMED' if claimed else 'NOT_DUE', writes=0)


def dispatch_stage(root):
    from manager_core.owned_cycle import dispatch_owned_once
    _, store, host, packet, now = reconstruct(root)
    event(root, 'stage_body', stage='dispatch')
    result = dispatch_owned_once(store, host, packet, now)
    event(root, 'helper_return', result=result)
    crash_once(root, 'checkpoint_loss', result=result)
    return result


def occurrence_stage(root, observation=1):
    from manager_core.reconcile import reconcile_owned
    _, store, host, packet, _ = reconstruct(root)
    event(root, 'stage_body', stage='occurrence', observation=observation)
    with store.owner_lock() as acquired:
        if not acquired:
            return dict(status='OWNER_BUSY', receipt_ref=None)
        reader = (lambda _key: None) if observation == 0 else host.occurrence
        result = reconcile_owned(store.journal, packet['effect_key'], reader, datetime.now(timezone.utc))
    return asdict(result)


def delivery_stage(root, occurrence):
    _, store, host, packet, _ = reconstruct(root)
    event(root, 'stage_body', stage='delivery')
    verified = occurrence['status'] == 'PRESENT' and host.readback(packet['candidate'])
    return dict(status=occurrence['status'], receipt_ref=occurrence['receipt_ref'],
                delivery_status=('VERIFIED_SANDBOX_TECHNICAL' if verified else
                                 'NOT_CHECKED_OCCURRENCE_UNKNOWN'), deployed=False, proof_level='P0')


def next_slot_stage(root):
    from manager_core.owned_cycle import run_owned_cycle
    config, store, host, _, now = reconstruct(root)
    event(root, 'stage_body', stage='next_slot')
    return run_owned_cycle(config, store, host=host, now=now + timedelta(seconds=config.interval_seconds))


def current_workflow(root, phase):
    case = load(Path(root) / 'fixture.json')['case']
    if phase == 'next_slot':
        return next_slot_stage(root)
    if case == 'slot_claim':
        return slot_stage(root)
    cache = Path(root) / 'current-caller-checkpoint.json'
    if case == 'cached_step_replay' and cache.exists():
        dispatched = load(cache)
        event(root, 'caller_cache_replay', result=dispatched)
    else:
        dispatched = dispatch_stage(root)
        if case == 'cached_step_replay':
            dump(cache, dispatched)
    crash_once(root, 'cached_step_replay', result=dispatched)
    if case == 'readonly_multistage_wait':
        first = occurrence_stage(root, 0)
        event(root, 'wait_started', seconds=WAIT_SECONDS, first_status=first['status'])
        crash_once(root, 'readonly_multistage_wait', wake_at=time.time() + WAIT_SECONDS,
                   kind='current plain wait; diagnostics do not resume deadline')
        wait_started = time.monotonic()
        time.sleep(WAIT_SECONDS)
        event(root, 'wait_completed', backend='current', seconds=time.monotonic() - wait_started)
    occurrence = occurrence_stage(root)
    crash_once(root, 'before_delivery_read', occurrence=occurrence)
    return delivery_stage(root, occurrence)


def dbos_workflow(root, phase, engine_name):
    # This child never consumes a third-party pickle database. Every engine file
    # is created by this probe using public portable JSON serialization.
    from dbos import DBOS, DBOSPortableJSONSerializer, SetWorkflowID, WorkflowSerializationFormat

    @DBOS.step(name='e16-slot', retries_allowed=False)
    def slot(path):
        return slot_stage(path)

    @DBOS.step(name='e16-dispatch', retries_allowed=False)
    def dispatch(path):
        return dispatch_stage(path)

    @DBOS.step(name='e16-occurrence', retries_allowed=False)
    def occurrence(path, observation):
        return occurrence_stage(path, observation)

    @DBOS.step(name='e16-delivery', retries_allowed=False)
    def delivery(path, result):
        return delivery_stage(path, result)

    @DBOS.step(name='e16-next-slot', retries_allowed=False)
    def next_slot(path):
        return next_slot_stage(path)

    @DBOS.workflow(name='e16-offline-probe', serialization_type=WorkflowSerializationFormat.PORTABLE)
    def probe(path, action):
        case = load(Path(path) / 'fixture.json')['case']
        if action == 'next_slot':
            return next_slot(path)
        if case == 'slot_claim':
            return slot(path)
        dispatched = dispatch(path)
        crash_once(path, 'cached_step_replay', result=dispatched)
        if case == 'readonly_multistage_wait':
            first = occurrence(path, 0)
            event(path, 'workflow_wait_call', first_status=first['status'])
            wait_started = time.monotonic()
            DBOS.sleep(WAIT_SECONDS)
            event(path, 'wait_completed', backend='dbos', seconds=time.monotonic() - wait_started)
        result = occurrence(path, 1)
        crash_once(path, 'before_delivery_read', occurrence=result)
        return delivery(path, result)

    DBOS(config=dict(name='e16-offline-probe',
        system_database_url='sqlite:///' + str(Path(root) / (engine_name + '.sqlite')),
        application_version='e16-probe-v1-' + hashlib.sha256(SCRIPT.read_bytes()).hexdigest()[:12],
        executor_id='e16-probe-local', serializer=DBOSPortableJSONSerializer(),
        enable_otlp=False, otlp_traces_endpoints=[], otlp_logs_endpoints=[],
        conductor_key=None, conductor_url=None, log_level='WARNING', max_executor_threads=4))
    DBOS.launch()
    workflow_id = 'e16-case' + ('-next' if phase == 'next_slot' else '')
    if phase == 'restart':
        handle = DBOS.retrieve_workflow(workflow_id)
    else:
        with SetWorkflowID(workflow_id):
            handle = DBOS.start_workflow(probe, str(root), 'next_slot' if phase == 'next_slot' else 'main')
    case = load(Path(root) / 'fixture.json')['case']
    if case == 'readonly_multistage_wait' and not (Path(root) / 'crash.json').exists():
        def interrupt_wait():
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                for step in DBOS.list_workflow_steps(workflow_id):
                    if step['function_name'] == 'DBOS.sleep':
                        crash_once(root, case, wake_at=step['output'],
                                   observed_via='DBOS.list_workflow_steps')
                time.sleep(0.01)
        threading.Thread(target=interrupt_wait, daemon=True).start()
    result = handle.get_result(polling_interval_sec=0.02)
    dump(Path(root) / ('dbos-public-steps-' + phase + '.json'), DBOS.list_workflow_steps(workflow_id))
    DBOS.destroy(workflow_completion_timeout_sec=1)
    return result


def child(args):
    # Disable inherited cloud mode before DBOS import; do not log any values.
    for name in tuple(os.environ):
        if name.startswith(('DBOS_', 'DBOS__', 'OTEL_')):
            os.environ.pop(name)
    os.chdir(args.state_dir)
    def no_network(name, event_args):
        if name in ('socket.connect', 'socket.getaddrinfo', 'socket.bind'):
            raise PermissionError('offline probe forbids socket connection/name lookup/listening')
    sys.addaudithook(no_network)
    source_imports()
    started = time.monotonic()
    event(args.state_dir, 'child_started', backend=args.backend, phase=args.phase)
    if args.backend == 'dbos':
        result = dbos_workflow(args.state_dir, args.phase, args.engine_name)
    else:
        result = current_workflow(args.state_dir, args.phase)
    dump(args.state_dir / ('result-' + args.phase + '.json'),
         dict(result=result, elapsed_seconds=time.monotonic() - started))
    event(args.state_dir, 'child_completed', phase=args.phase, result=result)


def execute_child(root, backend, phase, engine_name='engine'):
    command = [sys.executable, '-B', str(SCRIPT), '--child', '--backend', backend,
               '--state-dir', str(root), '--phase', phase, '--engine-name', engine_name,
               '--source-root', str(PRODUCT)]
    env = dict(os.environ)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    log = root / ('child-' + phase + '.log')
    with log.open('w') as stream:
        try:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                    env=env, timeout=30)
            return dict(phase=phase, exit_code=result.returncode, log=str(log))
        except subprocess.TimeoutExpired:
            return dict(phase=phase, exit_code=None, timed_out=True, log=str(log))


def snapshot(root):
    _, store, host, packet, _ = reconstruct(root, instrument=False)
    record = store.journal.record(packet['effect_key'])
    observed_events = events(root)
    return dict(dispatch_count=sum(e['kind'] == 'send_attempt' for e in observed_events),
        target_advance_count=int(host.git('rev-list', '--count', 'HEAD')) - 1,
        target_sha=host.git('rev-parse', 'HEAD'),
        journal=({key: getattr(record, key) for key in
                  ('key', 'expected_parent', 'status', 'receipt_ref', 'dispatch')} if record else None),
        events=observed_events)


def run_case(root, backend, case):
    root.mkdir(parents=True, mode=0o700)
    setup_fixture(root, backend, case)
    runs = [execute_child(root, backend, 'start')]
    crashed = case != 'fresh_engine_metadata'
    expected_exit = CRASH_CODE if crashed else 0
    if runs[0]['exit_code'] != expected_exit:
        raise AssertionError(f'{backend}/{case}: expected first exit {expected_exit}, got {runs[0]}; see log')
    after_crash = snapshot(root)
    dump(root / 'after-crash.json', after_crash)
    if case == 'readonly_multistage_wait':
        # Let the shortened original wake deadline pass. Current has no durable
        # deadline; DBOS should skip its completed wait when the process returns.
        wake = load(root / 'crash.json')['wake_at']
        time.sleep(max(0, float(wake) - time.time()) + 0.15)
    if crashed:
        runs.append(execute_child(root, backend, 'restart'))
    else:
        runs.append(execute_child(root, backend, 'fresh_engine', 'fresh-engine'))
    if runs[-1]['exit_code'] != 0:
        raise AssertionError(f'{backend}/{case}: restart/fresh failed: {runs[-1]}; see log')
    after_restart = snapshot(root)
    if case == 'slot_claim':
        assert after_restart['journal'] is None, 'slot marker became effect completion'
        assert after_restart['dispatch_count'] == 0
        assert load(root / 'result-restart.json')['result']['status'] == 'NOT_DUE'
        runs.append(execute_child(root, backend, 'next_slot'))
        assert runs[-1]['exit_code'] == 0, runs[-1]
    final = snapshot(root)
    expected_attempts = 0 if case == 'reserved_before_send' else 1
    assert final['dispatch_count'] == expected_attempts, (backend, case, final['dispatch_count'])
    assert final['target_advance_count'] == expected_attempts, (backend, case, final['target_advance_count'])
    if case == 'reserved_before_send':
        assert final['journal']['status'] != 'PRESENT'
        assert load(root / 'result-restart.json')['result']['status'] == 'UNKNOWN'
    else:
        assert final['journal']['status'] == 'PRESENT', final['journal']
        assert final['journal']['receipt_ref'] == final['target_sha']
        assert final['journal']['expected_parent'] == load(root / 'fixture.json')['expected_parent']
        assert final['journal']['dispatch'] is False
    if case == 'before_delivery_read':
        assert after_crash['journal']['status'] == 'PRESENT'
        assert not any(e['kind'] == 'stage_body' and e.get('stage') == 'delivery' for e in after_crash['events'])
    if case == 'checkpoint_loss':
        assert sum(e['kind'] == 'stage_body' and e.get('stage') == 'dispatch' for e in final['events']) == 2
    if case in ('cached_step_replay', 'readonly_multistage_wait') and backend == 'dbos':
        assert sum(e['kind'] == 'stage_body' and e.get('stage') == 'dispatch' for e in final['events']) == 1
    phase = runs[-1]['phase']
    result = load(root / ('result-' + phase + '.json'))
    if case != 'slot_claim':
        expected_delivery = ('NOT_CHECKED_OCCURRENCE_UNKNOWN' if case == 'reserved_before_send'
                             else 'VERIFIED_SANDBOX_TECHNICAL')
        assert result['result']['delivery_status'] == expected_delivery, result
    if case == 'before_delivery_read':
        assert any(e['kind'] == 'stage_body' and e.get('stage') == 'delivery'
                   for e in final['events'] if e['id'] > after_crash['events'][-1]['id'])
    if case == 'readonly_multistage_wait':
        waits = [e['seconds'] for e in final['events'] if e['kind'] == 'wait_completed']
        assert len(waits) == 1, waits
        if backend == 'dbos':
            assert waits[0] < WAIT_SECONDS / 2, waits
        else:
            assert waits[0] >= WAIT_SECONDS * .9, waits
    limitations = ['P0 local Git sandbox; no production authority or official delivery',
                   'No stale backup restore or live volume/owner proof']
    if backend == 'current':
        limitations.append('No durable workflow engine; direct function restart baseline')
        if case == 'cached_step_replay':
            limitations.append('Explicit caller JSON cache injection, not native current engine checkpoint')
    if case == 'readonly_multistage_wait':
        limitations.append(f'Shortened {WAIT_SECONDS}s wait; not long-duration proof')
    receipt = dict(backend=backend, version=importlib.metadata.version('dbos') if backend == 'dbos' else 'existing-single-worker',
        source=PIN if backend == 'dbos' else source_metadata()['manager'],
        failure_case=case, dispatch_count=final['dispatch_count'],
        target_advance_count=final['target_advance_count'], receipt=final['journal']['receipt_ref'],
        status='PASS_OFFLINE_INVARIANTS', outcome=result, after_crash=after_crash,
        after_restart=after_restart, final=final, child_runs=runs, limitations=limitations)
    dump(root / 'receipt.json', receipt)
    return receipt


def source_metadata():
    core_paths = ['manager_core/owned_cycle.py', 'manager_core/outbox.py', 'manager_core/reconcile.py',
                  'manager_core/owned_public_collector.py', 'scripts/phase06_kernel_release.py']
    manager = dict(repo='Daisuke134/life-manager',
        head=subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip(),
        working_file_sha256={name: hashlib.sha256((PRODUCT / name).read_bytes()).hexdigest() for name in core_paths})
    try:
        dist = importlib.metadata.distribution('dbos')
    except importlib.metadata.PackageNotFoundError:
        dbos_metadata = dict(available=False, required_source=PIN)
    else:
        direct = json.loads(dist.read_text('direct_url.json'))
        if direct.get('vcs_info', {}).get('commit_id') != PIN:
            raise ValueError('installed DBOS differs from fixed audited source')
        dbos_metadata = dict(available=True, version=dist.version, direct_url=direct)
    return dict(manager=manager, dbos=dbos_metadata,
        python=sys.version, executable=sys.executable,
        dependencies={d.metadata['Name']: d.version for d in importlib.metadata.distributions()},
        probe_sha256=hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
        serializer='DBOSPortableJSONSerializer + PORTABLE workflow, fresh probe-owned DB only')


def make_source_snapshot(destination):
    """Copy source for comparison, never edit it or mix later root changes in."""
    selected = []
    for directory in ('manager_core', 'scripts', 'public_goods'):
        selected.extend(path for path in (PRODUCT / directory).rglob('*') if path.is_file()
                        and '__pycache__' not in path.parts and path.suffix != '.pyc')
    selected.extend((PRODUCT / 'tests').glob('*.py'))
    before = {str(path.relative_to(PRODUCT)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in selected}
    for path in selected:
        target = destination / path.relative_to(PRODUCT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    after = {str(path.relative_to(PRODUCT)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in selected}
    copied = {name: hashlib.sha256((destination / name).read_bytes()).hexdigest() for name in before}
    if before != after or before != copied:
        raise RuntimeError('source changed during snapshot; preserve this attempt and retry')
    dump(destination / 'snapshot-hashes.json', copied)


def main():
    global PRODUCT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=['current', 'dbos', 'both'], default='both')
    parser.add_argument('--case', choices=[*CASES, 'all'], default='all')
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--phase', choices=['start', 'restart', 'fresh_engine', 'next_slot'], default='start', help=argparse.SUPPRESS)
    parser.add_argument('--engine-name', choices=['engine', 'fresh-engine'], default='engine', help=argparse.SUPPRESS)
    parser.add_argument('--source-root', type=Path, default=PRODUCT, help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.state_dir = args.state_dir.resolve()
    if args.child:
        PRODUCT = args.source_root.resolve()
        child(args)
        return
    if args.state_dir.exists():
        parser.error('state-dir must be new; preserve previous experiment evidence')
    if args.state_dir == REPO or REPO in args.state_dir.parents:
        parser.error('offline probe state must be outside source')
    args.state_dir.mkdir(parents=True, mode=0o700)
    snapshot = args.state_dir / 'source-snapshot'
    make_source_snapshot(snapshot)
    PRODUCT = snapshot
    metadata = source_metadata()
    dump(args.state_dir / 'source-metadata.json', metadata)
    receipts, failures = [], []
    backends = ['current', 'dbos'] if args.backend == 'both' else [args.backend]
    selected = CASES if args.case == 'all' else [args.case]
    for backend in backends:
        for case in selected:
            root = args.state_dir / backend / case
            try:
                receipt = run_case(root, backend, case)
                receipts.append(receipt)
                print(json.dumps({key: receipt[key] for key in
                    ('backend', 'failure_case', 'status', 'dispatch_count', 'target_advance_count')}) , flush=True)
            except Exception as error:
                failure = dict(backend=backend, failure_case=case,
                               error=f'{type(error).__name__}: {error}', case_dir=str(root))
                failures.append(failure)
                dump(root / 'failure.json', failure)
                print(json.dumps(failure), flush=True)
    summary = dict(schema='e16-runtime-fit-results.v1', generated_at=datetime.now(timezone.utc).isoformat(),
        metadata=metadata, case_count=len(receipts), failure_count=len(failures), failures=failures,
        receipts=receipts, adoption='UNDECIDED', production_evidence=False,
        fit='OFFLINE_FENCES_PASSED' if not failures else 'PROBE_FAILURES_REQUIRE_REVIEW')
    dump(args.state_dir / 'results.json', summary)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
