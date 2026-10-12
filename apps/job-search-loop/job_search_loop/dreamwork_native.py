"""Dreamwork owns native submissions; this owner configures and reads them back."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import unicodedata
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .application_reporting import _write_private_json
from .state import DEFAULT_EMPLOYER_EXCLUSIONS, canonical_url, is_excluded_employer

API_ORIGIN = 'https://api.dreamworkhq.com'
PROOFS = frozenset({'browser', 'employer_email', 'ats_receipt', 'vendor_receipt', 'portal'})


class DreamworkError(RuntimeError):
    pass


def _employer_key(value: str) -> str:
    return ''.join(character for character in unicodedata.normalize('NFKC', value).casefold()
                   if character.isalnum())


def select_free_matches(matches: list[dict], *, employer_exclusions: list[str],
                        fenced_companies: list[str]) -> list[dict]:
    """Keep Dreamwork-ranked matches that are neither excluded nor applied.

    Match order is owned by Dreamwork. This deterministic boundary only
    enforces explicit profile exclusions, existing company fences and the
    provider's applied flag; it does not add a local score threshold.
    """
    exclusions = frozenset(DEFAULT_EMPLOYER_EXCLUSIONS) | frozenset(
        value.strip() for value in employer_exclusions
        if isinstance(value, str) and value.strip()
    )
    fenced = {_employer_key(value) for value in fenced_companies if isinstance(value, str)}
    selected = []
    for row in matches:
        if not isinstance(row, dict) or row.get('applied') is not False:
            continue
        job_id = row.get('id')
        company = row.get('company')
        title = row.get('title')
        if not all(isinstance(value, str) and value.strip()
                   for value in (job_id, company, title)):
            continue
        if is_excluded_employer(company, exclusions) or _employer_key(company) in fenced:
            continue
        selected.append(dict(row))
    return selected


def _private_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return json.loads(json.dumps(default))
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise DreamworkError('unsafe_private_state')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise DreamworkError('malformed_private_state')
    return value


def _profile_hash(profile: dict) -> str:
    return hashlib.sha256(json.dumps(profile, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _safe_employer_posting_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or '').casefold().rstrip('.')
    if (parsed.scheme != 'https' or not host or parsed.username or parsed.password
            or host == 'dreamworkhq.com' or host.endswith('.dreamworkhq.com')):
        return None
    return canonical_url(value)


def _source_employer_key(company: str, source_url: str) -> set[str]:
    keys = {_employer_key(company)}
    parsed = urlsplit(source_url)
    host = (parsed.hostname or '').casefold().rstrip('.')
    parts = [part for part in parsed.path.split('/') if part]
    if host.endswith('.myworkdayjobs.com'):
        keys.add(_employer_key(host.split('.', 1)[0]))
    elif host in {'jobs.ashbyhq.com', 'app.ashbyhq.com', 'jobs.lever.co'} and parts:
        keys.add(_employer_key(parts[0]))
    elif host in {'boards.greenhouse.io', 'job-boards.greenhouse.io'} and parts:
        keys.add(_employer_key(parts[0]))
    return {key for key in keys if key}


def _local_company_fences(ledger) -> tuple[set[str], set[str], set[str]]:
    rows = ledger.connection.execute(
        """
        SELECT DISTINCT a.company, a.canonical_url
        FROM applications a
        WHERE a.current_state IN ('submitted','submit_unknown','submit_claimed')
          AND NOT EXISTS (
            SELECT 1 FROM events e
            WHERE e.application_id=a.id AND e.from_state IS NULL
              AND json_extract(e.payload_json,'$.source')='dreamwork'
          )
        """
    ).fetchall()
    company_keys: set[str] = set()
    source_keys: set[str] = set()
    for row in rows:
        company_keys.add(_employer_key(str(row['company'])))
        source_keys.update(_source_employer_key(str(row['company']), str(row['canonical_url'])))
    urls = {canonical_url(str(row['canonical_url'])) for row in rows}
    return company_keys, source_keys, urls


def prepare_free_matches(client, *, state_root: Path, ledger, profile: dict,
                         usage: dict, max_job_reads: int = 3) -> dict:
    """Queue Dreamwork Free matches and prepare only its reported free packs.

    This function never submits an application. The local ATS owner remains the
    sole submitter and the browser agent validates each live employer posting.
    """
    if usage.get('tier') != 'free' or usage.get('applicationsLimit') != 0:
        return {'status': 'not_free_fallback_scope', 'queued_application_ids': [],
                'pack_jobs_queued': 0}
    limit = usage.get('packsLimit')
    used = usage.get('packsUsedToday')
    pack_remaining = (max(0, limit - used)
                      if type(limit) is int and type(used) is int else 0)
    if type(max_job_reads) is not int or not 1 <= max_job_reads <= 10:
        raise ValueError('max_job_reads must be between 1 and 10')

    candidate = profile.get('candidate', {}) if isinstance(profile, dict) else {}
    if not isinstance(candidate, dict):
        raise DreamworkError('invalid_private_candidate_profile')
    preference = candidate.get('dreamwork_preferences', {})
    preference = preference if isinstance(preference, dict) else {}
    exclusions = list(candidate.get('employer_exclusions', []))
    exclusions.extend(preference.get('excludedCompanies', []))
    fenced_companies, fenced_source_keys, fenced_urls = _local_company_fences(ledger)
    digest = _profile_hash(profile)
    cursor_path = state_root / 'dreamwork-match-cursor.v1.json'
    cursor_state = _private_json(cursor_path, {
        'version': 1, 'profile_sha256': digest, 'cursor': None,
        'pending_matches': [], 'offset': 0, 'next_cursor': None,
        'cycle_complete': False,
    })
    if cursor_state.get('version') != 1 or cursor_state.get('profile_sha256') != digest:
        cursor_state = {'version': 1, 'profile_sha256': digest, 'cursor': None,
                        'pending_matches': [], 'offset': 0, 'next_cursor': None,
                        'cycle_complete': False}

    pending = cursor_state.get('pending_matches')
    if not isinstance(pending, list) or not pending:
        args = {'limit': 50}
        cursor = cursor_state.get('cursor')
        if isinstance(cursor, str) and cursor:
            args['cursor'] = cursor
        page = client.action('list_matches', args)
        if page.get('status') != 'completed' or not isinstance(page.get('output'), dict):
            message = str(page.get('error', {}).get('message', '')) if isinstance(page.get('error'), dict) else ''
            status = 'rate_limited' if 'rate limit' in message.casefold() else 'unavailable'
            return {'status': status, 'reason': 'dreamwork_list_matches_failed',
                    'queued_application_ids': [], 'pack_jobs_queued': 0,
                    'retryable': True, 'next_action': 'next_natural_wake'}
        output = page['output']
        if output.get('poolStatus') != 'ready' or not isinstance(output.get('jobs'), list):
            return {'status': 'pool_building', 'queued_application_ids': [],
                    'pack_jobs_queued': 0, 'retryable': True,
                    'next_action': 'next_natural_wake'}
        if cursor and output.get('poolChanged') is True:
            cursor_state.update(cursor=None, pending_matches=[], offset=0,
                                next_cursor=None, cycle_complete=False)
            _write_private_json(cursor_path, cursor_state)
            return {'status': 'pool_changed', 'queued_application_ids': [],
                    'pack_jobs_queued': 0, 'retryable': True,
                    'next_action': 'restart_match_walk'}
        cursor_state['pending_matches'] = [
            {key: row.get(key) for key in
             ('id','title','company','location','remote','salary','matchPercent','saved','applied')}
            for row in output['jobs'] if isinstance(row, dict)
        ]
        cursor_state['offset'] = 0
        cursor_state['next_cursor'] = output.get('nextCursor')

    queued_ids: list[str] = []
    pack_candidates: list[dict] = []
    details_read = 0
    local_seen_urls: set[str] = set()
    pending = cursor_state['pending_matches']
    offset = cursor_state.get('offset') if type(cursor_state.get('offset')) is int else 0
    offset = max(0, min(offset, len(pending)))
    while offset < len(pending) and details_read < max_job_reads:
        match = pending[offset]
        selected = select_free_matches([match], employer_exclusions=exclusions,
                                       fenced_companies=list(fenced_companies | fenced_source_keys))
        if not selected:
            offset += 1
            continue
        job_id = selected[0]['id']
        details = client.action('get_job', {'jobId': job_id})
        if details.get('status') != 'completed' or not isinstance(details.get('output'), dict):
            message = str(details.get('error', {}).get('message', '')) if isinstance(details.get('error'), dict) else ''
            cursor_state['offset'] = offset
            _write_private_json(cursor_path, cursor_state)
            status = 'rate_limited' if 'rate limit' in message.casefold() else 'unavailable'
            return {'status': status, 'reason': 'dreamwork_get_job_failed',
                    'queued_application_ids': queued_ids, 'pack_jobs_queued': 0,
                    'retryable': True, 'next_action': 'next_natural_wake'}
        details_read += 1
        output = details['output']
        job = output.get('job', output)
        if not isinstance(job, dict) or job.get('eligible') is not True:
            offset += 1
            continue
        company = job.get('company') if isinstance(job.get('company'), str) else selected[0]['company']
        title = job.get('title') if isinstance(job.get('title'), str) else selected[0]['title']
        source_url = _safe_employer_posting_url(job.get('sourceUrl'))
        if (not isinstance(company, str) or not company.strip()
                or not isinstance(title, str) or not title.strip() or source_url is None):
            offset += 1
            continue
        if is_excluded_employer(company, frozenset(exclusions)):
            offset += 1
            continue
        source_keys = _source_employer_key(company, source_url)
        if (source_keys & fenced_companies or source_keys & fenced_source_keys
                or source_url in fenced_urls or source_url in local_seen_urls):
            offset += 1
            continue
        existing = ledger.connection.execute(
            "SELECT id,current_state FROM applications WHERE canonical_url=? ORDER BY rowid LIMIT 2",
            (source_url,),
        ).fetchall()
        if len(existing) > 1:
            offset += 1
            continue
        if existing:
            application_id = str(existing[0]['id'])
            current_state = str(existing[0]['current_state'])
            if current_state in {'submitted','submit_unknown','submit_claimed','rejected'}:
                offset += 1
                continue
        else:
            try:
                application_id = ledger.add_application(company, title, source_url)
            except Exception as error:
                from .ledger import ExcludedEmployerError
                if isinstance(error, ExcludedEmployerError):
                    offset += 1
                    continue
                raise
        current_state = ledger.current_state(application_id)
        if current_state == 'discovered':
            ledger.transition(application_id, 'qualified', {
                'reason': 'dreamwork_free_match', 'source': 'dreamwork',
                'dreamwork_job_id': job_id,
            })
            current_state = 'qualified'
        if current_state == 'qualified':
            ledger.transition(application_id, 'materials_ready', {
                'reason': 'mandatory_model_browser_lane', 'source': 'dreamwork',
                'dreamwork_job_id': job_id,
            })
        local_seen_urls.add(source_url)
        queued_ids.append(application_id)
        pack_candidates.append({'dreamwork_job_id':job_id,'application_id':application_id,
                                'company':company,'title':title,'canonical_url':source_url,
                                'eligible':True,
                                'match_percent':selected[0].get('matchPercent')})
        offset += 1

    cursor_state['offset'] = offset
    if offset >= len(pending):
        cursor_state['cursor'] = cursor_state.get('next_cursor')
        cursor_state['pending_matches'] = []
        cursor_state['offset'] = 0
        cursor_state['cycle_complete'] = cursor_state['cursor'] is None
    _write_private_json(cursor_path, cursor_state)

    packs_state_path = state_root / 'dreamwork-free-packs.v1.json'
    packs_state = _private_json(packs_state_path, {'version':1,'entries':{}})
    if packs_state.get('version') != 1 or not isinstance(packs_state.get('entries'), dict):
        raise DreamworkError('invalid_dreamwork_pack_state')
    entries = packs_state['entries']
    available = []
    for row in pack_candidates:
        entry = entries.get(row['application_id'])
        if entry and entry.get('status') in {
            'prepare_pending','pack_queued','pack_generating','pack_ready','prepare_unknown'
        }:
            continue
        row['profile_sha256'] = digest
        row['status'] = 'local_only'
        entries[row['application_id']] = row
        if row['eligible'] and len(available) < min(pack_remaining, 10):
            available.append(row)
    _write_private_json(packs_state_path, packs_state)

    pack_jobs_queued = 0
    if available:
        job_ids = [row['dreamwork_job_id'] for row in available]
        for row in available:
            entries[row['application_id']]['status'] = 'prepare_pending'
        _write_private_json(packs_state_path, packs_state)
        try:
            prepared = client.action('prepare_applications', {
                'jobIds': job_ids, 'assets': ['resume','coverLetter','answers']
            })
        except (OSError, TimeoutError, DreamworkError):
            for row in available:
                entries[row['application_id']]['status'] = 'prepare_unknown'
            _write_private_json(packs_state_path, packs_state)
            return {'status':'prepare_unknown','queued_application_ids':queued_ids,
                    'pack_jobs_queued':0,'retryable':True,'next_action':'provider_readback'}
        result_list = prepared.get('output', {}).get('results', []) if isinstance(prepared, dict) else []
        by_job = {str(item.get('jobId')):item for item in result_list if isinstance(item, dict)}
        if prepared.get('status') != 'completed':
            message = str(prepared.get('error', {}).get('message', '')) if isinstance(prepared.get('error'), dict) else ''
            status = 'rate_limited' if 'rate limit' in message.casefold() else 'prepare_unknown'
            for row in available:
                entries[row['application_id']]['status'] = status
            _write_private_json(packs_state_path, packs_state)
            return {'status':status,'queued_application_ids':queued_ids,
                    'pack_jobs_queued':0,'retryable':True,'next_action':'provider_readback'}
        for row in available:
            item=by_job.get(row['dreamwork_job_id'])
            if not item:
                entries[row['application_id']]['status']='prepare_unknown'
                continue
            outcome=str(item.get('outcome') or '')
            entries[row['application_id']]['dreamwork_application_id']=item.get('applicationId')
            entries[row['application_id']]['status']={
                'queued':'pack_queued','in_progress':'pack_generating',
                'already_prepared':'pack_pending_readback','quota_blocked':'quota_blocked',
                'failed':'pack_failed','not_found':'match_not_found',
            }.get(outcome,'prepare_unknown')
            if outcome in {'queued','in_progress','already_prepared'}:
                pack_jobs_queued+=1
        _write_private_json(packs_state_path, packs_state)

    return {'status':'matches_queued' if queued_ids else 'no_eligible_matches',
            'queued_application_ids':list(dict.fromkeys(queued_ids)),
            'pack_jobs_queued':pack_jobs_queued,'pack_remaining_before':pack_remaining,
            'match_details_read':details_read,'next_action':'browser_agent'}


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


def unavailable_fallback_is_verified(result: dict, pipeline: dict) -> bool:
    """Use a complete no-send view; saved/prepared free packs are not submissions."""
    jobs = pipeline.get('jobs')
    if not isinstance(jobs, list) or pipeline.get('hasMore') is not False:
        return False
    counts_complete = (
        all(type(pipeline.get(k)) is int for k in ('count','total','activeTotal','closedTotal'))
        and pipeline['count'] == pipeline['total'] == len(jobs)
    )
    if not counts_complete:
        return False
    no_send_rows = True
    for row in jobs:
        if not isinstance(row, dict) or row.get('applied') is True or row.get('inFlight') is True:
            no_send_rows = False
            break
        submission = row.get('submission')
        if submission is not None:
            if not isinstance(submission, dict) or submission.get('disposition') not in {'draft','prepared','not_submitted'}:
                no_send_rows = False
                break
        board_state = str(row.get('status') or row.get('column') or row.get('pipelineStatus') or '').upper()
        if board_state and board_state not in {'SAVED','PACK_READY','READY','PREPARING','IN_REVIEW'}:
            no_send_rows = False
            break
        if row.get('saved') is not True and board_state not in {'SAVED','PACK_READY','READY','PREPARING','IN_REVIEW'}:
            no_send_rows = False
            break
    no_provider_work = (not jobs or no_send_rows)
    return (result.get('status') == 'unavailable' and result.get('native_managed_on') is False
            and (result.get('reason') == 'paid_plan_not_authorized'
                 or result.get('readiness', {}).get('entitlement', {}).get('autoApply') is False
                 and result.get('readiness', {}).get('entitlement', {}).get('reason') == 'tier'
                 and result.get('usage', {}).get('applicationsLimit') == 0)
            and result.get('autopilot', {}).get('state') == 'unavailable'
            and 'inFlightCount' in result.get('autopilot', {})
            and (result['autopilot']['inFlightCount'] is None
                 or type(result['autopilot']['inFlightCount']) is int and result['autopilot']['inFlightCount'] == 0)
            and result.get('autopilot', {}).get('sentToday') == 0
            and result.get('autopilot', {}).get('sentThisMonth') == 0
            and no_provider_work)


def ensure_autopilot(client, state_path: Path, preferences_patch: dict) -> dict:
    state = json.loads(state_path.read_text()) if state_path.exists() else {'actions': {}}
    actions = state['actions']
    usage = read_action(client, 'get_usage')
    readiness = read_action(client, 'get_application_readiness')
    status = read_action(client, 'get_autopilot_status')
    if usage.get('tier') != 'free':
        managed_on = any(record['action'] == 'set_autopilot' and record['args'].get('state') == 'on'
                         for record in actions.values())
        return {'status': 'unavailable', 'reason': 'paid_plan_not_authorized',
                'readiness': readiness, 'usage': usage, 'autopilot': status,
                'native_managed_on': managed_on,
                'fallback_safe': not managed_on and status.get('state') == 'off'
                and status.get('inFlightCount') == 0 and status.get('sentToday') == 0
                and status.get('sentThisMonth') == 0}
    if not (readiness.get('autopilotReady') is True and readiness.get('autopilotAvailable') is True
            and readiness.get('entitlement', {}).get('autoApply') is True):
        if any(record['status'] == 'effect_unknown' for record in actions.values()):
            return {'status': 'effect_unknown', 'autopilot': status, 'usage': usage}
        managed_on = any(record['action'] == 'set_autopilot' and record['args'].get('state') == 'on'
                         for record in actions.values())
        return {'status': 'unavailable', 'readiness': readiness, 'usage': usage, 'autopilot': status,
                'native_managed_on': managed_on,
                'fallback_safe': not managed_on and status.get('state') == 'off'
                and status.get('inFlightCount') == 0 and status.get('sentToday') == 0
                and status.get('sentThisMonth') == 0}
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
        return 75 if (args.state_root / 'dreamwork-actions.json').exists() else 69
    key = load_key(Path.home() / '.local/share/anicca/credentials.json')
    if key is None:
        _write_private_json(args.output, {'status': 'not_configured', 'reason': 'credential_rotation_required'})
        return 75
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
            fenced = [row[0] for row in ledger.connection.execute("SELECT DISTINCT company FROM applications WHERE current_state IN ('submitted','submit_unknown','submit_claimed') AND NOT EXISTS (SELECT 1 FROM events e WHERE e.application_id=applications.id AND e.from_state IS NULL AND json_extract(e.payload_json, '$.source')='dreamwork')")]
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
        if unavailable_fallback_is_verified(result, pipeline):
            result['fallback_safe'] = True
            usage = result.get('usage', {})
            if usage.get('tier') == 'free' and usage.get('applicationsLimit') == 0:
                from .ledger import Ledger
                ledger = Ledger(args.state_root / 'ledger.sqlite3')
                try:
                    try:
                        result['free_match_preparation'] = prepare_free_matches(
                            client, state_root=args.state_root, ledger=ledger,
                            profile={'candidate': candidate}, usage=usage,
                        )
                    except (DreamworkError, OSError, ValueError, KeyError) as error:
                        result['free_match_preparation'] = {
                            'status': 'unavailable',
                            'reason': 'dreamwork_free_preparation_failed',
                            'error_class': type(error).__name__,
                            'retryable': True,
                            'next_action': 'existing_ats_lane',
                        }
                finally:
                    ledger.close()
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
        print(json.dumps({'status': 'failed', 'error_class': type(error).__name__,
                          'reason': str(error) if isinstance(error, DreamworkError) else type(error).__name__}))
        raise SystemExit(75)
