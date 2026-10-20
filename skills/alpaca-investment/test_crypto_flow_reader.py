"""Synthetic wire responses for the fixed-window, account-bound raw reader."""
import copy
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import alpaca_cli as cli


ACCOUNT = 'synthetic-flow-reader-account'
START = '2026-01-01T13:14:15.123456789+09:00'
END = '2026-01-02T03:04:05.987654321Z'
WALLET = [{'id': 'synthetic-wallet', 'asset': 'USDC',
    'amount': '66.12345678901234567890123456789', 'usd_value': '65.99',
    'direction': 'INCOMING', 'status': 'COMPLETE',
    'created_at': '2025-12-31T23:59:59.999999999Z',
    'fees': '0.01', 'network_fee': '0.02', 'native_extra': {'keep': 'raw'}}]


def records(count):
    return [{'id': f'synthetic-activity-{i}', 'activity_type': ('FILL', 'CFEE', 'OCT')[i % 3],
        'qty': '0.12345678901234567890123456789', 'native_extra': {'sequence': i}}
        for i in range(count)]


class CryptoFlowReaderTests(unittest.TestCase):
    def reader(self):
        reader = getattr(cli, 'read_crypto_flow_evidence', None)
        self.assertTrue(callable(reader), 'the bounded, scoped raw flow reader is required')
        return reader

    def read(self, *, mode='live', pages=None, wallet=WALLET, account=None, calls=None,
             page_token=None, period_start=START, period_end=END):
        reader = self.reader()
        env = {'synthetic-env': mode}
        calls = [] if calls is None else calls
        pages = iter(copy.deepcopy([records(3)] if pages is None else pages))
        account = {'id': ACCOUNT} if account is None else account

        def transport(args, **kwargs):
            command = args[1:]
            calls.append(copy.deepcopy(command))
            self.assertIs(kwargs['env'], env)
            if command == ['account', 'get', '--quiet', '--jq', '{id}']:
                body = account
            elif command == ['api', 'GET', '/v2/wallets/transfers', '--quiet', '--jq', '.']:
                body = wallet
            elif command[:3] == ['account', 'activity', 'list']:
                self.assertNotIn('--activity-types', command)
                self.assertEqual(command[command.index('--jq') + 1], '.')
                body = next(pages)
            else:
                self.fail('unexpected wire command: ' + str(command))
            if isinstance(body, Exception):
                raise body
            return subprocess.CompletedProcess(args, 0, json.dumps(body).encode(), b'')

        with patch.object(cli, '_context', return_value=env) as context, \
                patch.object(cli.subprocess, 'run', side_effect=transport):
            frame = reader(credentials_path=Path('unused'), cli_path=Path('unused'), mode=mode,
                period_start=period_start, period_end=period_end,
                native_trading_account_id=ACCOUNT, page_token=page_token)
        context.assert_called_once_with(Path('unused'), Path('unused'), mode=mode)
        return frame, calls

    def test_same_mode_native_account_and_fixed_raw_window_without_clock_read(self):
        original = copy.deepcopy(WALLET)
        for mode in ('paper', 'live'):
            with self.subTest(mode=mode):
                frame, calls = self.read(mode=mode)
                self.assertEqual(calls[0], ['account', 'get', '--quiet', '--jq', '{id}'])
                self.assertEqual(len(calls), 2 if mode == 'paper' else 3)
                self.assertEqual(frame['mode'], mode)
                self.assertIs(frame['paper'], mode == 'paper')
                self.assertEqual(frame['native_trading_account_id'], ACCOUNT)
                self.assertIsNone(frame['clock'])
                self.assertEqual(frame['activity_request'],
                    {'after': START, 'until': END, 'direction': 'asc', 'page_size': 100})
                self.assertEqual(frame['activity_pages'], [records(3)])
                self.assertEqual(frame['activity_pagination'], 'exhausted')
                self.assertEqual(frame['capture_status'], 'captured')
                self.assertEqual(frame['fee_completeness_status'], 'unknown')
                self.assertIsNone(frame['net_pnl_usd'])
                self.assertIsNone(frame['next_page_token'])
                if mode == 'paper':
                    self.assertEqual(frame['wallet_status'], 'unsupported_on_paper')
                    self.assertIsNone(frame['wallet_transfers'])
                else:
                    self.assertEqual(frame['wallet_status'], 'observed')
                    self.assertEqual(frame['wallet_transfers'], original)
                    frame['wallet_transfers'][0]['native_extra']['keep'] = 'changed'
        self.assertEqual(WALLET, original)

    def test_resumed_token_and_every_page_keep_exact_fixed_scope(self):
        rows = records(101)
        token = 'raw-token+opaque/='
        frame, calls = self.read(pages=[rows[:100], rows[100:]], page_token=token)
        self.assertEqual(frame['activity_request']['page_token'], token)
        requests = [c for c in calls if c[:3] == ['account', 'activity', 'list']]
        self.assertEqual(len(requests), 2)
        for request, expected_token in zip(requests, (token, 'synthetic-activity-99')):
            self.assertEqual(request[request.index('--after') + 1], START)
            self.assertEqual(request[request.index('--until') + 1], END)
            self.assertEqual(request[request.index('--page-size') + 1], '100')
            self.assertEqual(request[request.index('--direction') + 1], 'asc')
            self.assertEqual(request[request.index('--page-token') + 1], expected_token)
        self.assertEqual(frame['activity_pages'], [rows[:100], rows[100:]])
        self.assertEqual(frame['activity_pagination'], 'exhausted')
        self.assertIsNone(frame['next_page_token'])

    def test_four_full_pages_keep_valid_prefix_and_resume_token_as_partial(self):
        rows = records(400)
        pages = [rows[i:i + 100] for i in range(0, 400, 100)]
        frame, calls = self.read(pages=pages)
        self.assertEqual(frame['activity_pages'], pages)
        self.assertEqual(frame['activity_pagination'], 'partial')
        self.assertEqual(frame['capture_status'], 'partial')
        self.assertEqual(frame['next_page_token'], 'synthetic-activity-399')
        self.assertEqual(frame['capture_error_code'], 'crypto_flow_activity_limit_exceeded')
        self.assertEqual(len(calls), 6)
        terminal, _ = self.read(pages=[[]], page_token=frame['next_page_token'])
        self.assertEqual(terminal['activity_pages'], [[]])
        self.assertEqual(terminal['activity_pagination'], 'exhausted')
        self.assertIsNone(terminal['next_page_token'])
        self.assertEqual(terminal['fee_completeness_status'], 'unknown')
        self.assertIsNone(terminal['net_pnl_usd'])

    def test_wallet_timeout_shape_and_real_output_limit_keep_activity_evidence(self):
        oversized = [{**WALLET[0], 'native_extra': 'x' * 700} for _ in range(150)]
        self.assertGreater(len(json.dumps(oversized).encode()), 64 * 1024)
        variants = (
            (subprocess.TimeoutExpired('synthetic', 30), None, 'alpaca_cli_timeout:api_GET'),
            ({'unexpected': 'shape'}, {'unexpected': 'shape'}, 'crypto_flow_wallet_invalid'),
            ([None], [None], 'crypto_flow_wallet_invalid'),
            (oversized, None, 'alpaca_cli_output_too_large'),
        )
        for wallet, retained, error_code in variants:
            with self.subTest(error_code=error_code):
                frame, calls = self.read(wallet=wallet)
                self.assertEqual(frame['wallet_transfers'], retained)
                self.assertEqual(frame['wallet_status'], 'failed')
                self.assertEqual(frame['wallet_error_class'], 'ValueError')
                self.assertEqual(frame['wallet_error_code'], error_code)
                self.assertEqual(frame['activity_pages'], [records(3)])
                self.assertEqual(frame['activity_pagination'], 'exhausted')
                self.assertEqual(frame['capture_status'], 'partial')
                self.assertEqual(len(calls), 3)
                self.assertIsNone(frame['net_pnl_usd'])

    def test_invalid_or_timed_out_later_page_keeps_wallet_and_valid_prefix(self):
        first = records(100)
        for bad in ([first[0]], [{'id': 'bad', 'activity_type': ''}], {}, records(101),
                    subprocess.TimeoutExpired('synthetic', 30)):
            with self.subTest(bad_type=type(bad).__name__):
                frame, _ = self.read(pages=[first, bad])
                self.assertEqual(frame['wallet_transfers'], WALLET)
                self.assertEqual(frame['activity_pages'], [first])
                self.assertEqual(frame['activity_pagination'], 'partial')
                self.assertEqual(frame['capture_status'], 'partial')
                self.assertEqual(frame['next_page_token'], 'synthetic-activity-99')
                self.assertIn(frame['capture_error_code'],
                    ('crypto_flow_activity_invalid', 'alpaca_cli_timeout:account_activity'))

    def test_no_originals_is_failed_and_paper_unsupported_never_becomes_zero(self):
        for mode in ('paper', 'live'):
            with self.subTest(mode=mode):
                frame, calls = self.read(mode=mode,
                    wallet=subprocess.TimeoutExpired('synthetic', 30), pages=[{}])
                self.assertEqual(frame['capture_status'], 'failed')
                self.assertEqual(frame['activity_pages'], [])
                self.assertEqual(frame['activity_pagination'], 'unknown')
                self.assertIsNone(frame['wallet_transfers'])
                self.assertEqual(frame['fee_completeness_status'], 'unknown')
                self.assertIsNone(frame['net_pnl_usd'])
                self.assertEqual(len(calls), 2 if mode == 'paper' else 3)

    def test_wrong_or_missing_native_account_stops_before_wallet_or_activity(self):
        for account in ({'id': 'other-account'}, {'id': ''}, {'id': None}, {}, [], {'id': 1}):
            calls = []
            with self.subTest(account=account), self.assertRaisesRegex(ValueError, 'crypto_flow_account_invalid'):
                self.read(account=account, calls=calls)
            self.assertEqual(calls, [['account', 'get', '--quiet', '--jq', '{id}']])

    def test_invalid_arguments_are_rejected_before_context_or_transport(self):
        reader = self.reader()
        variants = [{'mode': value} for value in ('shadow', '', None, [])]
        variants += [{'native_trading_account_id': value} for value in ('', ' ', None, 1, [])]
        variants += [{'page_token': value} for value in ('', ' ', 'x' * 8193, False, [])]
        variants += [{'period_start': value} for value in ('invalid', None, '2026-01-03T00:00:00Z')]
        variants += [{'period_end': value} for value in ('invalid', None, '2025-01-01T00:00:00Z')]
        for changes in variants:
            args = dict(credentials_path=Path('unused'), cli_path=Path('unused'), mode='paper',
                period_start=START, period_end=END, native_trading_account_id=ACCOUNT)
            args.update(changes)
            with self.subTest(changes=changes), patch.object(cli, '_context') as context, \
                    patch.object(cli, '_run') as run, self.assertRaises(ValueError):
                reader(**args)
            context.assert_not_called()
            run.assert_not_called()

    def test_native_nanosecond_order_and_ninety_day_boundary_are_exact(self):
        reader = self.reader()
        invalid = (
            ('2026-01-01T00:00:00.000000001Z', '2026-01-01T00:00:00.000000000Z'),
            ('2026-01-01T00:00:00.000000001Z', '2026-04-01T00:00:00.000000002Z'),
            ('2026-01-01T00:00:00.1234567890Z', END),
        )
        for start, end in invalid:
            with self.subTest(start=start, end=end), patch.object(cli, '_context') as context, \
                    self.assertRaisesRegex(ValueError, 'crypto_flow_period_invalid'):
                reader(credentials_path=Path('unused'), cli_path=Path('unused'), mode='paper',
                    period_start=start, period_end=end, native_trading_account_id=ACCOUNT)
            context.assert_not_called()
        for start, end in (
            ('2026-01-01T00:00:00.000000001Z', '2026-04-01T00:00:00.000000001Z'),
            ('2026-01-01T09:00:00.000000001+09:00', '2026-01-01T00:00:00.000000001Z'),
        ):
            with self.subTest(start=start, end=end):
                frame, _ = self.read(mode='paper', period_start=start, period_end=end,
                    page_token='x' * 8192)
                self.assertEqual(frame['activity_request']['after'], start)
                self.assertEqual(frame['activity_request']['until'], end)


if __name__ == '__main__':
    unittest.main()
