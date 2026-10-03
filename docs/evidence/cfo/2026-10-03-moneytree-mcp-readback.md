# Moneytree MCP readback — 2026-10-03

Status: `partial/stale`; read-only provider access works, but transaction freshness is not current.

## Sanitized official readback

- Provider: Moneytree MCP
- Institution: MUFG
- Account count: `1`
- Balance readback: `JPY 504,302`
- Requested range: `2026-07-03..2026-10-03`
- Transaction rows: `187`
- Latest transaction date: `2026-08-25`
- Currency: `JPY`
- Income in returned rows: `JPY 824,656`
- Gross negative movement: `JPY 668,855`
- Transfer/card repayment bucket excluded from personal spending: `JPY 466,355`
- Spending after that exclusion: `JPY 202,500`

The balance and totals are provider-read values, not invented zeros. Because the latest transaction is 2026-08-25 and the connector does not provide an independent current completeness/freshness receipt in this readback, the CFO must display them as last-known/stale rather than today's fresh cash or spending.

No account number, transaction description, credential, or raw provider payload is stored in this evidence file.
