"""Mode-isolated BTC transport contract; provider access is replaced by fixtures."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import alpaca_cli as cli

CLIENT = 'lm-ai-' + 'd' * 24
BUY = {'asset_class': 'crypto', 'side': 'buy', 'symbol': 'BTC/USDC',
       'type': 'market', 'time_in_force': 'gtc', 'notional_usd': '10.00'}
SELL = {key: value for key, value in BUY.items() if key != 'notional_usd'}
SELL.update(side='sell', qty='0.000123456')


class CryptoGatewayTests(unittest.TestCase):
    def test_paper_and_live_share_exact_buy_and_sell_args_with_separate_contexts(self):
        for order in (BUY, SELL):
            calls = []
            for mode in ('paper', 'live'):
                with self.subTest(mode=mode, side=order['side']), \
                     patch.object(cli, '_context', return_value={'isolated_mode': mode}) as context, \
                     patch.object(cli, '_run', return_value={'client_order_id': CLIENT}) as run:
                    try:
                        cli.submit_order(credentials_path=Path(mode), cli_path=Path('fixture-cli'),
                                         client_order_id=CLIENT, order=copy.deepcopy(order), mode=mode)
                    except ValueError as error:
                        self.fail(f"valid bounded {mode} BTC order rejected: {error}")
                    context.assert_called_once_with(Path(mode), Path('fixture-cli'), mode)
                    self.assertEqual(run.call_args.args[2], {'isolated_mode': mode})
                    calls.append(run.call_args.args[1])
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0], calls[1])
            self.assertNotIn('--profile', calls[0])
            self.assertEqual(calls[0][calls[0].index('--side')+1], order['side'])

    def test_invalid_crypto_is_rejected_in_both_modes_before_provider_access(self):
        invalid = [dict(BUY, symbol=symbol) for symbol in ('BTC/USD', 'ETH/USD', 'ETH/USDC')]
        invalid += [dict(BUY, notional_usd=value) for value in ('10.01', '0', '-1', 'NaN', 'Infinity')]
        invalid += [dict(SELL, qty=value) for value in ('0', '-1', 'NaN', 'Infinity', '0.0000000001')]
        invalid += [dict(BUY, type='limit'), dict(BUY, time_in_force='day'),
                    dict(BUY, qty='1'), dict(SELL, notional_usd='10'), dict(BUY, side='other')]
        for mode in ('paper', 'live'):
            for order in invalid:
                with self.subTest(mode=mode, order=order), \
                     patch.object(cli, '_context') as context, patch.object(cli, '_run') as run:
                    with self.assertRaises(ValueError):
                        cli.submit_order(credentials_path=Path('unused'), cli_path=Path('unused'),
                                         client_order_id=CLIENT, order=order, mode=mode)
                    context.assert_not_called()
                    run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
