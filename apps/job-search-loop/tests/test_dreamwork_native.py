import importlib
import json
import tempfile
import unittest
from pathlib import Path
from job_search_loop.ledger import Ledger, FenceError

try:
    native = importlib.import_module('job_search_loop.dreamwork_native')
except ModuleNotFoundError:
    native = None


class Provider:
    def __init__(self):
        self.state = 'off'
        self.settings = {'scoreFloor': 70, 'resumeVariant': 'default'}
        self.preferences = {'excludedCompanies': []}
        self.confirmed = []
        self.timeout = False

    def action(self, name, args, confirmation_token=None):
        values = {
            'get_usage': {'tier': 'dreamer', 'applicationsLimit': 40, 'applicationsUsedToday': 0},
            'get_application_readiness': {'ready': True, 'autopilotReady': True, 'autopilotAvailable': True, 'entitlement': {'autoApply': True, 'reason': None}},
            'get_autopilot_status': {'state': self.state, 'inFlightCount': 0, 'sentToday': 0, 'dailyLimit': 40, 'sentThisMonth': 0, 'monthlyLimit': 1200, 'nextRunAt': None},
            'get_autopilot_settings': self.settings,
            'get_preferences': {'preferences': self.preferences, 'unanswered': []},
        }
        if name in values:
            return {'status': 'completed', 'output': values[name]}
        if confirmation_token is None:
            self.held = (name, json.loads(json.dumps(args)))
            return {'status': 'held', 'needsInput': {'token': 'fixture-confirmation', 'summary': 'authorized action'}}
        if (name, args) != self.held or confirmation_token != 'fixture-confirmation':
            raise ValueError('exact confirmation binding violated')
        self.confirmed.append(name)
        if name == 'set_autopilot':
            if self.timeout:
                raise TimeoutError('provider outcome unknown')
            self.state = args['state']
        elif name == 'update_autopilot_settings':
            self.settings.update(args)
        elif name == 'update_preferences':
            self.preferences.update(args['patch'])
        return {'status': 'completed', 'output': {'status': 'completed', 'taskId': 'fixture-task'}}


class DreamworkNativeTests(unittest.TestCase):
    def test_native_owner_exists(self):
        self.assertIsNotNone(native, 'native Dreamwork application owner is missing')

    @unittest.skipIf(native is None, 'owner is absent')
    def test_complete_official_tier_zero_view_allows_only_unmanaged_fallback(self):
        result = {'status': 'unavailable', 'native_managed_on': False, 'readiness': {'entitlement': {'autoApply': False, 'reason': 'tier'}}, 'usage': {'applicationsLimit': 0}, 'autopilot': {'state': 'unavailable', 'sentToday': 0, 'sentThisMonth': 0}}
        pipeline = {'jobs': [], 'count': 0, 'total': 0, 'activeTotal': 0, 'closedTotal': 0, 'hasMore': False}
        self.assertTrue(native.unavailable_fallback_is_verified(result, pipeline))
        self.assertFalse(native.unavailable_fallback_is_verified(result, {**pipeline, 'hasMore': True}))
        self.assertFalse(native.unavailable_fallback_is_verified({**result, 'native_managed_on': True}, pipeline))
        self.assertFalse(native.unavailable_fallback_is_verified({**result, 'status': 'effect_unknown'}, pipeline))

    @unittest.skipIf(native is None, 'owner is absent')
    def test_free_account_does_not_call_gated_settings(self):
        class FreeProvider(Provider):
            def action(self, name, args, confirmation_token=None):
                if name == 'get_application_readiness':
                    return {'status': 'completed', 'output': {'ready': False, 'autopilotReady': False, 'autopilotAvailable': True, 'entitlement': {'autoApply': False, 'reason': 'tier'}}}
                if name == 'get_autopilot_settings':
                    raise AssertionError('settings are tier-gated')
                return super().action(name, args, confirmation_token)
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(native.ensure_autopilot(FreeProvider(), Path(root) / 'state.json', {})['status'], 'unavailable')

    @unittest.skipIf(native is None, 'owner is absent')
    def test_authorized_tailored_autopilot_needs_no_recurring_human_confirmation(self):
        with tempfile.TemporaryDirectory() as root:
            provider = Provider()
            result = native.ensure_autopilot(provider, Path(root) / 'state.json', {'excludedCompanies': ['Aaru', 'Simily']})
            self.assertEqual(result['status'], 'active')
            self.assertEqual(provider.state, 'on')
            self.assertEqual(provider.settings['resumeVariant'], 'tailored')
            self.assertEqual(provider.preferences['excludedCompanies'], ['Aaru', 'Simily'])
            self.assertEqual(native.ensure_autopilot(provider, Path(root) / 'state.json', {'excludedCompanies': ['Aaru', 'Simily']})['status'], 'active')
            self.assertEqual(provider.confirmed.count('set_autopilot'), 1)

    @unittest.skipIf(native is None, 'owner is absent')
    def test_uncertain_enable_is_not_sent_twice(self):
        with tempfile.TemporaryDirectory() as root:
            provider = Provider()
            provider.timeout = True
            path = Path(root) / 'state.json'
            self.assertEqual(native.ensure_autopilot(provider, path, {})['status'], 'effect_unknown')
            provider.timeout = False
            self.assertEqual(native.ensure_autopilot(provider, path, {})['status'], 'effect_unknown')
            self.assertEqual(provider.confirmed.count('set_autopilot'), 1)
            provider.state = 'on'
            self.assertEqual(native.ensure_autopilot(provider, path, {})['status'], 'active')
            self.assertEqual(provider.confirmed.count('set_autopilot'), 1)

    @unittest.skipIf(native is None, 'owner is absent')
    def test_board_applied_and_queued_are_not_completed_submissions(self):
        rows = [
            {'applicationId': 'A', 'status': 'APPLIED', 'submission': {'disposition': 'unknown'}},
            {'applicationId': 'B', 'submission': {'disposition': 'user_reported'}},
            {'applicationId': 'C', 'submission': {'disposition': 'submitted', 'proof': 'ats_receipt', 'submittedAt': '2026-10-11T00:00:00Z'}},
        ]
        self.assertEqual([row['applicationId'] for row in native.confirmed_submissions(rows)], ['C'])


class ProviderReceiptImportTests(unittest.TestCase):
    def test_imported_receipt_has_one_append_only_origin(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = Ledger(Path(root) / 'ledger.sqlite3')
            try:
                first = ledger.import_provider_submission(company='Example', title='AI Engineer', url='https://example.com/jobs/1', provider='dreamwork', provider_application_id='native-1', applied_at='2026-10-11T00:00:00Z', evidence_sha256='a' * 64)
                second = ledger.import_provider_submission(company='Example', title='AI Engineer', url='https://example.com/jobs/1', provider='dreamwork', provider_application_id='native-1', applied_at='2026-10-11T00:00:00Z', evidence_sha256='a' * 64)
                self.assertEqual(first, second)
                self.assertEqual(len(ledger.events(first)), 1)
                self.assertEqual(ledger.events(first)[0]['to_state'], 'submitted')
                ledger.event_summary_rows()
            finally:
                ledger.close()

    def test_provider_receipt_does_not_clear_an_unbound_legacy_occurrence(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = Ledger(Path(root) / 'ledger.sqlite3')
            try:
                application = ledger.add_application('Example', 'AI Engineer', 'https://example.com/jobs/1')
                with self.assertRaises(FenceError):
                    ledger.import_provider_submission(company='Example', title='AI Engineer', url='https://example.com/jobs/1', provider='dreamwork', provider_application_id='native-1', applied_at='2026-10-11T00:00:00Z', evidence_sha256='a' * 64)
                self.assertEqual(ledger.events(application)[-1]['to_state'], 'discovered')
            finally:
                ledger.close()
