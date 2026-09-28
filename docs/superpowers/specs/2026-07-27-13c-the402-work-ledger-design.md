# 13c-WORK — The402 work revenue classification

## Goal

`done="The402 の公募仕事による外部 USDC 着金だけが x402_work として Life Manager の既存 earnings ledger に一度だけ記帳され、直接購入は x402_sale のまま、曖昧な provenance は記帳されない"`

## Observed production state

- `ai.anicca.x402-acquisition-controller`、`ai.anicca.the402-provider`、`ai.anicca.the402-worker` は launchd で稼働中。
- 公開案件を取得し、適合案件へ自動入札し、採用時の `job_dispatch` を durable SQLite inbox に保存し、成果物を生成して callback に `completed` を送る経路は実装済み。
- 2026-07-27 の実測では過去の実入札 2 件は期限切れ、現在の open postings / jobs / threads / settled / held / pending はすべて 0。
- したがって今回証明できるのは分類・記帳経路の生存までで、実仕事収益は外部採用と着金が起きるまで未実証。

## Current read-only refresh (2026-09-28)

- The402 postings API returned HTTP `200` with `0` total postings, `0` open postings, and `0` eligible postings.
- The local durable inbox contained `3` completed jobs, `0` pending jobs, and `0` dead jobs; no acquisition-action log was present.
- No bid, job dispatch, callback, or external message was sent during this refresh. The work-revenue path remains unproven for current-period cash, and the next safe probe is another read-only API check when an open eligible posting exists.

## Primary sources

- the402.ai OpenAPI: <https://api.the402.ai/openapi.json>
  - `"Post a work request for AI agents to bid on"`
  - `"Bid on a request (any registered provider; max budget scales with verification tier)"`
  - `"List your jobs (API key)"`
  - `"Provider earnings summary (API key)"`
- x402 specification: <https://github.com/coinbase/x402/blob/main/specs/x402-specification-v2.md>
  - 支払証拠とアプリケーション上の注文・仕事 provenance は別の境界として検証する。
- Base JSON-RPC finalized block behavior: <https://docs.base.org/base-chain/quickstart/connecting-to-base>
  - 既存 13c-SELL bridge と同じ Base mainnet finalized receipt 検証を再利用する。

## Decision

The402 の external-inflow row を金額だけで WORK と推測しない。記帳直前に provider earnings と jobs を取得し、次をすべて満たす一意な組だけを `x402_work` にする。

1. settlement ID、transaction hash、USDC atomic amount、service/offer ID が verified inflow row と一致する。
2. settlement に `job_id` または `posting_id` がある。
3. jobs 側に同じ job/posting があり、service ID が一致する。
4. settlement と job の双方が completed / settled / released の終端状態にある。

settlement が一致して仕事参照を持たない場合だけ `x402_sale` とする。API失敗、0件、複数一致、ID不一致は `provenance_rejected` として何も記帳しない。

## Accounting invariant

- SELL と WORK は同じ `entry_key = x402:<tx>:income` を使う。同一着金を rail 別に二重計上できない。
- WORK row は `source=x402_work`、`meta.recipe=work`、`job_id` / `posting_id` を持つ。
- SELL row は既存の `source=x402_sale` を維持する。
- Base chain、owned payTo、external payer、exact atomic amount、finalized receipt の既存検証は弱めない。
- sub-cent 着金は証拠には残るが cent ledger へ丸めない。

## Production flow

```text
The402 postings
  -> acquisition controller
  -> bid
  -> job_dispatch webhook
  -> durable inbox
  -> local worker
  -> completed delivery
  -> provider earnings settlement
  -> finalized Base USDC external-inflow
  -> earnings + jobs provenance join
       work match   -> x402_work
       direct match -> x402_sale
       ambiguous    -> no ledger write
  -> lm_agent_earnings
```

## Verification

- Pure classifier tests cover WORK, direct SELL, ambiguity, mismatched tx/amount/service, and non-terminal jobs.
- Bridge tests prove a work row delegates once and preserves the shared deterministic entry key.
- Focused earnings/x402 suite passes.
- Production launchd is kicked; current zero-market run must exit 0 and report zero without claiming revenue.
