"""Dreamwork owns native submissions; this owner configures and reads them back."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .application_reporting import _write_private_json

API_ORIGIN = 'https://api.dreamworkhq.com'
PROOFS = frozenset({'browser', 'employer_email', 'ats_receipt', 'vendor_receipt', 'portal'})


class DreamworkError(RuntimeError):
    pass


class DreamworkClient:
    def __init__(self, api_key: str):
        self._key = api_key

    def request(self, path: str, body: dict | None = None) -> dict:
        request = Request(API_ORIGIN + path, data=json.dumps(body).encode() if body is not None else None,
                          headers={'Authorization': 'Bearer ' + self._key, 'Content-Type': 'application/json'},
                          method='POST' if body is not None else 'GET')
        try:
            with urlopen(request, timeout=120) as response:
                if response.geturl().split('/')[2] != 'api.dreamworkhq.com':
                    raise DreamworkError('off-origin provider response')
                value = json.load(response)
        except HTTPError as error:
            # Provider bodies may include candidate data; never put them in a log.
            raise DreamworkError('provider_http_' + str(error.code)) from None
        if not isinstance(value, dict):
            raise DreamworkError('malformed_provider_response')
        return value

    def action(self, name: str, args: dict, confirmation_token: str | None = None) -> dict:
        body = {'args': args}
        if confirmation_token is not None:
            body['confirmationToken'] = confirmation_token
        return self.request('/assistant/actions/' + name, body)


def read_action(client, name: str) -> dict:
    result = client.action(name, {})
    if result.get('status') != 'completed' or not isinstance(result.get('output'), dict):
        raise DreamworkError('readback_failed:' + name)
    return result['output']


def confirmed_submissions(rows: list[dict]) -> list[dict]:
    return [row for row in rows if isinstance(row, dict)
            and row.get('applicationId') and isinstance(row.get('submission'), dict)
            and row['submission'].get('disposition') == 'submitted'
            and row['submission'].get('proof') in PROOFS
            and row['submission'].get('submittedAt')]


def ensure_autopilot(client, state_path: Path, preferences_patch: dict) -> dict:
    state = json.loads(state_path.read_text()) if state_path.exists() else {'actions': {}}
    actions = state['actions']
    usage = read_action(client, 'get_usage')
    readiness = read_action(client, 'get_application_readiness')
    status = read_action(client, 'get_autopilot_status')
    settings = read_action(client, 'get_autopilot_settings')
    preferences = read_action(client, 'get_preferences')['preferences']
    observed = {'update_preferences': preferences, 'update_autopilot_settings': settings, 'set_autopilot': status}
    # Resolve only the exact desired configuration using fresh official readback.
    for record in actions.values():
        if record['status'] == 'effect_unknown':
            expected = record['args'].get('patch', record['args'])
            if all(observed[record['action']].get(k) == v for k, v in expected.items()):
                record['status'] = 'verified'
                _write_private_json(state_path, state)
            else:
                return {'status': 'effect_unknown', 'action': record['action'], 'autopilot': status, 'usage': usage}
    if not (readiness.get('autopilotReady') is True and readiness.get('autopilotAvailable') is True
            and readiness.get('entitlement', {}).get('autoApply') is True):
        return {'status': 'unavailable', 'readiness': readiness, 'usage': usage, 'autopilot': status,
                'fallback_safe': status.get('state') in {'off', 'unavailable'} and status.get('inFlightCount') == 0
                and status.get('sentToday') == 0 and status.get('sentThisMonth') == 0}

    desired = [('update_preferences', {'patch': preferences_patch}),
               ('update_autopilot_settings', {'resumeVariant': 'tailored', 'scoreFloor': 70}),
               ('set_autopilot', {'state': 'on'})]
    for name, args in desired:
        expected = args.get('patch', args)
        if all(observed[name].get(k) == v for k, v in expected.items()):
            continue
        identity = hashlib.sha256(json.dumps([name, args], sort_keys=True).encode()).hexdigest()
        actions[identity] = {'action': name, 'args': args, 'status': 'effect_unknown'}
        # Preference actions may write immediately, so fence the initial request too.
        _write_private_json(state_path, state)
        try:
            held = client.action(name, args)
        except (OSError, TimeoutError, DreamworkError):
            return {'status': 'effect_unknown', 'action': name, 'autopilot': status, 'usage': usage}
        if held.get('status') == 'held':
            token = held.get('needsInput', {}).get('token')
            if not isinstance(token, str) or not token:
                raise DreamworkError('missing_confirmation_token')
            # The exact effect is fenced durably before its confirmation is sent.
            _write_private_json(state_path, state)
            try:
                confirmed = client.action(name, args, confirmation_token=token)
            except (OSError, TimeoutError, DreamworkError):
                return {'status': 'effect_unknown', 'action': name, 'autopilot': status, 'usage': usage}
            if confirmed.get('status') not in {'completed', 'queued'}:
                return {'status': 'effect_unknown', 'action': name, 'autopilot': status, 'usage': usage}
            fresh_name = {'update_preferences': 'get_preferences', 'update_autopilot_settings': 'get_autopilot_settings', 'set_autopilot': 'get_autopilot_status'}[name]
            fresh = read_action(client, fresh_name)
            if name == 'update_preferences':
                fresh = fresh['preferences']
            if not all(fresh.get(k) == v for k, v in expected.items()):
                return {'status': 'effect_unknown', 'action': name, 'autopilot': status, 'usage': usage}
            actions[identity]['status'] = 'verified'
            _write_private_json(state_path, state)
            observed[name] = fresh
        elif held.get('status') == 'completed':
            # Non-consequential preference updates can complete immediately.
            fresh = read_action(client, 'get_preferences') if name == 'update_preferences' else None
            if fresh is None or not all(fresh['preferences'].get(k) == v for k, v in expected.items()):
                raise DreamworkError('unexpected_unconfirmed_action')
            actions[identity]['status'] = 'verified'
            _write_private_json(state_path, state)
            observed[name] = fresh['preferences']
        else:
            raise DreamworkError('configuration_refused:' + name)
    return {'status': 'active', 'autopilot': observed['set_autopilot'], 'usage': usage,
            'resume_variant': 'tailored'}


def load_key(path: Path) -> str | None:
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise DreamworkError('unsafe_credential_ssot')
    value = json.loads(path.read_text())
    records = [row for row in value.get('credentials', []) if row.get('service') == 'dreamwork']
    if len(records) != 1 or not records[0].get('rotation_verified_at'):
        return None
    key = records[0].get('api_key')
    return key if isinstance(key, str) and key else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    candidate = json.loads(args.profile.read_text())['candidate']
    if candidate.get('application_autonomy', {}).get('authorized') is not True:
        result = {'status': 'not_configured', 'reason': 'application_autonomy_not_delegated'}
        _write_private_json(args.output, result)
        return 69
    key = load_key(Path.home() / '.local/share/anicca/credentials.json')
    if key is None:
        _write_private_json(args.output, {'status': 'not_configured', 'reason': 'credential_rotation_required'})
        return 69
    args.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = args.state_root / 'dreamwork-owner.lock'
    with lock_path.open('a') as lock:
        os.chmod(lock_path, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 75
        client = DreamworkClient(key)
        patch = dict(candidate.get('dreamwork_preferences', {}))
        from .ledger import Ledger
        ledger = Ledger(args.state_root / 'ledger.sqlite3')
        try:
            fenced = [row[0] for row in ledger.connection.execute("SELECT DISTINCT company FROM applications WHERE current_state IN ('submitted','submit_unknown','submit_claimed')")]
        finally:
            ledger.close()
        prior = read_action(client, 'get_preferences')['preferences']
        patch['excludedCompanies'] = list(dict.fromkeys(prior.get('excludedCompanies', []) + candidate.get('employer_exclusions', []) + fenced))
        if len(patch['excludedCompanies']) > 50:
            raise DreamworkError('exclusion_scope_exceeds_provider_limit')
        result = ensure_autopilot(client, args.state_root / 'dreamwork-actions.json', patch)
        pipeline = client.request('/pipeline?limit=500')
        if not isinstance(pipeline.get('jobs'), list):
            raise DreamworkError('malformed_pipeline')
        proof = []
        for row in confirmed_submissions(pipeline['jobs']):
            readback = client.action('get_application_status', {'applicationId': row['applicationId']})
            status = readback.get('output', {})
            if readback.get('status') == 'completed' and status.get('applicationId') == row['applicationId'] and status.get('truth', {}).get('submitted') is True:
                record = {'pipeline': row, 'official_status': status}
                proof.append(record)
                digest = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
                # Provider IDs are data, not filesystem paths.
                receipt_path = args.state_root / 'evidence' / 'dreamwork' / (hashlib.sha256(row['applicationId'].encode()).hexdigest() + '.json')
                _write_private_json(receipt_path, record)
                if row.get('sourceUrl'):
                    ledger = Ledger(args.state_root / 'ledger.sqlite3')
                    try:
                        ledger.import_provider_submission(company=row['company'], title=row['title'], url=row['sourceUrl'],
                            provider='dreamwork', provider_application_id=row['applicationId'],
                            applied_at=row['submission']['submittedAt'], evidence_sha256=digest)
                    except Exception as error:
                        from .ledger import FenceError
                        if not isinstance(error, FenceError):
                            raise
                        record['ledger_status'] = 'unbound_legacy_occurrence'
                    finally:
                        ledger.close()
                else:
                    record['ledger_status'] = 'source_url_missing'

        from .telegram import send_once
        for record in proof:
            row = record['pipeline']
            confirmation = record['official_status']['truth']['employerConfirmed']
            message = (f"Dreamworkで応募完了を公式確認しました。\n会社: {row['company']}\n職種: {row['title']}"
                       f"\n雇用主からの確認: {'あり' if confirmation else '未確認'}"
                       f"\n{row.get('sourceUrl', 'Dreamwork Applicationsで確認できます。')}")
            report = send_once(database=args.state_root / 'telegram-outbox.sqlite3',
                               event_key='dreamwork-submitted:' + row['applicationId'], message=message)
            record['report_message_id'] = report.get('message_id')
        result.update(confirmed_submissions=proof, pipeline_complete=pipeline.get('hasMore') is False,
                      provider='dreamwork', official_readback_ref=str(args.output))
        _write_private_json(args.output, result)
        _write_private_json(args.state_root / 'dreamwork-latest.json', result)
        print(json.dumps({'status': result['status'], 'confirmed_count': len(proof), 'pipeline_complete': result['pipeline_complete']}))
        if result['status'] == 'active':
            return 0
        return 69 if result.get('fallback_safe') is True else 75


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (DreamworkError, OSError, ValueError, KeyError) as error:
        print(json.dumps({'status': 'failed', 'error_class': type(error).__name__}))
        raise SystemExit(75)
