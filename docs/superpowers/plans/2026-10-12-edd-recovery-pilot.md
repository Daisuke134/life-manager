# EDD pilotから公開benchmarkまでの実装前計画案

> この文書は `superpowers:executing-plans` に沿う詳細な実装計画。pilotの実行は開始済みで、順序・状態・現在cursorの正本は統一SSOTだけとする。この計画は新しいcursorを作らない。

**選定:** Writerの一記事・一言語・一媒体の公開前品質評価をPilot Aとする。effect-unknown recoveryはPilot Bとして続ける。Writer quality PASSを売上改善と扱わず、既存recovery-intent/apply-plan testを再利用する。実行順とcursorはcanonical SSOTが所有する。
**今回の作業境界:** E02 Writer Pilot Aだけを進める。E01 Agent Economyは別cursorであり、このWriter計画の調査・実装対象に含めない。

**実行順の参照:** A8a synthetic-reference fixture → A9 baseline freeze → A8b fixture comparisonの後、canonical SSOTのDD01–DD12共通配信EDDを先に実施してからA10以降へ戻る。人間注釈を実行gateにしない。synthetic agreementをhuman calibrationや自然性能と呼ばず、judge呼び出しはA9のfreeze前に行わない。この参考計画へDD checklistを複製しない。

**Goal:** Writerの自然traceから観測された失敗を一つ選び、同じ条件のevalで修正前後を測る。task完了・外部effect・費用控除後のsettled net・時間・人の介入を分け、自己修復・自己改善を経て独立再現可能なbenchmark報告へつなぐ。

**Architecture:** Writerの既存gate/run artifact、runtime event、LM-EAB scorer、recoveryのpure-function testを再利用する。A8のhuman-label exportとbinary metricsを接続するjoinerまで実装した結果、残る具体的な欠落は、ラベル済みcaseを既存identity gateへ流すbatch runnerだったため、その薄いadapterだけ追加する。新eval frameworkは持ち込まない。実judgeは20/20の人手ラベルとA9のmodel/runtime/hash/split freezeが揃うまで呼ばない。

**Tech Stack:** 既存Node.js ESM、`node:test`、Markdown。新依存なし。

**Spec:** [EDD recovery pilot design](../specs/2026-10-12-edd-recovery-pilot-design.md)

**読者向け説明:** [英語版ブログ記事](https://aniccaai.com/blog/good-agent-evals-measure-outcomes) と [X post](https://x.com/selawmqt/status/2109636732962668720)。X Articles editorはこのaccountで利用できず、Xにはブログへ誘導する標準postを公開した。記事公開はE01–E06の完了や実測性能とは数えない。

### 英語記事の配信atom

- [x] 英文と出典snapshotを固定し、合成fixture・収益・lab採用に関する限界を保持する。一次資料とfresh read-only adversarial verificationで確認済み。
- [x] 既存 `/blog` テンプレートに記事recordと画像を追加し、site PRをmainへ統合。PR #456 merge `23b2eeb`、deploy/smoke PASS、live本文readback、画像3件HTTP 200を確認。
- [x] live登録済み `x:anicca` accountから英語記事へ誘導する標準X postを公開する（X Articles editorは公式URLで404）。本文とblog linkのreadback済み。
- [x] X post URLをblog mirror metadataに入れ、site PR #457をmainへ統合。deploy/smoke PASS、live pageのX hrefと表示 `X ↗` を確認。
- [x] blog/Xの実URLと公式readbackをこのspecへ記録する。記事配信をagent実行、自然収益、E06完了、lab採用として数えない。

## Global Constraints

- canonical repoの最新main由来の専用worktree。現在のbranchは文書専用。
- spec/task順は統一SSOT。実装ownerと範囲を調整し、他者変更を戻さない。
- provider・browser・credential・production state・launchdのmutationなし。
- privateな自然traceは既存ownerのprivate storeに保持し、Gitには匿名case cardと参照可能なsanitize済み根拠だけ置く。
- 新framework/scheduler/optimizerを追加しない。
- policy判定は業務完了・自然自己修復・実利益・モデル順位の証拠ではない。
- 公開held_outを秘密試験と称さない。

## Atomic sequence: Writer Pilot Aから外部再現まで

canonical SSOTのE01は`agent-economy-loop`のrelease adoptionと自然評価を追跡し続けるが、Writerの評価作業の前提条件ではない。Writer Pilot Aの旧順`A1 → A2 → A3…A7 → A3b → A8…A14`を`A1 → A2 → A3…A7 → A3b → A3c → A8…A14`へ変更する。理由は、251件のchild judge summaryにparent article run/occurrence/release fieldsがなく、case入力と親runを再構成できないため。A3cのchild-to-parent metadata bindingを直してからjudge較正へ進む。E01は別cursorとして未完のままにし、Writer進捗で完了扱いしない。

このchecklistはWriter Pilot Aの詳細計画であり、canonical SSOTの全体TODOを複製しない。完了表示は実測後にcanonical SSOTへ反映する。

### Pilot A — Writer公開前quality eval

- [x] **A1:** Writer owner・lease・run状態をread-only確認し、既存ownerと重複しない評価専用範囲を選んだ。観測checkpointはdesign specのWriter trace checkpoint。今回の変更は新規eval files、package script、CI jobに限定し、production Writer runtimeや外部effectを変更しない。
- [x] **A2:** English blog article draftの公開前quality gateを一つのstageとして選んだ。本文/CTA/identity gateを評価し、blog・note・Substack等への新規公開や再送を行わない。
- [x] **A3:** task-level article runとchild agent-runner traceを別々に数える。8件の自然article runと276件の`article-daily` child summaryを照合し、全article source SHAが`UNKNOWN`、child summaryのparent run/occurrence/source SHAが欠落と記録した。child callを独立task数へ足さず、human labelとlineageが揃うまで性能率・saturationを出さない。詳細 → [Writer EDD trace discovery](../../evals/writer-edd-trace-discovery.md)。
- [x] **A4:** 実traceからfailure taxonomyを作り、`quality_self_heal_record_unparseable`を最初のcode-checkable failure classに選んだ。W-01のartifactは0 bytesでSHA-256=`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`、JSONDecodeError。これはevidence-integrity failureで、agent content qualityやhuman labelの代わりにしない。E01 cursorは動かさない。taxonomy → [Writer EDD trace discovery](../../evals/writer-edd-trace-discovery.md)。
- [x] **A5:** W-01のcase cardにtask、initial state、allowed tools、budget、期待outcome、natural provenance、evidence refsを記録した。これは0-byte recovery artifactのevidence-integrity caseであり、writer quality、人手identity label、source reproductionはunknown/pendingのまま別表示する。case → [Writer EDD trace discovery](../../evals/writer-edd-trace-discovery.md)。
- [x] **A6 / E02 case-level vector:** W-01 cardにtask completion、quality、safety gate、effect integrity、settled net、cost coverage、latency、human interventionを別fieldで記録した。証拠がない項目は`unknown`のまま保持し、publication stageは`blocked-before-publication`として分離する。これはPilot Aのcase定義だけで、canonical E02の自然failure/CFO official receipt joinは未完。
- [x] **A7:** hash/schema/receipt/重複/publication statusをcodeで採点するgraderを`apps/life-manager/eval/writer/receipt-grader.js`へ追加。9 testsとW-01 CLI出力は`npm run test:writer-eval`でPASS。意味判定は行わず、task completion・quality・effect integrity・settled netは`unknown`のまま保持する。詳細 → [Writer EDD trace discovery](../../evals/writer-edd-trace-discovery.md)。
- [x] **A3b:** Writer runはvalidな`LIFE_MANAGER_RELEASE_SHA`を`git-hash.txt`へ記録し、local checkoutではGit fallbackを使う。focused regressionとWriter CIはPASS。source merge PR #7878 / main `a6fccbb8`。live article-dailyは旧releaseのままなのでnatural adoptionは未確認。過去run `20261011-210544`のsourceはUNKNOWNのまま、publish fence/live ownerを変更しない。
- [x] **A3c:** `attach_runtime_event` summary now carries child event identity plus parent lifecycle/article IDs. Focused regression and Loop control CI pass; PR #7881 / main `e2463ba9`. Live article-daily still runs old release with an unresolved publish fence, so natural adoption is pending.
- [ ] **A8a — no-human synthetic reference source acceptance:** `apps/life-manager/eval/writer/fixtures/a8-category-c-reference-v1.jsonl` contains 40 synthetic Category C references (20 PASS / 20 FAIL) bound to dataset v3 SHA and `synthetic_policy_reference_v1`. `npm run test:writer-eval` 30/30 passes; the runner rejects human-review exports and requires `--freeze-manifest`. Missing/mismatched hashes, provider fallback, and runtime-version drift fail in preflight with `effect=none`. Freeze identity/hash and model identity flow into predictions and metrics. Metric scope remains synthetic reference agreement; human validation and natural performance remain unknown. No real judge call was made. Fresh review returned `ship`; PR #7931 is open against current main, CI is in progress, and main integration is pending.
- [ ] **A9 / E04 — next after A8a integration (before A8b):** create `docs/evals/writer-edd-a9-freeze-v1.json` and a Writer-eval-only `composition-agent` config with exactly one Codex candidate (`gpt-5.6-terra`, medium, acct1; no provider/account fallback). Freeze dataset/reference/split, runner/grader, runtime entrypoints/config, and Node/Python/Codex runtime identities plus hashes. `run-identity-cases.js` verifies the manifest, current artifact hashes, and the single-candidate config before any provider process starts; missing/mismatch exits with `effect=none`. Do not call the real judge before this freeze. Public fixtures are not secret tests.
- [ ] **A8b:** run the frozen baseline on the versioned synthetic reference cases, join predictions by case ID, and compute fixture false-pass/false-fail; keep rates null if predictions are incomplete. Report `reference_source` and `human_validation=not_performed`; synthetic agreement is not human accuracy.
- [ ] **A10:** 同一model/runtime/tool/budgetでbaselineを各case 3回以上実行し、trial数・結果のばらつき・費用を保存する。
- [ ] **A11:** 自然traceから選んだ失敗を最小の回帰testにし、修正前REDを確認する。既存testが覆うassertionのwrapperを作らない。
- [ ] **A12:** 一つの原因だけを最小修正し、同じtest GREEN・関連acceptance・CIを確認する。修正内容と変更SHAをcaseへ結ぶ。
- [ ] **A13:** 凍結held-outでbaseline/candidateを比較し、品質/safety/effect/net/cost/latency/介入を個別に報告する。
- [ ] **A14:** 公式publication/readership/payment receipt、refund・fee・同期間のactual costを同一artifact/campaign IDへ結ぶ。complete coverageが無ければnet upliftを主張しない。

### Pilot B — effect-unknown回復安全case

- [ ] **B1 / H01:** 自然障害一件をexact owner/run/occurrence/release/error/next actionとrecovery intentへ結ぶ。
- [ ] **B2 / H02:** 公式readbackで対象occurrenceを照合し、effect unknownのままならfence保持・再送なしを示す。近似receiptを流用しない。
- [ ] **B3 / H03:** 原因ownerが必要な最小修正を既存PR/CI/main/immutable release契約で行う。pilot担当はprovider/browser/production actionを実行しない。
- [ ] **B4 / H04:** 次の自然runでintent→repair→release→official outcome→replay-zeroの因果が同一caseに結び付くことを確認する。

### I01–I04 — bounded self-improvement

- [ ] **I01:** prompt/tool/routing/offerから候補を一つだけ作る。grader、dataset、permission、identity、effect fence、spend capは候補が変えられない。
- [ ] **I02:** frozen baselineと同じcase・model/runtime・予算・trial条件で比較し、品質だけでなくsafetyとcost-complete netの事前条件を満たすか採点する。
- [ ] **I03:** offline gateを通った候補だけ既存ownerの承認済みcanary経路で試す。悪化時はsourceを戻し、外部effect fenceはreadbackなしに解除しない。
- [ ] **I04:** observe→candidate→eval→promote/rollbackを有限のtrial・時間・費用内で繰り返す。agentが自分のgraderやsuccess labelを書き換えない。

### E03/E05/E06 — 公開benchmark

- [ ] **E03:** Writer以外は、natural traceと実outcomeを用意できる経済task familyから一つずつ拡張する。synthetic contract caseをagent performanceと混同しない。
- [ ] **E05:** 既存runnerに別harness adapterを接続し、独立環境で同version・同条件の結果を再現する。新framework先行導入はしない。
- [ ] **E06:** task作成法、provenance、grader、split、model/runtime/budget、trial、測定値、不確かさ、限界を公開する。open-source公開後も第三者再現とlab採用は別の外部成果として記録する。
- [ ] 外部研究者またはlabによる再実行を得て、同条件で結果が再現した時だけ第三者再現を報告する。「leading」やlab採用を主張する時は、その利用を示す公開sourceを添える。

## Review Focus

- 既存testのhold/nonretryable/no commands/owner拒否を別wrapperで複製しない。
- safe holdは業務完了にならない。
- 別occurrenceの近似receiptを対象の成功証拠にしない。
- known pre-effectの回復経路を全holdに変えて安全点だけを稼がない。
- 本番でしか観測できない未測定境界を、fixtureの合格で完了扱いにしない。

## Pilot B task 1: 一件の自然障害と既存testを対応付ける

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

## Pilot B task 2: 既存回帰試験の基準を確認する

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

## Pilot B task 3: 欠けた境界を修理ownerのEDDへ接続する

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
