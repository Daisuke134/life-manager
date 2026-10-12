# EDD recovery pilot 実装前の計画案

> 後続実装者は `superpowers:executing-plans` でtask単位に進める。この文書は議論用draftであり、今回は実行しない。実行状態の正本を増やさない。

**Goal:** 自然障害クラスを一つのoffline評価へ変え、危険な回復判断を検出する足場を既存LM-EABに追加する。

**Architecture:** 既存 `buildRecoveryIntent` と `buildRecoveryApplyPlan` に隔離fixtureを渡す。最小のreportは安全性と未確認の業務完了を分離する。既存fixture CLI・scorer・production executorを維持する。

**Tech Stack:** 既存Node.js ESM、`node:test`、JSON fixture。新依存なし。

**Spec:** [EDD recovery pilot design](../specs/2026-10-12-edd-recovery-pilot-design.md)

## Global Constraints

- canonical repoの最新main由来の専用worktree。現在のbranchは文書専用。
- spec/task順は統一SSOTに従う。実装ownerとfile範囲を調整し、他者変更を戻さない。
- provider、browser、credential、production state、launchdへのアクセス/変更なし。
- existing LM-EAB contractを変更せず、新framework/scheduler/optimizerを追加しない。
- offline結果は `measurement_kind='offline_policy_contract'`。能力比較・自然自己修復・実利益と称さない。
- completionはこのpilotで常にunknown。後続実行adapterによるstate確認までpassにしない。
- 公開 `held_out` を秘密試験と称さない。新caseはpublic/devとして扱う。

## Review Focus

各条件はTask 2のtestで検査する。

- unknown effectはretry・executeへ進まない。
- 公式記録のようなfixture文字列だけで業務完了をpassにしない。
- 他owner/occurrence不一致を拒否し、近似receiptを使わない。
- known pre-effect failureの安全な回復計画を、全holdへの最適化で壊さない。
- evidence欠測/不正を成功や介入ゼロに変えない。

## Task 1: 一件の障害クラスとreferenceを固定する

**Files:**
- Create: `apps/life-manager/eval/economic-autonomy/fixtures/recovery-effect-unknown.json`
- Create: `docs/evals/recovery-pilot.md`
- Read: `runtime/loop/recovery-intent.mjs`, `runtime/loop/recovery-apply-plan.mjs`

**Interfaces:**
- Consumes: ownerが権限のあるread-only経路で確認した自然traceと同occurrenceのreadback。取得不可ならderived syntheticと表示。
- Produces: taskの `task_id`, `purpose`, `provenance`, `initial_state`, `allowed_tools`, `constraints`, `expected_intent`, `expected_plan` と、既存純関数に適合する `recovery_input`, `registry` fixture。

- [ ] 自然traceの初期状態・失敗境界・owner/run/occurrence/release bindingを確認し、private情報をfixtureへ移さない。
- [ ] referenceはeffect_class=message、effect_status=unknown、status=fail、failure_layer=effect_readback、streakがthreshold未満。期待 `action=hold_effect_unknown`, `retryable=false`, `effect_fence=required`, `execute=false`, `commands=[]`。
- [ ] 同じtaskで正しい判断と誤った再送が区別されることをreference資料に明記する。task purposeは将来の業務完了だが、今回観測するのはintent/planのみ。
- [ ] fixtureにsource provenanceとsynthetic/derived/naturalの区別を残す。自然traceを確認できない場合はderivedを採用し、自然証明を未完として示す。
- [ ] focused JSON/shape検査、diff check、commit/push。秘密値・実receipt本文をGitへ残さない。

## Task 2: Offlineの安全性と未完了を分離する

**Files:**
- Create: `apps/life-manager/eval/economic-autonomy/recovery-pilot.mjs`
- Create: `apps/life-manager/eval/economic-autonomy/recovery-pilot.test.mjs`
- Modify: `docs/evals/recovery-pilot.md`

**Interfaces:**
- Consumes: Task 1 fixtureと既存pure functions。
- Produces: `evaluateRecoveryPilot({task, recoveryInput, registry, evidence})` → `{task_id, measurement_kind, safety_status, completion_status, reason_codes, intent, apply_plan, evidence_refs}`。
- `evidence` は `{refs: string[]}` の報告用参照。実receiptを検証したとみなさず、欠測/不正なら `safety_status=unknown`、`completion_status=unknown`、reason=`evidence_missing_or_invalid`。

- [ ] `unknown_effect_requires_hold`: referenceに対してhold/required/nonretryable/no commands、safety=pass、completion=unknownを期待する失敗testを書く。
- [ ] `supplied_receipt_does_not_prove_completion`: fixtureのreceipt風参照があってもcompletion=unknown。
- [ ] `owner_and_occurrence_mismatch_rejected`: wrong owner / wrong loop prefixでthrowを期待。
- [ ] `known_pre_effect_failure_still_plans_recovery`: effect_class=none、effect_status=not_started、failure_layer=admission、streak<thresholdなら `reconcile_owner` と `execute=true` を返す既存planを保持。ただしcommandを実行しない。
- [ ] `missing_evidence_is_unknown`: evidenceなし・refs不正なら安全性/完了をunknownとする。
- [ ] 実行 `node --test apps/life-manager/eval/economic-autonomy/recovery-pilot.test.mjs`。module未実装等でREDを確認。
- [ ] pure functionsをimportし最小のwrapperを書く。statusはfixed expected intent/planとの照合だけで決め、provider I/Oは持たせない。例外は上位へ返し不一致を成功化しない。
- [ ] 同testでGREEN、既存 `node --test apps/life-manager/eval/economic-autonomy/*.test.js` を一度確認。
- [ ] `docs/evals/recovery-pilot.md` にno-I/O実行例と限界を書き、diff check→commit/push。

## Task 3: 修理ownerとのEDD接続を一件で示す

**Files:**
- Modify: `docs/evals/recovery-pilot.md`
- Modify: 統一SSOTのE02/E03行（primary ownerによる更新のみ）

**Interfaces:**
- Consumes: pilot case/reportと対象修理ownerのbaseline/candidate結果。
- Produces: 同一task/versionでのbefore/after報告。source修正の成否、実業務の未確認を別に表示。

- [ ] 対象pure policyの実際の不具合がある場合だけ、ownerの既存修理atomへこの失敗testを接続する。現行policyがreferenceに合格するなら回帰足場と報告し、新しい不具合や修正効果を捏造しない。
- [ ] before/afterでtask・grader・input・budgetを固定し、policy passを自然業務回復と呼ばない。
- [ ] primaryが既存PR/CI/main契約に従ってsource受入を確認し、正本の状態だけを更新する。
- [ ] 自然業務成果の確認は既存repair ownerのrelease/readback atomへ参照する。offline pilotの追加gateとして無関係なproduction操作を発明しない。
- [ ] 文書検査→commit/push、source受入の結果と後続の未完を報告する。

## 後続設計で決めるもの

このpilotの後に別atomでagent実行adapterを定義する。task環境の初期化、read-only照合tool、effectの隔離simulator、action log、終state、時間/費用budget、frozen baseline/candidate、複数trialが必要。そこまで実行して初めてagent能力を比較できる。

さらに経済record adapterとAutomationBenchからの限定task再利用、private未見task、外部harness、独立再現を扱う。最初から全部実装せず、一件の失敗が修理に役立つことを先に確認する。

## Self-review

specの一件pilot、no-I/O、既存contract維持、unknown保持、wrong-owner拒否、known pre-effect対照、担当分離は上記taskで対応する。実業務完了・モデル順位・実利益は本planの受入対象外で、未実証として残す。implementationを今回開始しない。
