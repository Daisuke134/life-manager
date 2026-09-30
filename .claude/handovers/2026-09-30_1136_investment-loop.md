# 投資loop handover

## 正本

- spec: `/Users/anicca/Projects/life-manager-main/.worktrees/investment-owner-readback-20260929-v4/docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`
- remaining-TODO SSOT: `## 投資loop Atomic Todo（唯一の実行正本・1行 = 1操作）`（現在cursor `AT-13`）
- exact restart goal: 同じディレクトリの`2026-09-30_1136_investment-loop.goal.txt`

## Git routing

- spec worktree: `/Users/anicca/Projects/life-manager-main/.worktrees/investment-owner-readback-20260929-v4`
- branch/upstream: `docs/investment-owner-readback-20260929-v4` / `origin/docs/investment-owner-readback-20260929-v4`
- verified commit: `b46f48b8b8ee9f89bb16da216943e11326143897`
- spec worktree dirty state: clean at handover creation
- implementation worktree: `/Users/anicca/Projects/life-manager-main/.worktrees/investment-paper-pnl-20260930`
- implementation branch/upstream: `feat/investment-paper-pnl-20260930` / `origin/main`
- implementation commit: `d0dcb53a72b22805528152e3d77d6a213212d327`
- implementation dirty warning: untracked `risk-day.json`; do not remove or edit it in this handover
- implementation PR: `#6259` is open/unstable; `OSS self-contained boundary` fails while the other listed checks pass. Do not fix this from the investment spec lane.
- do not touch the repository root/CAPFY worktrees or shared files owned by the other agent

## Verified state

- completed: `AT-01` through `AT-12` (12 rows)
- remaining: 277 expanded atomic rows; total 289
- current item: `AT-13` only — wait for the next daily decision that says the held QQQ should be sold
- latest decision: `d0c175c0fab7fefb2ab03c4d27f6ceb5e3005e36ba6fdf06179e456a5e4de780`, recorded `2026-09-30T02:34:02.830457Z`, `decision_session=2026-09-29`, `HOLD / hold_period_not_elapsed`, paper mode, no trade
- latest natural run: occurrence `alpaca-investment-paper:18d9f88ff361d2a8-75349`, event `ac4e2fe5932c4f23a447e7d7`, pass, exit `0`
- current release: `/Users/anicca/loops/releases/20260930T113159-de3c9064`, SHA `de3c9064fac327e869558a43f93ae32957317d3f`, ancestor of `origin/main`
- runtime status: `admission_effect_unknown=false`, `provider_receipt_id=null`, `official_readback_ref=null`, `launchd_state=loaded-idle`, next natural run interval `300s`
- natural capacity defers occurred before later automatic passes; they are not an investment-source failure and are not a reason to touch shared admission or another agent's work
- no live order, Binance transfer, wallet funding, meme-coin signing, yield deposit, or cap increase has occurred
- QQQ is a paper open position; verified realized investment revenue remains `$0/month`
- the user's approval for future small live use is recorded in the spec, but it does not complete `AT-29`; the 30 measured round trips and safety decision are still missing

## First safe resume action

Fresh-fetch both relevant branches, verify HEAD/upstream/dirty state, reread this file and the Atomic Todo section, then read `lm-loop status alpaca-investment-paper` and the newest paper receipt. Continue only from `AT-13`. Do not manually wake, sell, replay, transfer money, or jump to `AT-14`. When a new daily session produces an exit reason `ranked_symbol_changed` or `hold_sessions_elapsed`, perform the official order readback for `AT-14`; otherwise record the new same-session result in the spec and keep waiting for the natural scheduler.
