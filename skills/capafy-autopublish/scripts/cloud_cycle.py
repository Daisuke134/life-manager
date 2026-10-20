#!/usr/bin/env python3
"""Tenant host adapter for the existing factory runner; no scheduler or publisher."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

RELEASE = Path(__file__).resolve().parents[3]


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


def run_cycle(tenant_id, occurrence_id, date_key, *, env=None, data_root=Path('/data'), runner=subprocess.run):
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
    if not receipt.is_relative_to(home):
        raise ValueError('receipt_binding_invalid')
    child_paths = {name: home / relative for name, relative in {
        'HOME': 'home', 'CODEX_HOME': 'codex', 'CLAUDE_CONFIG_DIR': 'claude',
        'TMPDIR': 'tmp', 'ANICCA_USAGE_LEDGER': 'ledgers/usage.jsonl',
        'ANICCA_TOKEN_BUDGET_LEDGER': 'ledgers/token-budget.jsonl',
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
                        'no_work', 'runner_reported_failure', 'completion_evidence_missing', 'runner_timeout')
                    or not isinstance(cached['artifactRefs'], list)):
                raise ValueError()
            for ref in cached['artifactRefs']:
                if not isinstance(ref, str) or not ref.startswith('artifact://'):
                    raise ValueError()
                relative = Path(ref[len('artifact://'):])
                artifact = (workspace / relative).resolve()
                if (relative.is_absolute() or '..' in relative.parts
                        or not artifact.is_relative_to(workspace) or not artifact.is_file()):
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
    receipt.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    initial = {'dateKey': date_key, 'releaseSha': release_sha,
               'result': result('effect_unknown', 'cycle_in_progress')}
    try:
        with receipt.open('x') as stream:
            json.dump(initial, stream)
    except FileExistsError:
        return result('effect_unknown', 'cycle_in_progress')
    # Only the tenant model key crosses this boundary; founder/provider secrets do not.
    child = {key: context[key] for key in (
        'PATH', 'LANG', 'LC_ALL', 'TZ', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
        'LM_CLOUD_MODEL_API_KEY',
    ) if key in context}
    child.update({key: str(path) for key, path in child_paths.items() if key != 'EVIDENCE_DIR'})
    child.update(AGENT_RUNNER_CONFIG=str(config), AGENT_RUNNER_WORKDIR=str(workspace),
                 LM_RUNTIME_HOST='maritime', LM_RUNTIME_TENANT_ID=tenant_id,
                 LM_RELEASE_SHA=release_sha, LIFE_MANAGER_STATE_HOME=str(home),
                 LIFE_MANAGER_BUILD_WORKSPACE=str(workspace),
                 LIFE_MANAGER_REPO=str(RELEASE), LIFE_MANAGER_RELEASE_ROOT=str(RELEASE),
                 LIFE_MANAGER_SOURCE_REPO=str(workspace))
    for directory in ['HOME', 'CODEX_HOME', 'CLAUDE_CONFIG_DIR', 'TMPDIR']:
        Path(child[directory]).mkdir(parents=True, exist_ok=True, mode=0o700)
    (home / 'ledgers').mkdir(parents=True, exist_ok=True, mode=0o700)
    account_context = ('No provider account is connected. Create an original product and listing offline; do not publish or call commerce mutation APIs.'
                       if binding is None else 'Use only this tenant provider binding: ' + json.dumps(binding))
    prompt = '\n'.join([
        f'You are Life Manager for tenant {tenant_id}, occurrence {occurrence_id}, date {date_key}.',
        'Choose and complete one useful revenue-oriented action from actual feedback. No user goal or budget input is required.',
        f'Reuse the existing Capafy factory in {RELEASE}/skills/capafy-autopublish and its runbooks; do not create another publisher.',
        account_context,
        f'Write original artifacts only under {workspace}; runtime state belongs under {home}.',
        'Do not modify the immutable release, borrow founder accounts, send Telegram to Dais, or commit/push tenant work to the source repository.',
        'Keep credentials out of artifacts and reports. Verify what happened; creation, publication, sales and payouts are distinct.',
        'Return the existing pass schema. Evidence must include actual artifact file paths, not a claim without a file.',
    ])
    command = ['bash', str(RELEASE / 'skills/earn/marketing-engine/run_agent.sh'),
               '--task-class', 'application-lane-agent', '--evidence-dir', str(child_paths['EVIDENCE_DIR']),
               '--task-label', 'maritime:' + occurrence_id, '--loop', 'capafy',
               '--schema', str(RELEASE / 'skills/self/capafy-loop/capafy-loop-pass.schema.json'),
               '--workdir', str(workspace), '--print-result']
    try:
        process = runner(command, cwd=str(workspace), env=child, input=prompt, text=True, capture_output=True, timeout=3600)
        payload = json.loads(process.stdout) if process.returncode == 0 else None
        if not isinstance(payload, dict) or payload.get('status') not in ('success', 'failure', 'no_op') or not isinstance(payload.get('evidence'), list):
            final = result('effect_unknown', 'runner_result_unconfirmed')
        elif payload['status'] == 'no_op':
            final = result('deferred', 'no_work')
        elif payload['status'] == 'failure':
            final = result('effect_unknown', 'runner_reported_failure')
        else:
            artifacts = []
            for item in payload['evidence']:
                if not isinstance(item, str):
                    continue
                path = Path(item.removeprefix('file://'))
                path = (path if path.is_absolute() else workspace / path).resolve()
                if path.is_relative_to(workspace) and path.is_file():
                    artifacts.append('artifact://' + path.relative_to(workspace).as_posix())
            final = result('completed', artifacts=artifacts) if artifacts else result('effect_unknown', 'completion_evidence_missing')
    except subprocess.TimeoutExpired:
        final = result('effect_unknown', 'runner_timeout')
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
