# Life Manager → Manager：実コードからの移行地図

調査日: 2026-10-02。これは親エージェントへの設計・実装計画入力であり、新しいSSOTではない。TODO・順序・状態は既存の `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` に統合する。

## 調査境界と証拠

- Git root: `/home/agent/Projects/life-manager-main/.worktrees/manager-pivot-20261002`
- common Git dir: `/home/agent/Projects/life-manager-main/.git`
- branch: `docs/manager-pivot-20261002`
- origin: `https://github.com/Daisuke134/life-manager.git`
- 読んだcommit: `539761d772e084b84fe2960d31f88df2c21a25d4`
- `AGENTS.md` と `skills/loop-development/SKILL.md` を読んだ。ソースは主に `git show HEAD:<path>` で参照。sparse checkoutのファイル有無を機能有無と取り違えていない。
- リポジトリ変更、テスト実行、production process・provider呼出し、認証情報・個人runtime stateの読取りはしていない。以下はソースの存在と仕様であり、本番稼働・収益・社会的改善の現在値を示さない。

## 製品契約の転換

Managerは一つの持続的なAI主体として、経済・社会・物理環境の構造を変更し、多数の人の可処分所得、健康、時間、アクセス、機会を改善する。受益者の氏名、アカウント、login、credential、signup、操作画面、email、Telegramを入口にしない。建物エネルギー管理を中心製品にしない。

既存の有限wake・永続cursor・単一ownerは維持できる。「一つの持続的主体」は一つの無期限processではなく、同じ `manager_id`・目的・構造介入台帳・学習状態を引き継ぐ有限wakeとして表現する。人ごとのagentを作らず、内部モデル呼出しも同じManagerの判断工程にする。

**継承するのはruntimeと証拠契約、変えるのは目的・作業単位・評価対象。** 個人のcalendarや口座を管理する仕事を匿名化しただけでは要件を満たさない。作業単位は `person/user/tenant` ではなく `environment/structure/intervention/cohort`。

## 既存境界：keep / adapt / legacy

| 境界 | 実際の関数・仕様 | 分類と移行方針 |
|---|---|---|
| `config/loop-registry.json` | schema_version=2、`loops` map。canonical lifecycle registry | keep。一つのruntimeと `bin/lm-loop` のままManager entrypointを追加。既存ownerを一斉rename/stopしない |
| `runtime/loop/macos_loop_registry.py` | `validate_registry`, `admission_effect_scope`, `render_job_models`, `loop_json_schema` | keep。新domain/effectを無根拠に追加しない。domain `system` + Manager専用schema内の領域を使える |
| `runtime/loop/runtime_event.py` | `validate_runtime_event`, `build_runtime_event`, `build_runtime_start_event`, `build_install_event`, `append_runtime_event`, `rotate_jsonl_locked` | keep。構造成果は別recordとして保存し `evidence_refs` で結ぶ。未知フィールドをeventへ差し込まない |
| `runtime/host/resource_admission.py` | `enqueue_durable`, `claim_durable`, `transfer_durable`, `heartbeat_durable`, `defer_durable`, `release_and_reserve`, `owner_deploy_lock` | keep。Managerも有限timeout、durable occurrence、lease、headroom、backoffを使う。別schedulerを作らない |
| 同host admissionの優先順位 | admission=`borrow/revenue`, priority=`critical_paid/revenue/support`, resource=`agent/browser/deterministic` | adaptは後段。社会的改善を売上扱いして `revenue` に便乗しない。初期は `borrow/support`。公益仕事のstarvationが観測された場合に共有policyを根拠付き変更 |
| `runtime/agent-runner/agent_runner.py` | `configured_task_classes`, `run`, `validate_schema`, `parse_contract_result`, `candidate_capabilities`, `emit_runtime_event`, `attach_runtime_event` | keep。既存provider routing・budget・evidence retentionを再利用。Manager専用task classを既存 `config.json` に追加するなら、loopからprovider/model/authを直指定しない |
| `apps/life-manager/eval/economic-autonomy/records.js` | `validateEpisode`, `validateAttribution`, `validateAutonomyEvent`, `validateCostCoverage`, `validateCase`, `validateRun`, `validateScore` | keep＋adapt。Manager自身の事業持続性評価として再利用可能。受益者の可処分所得・健康・時間の成果評価とは別 |
| 同 `score.js` | `scoreEconomicAutonomy` | keep。provider検証、外部顧客分類、実現利益、全cost coverage、duplicate・human credential failは有益。構造介入の社会的効果をこのscoreで代用しない |
| 同 `run.js` | `parseCasesText`, `evaluateCase`, `runCorpus` | keep。hash付きfixture、tuning/held_out、positive/negativeケースを模倣。これはfixture再生で、本番社会成果を証明しない |
| `apps/life-manager/lib/effect-reconciler.js` | `reconcileUnknownEffect(job,{adapter,store})` | keep境界＋adapt必要性を検討。tenant_id は受益者でなく実行主体の内部namespaceに対応可能。対象effectは publish/message/moneyだけ。他class対応は既存host readback境界を使うか、実消費者と試験を伴って共有関数を拡張 |
| `mental-outcome-ingest.js` | `signOutcomeEnvelope`, `verifyOutcomeEnvelope`, `persistVerifiedOutcome` | legacy製品契約。uid/company/role、interview/offer/rejection、Supabase個人成果table。署名・replay抑止・strict schemaの考え方を参照するが、Manager recordをここへ押し込まない |
| `mental-outcome.js` | `decideMentalOutcome` | legacy。verified outcomeを個人へのquote送信に変換する。健康改善の評価器ではない |
| `mental-outcome-runtime.js` | `handleVerifiedOutcome`, `runVerifiedOutcomes` | legacy。user.uid、user.telegram_chat_id、sendMessage、send logが前提。Manager実行・成果経路から外す |
| `mental-outcome-store.js` | `readOutcomeSendState`, `readVerifiedOutcomes`, `recordOutcomeSend` | legacy。uid単位のsend状態と個人成果取得をManagerの受益者モデルに再利用しない |
| `mental-outcome-http.js` | `ingestMentalOutcome` | legacy。個人成果ingress。新Managerは制度・環境の証拠入力を持ち、本人連絡を要求しない |
| `.agents/startup-context.json`, `scripts/startup-context/*.mjs` | 下記の強い旧製品前提あり | adapt。JSONの名称置換だけでは不十分。generator・validator・testsを同時に移行 |
| `export-openclaw.mjs` | 生成済みkitのexport、submitted history保護 | legacy配布経路。runtime依存にしない。維持するならManager target条件を調整し、過去提出物は変えない |

旧機能のlegacy指定は「Manager新経路に載せない」を意味し、productionをこの調査で停止・削除する意味ではない。運用移行はownerごとのpromotion contractで別途確認する。

## 共有schemaの正確な制約

### Registry

`macos_loop_registry.py:14` の必須row fieldsは `label, domain, entrypoint, cadence, effect_class, state_root, log_root, cleanup, provider_route`。rowは未知fieldとsecretらしいfield名を拒否する。

- loop ID: `[a-z0-9][a-z0-9-]*`。labelは `ai.anicca.` prefix、重複不可。
- domain: `physical, mental, financial, earn, growth, system`。
- effect_class: `none, publish, message, money, application, trade, account_mutation`。
- provider_route: `deterministic` または `shared-agent-runner`。
- entrypointはrepo相対、絶対path・`..`は禁止。
- cadenceは `start_interval_seconds/calendar_interval/run_at_load/keep_alive` の一つだけ。
- `adapter` と `command` は同時宣言。adapterは `exec/python`。
- `admission_effect_scope=occurrence` は入口allowlistが必要。初期Managerは既定のowner scopeを使う。
- `coalesce_queued_wakes=true` は `coalesce_reserved_wakes=true` を要求。
- `reconcile_queued_release` を宣言すると `resource_class/admission_class/priority` も必須。
- effect_reconcileはrepo相対argvと `occurrence_flag/resolve_flag/timeout_seconds`（最大1000秒）。

このほかProduct Loop構造gateは `./bin/lm-loop-contract`。新loopは `apps/life-manager/config/product-loop-catalog.json` のcanonical jobsとのjoinが必要。Manager機能を作るだけで別registryやinstallerを作らない。

### Runtime event

必須fields: `version,event_id,timestamp,loop_id,domain,run_id,phase,status,release_sha,provider,profile_alias,effect_class,effect_status,blocker,evidence_refs`。

`version=1`。phase=`plan/execute/reconcile/verify/report`、status=`running/pass/fail/blocked`、effect_status=`not_applicable/unknown/planned/started/verified/failed/reconciled`。evidence refsは最大32件、URI形式 `[a-z][a-z0-9+.-]*://[A-Za-z0-9._:/-]{1,512}`。任意診断fieldは一つでも入れると診断集合すべて必要。`occurrence_id` は `job_id:` prefix必須。秘密らしい内容・未知field拒否。

重要: `build_runtime_event(succeeded=True,effect_class!='none')` でも effect_status は **unknown** を生成する。exit=0、status=passは実行の成功であり、provider effectのverifiedでも、多人数への改善でもない。Managerは「変更のofficial readback」と「変更後の受益結果」を分けて保存する。

### Unknown effect

JS `reconcileUnknownEffect` は job.status=`reconciling` と effect_key を要求。adapter.inspectEffectへ tenantId/loopId/effectClass/effectKey/jobId/attempt を渡す。proof.state=`present/absent/unknown`。unknownは最大回数でdead_letter、再実行しない。present/absentにはreceipt object必須。

Python `resolve_unknown_occurrence(owner_id,occurrence_id,official_readback=...)` は exact owner/occurrence、verified=true、provider_receipt_id を要求。absence/inconclusiveは閉じず、再試行を許可しない。`resolve_pre_effect_occurrence` は proof_type=`pre_effect`、evidence_ref と no-dispatch証明専用。JSのabsent resolutionとPythonのunknown fenceを同一意味として統合しない。

### Agent runner

CLI必須: `--task-class`, `--prompt-file` または `--prompt-stdin`, `--schema`, `--evidence-dir`, `--task-label`。`--loop`, `--timeout-seconds`, `--read-only` 等を持つ。task classはconfigのkeysでchoicesが決まる。`application-intent-planner` 等はstdinのみ。新Manager plannerにはtool-less/read-onlyを **既存コードで確実に制御する必要がある**。class追加だけで既存plannerのbrowser-route除去や権限制限が自動継承されると仮定しない。

### Economic autonomy

episodeはexact keysを要求し、subject_id, track, currency, period_start/end, starting_capital_minor, spend_cap_minor, release_sha256, model, toolchain_sha256, policy_sha256を含む。track=`agent_native/one_shot_onboarding/simulation`。全hashは64桁hex、金額は整数minor units、期間はtimezone付き。

autonomy_event: actor_class=`life_manager/human/external_ai/provider`、credential_class=`none/agent_owned/one_shot_user/recurring_user`、event_kind=`bootstrap/human_intervention/credential_use/external_ai_intervention/external_effect/policy_violation`。`agent_native` は両user credentialを拒否。運営主体の既存provider権限と受益者のcredentialを区別できるが、氏名・signup・UI不使用やpopulation benefitは現在のschemaで検証されない。

scoreは settled_customer_revenue_minor/total_cost_minor/settled_net_profit_minor/self_fundedを持つ。fundraising/internal_transferは顧客売上・MRRの証明にしない。Manager revenueを受益者incomeと同一変数にしない。

## Startup contextを実際に変える範囲

`validateStartupContext` は schema_version=1、product.name、one_liner/mission/vision、company.legal_name（productと異なる）、exactly three organs、local/cloud delivery、founder_attested revenue（表示・scope・attested_at）、11項目application_answersを要求する。

`REQUIRED_LINKS=['product','repository','telegram']` は全てverified、URL、expected_text、verified_at、evidenceを必須にする。Managerの受益者にはTelegramを要求しないため、この強制は削除/optional legacy化し、link validatorとpublic allowlistも変更する。未検証のManager URLに過去Life Managerのverified証拠を流用しない。

claim topicsはmission/revenue/users/applications/agi。mission文一致とfounder revenue claim一致を強制。過去founder revenueはLife Manager由来の歴史的証拠としてscopeを保ち、Manager介入成果へ言い換えない。Managerのcoverageは登録users数でなくenvironment/cohort対象人口と観測・推計の根拠にする。

`contextDigest` はstable JSON SHA256、`validatePublicArtifact` はversion/digest、claim guards、秘密・電話/email・placeholder防止を検証。ここはkeep。

`build-kit.mjs` の `markdownArtifacts` は日本語answers、deck、one-pagerで個人管理・organs・Telegramを直書きしている。`buildApplicationKit` もtelegram assetを必須出力する。JSON renameだけでは旧製品説明が残る。全言語出力を意味的に更新し、生成kit・PDF receiptのdigest一致を再検証する。`audit.mjs` は `auditStartupContext` でネットワークreadbackを行うため、offline schema検証と分ける。

## 新しいコードの正確な所有path案

次は追加予定pathであり、存在・実装完了は主張しない。2実消費者ができるまでdomain kernelを `skills/_shared` に抽出しない。

- `loops/manager/README.md`: 目的、受益者接点ゼロ、運営権限と受益者認証の区別。
- `loops/manager/manager.py`: 既存lm-loopから呼ばれる有限wake入口。cursor読み込み、現時点でeligibleな一遷移、receipt保存、終了。
- `loops/manager/contracts.py`: strict record validation。匿名化個人profileを作るのではなくenvironment/cohort/structure/action/observationを作る。
- `loops/manager/schemas/structure.json`: environment_id, structure_id, domain, scope, authority_ref, baseline_refs, constraints, population_estimate, estimate_method。
- `loops/manager/schemas/intervention.json`: intervention_id, manager_id, structure_id, hypothesis, mechanism, alternatives, bounded_action, authority_ref, spend_cap, effect_class, effect_key, readback_contract, outcome_plan, next_eligible_at, status, evidence_refs。
- `loops/manager/schemas/outcome.json`: intervention_id, cohort_id（地域・集団のID）、measurement_window, metric, unit, baseline, observed, counterfactual_method, uncertainty, distribution, displacement_or_harm, source_refs, verification_status。個人ID・氏名・連絡先なし。
- `loops/manager/state_store.py`: 外部state rootのatomic cursor/learned world model/介入状態、同一owner lock下の更新。immutable releaseへstateを書かない。
- `loops/manager/observe.py`: public/operating-authorized environmental evidence取得、出所・観測時刻・対象範囲の記録。
- `loops/manager/plan.py`: shared agent-runnerへbounded read-only judgmentを渡し、schema validation済み候補を返す。
- `loops/manager/action_gate.py`: authority、effect allowance、spend、beneficiary-contact-zero、必要な観測、replay fenceのdeterministic gate。
- `loops/manager/provider_adapter.py`: 既存provider boundaryのloop-local bridge。provider-specific effect/readback実装は既存 `providers/<provider>/` に置く。新しいAPI client/認証managerをManager内に作らない。
- `loops/manager/evidence.py`: runtime occurrence・provider receipt・介入・population outcomeをjoin。provider verifiedとcausal outcome unknownを併記可能にする。
- `loops/manager/evaluate.py`: income/health/time/access/opportunityを別々に評価、coverage・分布・害・不確実性、持続性のfinance scoreと並置。
- `loops/manager/eval/cases.jsonl`, `loops/manager/eval/fixtures/*.json`, `loops/manager/tests/test_contracts.py`, `test_state_store.py`, `test_action_gate.py`, `test_cycle.py`, `test_evaluate.py`: offline corpus・再実行・失敗境界テスト。

registry初期row案: `manager-cycle`、domain=`system`、entrypoint=`loops/manager/manager.py`、adapter=`python`、command=`[]` または入口の有限wake引数、state/log root=`~/.local/state/life-manager/manager/...`、admission=`borrow/support`、resource=`agent`、finite runtime_timeout_seconds。read-only初期は effect_class=`none`。実effect有効化時は介入adapterの正しい既存effect_classを宣言し、official readback契約を追加する。「publish」宣言のままmoney/physical制御をこっそり実行しない。複数effectが必要なら共有runtime内の別job ownerに分割し、manager_id・介入ledger・目的を一つに保つ。人ごとのruntimeを作らない。

最初の構造介入はまだ選定されていない。共同調達、地域の無償アクセス改善、供給・配分・待ち時間の改善等を候補schemaで比較できるが、権限・実行可能性・対象人口・公式readback・結果観測が揃う一件を選ぶ。単なる提案公開を実際の改善に数えない。省エネへの自動収束を防ぐため、この段階の候補とevalに非建物領域を明示する。


実装順と検証commandは [統合SSOT](../../superpowers/specs/2026-09-25-life-manager-unified-ssot.md#manager-20261002) に集約する。
