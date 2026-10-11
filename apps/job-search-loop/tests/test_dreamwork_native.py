import importlib
import json
import tempfile
import unittest
from pathlib import Path

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
