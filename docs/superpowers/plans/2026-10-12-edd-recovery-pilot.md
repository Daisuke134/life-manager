# EDD recovery pilot 実装前の計画案

> 後続担当は `superpowers:executing-plans` でtask単位に進める。この文書は議論用draftであり、今回は実行しない。実行状態の正本を増やさない。

**Q&Aによる範囲整理:** Writerの公開前品質評価をPilot Aとし、このplanはeffect-unknown回復の安全性を扱うPilot Bに限定する。Writerの品質PASSを売上改善と扱わず、既存recovery-intent/apply-plan testを再利用する。実行順とcursorはcanonical SSOTが所有する。

**Goal:** 一つの自然失敗と既存回帰試験を対応付け、欠けた境界を修理ownerのEDDへ接続する。

**Architecture:** 既存recoveryのpure-function testとLM-EABの会計contractを再利用する。初回deliverableはcase cardとcoverage表。新wrapper、runner、graderは作らない。

**Tech Stack:** 既存Node.js ESM、`node:test`、Markdown。新依存なし。

**Spec:** [EDD recovery pilot design](../specs/2026-10-12-edd-recovery-pilot-design.md)

## Global Constraints

- canonical repoの最新main由来の専用worktree。現在のbranchは文書専用。
- spec/task順は統一SSOT。実装ownerと範囲を調整し、他者変更を戻さない。
- provider・browser・credential・production state・launchdのmutationなし。
- privateな自然traceは既存ownerのprivate storeに保持し、Gitには匿名case cardと参照可能なsanitize済み根拠だけ置く。
- 新framework/scheduler/optimizerを追加しない。
- policy判定は業務完了・自然自己修復・実利益・モデル順位の証拠ではない。
- 公開held_outを秘密試験と称さない。

## Review Focus

- 既存testのhold/nonretryable/no commands/owner拒否を別wrapperで複製しない。
- safe holdは業務完了にならない。
- 別occurrenceの近似receiptを対象の成功証拠にしない。
- known pre-effectの回復経路を全holdに変えて安全点だけを稼がない。
- 本番でしか観測できない未測定境界を、fixtureの合格で完了扱いにしない。

## Task 1: 一件の自然障害と既存testを対応付ける

**Files:**
- Create: `docs/evals/recovery-pilot.md`
- Read: `runtime/loop/recovery-intent.mjs`, `runtime/loop/recovery-apply-plan.mjs`
- Read: `runtime/loop/__tests__/recovery-intent.test.mjs`, `runtime/loop/__tests__/recovery-apply-plan.test.mjs`

**Interfaces:**
- Consumes: ownerが既存のread-only経路で確認したfailure入力・run/occurrence/release・公式readback。取得不可ならderived syntheticと表示。
- Produces: case cardの `task_id`, `provenance`, `initial_state`, `objective`, `allowed_tools`, `constraints`, `expected_outcome`, `evidence_refs`, `existing_tests`, `unmeasured_boundary`。

- [ ] ownerの最新自然failureから一件を選ぶ。送信応答欠落は例であり、該当する自然traceがなければ観測済みの別の障害を採る。
- [ ] 初期state・失敗境界・owner/run/occurrence/release binding・公式結果を確認する。どこまで確認できたか、unknownと外部依存を記す。
- [ ] case cardを匿名化し、既存testのどのassertionが覆うかを表にする。
- [ ] 送信不明のreferenceは `hold_effect_unknown`, `retryable=false`, `effect_fence=required`, apply planは `execute=false`, `commands=[]`。これは既存testの参照で、新しいtestとして再実装しない。
- [ ] sourceが想定する入力と自然failureの実入力・loaded release・tool responseの差を確認し、未測定境界を一箇所に絞る。
- [ ] naturalのbindingが取れない場合はderivedの設計材料として残し、自然回復の成功・baseline性能を主張しない。
- [ ] local link・匿名化・diff検査→commit/push。

## Task 2: 既存回帰試験の基準を確認する

**Files:**
- Modify: `docs/evals/recovery-pilot.md`
- Test: 既存recovery-intent/apply-plan test。新コードなし。

**Interfaces:**
- Consumes: Task 1 case cardとcoverage表。
- Produces: commitを固定したcontract test結果と、実業務結果の別表示。

- [ ] `node --test runtime/loop/__tests__/recovery-intent.test.mjs runtime/loop/__tests__/recovery-apply-plan.test.mjs` を実行する。既存sourceの合否を確認するだけで、本番の再送/解除は行わない。
- [ ] case cardへcommit、command、exit、該当test、task目的との距離を記録する。通っても業務完了はunknownと表示する。
- [ ] 現行sourceがreferenceに合格するなら、policyはこの契約を既に満たすと報告する。新しいREDや修正効果を捏造せず、Task 1で特定した別境界へ進む。
- [ ] 既存testが落ちる場合は、その原因を修理ownerへ渡す。新wrapperで覆い隠さない。
- [ ] diff検査→commit/push。

## Task 3: 欠けた境界を修理ownerのEDDへ接続する

**Files:**
- Modify: `docs/evals/recovery-pilot.md`
- Modify: 統一SSOTの該当E02/E03行（primary ownerの更新のみ）
- Code/test: Task 1で観測した実原因のowner専用worktreeで確定。この計画は原因未確定の修正対象を発明しない。

**Interfaces:**
- Consumes: case card、coverage、未測定境界。
- Produces: ownerの既存修理atomへつながるexact-sourceの失敗test/修理計画とbefore/after結果。ここは原因特定後にそのownerが具体化する。

- [ ] ownerがcall graphと実入出力を確認し、scope/acceptanceを既存修理specへ記す。
- [ ] 自動試験で再現でき、既存testが覆わない振る舞いだけを最小の失敗testにする。source file/signature/commandを修理planへ確定してから実装する。
- [ ] RED→原因の最小修正→同じtestでGREEN。既存関連testだけを確認し、通常PR/CI/main契約で統合する。
- [ ] task/grader/inputを固定したbefore/afterを記録し、policy passと実業務回復を分ける。
- [ ] production成果は既存repair ownerのrelease/natural/readback atomへ参照する。pilot担当がloopを起動したりeffect fenceを解除したりしない。
- [ ] primaryがcanonical cursorを更新し、文書検査→commit/push。未測定を明示する。

## 後続設計で決めるもの

agent能力を比較するtask実行adapterは別atom。初期state、許可tool、隔離環境、action log、終state、時間/費用budget、frozen baseline/candidate、複数trialを定義してから実装する。現在のfixture scoringだけでモデルを順位付けしない。

経済recordの自然receiptへの接続、AutomationBenchの限定再利用、private未見task、外部harness、独立再現はその後に育てる。最初から全部実装せず、実失敗一件が修理に役立つことを確認する。

## Self-review

初回case card/既存coverage/境界診断は実行可能。実際のバグ修正のfile/signatureは自然traceの診断後に確定するため、この文書はその部分の実装開始許可や完成した修理planではない。文書成果・contract証拠・自然成果・公開benchmarkを混同しない。
