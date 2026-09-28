# 無人投資収益ループ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 投資loopを人間の手動wakeなしで動かし、公式provider receiptから全コスト控除後のrealized net P&Lを測定し、正の証拠がある時だけ一段ずつ資本を増やす。`$10,000/month`は予測ではなく、rolling 30-day official net receiptで初めて達成とする。

**Architecture:** Alpaca、Hyperliquid、Solanaはそれぞれのeffect ownerを維持する。`investment-core`は注文・署名・送金をせず、各ownerの公式状態をcanonical `VenueSnapshot`へ変換し、fee/funding/borrow/slippage/gas/model costを一度だけ控除してreportする。Life Manager runtimeがregistry、cadence、release/apply、runtime executionを所有し、このlaneは投資コード・read-only evidence spine・投資仕様を所有する。

**Tech Stack:** Python 3.14、stdlib `decimal`/`json`/`unittest`、既存のAlpaca official readback、Hyperliquid official `/info`、Solana RPC/Jupiter receipt、既存Telegram outbox、append-only state。

**Spec:**

- `docs/superpowers/plans/2026-09-28-investment-loop-generational-wealth.md`
- `docs/superpowers/plans/2026-09-27-cross-venue-capital-allocator-net-pnl.md`
- `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` §8-4
- `docs/superpowers/plans/2026-09-27-hyperliquid-carry-live-loop.md`
- `docs/superpowers/plans/2026-09-27-solana-memecoin-copy-trading.md`

## Global Constraints

- `$10,000/month`に数えるのは、fee、funding/borrow、slippage、gas、model cost控除後の公式realized net P&Lだけ。deposit、unrealized P&L、paper結果、fixture、顧客売上は投資利益ではない。
- 現在のAlpaca capは`$100`、最大損失は一取引`$10`、日次loss haltは`$20`。30往復と正のcost-complete net P&Lなしにcapを上げない。
- Hyperliquidはleg cap`$25`、delta-neutral一ポジション、日次loss cap`5%`、drawdown cap`20%`。口座残高0の現在、Binanceから送金しない。
- Solanaはread-only scout → paper → exactly one `$2.00` canary、累積`$3.00` ceiling。先行venueの再現可能なpositive netなしにcanaryを開けない。
- `unknown`、`effect_unknown`、cost欠損、重複receipt、delivery uncertainはゼロや成功に変換せずhold/blockする。
- productionのmanual wake、manual restart、fabricated receipt、duplicate schedulerを進捗と数えない。
- このlaneは他agentのworktree、Capafy、PromptBaseを変更しない。Life Manager runtimeのregistry/apply/host制御は専用runtime手順で扱い、投資laneから別のagentへ依頼する設計にはしない。
- owner wallet/口座から外部へ資金を出す操作、Binance transfer、wallet creation、signed orderはこの計画では実行しない。

## Wealth architecture and money target

The long-run plan uses a diversified core plus capped experimental sleeves: 90% core wealth account (Japanese NISA/regulated brokerage), 5% measured Alpaca trading, 3% Hyperliquid only after read-only/shadow proof, and 2% Solana/meme-coin experiments only after a prior venue is positive. This is a future allocation rule, not current funding authorization; the existing `$100`/`$25`/`$2` caps remain stricter.

`$10,000/month` is not an expected platform yield. At hypothetical net monthly returns of 2%, 5%, and 10%, the arithmetic capital requirements are `$500,000`, `$200,000`, and `$100,000`, respectively; the plan assumes none of those returns. A `$100` cap cannot rationally be reported as `$10,000/month`.

For generational wealth, the compounding target is explicit: at a hypothetical 8% annual nominal return, monthly contributions are approximately `$671` for `$1M` in 30 years, `$3,355` for `$5M`, or `$6,710` for `$10M`. These figures are illustrations, not forecasts or guarantees.

## Review Focus

- deferred wakeがtrade sampleに化ける: `1,047` wakeは往復数ではなく、official completed round tripだけを数える。
- cost欠損が利益に化ける: funding、gas、model costのどれかが欠けたvenueは`cost_unknown`/`partial`でallocation対象外にする。
- depositが利益に化ける: owner cash flowはP&Lと別列にし、正負どちらもnetへ加算しない。
- 同一receiptが二重計上される: venue間source ID、daily provider ID、cost evidenceの重複をblockする。
- 自動化が手動運用に戻る: natural wake、single writer、pre-effect journal、official readback、Telegram provider ID、replay-zeroを一組で確認する。

## Current truth (2026-09-28)

- Alpacaは公式net P&L`-$0.15`（realized`-$0.10`、unrealized`-$0.05`）、completed round trips`1/30`、capital expansion `false`。残り29回を手動で起こす段階ではない。
- Hyperliquidはofficial account value、withdrawable、positions、funding rows、non-funding rowsが0。これは「$0利益」ではなく、P&L receiptが無い状態。
- Solanaは`scout_unknown`、候補0、effectなし。live transaction receiptは無い。
- cross-venue daily receiptは0件。rolling 30-day netは`unknown/daily_receipt_missing`で、`$10,000` gapは数値化できない。
- Life Managerのregistryには`alpaca-investment-live`が登録され、cadenceは300秒、entrypointは`skills/alpaca-investment/run.py`、effect reconcileは`skills/alpaca-investment/effect_reconcile.py`。投資系registry entryとして確認できるのは現在これだけで、Hyperliquid/SolanaはまだLife Manager loopとして登録されていない。
- runtime stateの最新readbackは occurrence `alpaca-investment-live:18d98b3bac7bfd08-2993`、`host_admission_deferred:resource_capacity_busy`、exit `75`、`effect_status=unknown`、provider receiptなし。loaded releaseは旧版で、fleet doctorは`missing_entrypoints=[]`・`registry_entries=170`でpass。したがって「Life Managerがloopを登録している」は事実だが、「新しい投資境界で健全な無人運転」は未証明。branch側では投資loopのadmission契約を`9dbc773bff`で`revenue/revenue`へ修正済み。
- 投資の検証境界は `ba235e66c0` / `2b5ea444b7` / `b36def560a` までpush済み。ただしLife Managerのproduction releaseに載ったとは扱わない。
- 同read-only runtime readbackでは、registry契約（300秒、`skills/alpaca-investment/run.py`）は確認できるが、`selected-strategy.json`は存在せず、deterministic selectionは`NO_STRATEGY` / `validation_reports_missing`。LaunchAgentは`loaded-idle`で、現在releaseは`92f04c91fa594ae2209b2ff323fe9fdfa91e5b5e`（`~/loops/releases/20260929T011449-92f04c91`）。loaded release内にETF evaluator／selector／policy境界は無い。
- 最新runtime eventは occurrence `alpaca-investment-live:18d98b3bac7bfd08-2993` の`phase=report`、`last_terminal_result=blocked`、`error_class=host_admission_deferred:resource_capacity_busy`、`exit_code=75`、`next_action=retry_after_eligibility`。`provider_receipt_id`と`official_readback_ref`はnullで、これはP&L、往復、paper receiptの証拠ではない。現在の未完了条件は、branchの新admission契約を含むimmutable release handoffとprovider receiptである。
- 追加のbounded candidate screenでは、固定cost後にBTC/USDC・ETH/USDCの事前定義reversion/breakout/pullback候補がすべてholdout不合格となった。新しいStrategyCardは追加していない。
- **候補戦略の公式replay（2026-09-29）**: read-only Alpaca paper BTC/USDC 5分足は `6,855` bars（返却範囲 `2026-08-30T00:00:00Z`–`2026-09-28T15:30:00Z`、raw SHA-256 `283ca45e9b14e8573120b7a3d73bba8b51700878626097465f4349d66801c5a0`）。reversionはholdout `-$0.89` / 12 trades、trendは `-$0.08` / 1 tradeで、両方とも費用後holdoutと9点sensitivity gateに失敗した。これは口座P&Lではなく、StrategyCard選定を止める証拠である。
- **長期窓の公式replay（2026-09-29、read-only）**: 同じ固定costでBTC/USDC 5分足を2026-06-30T00:00:00Z〜2026-09-28T15:30:00Zまで105 bounded queriesで取得し、20,126 unique bars（canonical hash `1a00e5e02496e117419beceaf7626649d34f95d73c381fc4a916be4c97d7f713`）を検証した。reversionはholdout `-$2.18` / 29 trades、trendは `+$0.13` / 7 tradesだがsensitivity `0/9`で不成立。両方rejectedで、選択カード・追加資金・30往復サンプルの根拠にはならない。
- **研究候補の追加（2026-09-29、read-only）**: 別の株式daily momentum evaluatorをTDDで実装し、公式IEX split-adjusted barsの固定8 ETF universeを126/21で測定した。holdoutは`+$1.62` / 14 trades、9点gridは`9/9` positive・median`+$1.62`、片側25/50bp stressはpositive、100bpはnegative。standard reportは`decision=paper`、pure selectorは`selected`を返したが、`alpaca-etf-126d-momentum-v1`はresearch/runtime handoff段階で、daily ingestion・paper order・official receipt・live注文・追加資金には未接続である。
- **ETF pure policy boundary（2026-09-29、code-only）**: `skills/alpaca-investment/etf_policy.py` をTDDで追加し、completed-session boundary、future/duplicate/unsorted/missing history、effect fence、owner check、21-session exit、rank-change exitを固定した。focused `24/24`、Alpaca全体 `175/175`。これはselected state、daily provider ingestion、paper order、official receipt、account P&Lではない。
- **ETF selection/allocator boundary（2026-09-29、code-only）**: canonical ETF cardをrelease-pinned loaderへ追加し、pure policy dispatch、complete-daily-bars時のfixed ETF candidates、paper-only risk gate、live拒否、`us_equity` day/market order shapeを実装した。focused `21/21`、Alpaca全体`183/183`。temporary test state以外のselected state、production release、paper order、official receipt、account P&Lはまだ無い。
- **ETF daily ingestion boundary（2026-09-29、code-only）**: `read_etf_daily_bars()` とallocator snapshot integrationを追加し、Alpaca CLI `data multi-bars`のIEX/split/1Day契約、NY open-session除外、future/duplicate/missing拒否、127 common sessions、source hashを固定した。adapter `6/6`、full Alpaca `200/200`。公式paper read-only preflightも8銘柄・127 common sessions・source receipt 1件でPASSし、注文は0件。production release、paper order、official receipt、account P&Lはまだ無い。
- **ETF paper execution boundary（2026-09-29、pushed `faab25176a`）**: exact `$10.00` market/day `us_equity` order、fixed-universe/owner/strategy/client identity、typed live refusal、provider fill/account readback、foreign ownership rejection、effect-before-close callback、durable ownership、replay-zeroを実装した。execution focused `11/11`、full Alpaca `200/200`。これは実行可能なcode boundaryであり、paper orderを送った証拠やP&Lではない。Life Manager loaded releaseへのhandoffとnatural paper receiptが残る。

```mermaid
flowchart LR
    A["As-is\nAlpaca 1/30\nHL/Solana receiptなし"] --> B["Task 1\nfail-closed入口をcommit"]
    B --> C["Task 2\nLife Manager runtime health"]
    C --> D["Task 3\nnatural unattended run"]
    D --> E["Task 4\n公式reconcile + daily report"]
    E --> F["Task 5\nAlpaca残り29往復 + 30日receipt"]
    F --> G["Task 6\npositive net時だけ一段promotion"]
    G --> H["Task 7/8\nHL/Solanaを条件付き測定"]
    H --> I["Task 9\n30d net >= $10,000を検証"]
    I --> J["Task 10\nreserve・税・長期資産へ蓄積"]
```

## File map

- `apps/life-manager/investment-core/cross_venue_run.py`: canonical snapshotだけを読む有限entrypoint。credentials、signing、order、fundingを呼ばない。
- `apps/life-manager/investment-core/test_cross_venue_run.py`: entrypointのunknown、cost validation、idempotent delivery、CLI境界。
- `apps/life-manager/investment-core/cross_venue_reporter.py`: UTC daily aggregate、Telegram outbox、provider message ID、rolling replay。
- `apps/life-manager/investment-core/venue_receipts.py` / `portfolio_receipts.py` / `net_pnl.py`: canonical schema、全コスト控除、重複・unknown防止。
- `docs/superpowers/plans/2026-09-28-investment-loop-generational-wealth.md`: 全体の投資cursorとカテゴリ別accounting。
- `docs/superpowers/plans/2026-09-27-cross-venue-capital-allocator-net-pnl.md`: cross-venue acceptanceと30日data gate。
- `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`: 投資loopのSSOTとruntime ownership。

---

### Task 1: Fail-closed cross-venue entrypointを確定する

**Files:**

- Modify: `apps/life-manager/investment-core/cross_venue_run.py`
- Modify: `apps/life-manager/investment-core/test_cross_venue_run.py`
- Modify: `docs/superpowers/plans/2026-09-28-investment-loop-generational-wealth.md`

**Interfaces:**

- `parse_snapshot_spec(value: str) -> tuple[str, Path]`
- `build_readers(snapshot_specs: Iterable[str]) -> dict[str, Callable[[], Any]]`
- `run_once(*, snapshot_specs, state_dir, today, owner_cash_flow_path, available_capital_usd, send) -> dict[str, Any]`
- missing standard venue、malformed snapshot、missing cost、invalid owner cash flowはunknownのまま返す。

- [x] **Step 1: Write failing tests.** `test_reader_rejects_snapshot_with_missing_cost_before_aggregation`を追加し、canonical snapshotの`model_cost_usd`欠損が`cost_unknown`になることを固定する。
- [x] **Step 2: Run the focused test and observe RED.** `cd apps/life-manager/investment-core && python3 -m unittest test_cross_venue_run`で、入口が欠損costを受け入れる失敗を確認した。
- [x] **Step 3: Implement the minimum validation.** `VenueSnapshot.from_mapping()`と`validation_reason()`を入口で実行し、valid snapshotだけを`wake()`へ渡す。
- [x] **Step 4: Run verification.** `python3 -m unittest test_cross_venue_run`と`python3 -m unittest discover -s . -p 'test_*.py'`を実行し、期待値はそれぞれ`5/5`、`66/66`。
- [x] **Step 5: Commit and push.** `git fetch origin && git add ... && git commit -m "fix(investment): validate cross-venue snapshots before aggregation" && git push origin HEAD`を実行し、commit `3a4a6cacae` をprimary planとSSOTへ記録した。

### Task 2: Life Manager runtime healthを確認・修復する

**Files:**

- Do not modify: `config/loop-registry.json`, `runtime/loop`, `runtime/host`, `bin/`
- Modify after evidence: `docs/superpowers/plans/2026-09-28-investment-loop-generational-wealth.md`, `docs/superpowers/plans/2026-09-27-cross-venue-capital-allocator-net-pnl.md`, `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

**Interfaces:**

Life Managerのregistry/state receipt must expose `run_id`, `owner_id=alpaca-investment-live`, `occurrence_id`, `release_sha`, loaded entrypoint, cadence, state root, phase, command, `exit_code`, `effect`, official `readback`, `provider_receipt_id`, `evidence_refs`, `error_class`, `retryable`, and `next_action`.

- [ ] **Step 1: Verify the Life Manager contract.** Read the registry entry and current state; require the expected 300-second cadence, `skills/alpaca-investment/run.py`, effect reconcile, and a release containing the latest investment validation boundary. Read-only result: registry and fleet doctor pass, but loaded release `92f04c91fa594ae2209b2ff323fe9fdfa91e5b5e` at `/Users/anicca/loops/releases/20260929T011449-92f04c91` lacks `etf_momentum.py`, `strategy_selection.py`, and the ETF policy boundary; the LaunchAgent is `loaded-idle`. Hold as `strategy_release_missing`.
- [ ] **Step 2: Verify release/effect boundary.** Through the Life Manager runtime path, load the immutable release containing the ETF boundary and the new `revenue/revenue` admission contract, then verify single-writer/active-state evidence. Keep the cap at `$100` and do not manually wake the loop. Current read-only evidence is occurrence `alpaca-investment-live:18d98b3bac7bfd08-2993`, `host_admission_deferred:resource_capacity_busy`, exit `75`, `effect_status=unknown`, no provider-effect receipt, and no official readback. No restart, queue deletion, or runtime mutation was performed.
- [ ] **Step 3: Verify one natural Life Manager wake.** Require one terminal event with the expected release, single writer, pre-effect journal, official broker readback, durable state receipt, and Telegram delivery. A deferred, install-only, or typed hold is not a trade sample. No qualifying event exists in the current readback.
- [x] **Step 4: Update the three spec files.** Record the exact Life Manager event, release, blocker/readback, and whether the next task is natural P&L verification. The read-only result is recorded here, in the primary investment plan, and in the SSOT; Task 8 remains incomplete.

### Task 3: Prove one natural unattended runtime wake

**Files:**

- Read-only provider/runtime state owned by Life Manager runtime
- Modify only the three investment plan/spec files after evidence

**Acceptance:** one natural wake proves a single owner/writer, fixed release, pre-effect journal, official provider reconciliation, durable state receipt, and typed failure handling. No manual kick, restart, or duplicate scheduler is allowed in the evidence.

- [ ] **Step 1: Observe the Life Manager cadence, not a manual invocation.** Inspect the runtime event and state receipt by read-only means.
- [ ] **Step 2: Verify the event fields.** Require `run_id`, `owner_id`, `occurrence_id`, `release_sha`, loaded argv/env, phase, command, exit code, effect, readback, and next action.
- [ ] **Step 3: Verify financial truth.** Confirm official order/fill/account/cash readback and cost-complete P&L; `resource_capacity_busy`, `resource_effect_unknown`, stale release, or heartbeat/database failure must be typed hold/recovery, not a successful sample.
- [ ] **Step 4: Record pass/fail in the specs.** If it fails, fix the Life Manager/runtime or investment-code boundary; do not count the wake as one of the 29 samples.

### Task 4: Connect automatic cross-venue reporting to natural receipts

**Files:**

- Read-only source receipts from Alpaca, Hyperliquid, Solana, and owner cash-flow ledger
- Existing: `apps/life-manager/investment-core/cross_venue_run.py`, `cross_venue_reporter.py`, `rolling_measurement.py`
- Modify: `apps/life-manager/investment-core/README.md` and the three investment plan/spec files after evidence

**Acceptance:** one natural UTC report writes `cross-venue-YYYY-MM-DD.json`, delivers exactly one Telegram message through the outbox, stores the provider message ID, and makes a same-day replay without a second send. Missing inputs remain visible as unknown.

- [ ] **Step 1: Supply canonical snapshots from the Life Manager runtime.** Every venue snapshot must contain official `source_receipt_ids`, observed time, equity/free cash, gross P&L, all five cost fields, risk, and `measurement_status`.
- [x] **Step 2: Run the existing reporter tests.** `python3 -m unittest test_venue_snapshot test_net_pnl test_cross_venue_reporter test_cross_venue_run test_rolling_measurement` passed `27/27` at candidate `0696a45558`; `git diff --check` passed. This proves the pure reporter boundary only; it does not create a natural daily receipt, Telegram provider ID, or P&L.
- [ ] **Step 3: Verify one natural delivered receipt.** Require `status=delivered`, a provider message ID, unique event key, and `measurement_status` that truthfully reflects missing/partial sources.
- [ ] **Step 4: Verify replay-zero.** Read the same UTC day twice and prove no second Telegram provider ID or duplicate daily file was created.

### Task 5: Accumulate the Alpaca sample without babysitting

**Files:**

- Read-only: `~/.local/state/life-manager/alpaca-investment-live/performance-latest.json`, official receipt ledger, account/order/fill/fee readbacks
- Modify: investment plan/spec files only after each verified milestone

**Acceptance:** completed round trips reach `30/30` through natural owner wakes, every round trip has official provider evidence, all costs are known, net P&L is positive, risk caps never breach, and `capital_expansion_allowed` remains false until explicit promotion.

- [ ] **Step 1: Keep cap at `$100`.** No transfer and no cap increase while the gate is incomplete.
- [ ] **Step 2: Let natural wakes generate the remaining `29` round trips.** Do not manufacture samples from wake count, paper receipts, fixtures, or manual runs.
- [ ] **Step 3: After each official performance receipt, verify** realized net, fees, slippage, model cost, source IDs, round-trip count, drawdown, and owner cash flow separately.
- [ ] **Step 4: Stop and hold on any negative/unknown/effect-unknown result.** Update the exact blocker and next owner action in the specs.

### Task 6: Execute one-step promotion only after the deterministic gate

**Files:**

- Existing: `apps/life-manager/investment-core/capital_ladder.py`, `performance_gate.py`, `cross_venue_allocator.py`
- Modify: investment plan/spec files after authorized evidence

- [x] **Step 1: Run the pure promotion gate** with the current official receipt IDs and requested next cap. It returned `status=reject`, `capital_expansion_allowed=false`, current cap `$100`, next cap `$1,000`, with reasons `net_non_positive`, `sample_insufficient`, `cost_unknown`, `drawdown_unknown`, and `venue_unhealthy`.
- [ ] **Step 2: Require an explicit Life Manager owner promotion receipt.** Telegram text cannot authorize cap, leverage, destination, or funding changes.
- [ ] **Step 3: Promote exactly one cap step or hold.** Record before/after cap, evidence IDs, decision, and rollback condition.
- [ ] **Step 4: Verify the next natural run** uses the promoted release and remains inside the new cap. If not, rollback/hold through the owner path.

### Task 7: Measure Hyperliquid only after the system and funding gates

**Files:**

- Existing: `skills/earn/hyperliquid-carry/{run.py,ledger.py,market.py,execute.py}`
- Modify: `docs/superpowers/plans/2026-09-27-hyperliquid-carry-live-loop.md` and investment SSOT after evidence

- [ ] **Step 1: Keep current wallet/read-only boundary.** No Binance transfer, wallet creation, or signed action in this task.
- [ ] **Step 2: After explicit owner funding/admission only, keep leg cap at `$25`.** Reconcile official spot/perp state after every effect.
- [ ] **Step 3: Accumulate `14` daily cost-complete net receipts.** Funding, trading fees, slippage, model cost, and account-equity changes must be separately attributable.
- [ ] **Step 4: Promote only if the measured net is positive and risk gates pass.** Expected APR or market funding quote is not realized P&L.

### Task 8: Keep Solana canary closed until a prior venue is reproducibly positive

**Files:**

- Existing: `skills/earn/solana-memecoin-copytrade/{run.mjs,journal.mjs,receipt.mjs,policy.mjs}`
- Modify: `docs/superpowers/plans/2026-09-27-solana-memecoin-copy-trading.md` and investment SSOT after evidence

- [ ] **Step 1: Continue read-only scout/paper evidence.** `scout_unknown`, no candidates, or missing RPC evidence is hold.
- [ ] **Step 2: Require prior positive venue net and explicit owner-funded runtime receipt.** No canary based on forecast or market demand.
- [ ] **Step 3: Run exactly one `$2` canary under the cumulative `$3` ceiling** only when both mode gates are satisfied.
- [ ] **Step 4: Verify transaction signature, token deltas, owner, mint, lamport fee, and final balance.** Any mismatch is `effect_unknown` and blocks retry.

### Task 9: Verify the `$10,000/month` target honestly

**Files:**

- Existing: `apps/life-manager/investment-core/rolling_measurement.py`, `cross_venue_reporter.py`, treasury receipt adapters
- Modify: investment primary plan and SSOT

- [ ] **Step 1: Require 30 inclusive UTC daily receipts** with delivered provider IDs, measured aggregates, explicit owner cash flow, unique source IDs, and no malformed/partial day.
- [ ] **Step 2: Claim success only when official rolling `net_pnl_usd >= 10000`.** Until then `target_gap_usd` is unknown or a measured positive gap.
- [ ] **Step 3: Keep investment P&L separate from customer revenue, Capafy, PromptBase, and USDC-only cash.** No cross-category arithmetic.
- [ ] **Step 4: Record the truth in Telegram and the SSOT.** No projected APR, capital multiple, or fixture substitutes for the official receipt.

### Task 10: Convert verified surplus into generational wealth

**Files:**

- Existing treasury and financial-record adapters under `apps/life-manager/investment-core/`
- Modify: investment primary plan and SSOT after verified surplus exists

- [ ] **Step 1: Record settled net cash separately from owner deposits and unrealized value.**
- [ ] **Step 2: Allocate tax reserve, emergency reserve, and operating reserve before reinvestment.**
- [ ] **Step 3: Add explicit long-term contribution receipts and diversified asset buckets.** Trading capital is not the whole wealth plan.
- [ ] **Step 4: Reconcile monthly net worth and cash receipts.** Do not call generational wealth achieved from a trading target alone.

## Execution order and next cursor

The actual execution order is `① Life Manager runtime health (NO_TRADE-safe) → ② release-pinned ETF selected state and immutable release handoff → ③ natural Alpaca paper order/fill/account receipt → ④ official cost-complete P&L/report → ⑤ conditional 30-round-trip sample gate → ⑥ one-step promotion → ⑦ Hyperliquid read-only/shadow → ⑧ Solana read-only/paper → ⑨ tiny canary only after positive evidence → ⑩ rolling $10k verification → ⑪ settled-surplus wealth ledger`. The BTC cards fail the current validation gate; the ETF code boundary is now tested and pushed, and clean investment-only candidate `5415939083` is ready for owner-path release handoff, but there is still no loaded release, selected production state, natural paper receipt, or account P&L. Steps ③–⑪ remain closed.

The finite cross-venue code task is complete at `3a4a6cacae`, the validation-boundary commits are `ba235e66c0` / `2b5ea444b7`, the paper ETF execution boundary is pushed at `faab25176a`, and the investment admission-contract fix is pushed at `9dbc773bff`. A clean investment-only candidate based on old `origin/main` `d0a2f91635` is pushed at `5415939083`; its Alpaca `200/200`, investment-core `101/101`, registry `124/124`, loop-contract `9/9`, runtime/loop `669/669`, and adapter `15/15` checks pass. The candidate/source doctor is `ok=true` with `registry_entries=170`, `missing_entrypoints=[]`, and `unmanaged_labels=[]`. External main/release movement has since advanced `origin/main` to `e0fd94a1a5` and production to `1105615058`, but that loaded release still lacks the ETF boundary and retains `borrow/support` investment admission. The repository-wide contract gate remains RED at Capafy `loops[12]` recovery-class mismatch; this lane will not edit Capafy. The immediate cursor is **refresh the investment candidate against current main, then owner-path promotion after the mandatory gate is green**. Latest occurrence `alpaca-investment-live:18d993ba15e0a1f0-96273` is a typed `resource_capacity_busy` defer with no provider receipt. The `29` number is conditional evidence collection, not a command to execute 29 trades.

**最新投資cursor（2026-09-29）**: candidateは`origin/main=8348587ac2`をmerge commit `97b821b9b7`で同期しpush済み。投資専用検証はAlpaca `200/200`、investment-core `101/101`、candidate doctor PASS。loaded releaseは`110561...`のままでinvestment rowは`borrow/support`、ETF/cross-venue未搭載。自然wake `18d99400582f1be0-5050`は`resource_capacity_busy`・exit `75`・provider receiptなし。全体contract gateはCapafy mismatchでREDのため、Capafyを変更せず、gate green後にLife Manager owner-path release handoff→自然paper receiptへ進む。

**最新main同期後のcursor（2026-09-29 04:54 JST）**: `origin/main=ce3a85cb49`はSSOT文書更新のみで、投資ファイルを保持したままmerge `c2bb9a4a11`をpush済み。全体contract gateはCapafy `loops[12]` mismatchでREDのまま。最新natural wake `18d9944687719400-16005`は`resource_fifo_wait`・exit `75`・provider receiptなし。次はgate green後のLife Manager owner-path release→natural paper receiptであり、手動wake・送金・cap増額はしない。

**Admission readback（2026-09-29 05:00 JST）**: production DBでは`alpaca-investment-live`が`agent` queue sequence `269435`、`borrow/support`、reservationなし、effect-unknown claimなし。queue総数は74件で、投資のstale claimではない。candidateの`revenue/revenue` admission契約を本番immutable releaseへ反映することが次の境界であり、DB直接変更や手動wakeはしない。

**最新natural wake（2026-09-29）**: `alpaca-investment-live:18d9948d01173300-25286`は`resource_capacity_busy`・exit `75`・provider receiptなしでeffect前にdefer。loaded releaseは`110561...`のままで、これはtrade/P&L/sampleではない。shared gate green後のowner-path releaseが次の一手。

**最新main同期（2026-09-29）**: `origin/main=20753ada4c`をmerge `84400303e7`で同期済み。変更はmarketingだけで投資ファイルは保持。contract gateはCapafy mismatchでRED、loaded investment rowは`borrow/support`のまま。次はgate green後のowner-path immutable releaseであり、他laneの実装は変更しない。

**再開runの最終audit（2026-09-29）**: candidate `e9b9a66b66`はAlpaca `200/200`、investment-core `101/101`、doctor PASS。shared gateは同じCapafy mismatch、productionは旧`borrow/support`、自然wakeはeffect前defer。candidate同期・根因診断・spec更新・検証は完了し、次の一手は外部gate green後のowner-path releaseのみ。

## Completion definition

This plan is complete only when Task 1–10 have their stated evidence. In particular, a green unit-test suite, a registered loop, a funded wallet, 29 wake attempts, or a positive fixture does not complete the plan. Completion requires healthy Life Manager natural operation, official cost-complete realized net P&L, the promotion receipts, the verified rolling `$10,000/month` result, and a separate settled-surplus wealth ledger.

**Ownership revalidation（2026-09-29）**: Life Manager is the runtime owner; this investment lane owns the candidate and its evidence. Candidate merge `7efcd1a13a` contains the latest `origin/main=5dfb1f84f6` while preserving the investment boundary. Production still loads the immutable release `20260929T052319-5dfb1f84`, so the remaining order is: candidate verification → shared contract gate green → Life Manager immutable release handoff → natural paper receipt → cost-complete P&L. Waiting for an imaginary owner is not a step; bypassing the shared gate or placing a live order is also not a step.

**Fresh candidate verification（2026-09-29）**: candidate `46eec8d617` is pushed and clean. Doctor passed with `170` registry entries and no missing/unmanaged labels; Alpaca tests passed `200/200`; investment-core tests passed `101/101`. The shared contract gate remains red on the pre-existing recovery-class mismatch, so the release handoff stays closed. This is a promotion gate, not a reason to invent 29 manual wakes or add capital.

**Task 4 pure-boundary verification（2026-09-29）**: the specified venue snapshot, net-P&L, reporter, cross-venue entrypoint, and rolling-measurement tests passed `27/27` at candidate `0696a45558`. No runtime state, provider receipt, or external effect was created; Task 4 Steps 1, 3, and 4 remain open until Life Manager supplies a natural delivered daily report and replay-zero evidence.

**Authoritative runtime recheck（2026-09-29）**: `lm-loop status alpaca-investment-live` identifies `owner=life-manager`, `launchd_state=loaded-idle`, loaded SHA `5dfb1f84…`, and the latest terminal occurrence as a typed `resource_capacity_busy` admission defer (`exit=75`, no provider or official readback). The loaded registry remains `borrow/support` without queued-release reconciliation, and the ETF/cross-venue runtime files are absent from that immutable release. The shared contract gate is still RED; Task 2 release handoff and Task 3 natural receipt therefore remain unchecked.

**Owner wording correction（2026-09-29）**: the investment-core README now names Life Manager runtime—not an undefined agent label—as the owner of argv/env, cadence, release, and provider acknowledgement. No runtime or provider state changed.

**Latest-main verification（2026-09-29）**: candidate merge `41bc8be6d3` includes `origin/main=b79275cfed`; doctor, Alpaca `200/200`, investment-core `101/101`, and cross-venue `27/27` pass. The repository-wide contract gate remains RED on the existing recovery-class mismatch, so immutable promotion and natural receipt remain open items. The worktree is clean after removing the test fixture.

**Shared-gate handoff（2026-09-29）**: sent the exact promotion-gate failure and investment candidate evidence through the registered `lm` agent channel to the shared-gate owner. This lane remains responsible for the investment candidate and will continue with immutable release handoff as soon as the gate is GREEN; it does not modify the gate owner’s code or request capital/order effects.

**External install readback（2026-09-29）**: Life Manager installed immutable release `b79275cfed5f61a01137e2105da0cf089873f8a2` (`20260929T073044-b79275cf`, install event PASS), but the release is still missing the investment ETF/cross-venue boundaries and retains `borrow/support` admission. The latest investment terminal event belongs to the previous SHA and is a capacity defer. Installation alone is not promotion, paper evidence, or P&L.

**Pure promotion-gate readback（2026-09-29）**: using the official performance state (`net_pnl_usd=-0.15`, `completed_round_trips=1`, cap `$100`) and its receipt IDs, `recommend_next_cap(..., requested_cap=1000)` returned `reject` with `capital_expansion_allowed=false`. This closes only Task 6 Step 1; no cap, wallet, order, or runtime state changed.

**Candidate/install boundary proof（2026-09-29）**: candidate `e35831019c` has the investment admission `revenue/revenue` with queued-release reconciliation and both ETF/cross-venue files; installed `b79275cfed` has `borrow/support` without reconciliation and lacks both files. The installed release is stale; this does not prove that the source-side unattended investment loop is finished.

**Scope correction（2026-09-29）**: “promotion gate” is not an external manager, agent, or prerequisite for investment worktree development. `skills/alpaca-investment/performance_gate.py` is a pure capital-cap recommendation, and `./bin/lm-loop-contract` is a repository-wide catalog check. Life Manager is the runtime manager; `alpaca-investment-live` is the investment loop owner. The current source cursor is to connect the tested `apps/life-manager/investment-core/cross_venue_run.py` to one Life Manager-owned investment wake/receipt path, test and push it, then perform the runtime handoff and natural paper receipt.

**Source-side connection completed（2026-09-29）**: the canonical Life Manager job ID is `investment-cross-venue-report`. `config/loop-registry.json` now declares the daily `86400`-second Python entrypoint `apps/life-manager/investment-core/cross_venue_run.py`, state root `~/.local/state/life-manager/investment-cross-venue`, and fixed manifest path `inputs.json`; `apps/life-manager/config/product-loop-catalog.json` maps it into the investment product beside `alpaca-investment-live`. The manifest boundary is fail-closed: missing/invalid input is explicitly recorded and cannot produce capital or profit. Verification passed with investment-core `105/105`, runtime-contract plus entrypoint tests `9/9`, JSON validation, and `git diff --check`. This completes source wiring only. The remaining evidence is the loaded Life Manager release, one natural paper/provider receipt, replay-zero, cost-complete P&L, and then the measured sample/rolling gates.

**Latest main synchronization and runtime readback（2026-09-29）**: candidate merge `5936108972` contains `origin/main=00cc2c9d1f`; the shared contract gate is green (`registry_jobs=171`, `errors=[]`) and candidate doctor is clean. The installed report job is still `unloaded`, with no occurrence/provider ID/daily receipt; the installed Alpaca owner is still on the older `f143cbaa…` release and its latest result is a typed admission defer. Task 4 source wiring is complete, but natural runtime evidence remains open.

**Alpaca owner-state adapter slice（2026-09-29）**: the daily report now accepts `--alpaca-state-dir` and, when no explicit Alpaca snapshot is supplied, reads the three durable owner files (`performance-latest.json`, `observation-latest.json`, `risk-latest.json`) through the read-only `alpaca_snapshot.py` adapter. Missing cost categories are preserved as unknown; the live readback is `partial` with gross `-$0.14`, fees `$0.01`, `9` source receipt IDs, and `1` completed round trip. Source verification passed: investment-core `108/108`, runtime fixture `2/2`, contract/entrypoint `9/9`, repository contract `ok=true` (`registry_jobs=171`), doctor `ok=true`, JSON validation, and `git diff --check`. This closes only the source-side Alpaca input bridge; installed release, natural provider receipt, replay-zero, and cost-complete P&L remain open.

**External runtime recheck after shared main fix（2026-09-29）**: the official status readback reports event release `00cc2c9d…`, installed release `c2e99f7…`, `alpaca-investment-live` `loaded-idle` with a natural terminal `pass` (`exit=0`), but no `provider_receipt_id` or `official_readback_ref`. `investment-cross-venue-report` is still `unloaded` with no occurrence/provider ID. Candidate `363d456f24` contains the source adapter and is pushed; it has not been installed, so this does not close the runtime handoff or natural P&L tasks.

**Latest main sync after shared fix（2026-09-29）**: candidate merge `3c890851d4` now contains `origin/main=c2e99f7327`; the main delta was writer/docs only, and the investment source boundary was preserved. Post-merge source verification passed: investment-core `108/108`, runtime `2/2`, contract/entrypoint `9/9`, shared contract `ok=true` (`registry_jobs=171`), doctor `ok=true`, JSON validation, and `git diff --check`. The installed report job remains unloaded and no official investment provider receipt exists.

**Manifest fail-closed correction（2026-09-29）**: fixed `--alpaca-state-dir` is now gated on `input_manifest_status=configured`; a missing or invalid manifest cannot accidentally turn durable Alpaca state into a daily venue measurement. The regression test was observed RED before the code change and GREEN after it (`test_cross_venue_run` `9/9`); full investment-core is `109/109`. Runtime `2/2`, contract/entrypoint `9/9`, shared contract `ok=true` (`registry_jobs=171`), doctor `ok=true`, JSON validation, and `git diff --check` pass.
