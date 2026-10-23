import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


class OutcomeWatchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.root = self.home / 'repo'
        self.watch = self.root / 'tools/gig-outcome-watch'
        self.watch.mkdir(parents=True)
        for name in ('notify.sh', 'outcome_watch.py', 'verify_domain_skills.sh'):
            if (HERE / name).exists():
                shutil.copy2(HERE / name, self.watch / name)
        utility = self.root / 'skills/earn/gig/scripts'
        utility.mkdir(parents=True)
        shutil.copy2(REPO / 'skills/earn/gig/scripts/daily_verdict.py', utility)
        sender = self.root / 'skills/_shared/send-telegram.sh'
        sender.parent.mkdir(parents=True)
        sender.write_text('#!/bin/sh\necho called >> "$HOME/sender-calls"\necho TELEGRAM_SENT=true MSGID=fixture\n')
        sender.chmod(0o755)
        self.env = {**os.environ, 'HOME': str(self.home), 'LIFE_MANAGER_STATE_ROOT': str(self.home / 'watch-state'),
                    'LIFE_MANAGER_ENV_FILE': str(self.home / 'owner.env'),
                    'LIFE_MANAGER_RUNTIME_PYTHON': sys.executable, 'PY': '/nonexistent/legacy/python',
                    'GIG_STATE_DIR': str(self.home / 'gig')}

    def run_notify(self):
        return subprocess.run(['bash', str(self.watch / 'notify.sh')], env=self.env,
                              capture_output=True, text=True, timeout=10)

    def test_missing_helper_is_observation_failure_not_no_alerts(self):
        (self.watch / 'outcome_watch.py').unlink(missing_ok=True)
        result = self.run_notify()
        self.assertEqual(result.returncode, 75, result.stdout + result.stderr)
        self.assertNotIn('ok: no alerts', result.stdout)
        self.assertIn('helper_missing', result.stderr)
        self.assertFalse((self.home / 'sender-calls').exists())

    def test_fresh_owner_uses_selected_python_and_reports_missing_evidence(self):
        result = self.run_notify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('LEDGER_ABSENT', result.stdout)
        self.assertEqual((self.home / 'sender-calls').read_text().splitlines(), ['called'])
        row = json.loads((self.home / 'watch-state/history.jsonl').read_text())
        self.assertEqual(row['outcomes'], 0)

    def test_only_settled_and_verified_outcomes_count(self):
        gig = self.home / 'gig'
        gig.mkdir()
        now = time.time()
        def rows(path, values):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(''.join(json.dumps(row) + '\n' for row in values))
        rows(gig / 'earnings.jsonl', [
            {'ts': now, 'jpy': 900, 'status': 'pending'},
            {'ts': now, 'jpy': 100, 'status': 'paid', 'evidence': 'official-receipt'},
        ])
        rows(gig / 'applied.jsonl', [
            {'ts': now, 'status': 'applied', 'applied_page_verified': True},
            {'ts': now, 'status': 'applied', 'submit_verified': True, 'applied_page_verified': True},
        ])
        rows(self.home / '.local/state/life-manager/telemetry/token-budget.jsonl', [
            {'timestamp': now - 1, 'day': 'today', 'loop': 'gig', 'daily_consumed_after_tokens': 0},
            {'timestamp': now, 'day': 'today', 'loop': 'gig', 'daily_consumed_after_tokens': 100},
        ])
        result = subprocess.run([sys.executable, str(self.watch / 'outcome_watch.py'), '--json'],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        row = json.loads(result.stdout)
        self.assertEqual(row['outcomes'], 2)
        self.assertEqual(row['earnings_jpy'], 100)
        self.assertEqual(row['spend_tokens'], 100)

    def test_current_agent_runner_settlements_trigger_silent_success_once(self):
        gig = self.home / 'gig'
        gig.mkdir()
        now = time.time()
        (gig / 'earnings.jsonl').write_text(json.dumps({
            'ts': now - 30 * 3600, 'jpy': 100, 'status': 'paid', 'evidence': 'official-receipt'}) + '\n')
        (gig / 'applied.jsonl').touch()
        ledger = self.home / '.local/state/life-manager/telemetry/token-budget.jsonl'
        ledger.parent.mkdir(parents=True)
        events = [
            {'type': 'reservation', 'event_id': 'apply', 'loop': 'hf-gig-apply-direct', 'status': 'allowed', 'timestamp': now, 'reservation_tokens': 900000},
            {'type': 'settlement', 'event_id': 'apply', 'timestamp': now, 'charged_tokens': 600000},
            {'type': 'settlement', 'event_id': 'apply', 'timestamp': now, 'charged_tokens': 600000},
            {'type': 'reservation', 'event_id': 'unsettled', 'loop': 'hf-gig-paid-direct', 'status': 'allowed', 'timestamp': now, 'reservation_tokens': 900000},
            {'type': 'reservation', 'event_id': 'other', 'loop': 'writer', 'status': 'allowed', 'timestamp': now},
            {'type': 'settlement', 'event_id': 'other', 'timestamp': now, 'charged_tokens': 700000},
        ]
        ledger.write_text(''.join(json.dumps(row) + '\n' for row in events))
        result = subprocess.run([sys.executable, str(self.watch / 'outcome_watch.py'), '--json'],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1, result.stderr)
        row = json.loads(result.stdout)
        self.assertEqual(row['spend_tokens'], 600000)
        self.assertEqual(row['model_calls'], 1)
        self.assertEqual(row['alerts'], ['SILENT_SUCCESS'])


if __name__ == '__main__':
    unittest.main()
