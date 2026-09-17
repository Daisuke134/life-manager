"""reward_mm — Polymarket liquidity-rewards market-making, ported from poly-maker.

Source: warproxxx/poly-maker (MIT, github.com/warproxxx/poly-maker, ★1387,
clone verified live 2026-07-12, 111 tests passing on the real Gamma API).
See ../SKILL.md "REWARD-MM (poly-maker port)" section and the repository earn
design records for the research trail that led here.

★★★ LEGAL PIVOT (repository earn design record, 2026-07-12):
Polymarket-from-Japan carries 刑法185条 (gambling) exposure per
legal research done the same day this module was written. This package is
PAPER-MODE ONLY (no order placement, no wallet, no signing) precisely because
of that finding — do not wire it into a live execution path without first
resolving the jurisdiction question (see the SKILL.md section for detail).

Everything here is a pure port + a paper-mode read-only pipeline:
  gamma_scan  — market discovery + reward/rebate scoring (real Gamma/CLOB REST)
  book        — public (no-auth) CLOB order-book snapshot + microprice
  estimators  — EWMA vol/flow/markout(toxicity) online estimators
  regime      — QUIET/TRENDING/EVENT/REDUCE_ONLY/HALTED state machine
  quoting     — pure (book, inventory, params) -> two-sided post-only quotes
  risk        — pre-trade caps + daily-loss kill switch (paper ledger only)
  profiles    — strategy parameter presets (ported from poly-maker's
                config/strategy.toml, live-sampled defaults)
  paper_run   — CLI: scan -> pick -> quote -> print JSON. Never posts an order.
"""
