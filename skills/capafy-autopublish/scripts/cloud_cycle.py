#!/usr/bin/env python3
"""Tenant host adapter for the existing factory runner; no scheduler or publisher."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import stat
import sys
import tempfile
import uuid

RELEASE = Path(__file__).resolve().parents[3]
MARITIME_RUNTIME = RELEASE / 'apps/life-manager/maritime'
if str(MARITIME_RUNTIME) not in sys.path:
    sys.path.insert(0, str(MARITIME_RUNTIME))
from browser_session import BrowserSessionError, MaritimeBrowserSession as BrowserSession

_BROWSER_ERRORS = frozenset({
    'browser_session_unavailable', 'browser_session_path_unavailable',
    'browser_profile_unavailable', 'browser_binary_unavailable',
    'browser_session_startup_failed',
    'browser_session_shutdown_failed',
})


def _save(path, value):
    fd, temporary = tempfile.mkstemp(prefix='.cycle-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _private_directory(path, owner):
    try:
        info = path.lstat()
        return (stat.S_ISDIR(info.st_mode) and info.st_uid == owner
                and stat.S_IMODE(info.st_mode) == 0o700 and path.resolve(strict=True) == path)
    except OSError:
        return False


def _artifact_file(value, workspace, owner):
    if not isinstance(value, str):
        return None
    candidate = Path(value.removeprefix('file://'))
    if not candidate.is_absolute():
        candidate = workspace / candidate
    candidate = Path(os.path.abspath(candidate))
    try:
        if candidate == workspace or not candidate.is_relative_to(workspace):
            return None
        if candidate.resolve(strict=True) != candidate:
            return None
        info = candidate.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_uid != owner or info.st_nlink != 1:
        return None
    return candidate


def _browser_action_effect_unknown(path, owner):
    """Fail closed when a browser action has no durable terminal receipt."""
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0))
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or info.st_size > 1_048_576):
            return True
        data = bytearray()
        while len(data) <= 1_048_576:
            chunk = os.read(fd, min(65_536, 1_048_577 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > 1_048_576:
            return True
        lines = data.decode('utf-8').splitlines()
        if not lines:
            return True
        seen = set()
        pending = {}
        observations = set()
        latest_observation = None
        effect_unknown = False
        for line in lines:
            row = json.loads(line)
            required = {'at', 'actionId', 'tool', 'outcome', 'origin'}
            optional = {'stateHash', 'observationId', 'linkId', 'linkCount'}
            if (not isinstance(row, dict) or not required.issubset(row)
                    or set(row) - required - optional
                    or not isinstance(row['at'], str) or not isinstance(row['origin'], str)
                    or row['tool'] not in {'browser_observe', 'browser_navigate', 'browser_follow_link', 'browser_search'}
                    or not isinstance(row['actionId'], str)
                    or not re.fullmatch(r'[0-9a-f]{32}', row['actionId'])
                    or row['outcome'] not in {'read', 'started', 'opened', 'searched', 'blocked', 'effect_unknown'}):
                return True
            state_hash = row.get('stateHash')
            observation_id = row.get('observationId')
            link_id = row.get('linkId')
            link_count = row.get('linkCount')
            if (('stateHash' in row and (not isinstance(state_hash, str)
                                         or not re.fullmatch(r'[0-9a-f]{64}', state_hash)))
                    or ('observationId' in row and (not isinstance(observation_id, str)
                                                    or not re.fullmatch(r'[0-9a-f]{32}', observation_id)))
                    or ('linkId' in row and (not isinstance(link_id, str)
                                             or not re.fullmatch(r'[1-9][0-9]?', link_id)))
                    or ('linkId' in row and row['tool'] != 'browser_follow_link')
                    or ('linkCount' in row and (isinstance(link_count, bool)
                                                or not isinstance(link_count, int)
                                                or not 0 <= link_count <= 25
                                                or row['tool'] != 'browser_observe'
                                                or row['outcome'] != 'read'))):
                return True
            action_id, tool, outcome = row['actionId'], row['tool'], row['outcome']
            if outcome == 'started':
                if action_id in seen or tool not in {'browser_navigate', 'browser_follow_link', 'browser_search'}:
                    return True
                evidence = None
                if tool == 'browser_follow_link':
                    if (state_hash is None or observation_id is None or link_id is None
                            or not isinstance(latest_observation, tuple)
                            or latest_observation[0] != observation_id
                            or latest_observation[1] != state_hash
                            or not isinstance(latest_observation[2], int)
                            or isinstance(latest_observation[2], bool)
                            or int(link_id) > latest_observation[2]):
                        return True
                    evidence = {'stateHash': state_hash, 'observationId': observation_id,
                                'linkId': link_id}
                seen.add(action_id)
                pending[action_id] = {'tool': tool, 'evidence': evidence}
                latest_observation = None
                continue
            if outcome in {'opened', 'searched', 'effect_unknown'}:
                started = pending.get(action_id)
                if not isinstance(started, dict) or started.get('tool') != tool:
                    return True
                if (outcome == 'opened' and tool not in {'browser_navigate', 'browser_follow_link'}
                        or outcome == 'searched' and tool != 'browser_search'):
                    return True
                expected_evidence = started.get('evidence')
                if expected_evidence is not None and outcome != 'effect_unknown':
                    actual_evidence = {'stateHash': state_hash, 'observationId': observation_id,
                                       'linkId': link_id}
                    if actual_evidence != expected_evidence:
                        return True
                del pending[action_id]
                effect_unknown = effect_unknown or outcome == 'effect_unknown'
                continue
            if action_id in seen or (outcome == 'read' and tool != 'browser_observe'):
                return True
            if outcome == 'read':
                if (('stateHash' in row) != ('observationId' in row)
                        or ('linkId' in row)
                        or ('linkCount' in row and (state_hash is None or observation_id is None))
                        or (observation_id is not None and observation_id in observations)):
                    return True
                if observation_id is not None:
                    observations.add(observation_id)
                    latest_observation = (observation_id, state_hash, link_count)
                else:
                    latest_observation = None
            seen.add(action_id)
        return bool(pending) or effect_unknown
    except (OSError, ValueError, TypeError, UnicodeDecodeError):
        return True
    finally:
        if fd is not None:
            os.close(fd)


def run_cycle(tenant_id, occurrence_id, date_key, *, env=None, data_root=Path('/data'), runner=subprocess.run,
              browser_session_factory=None):
    context = dict(os.environ if env is None else env)
    try:
        valid_tenant = tenant_id.startswith('lm_') and str(uuid.UUID(tenant_id[3:])) == tenant_id[3:]
        valid_date = datetime.date.fromisoformat(date_key).isoformat() == date_key
    except (ValueError, TypeError, AttributeError):
        raise ValueError('invalid_cycle_input') from None
    if not valid_tenant or not valid_date or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', occurrence_id):
        raise ValueError('invalid_cycle_input')
    root = Path(data_root).resolve()
    home = (root / tenant_id).resolve()
    if home != root / tenant_id or context.get('LM_RUNTIME_HOST') != 'maritime' or context.get('LM_RUNTIME_TENANT_ID') != tenant_id:
        raise ValueError('tenant_binding_invalid')
    if Path(context.get('LIFE_MANAGER_STATE_HOME', '')).resolve() != home:
        raise ValueError('state_binding_invalid')
    workspace = Path(context.get('LIFE_MANAGER_BUILD_WORKSPACE', '')).resolve()
    if workspace != home / 'build':
        raise ValueError('workspace_binding_invalid')
    release_sha = context.get('LM_RELEASE_SHA', '')
    if not re.fullmatch(r'[0-9a-f]{40}', release_sha):
        raise ValueError('release_binding_invalid')
    binding = None
    if context.get('LM_CAPAFY_BINDING_JSON'):
        try:
            binding = json.loads(context['LM_CAPAFY_BINDING_JSON'])
            if not isinstance(binding, dict) or binding.get('tenantId') != tenant_id or binding.get('provider') != 'capafy' or not binding.get('subjectId'):
                raise ValueError()
            if set(binding) - {'tenantId', 'provider', 'subjectId', 'credentialRef', 'browserSessionRef'}:
                raise ValueError()
            if any(not isinstance(value, str) or not value for value in binding.values()):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('provider_binding_invalid') from None
    base = {'tenantId': tenant_id, 'occurrenceId': occurrence_id, 'artifactRefs': [],
            'providerSnapshotRef': None, 'providerReceiptRefs': [], 'nextEligibleAt': None}
    def result(status, error=None, artifacts=None):
        return dict(base, status=status, errorClass=error, artifactRefs=artifacts or [])
    receipt = (home / 'receipts' / occurrence_id / 'cycle.json').resolve()
    occurrence_workspace = workspace / 'occurrences' / occurrence_id
    if not receipt.is_relative_to(home):
        raise ValueError('receipt_binding_invalid')
    child_paths = {name: home / relative for name, relative in {
        'HOME': 'home', 'CODEX_HOME': 'agent-codex', 'CLAUDE_CONFIG_DIR': 'claude',
        'TMPDIR': 'tmp', 'ANICCA_USAGE_LEDGER': 'agent-ledgers/usage.jsonl',
        'ANICCA_TOKEN_BUDGET_LEDGER': 'agent-ledgers/token-budget.jsonl',
        'CAPAFY_STATE_DIR': 'state/capafy-autopublish',
        'CAPAFY_CATALOG_DIR': 'build/skills/capafy/catalog',
        'CAPAFY_PUBLISHER_STATE_HOME': 'runtime/capafy-publisher',
        'EVIDENCE_DIR': 'evidence/' + occurrence_id,
    }.items()}
    if any(not path.resolve().is_relative_to(home) for path in child_paths.values()):
        raise ValueError('child_path_binding_invalid')
    if receipt.exists():
        try:
            saved = json.loads(receipt.read_text())
            if saved['result']['tenantId'] != tenant_id or saved['result']['occurrenceId'] != occurrence_id or saved['dateKey'] != date_key:
                raise ValueError()
            cached = saved['result']
            if (set(cached) != set(result('completed'))
                    or cached['status'] not in ('completed', 'deferred', 'effect_unknown')
                    or cached['providerSnapshotRef'] is not None
                    or cached['providerReceiptRefs'] != [] or cached['nextEligibleAt'] is not None
                    or cached['errorClass'] not in (None, 'cycle_in_progress', 'runner_result_unconfirmed',
                        'no_work', 'runner_reported_failure', 'completion_evidence_missing', 'runner_timeout',
                        'occurrence_workspace_preexisting', 'occurrence_workspace_unavailable',
                        'browser_effect_unknown', *_BROWSER_ERRORS)
                    or not isinstance(cached['artifactRefs'], list)):
                raise ValueError()
            for ref in cached['artifactRefs']:
                if not isinstance(ref, str) or not ref.startswith('artifact://'):
                    raise ValueError()
                relative = Path(ref[len('artifact://'):])
                artifact = workspace / relative
                if (relative.is_absolute() or '..' in relative.parts
                        or not _private_directory(occurrence_workspace, os.geteuid())
                        or _artifact_file(str(artifact), occurrence_workspace, os.geteuid()) is None):
                    raise ValueError()
            if cached['status'] == 'completed' and not cached['artifactRefs']:
                raise ValueError()
            return result(cached['status'], cached['errorClass'], cached['artifactRefs'])
        except (OSError, ValueError, KeyError, TypeError):
            return result('effect_unknown', 'cycle_receipt_unreadable')
    config = Path(context.get('AGENT_RUNNER_CONFIG', '')).resolve()
    if not context.get('AGENT_RUNNER_CONFIG') or not config.is_file() or not (config.is_relative_to(home) or config.is_relative_to(RELEASE)):
        return result('deferred', 'cloud_model_config_missing')
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    for directory in (home / 'receipts', receipt.parent):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        if not _private_directory(directory, os.geteuid()):
            raise ValueError('receipt_binding_invalid')
    initial = {'dateKey': date_key, 'releaseSha': release_sha,
               'result': result('effect_unknown', 'cycle_in_progress')}
    try:
        with receipt.open('x') as stream:
            json.dump(initial, stream)
    except FileExistsError:
        return result('effect_unknown', 'cycle_in_progress')
    owner = os.geteuid()
    occurrence_parent = occurrence_workspace.parent
    try:
        try:
            occurrence_parent.mkdir(mode=0o700)
        except FileExistsError:
            pass
        if not _private_directory(occurrence_parent, owner):
            raise OSError('occurrence_parent_not_private')
        occurrence_workspace.mkdir(mode=0o700)
        if not _private_directory(occurrence_workspace, owner):
            raise OSError('occurrence_workspace_not_private')
    except FileExistsError:
        final = result('effect_unknown', 'occurrence_workspace_preexisting')
        _save(receipt, dict(initial, result=final))
        return final
    except OSError:
        final = result('effect_unknown', 'occurrence_workspace_unavailable')
        _save(receipt, dict(initial, result=final))
        return final
    # Only the tenant model key crosses this boundary; founder/provider secrets do not.
    child = {key: context[key] for key in (
        'PATH', 'LANG', 'LC_ALL', 'TZ', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
        'LM_CLOUD_MODEL_API_KEY',
    ) if key in context}
    child.update({key: str(path) for key, path in child_paths.items() if key != 'EVIDENCE_DIR'})
    child.update(AGENT_RUNNER_CONFIG=str(config), AGENT_RUNNER_WORKDIR=str(occurrence_workspace),
                 LM_RUNTIME_HOST='maritime', LM_RUNTIME_TENANT_ID=tenant_id,
                 LM_RELEASE_SHA=release_sha, LIFE_MANAGER_STATE_HOME=str(home),
                 LIFE_MANAGER_BUILD_WORKSPACE=str(workspace),
                 LM_MARITIME_BROWSER_RECEIPT=str(receipt.parent / 'browser-actions.jsonl'),
                 LIFE_MANAGER_REPO=str(RELEASE), LIFE_MANAGER_RELEASE_ROOT=str(RELEASE),
                 LIFE_MANAGER_SOURCE_REPO=str(workspace))
    for directory in ['HOME', 'CODEX_HOME', 'CLAUDE_CONFIG_DIR', 'TMPDIR']:
        Path(child[directory]).mkdir(parents=True, exist_ok=True, mode=0o700)
    (home / 'agent-ledgers').mkdir(parents=True, exist_ok=True, mode=0o700)
    schema = json.loads((RELEASE / 'skills/self/capafy-loop/capafy-loop-pass.schema.json').read_text())
    schema['properties']['evidence']['items'] = {
        'type': 'string',
        'pattern': r'^(?:file://)?' + re.escape(str(occurrence_workspace)) + r'/[^\x00]+$',
        'description': 'One literal absolute artifact file path, without prose or labels.',
    }
    schema_path = receipt.parent / 'pass.schema.json'
    _save(schema_path, schema)
    account_context = ('No authorized Publisher identity is connected. Do not sign up a new Publisher or claim an external outcome; inspect only public information and report the missing tenant binding.'
                       if binding is None else 'A Publisher identity is configured for this tenant, but current browser tools are public and read-only. Do not authenticate, use, or disclose provider binding details.')
    prompt = '\n'.join([
        f'You are Life Manager for tenant {tenant_id}, occurrence {occurrence_id}, date {date_key}.',
        'Choose and complete one useful revenue-oriented action from actual feedback. No user goal or budget input is required.',
        'The current browser tools are read-only: observe public text, navigate allowlisted public pages, and search same-origin GET forms. Non-GET requests, account forms, generic clicks, signup, publishing, payout, and earnings readback are unavailable; never claim them as completed.',
        'Use the maritime_browser MCP tools to observe the live page and choose each permitted browser action. Do not run a fixed Capafy workflow or execute provider API mutations.',
        'If any browser tool reports an effect_unknown receipt, do not retry it in this cycle; stop external browser work and preserve the unknown outcome.',
        account_context,
        f'Write original artifacts only under {occurrence_workspace}; runtime state belongs under {home}.',
        'Do not modify the immutable release, borrow founder accounts, send Telegram to Dais, or commit/push tenant work to the source repository.',
        'Keep credentials out of artifacts and reports. Verify what happened; creation, publication, sales and payouts are distinct.',
        'Return the supplied pass schema. Each evidence string must be exactly one absolute artifact file path; do not add descriptions or labels.',
    ])
    command = ['bash', str(RELEASE / 'skills/earn/marketing-engine/run_agent.sh'),
               '--task-class', 'application-lane-agent', '--evidence-dir', str(child_paths['EVIDENCE_DIR']),
               '--task-label', 'maritime:' + occurrence_id, '--loop', 'capafy',
               '--schema', str(schema_path),
               '--workdir', str(occurrence_workspace), '--print-result']
    browser_started = False
    try:
        browser_factory = browser_session_factory or BrowserSession
        with browser_factory(tenant_id=tenant_id, data_root=root, release_root=RELEASE) as browser_session:
            child['LM_MARITIME_BROWSER_CDP_URL'] = browser_session.cdp_url
            browser_started = True
            process = runner(command, cwd=str(occurrence_workspace), env=child, input=prompt, text=True, capture_output=True, timeout=3600)
        if _browser_action_effect_unknown(receipt.parent / 'browser-actions.jsonl', owner):
            final = result('effect_unknown', 'browser_effect_unknown')
            _save(receipt, dict(initial, result=final))
            return final
        payload = json.loads(process.stdout) if process.returncode == 0 else None
        if not isinstance(payload, dict) or payload.get('status') not in ('success', 'failure', 'no_op') or not isinstance(payload.get('evidence'), list):
            final = result('effect_unknown', 'runner_result_unconfirmed')
        elif payload['status'] == 'failure':
            final = result('effect_unknown', 'runner_reported_failure')
        else:
            artifacts = []
            for item in payload['evidence']:
                path = _artifact_file(item, occurrence_workspace, owner)
                if path is not None:
                    artifacts.append('artifact://' + path.relative_to(workspace).as_posix())
            if artifacts:
                final = result('completed', artifacts=artifacts)
            elif payload['status'] == 'no_op':
                final = result('deferred', 'no_work')
            else:
                final = result('effect_unknown', 'completion_evidence_missing')
    except subprocess.TimeoutExpired:
        final = result('effect_unknown', 'runner_timeout')
    except BrowserSessionError as error:
        error_class = str(error) if str(error) in _BROWSER_ERRORS else 'browser_session_unavailable'
        final = result('effect_unknown' if browser_started else 'deferred', error_class)
    except (OSError, ValueError, TypeError):
        final = result('effect_unknown', 'runner_result_unconfirmed')
    _save(receipt, dict(initial, result=final))
    return final


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tenant', required=True)
    parser.add_argument('--occurrence', required=True)
    parser.add_argument('--date', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run_cycle(args.tenant, args.occurrence, args.date)))
    except ValueError as error:
        print(json.dumps({'status': 'deferred', 'errorClass': str(error)}))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
