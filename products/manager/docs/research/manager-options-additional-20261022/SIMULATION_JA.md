# Manager追加調査：新しい社会シミュレーションと仕事エージェント評価

調査日：2026-10-22 UTC。読取対象：`Daisuke134/life-manager`、HEAD `ae06f4ccfa30b29e427f71d6413eba0858a34cf8`。リポジトリ編集なし。新規推論、人を対象にした実験、第三者コードの実行・インストール、送信、公開、契約は行っていない。再利用可能性を検討するため公式コードをscratchへ浅くcloneした。メタデータ、確認範囲、短い原文、制限、具体的patch候補は[SIMULATION_SOURCES.json](SIMULATION_SOURCES.json)に保存した。

この追加調査でManagerの設計に効くのは、企業名の追加より次の四点である。

- 集団の曲線が似ても、個人差・条件別の反応規則が人と異なることを実データ比較で示した研究がある。
- エージェントを採点するシミュレーター自身が、存在しない状態やルールを生成し、正しい手順を不合格にする。
- 現在の公開採点コードと原著の式が一致しない例がある。commit固定だけでは論文再現にならない。
- 見た目の評価では、LLM同士の一致と人との一致が乖離する。描画成功、意味、見やすさ、実便益を別々に残す必要がある。

## 新規性の確認

先に`AGENTS.md`、`REVIEW.md`、戦略調査の`REPORT_JA.md`と`PRIMARY_SOURCES.json`、既存90件atlasとコード監査を確認した。さらに`products/manager`全体を名前・IDで検索した。

**AgentSociety、OASIS、AgentTorch、TinyTroupe、TheAgentCompany、τ-bench、τ²-benchは既知。** 戦略本文の中心表にないからといって新発見として数えない。既存のlandscape、セミナー、記事、atlas等に存在する。

| 今回追加できる対象 | 正式ID・取得版 | 新規性 | 深さと利用目的 |
|---|---|---|---|
| Collective cooperation without individual fidelity in LLM agents | [2606.30454v1](https://arxiv.org/abs/2606.30454v1)、2026-06-29 | 名前/IDとも製品内一致なし | 本文方法・結果・限界。集団一致から個人/介入へ飛ばない反例 |
| AgentSociety 2 | [2607.11895v2](https://arxiv.org/abs/2607.11895v2)、v2 2026-07-15 | 既知プロジェクトの未読新論文/世代。別の新企業とは数えない | 選択した方法・失敗結果・限界＋実コード。実験の監査可能な部品 |
| OccuBench | [2604.10866v2](https://arxiv.org/abs/2604.10866v2)、2026-04-16 | 名前/IDとも一致なし | 故障設計、cross-simulator結果、限界＋公開reference実装 |
| DuMateBench | [2608.26546v1](https://arxiv.org/abs/2608.26546v1)、2026-08-27 | 名前/IDとも一致なし | 再構成、環境、採点、noise結果＋採点コード/権利告知 |
| EnterpriseClawBench | [2606.23654v1](https://arxiv.org/abs/2606.23654v1)、2026-06-22 | 名前/IDとも一致なし | 本文passage、judge/skillの反例、公開contractコード |
| ττ-Bench（hyper-tau） | [2609.04611v1](https://arxiv.org/abs/2609.04611v1)、2026-09-04 | 既知τ系列の別benchmark | 本文＋Appendix H全9故障類型。公式コード再利用は未確認 |

全6論文は取得時にarXiv preprintとして扱う。査読済み会議・journal採録は確認していない。検索は5つの異なる問いで各8 ranked hits、canonical inspect、質問別read、citation-graph探索、公式URLのexact-version HTMLと公式repoを使用した。40件の独立研究を読了したという意味ではない。引用graphは候補1件しか返らず、関連研究が1件だけという結論には使わない。

AgentSociety 2のcanonical historyはv1を2026-06-11と表示する。IDの月prefixと不整合に見えるが、取得記録を勝手に補正しない。全ての日時はJSONに保存した。

## 1. 集団の一致から介入の妥当性は導けない

[Collective cooperation](https://arxiv.org/html/2606.30454v1)は、既存の人のnetworked Prisoner's Dilemmaと同じpayoff、network、時系列接続、相互作用protocolで9つのopen-weight LLMを比較する。最も集団曲線に近いモデルを選び、その後に個人差と条件別の規則を調べている。

macro指標はRMSE/MAE、元曲線と一階差分の相関、差分系列のAR(1)。micro指標は個人ごとの協力率分布のWasserstein-1、直前の自分の行動と近隣の協力率による次の行動。時間順序を壊したnull、母集団平均と試行回数を保つBernoulli nullも比較する。この階層別検証が再利用できる方法である。

人のlattice条件の平均/SDは .368/.170、simulationは .291/.069。集団の減少・安定化を部分的に再現しても個人差は狭い。完全LLM集団のlattice W1=.101は、単純Bernoulli nullの .085（Monte Carlo区間 .082–.089）より悪い。20%のrandom agentを混ぜると .081へ改善するが、条件別のdecision ruleの不一致は残る。別network条件では混合が悪化する指標もある。

限界は一つの元実験・母集団・制度環境であること。モデル選択とrandom比率探索は同じbenchmarkへの適合であり、独立した新規介入予測の検証ではない。agentやroundを独立標本として水増ししない。

公式repo [hfarruda/collectivecooperationLLM](https://github.com/hfarruda/collectivecooperationLLM/tree/4e8c45659dc4b92932a55161b16cb73d07dd1efb)の固定treeにはREADMEしかなかった。実行可能コード・人データ・コードlicenseの公開を確認できない。論文の方法を参考に独自の合成fixtureを作る候補であり、「既存コードをそのまま導入できる」とは書かない。

Managerでは`eba_benchmark.score_suite`のTVD/Brierや`error_calibration.ErrorReference`が既に存在する。しかし後者はbinaryのscope別誤差診断であり、人の個別行動/相互作用の妥当性を測る型ではない。`phase_calibration_reference.py`もUCIの日次集計を明確に非人間較正としている。その意味を拡大しない。

**具体的patch候補 S02：** optionalな`manager_core/simulation_validation.py`にmacro/micro/conditionalのreportを作り、`reference_hash, protocol_hash, population, network_id, agent_id, round, previous_action, neighbor_cooperation_bin`をbindする。既存calibratorはscope fenceを保持する。

最初の合成fixtureは毎round全体協力率が .5になる二集団。一方は半分が常に協力、半分が常に非協力、他方は全員が交互に切り替える。macro error=0でも個人協力率分布の距離は正になる。さらに条件responseを置換してmacroと個人分布を保つfixtureを置き、conditional不一致を検出する。これはmetricの検査であり新しい人科学の結果ではない。真正な人参照がなければ`REFERENCE_DATA_REQUIRED`、`P0/NOT_MEASURED`のままにする。

## 2. AgentSociety 2の価値はtraceと実験部品、失敗も結果に含めること

[exact v2](https://arxiv.org/html/2607.11895v2)はAI研究者のworkflowとsilicon participantを同じruntimeでつなぐ。仮説、設定、生成コード、実行ログ、中間データ、解析、原稿を残す。§4.2では構造検査とassistant attestationによるphase gateを説明する。ただし§9.4は、traceability、simulation realism、experimental-mechanism validityを三層に分け、監査可能性だけで科学的な真実は証明できないと明記する。

134人のprofileを同じPersonAgentへ入れた心理課題の例が重要である。endowmentの方向は再現するが、WTA/WTPは人107.84/74.36に対しagent63.32/48.37 CNYと圧縮。reverse-coded self-enhancementは人43.61に対しagent53.72で方向が違う。IATのlatency差807.7/809.3msはp=.81、SREもself/friend/other 57.2/59.2/58.7%で期待順序を示さない。正しいformatで全手順を完走しても、constructが再現されるとは限らない。

disaster mobility例の低RMSEは11日系列をそれぞれsum-normalizeした形の比較で、移動量の絶対誤差ではない。人の政策介入効果の普遍的accuracyへ言い換えない。

[固定code](https://github.com/tsinghua-fib-lab/AgentSociety/tree/0ca73abca877b43eefb01f7d3cdf588461489861/packages/agentsociety2)は2.9.3、Python >=3.11,<3.14、Apache-2.0。読んだのは`env/base.py`の`@tool(readonly,kind)`、observe/statisticsの強制readonly、例外時もfinallyに残すcall record、`skills/experiment/models.py`の仮説/実験/run ID、metadataとLICENSE。全frameworkを監査・実行したのではない。

**再利用：** 新frameworkへManager coreを移す必要はない。optional sandbox adapterでread/write/observe/statisticsとtrace identityを対応させる。研究仮説→設定→実行→解析の監査契約は使えるが、人間研究者の構成概念判断をassistantの自己承認で置き換えない。paperはCC BY-NC-SA4.0、codeはApache2.0で条件が異なる。商用図版やprofileの権利をcode licenseから推定しない。

## 3. OccuBench：評価環境の故障をagentの能力不足にしない

[exact v2](https://arxiv.org/html/2604.10866v2)は100シナリオ、10業界、382 filtered task。reference planで複数回実行し、特定のLanguage Environment Simulator下でsolvableにする。E0 clean、E1明確な500/timeout、E2正常JSONに見えるmissing/truncated/stale、E3混合。defaultは2 fault events×連続2 callsで一過性。9モデル平均はE0 67.5%、E1 62.6%、E2 53.4%、E3 54.4%。4/9はE2がE3より悪く、目立つerrorより無言の欠損が難しい。

さらに同じ8 agentを別LESで動かすと平均67.9%（Gemini Flash）、63.4%（Qwen3.5+）、29.3%（GPT5.2）。特定LESが架空の部屋、欠落した担当者、指定にない期限ruleを生成して失敗させる。QwenとGeminiのpairwise順序一致24/28は条件付き整合性であり、現実へのfidelityではない。§8.1は正確な業務値を本物のDBから取得せず生成すること、simulatorを変えるとsolvableでなくなることを認める。

[公開code](https://github.com/GregxmHu/OccuBench/tree/d47bffb524b51d69748bf6801e803de04ed40820)はApache2.0だが、READMEが**paperの内部harnessはproprietaryで、公開物はclean standalone reimplementation**と明記する。`lwm.py`は履歴からobservationを生成し、`fault_injection.py`はfault指示をpromptへ足す。回数・位置をpromptで要求したことと実際のactivation receiptは別である。

`verifier.py`は`bool(result.get("is_correct",False))`へcoerceし、例外を不合格へ落とす。この部分はManagerへコピーしない。文字列falseのtruthinessやjudge障害をモデル失敗にする意味になる。既存Managerのstrict typesとUNKNOWNを保持する。

**具体的patch候補 S01：** 新runnerではなくhost-sideの`environment_reliability.py` sidecar。versioned manifestでstate inventory、許可operation、published/deployed API versions、fault seed、resource ID、request ordinal、activation receipt、期待/観測state hashをbindする。undeclared entity/rule、必須field欠落、stale snapshot、cursor欠落を`INSTRUMENT_INVALID/UNKNOWN`へ分離する。

既存`public_observer.fetch_snapshot`、`WorldState`、`owned_cycle.run_owned_cycle`と注入callbackを再利用する。`test_public_observer.py`はtimeout/empty/malformed timestamp、`test_world_state.py`はsupersession/stale/futureを既に検査している。追加するのはHTTP200の見かけ正常で必須URL欠落、候補list truncation、正しいfixture policyがLESのstate inventionで採点されない検査など。元テストと同じものを数だけ増やさない。

## 4. DuMateBench：公開codeの式を論文の式と照合する

[exact v1](https://arxiv.org/html/2608.26546v1)は200の実session由来taskを要求時点のvisible history/workspaceで復元し、人が確認する。insufficient、unstable、noisyを組み合わせ、seed・fault activation・recoveryを記録する。hidden atomic checklistと、人がreviewしoutput評価前に固定したartifact rubricを併用する。

ただし**原著§5.3/Table2はfinal=.3×partial+.7×judgeなのに、[固定公開scoring.py](https://github.com/baidubce/dumate-bench/blob/d423d52db3c5686e04f4d59401aca6b6346b1685/dumatebench/evaluator/scoring.py#L31)は.3×complete+.3×partial+.4×judge**。この不一致は未解決として残す。現在のcode defaultで原著数値を再現したと言わない。best .8548もweighted artifact scoreであり、85.48%のstrict completionではない。noise normal→highでClaude Code18.53pp、Hermes20.08pp、DuMate1.67pp低下と報告するが、作者のplatform/harness、単一由来session、judgeを含む限定結果である。

権利の具体的反証もある。[THIRD_PARTY_DATA_NOTICES](https://github.com/baidubce/dumate-bench/blob/d423d52db3c5686e04f4d59401aca6b6346b1685/THIRD_PARTY_DATA_NOTICES.md)はroot Apacheがown codeのみとし、教育部XLSX未確認、HTML snapshotにはcopy/mirror禁止、derived goldとsession captureにも未解決事項があると記載する。dataset cardのApache表示でこれを解除できない。

**具体的patch候補 S03：** 外部scorer manifestに`paper_version, repo_commit, blob_sha, formula_id, components, missingness_policy, known_mismatch, reproduces_published_score`を残す。論文式と実装式が異なるfixtureで`KNOWN_SCORER_MISMATCH`を返し、比較を止める。コードのfault YAMLのschemaとauditable scheduleを参考に、**元の合成fixtureのみ**を作る。restricted task assetsをManagerの公開benchmarkや記事へ取り込まない。

## 5. EnterpriseClawBench：judgeの一致と人の一致は別

[原著](https://arxiv.org/abs/2606.23654v1)の852 taskはproprietary enterprise sessions由来でfull dataset非公開。公開は構築/評価protocolとsanitizeしたexample等。harness+model、artifact delivery、text/visual、費用・runtimeを分ける点は有用だが、full benchmarkの独立再現はできない。

§3.5の人48 packet auditはtext24/visual24。textのMAE .134、Spearman .790に対しvisualはMAE .303、Spearman **-.259**。別LLM visual judgeとの相関 .866があっても、人との妥当性は保証されない。n24の限定auditから万能なjudge不良率へ一般化しない。§3.4のskill transferもcreator meanが+.0681、+.0518、-.0941と、skill追加が悪化する例を残す。

[固定repo](https://github.com/FrontisAI/EnterpriseClawBench/tree/68507699d1a61700f4281f1f34dcadb20f2de06d)の`docs/evaluation_protocol.md`、`report.choose_main_score`、testsはvisual必須時にtextへfallbackせずnull/errorを残す。一方`rules.py`はunknown ruleをpassedにするためその動作は採用しない。summaryは有効scoreのみの平均なので、scheduled/valid/missingの分母を必ず併記する。固定treeにLICENSE/COPYING/NOTICEが見当たらず、codeの利用権は未確認。**方法とcontractを独自実装する候補であり、そのままcode transplantとはしない。**

**具体的patch候補 S04：** `artifact_evaluation.py` sidecarにartifact hash、期待type、renderer/version/receipt、rubric hash、judge version、text/visual score、cannot_assess reason、scheduled/valid/missing、rights/export allowedを持たせる。描画失敗をtext scoreで埋めない。必要artifactの欠落とjudge自体の停止を分離する。公開readbackの成功はwebpage/deckの使いやすさや受益者便益の証拠へ昇格しない。

## 6. ττ-Benchの九故障はE16へ直接持ち込める

[exact v1 Appendix H](https://arxiv.org/html/2609.04611v1#A8)は53 task/four domainsで、既存資料・clientへの質問・継承code・serving予算からagentを構築させ、heldout user simulationで評価する。best23.9%対expert82.2%。一回build/taskなのでbuild varianceは未測定。single-LLM fixed client/user、全factが資料かclientに存在する設計、submission後maintenance未測定の限界を持つ。

九類型は、value remap、field rename、amount sign、date type drift、async completion、post-commit timeout、rate limit、pagination、projection lag。versioned manifestにoperation、task/resource selector、request ordinal、seeded delayをbindし、再現する。Appendix Hの実装思想だけを使用し、**公式code repoの再利用を確認したとは書かない**。

特にpost-commit timeoutは「失敗応答だから効果なし」、projection lagは「古いreadだから効果なし」という誤判定への反例になる。原著は静かなpaginationを見落とし、自己作成testを誤動作に合わせて弱める例も報告する。blind retryも永久retry禁止も正解ではなく、そのoperationのidempotency/status契約を確認する。

Managerには`test_owned_effect_recovery.py`と`test_digital_cycle_acceptance.py`のexact occurrence/readback/UNKNOWN/replay-zeroがある。S01へ九類型のうち未実装分だけを加え、commit後504→status lag→真正なreadbackのsequenceで書込数が増えないこと、async202はcompleteでないこと、paginationが先頭pageだけで確定不在にならないことを検査する。実際の第三者APIへ故障を注入する必要はない。

## 変更する場所と受入条件

| 順位 | 提案 | 既存の再利用箇所 | 追加受入条件 |
|---|---|---|---|
| 1 | S01 環境integrity/静かな故障sidecar | public_observer/world_state/owned_cycle、recovery/acceptance tests | env障害とagent誤りを区別、曖昧書込の再発行なし |
| 2 | S03 scorer provenance/式照合 | 既存atlas/code audit、test_eba_landscape_sources | DuMate式の不一致を隠さず比較不可、unknown ruleは成功不可 |
| 3 | S04 artifact judge/rights manifest | 既存publication/readback証拠と独立した評価 | render/judge欠測を保持、分母とrightsを明示 |
| 4 | S02 階層別simulation validation | 既存TVD/Brier、group split、scope別abstention | macro一致だけで個人/conditional/causal/welfareへ昇格不可 |

`collaboration_comparison.load_suite`はcases/rubric/schema/baseline hashを固定し、family splitを維持している。`evaluate_suite`は全attemptとtransport/format failureを残す。このv2 manifestへ列やcaseを黙って追加せず、別sidecar/versionとして連携する。`eba_benchmark.promotion_verdict`は常にfield effect不適格で、`test_calibrated_abstention`はaggregate→owned/human scope移送を拒否する。今回の文献でこれらを緩める根拠は得られていない。

検証はcanonical remote/HEAD、recursive novelty検索、code pin/path/blob、選択ファイルがcommitのbytesと一致すること、JSON構造/ローカルpathの実在確認まで。upstream benchmarkの実行、科学結果の独立追試、Managerの改善効果は未実施。AgentSociety cloneの無関係3ファイルはCRLF正規化差分を示したため触らず、読んだ対象はexact HEAD bytesとの一致を確認した。



---
統合注記: このlaneは読取調査。repoへ収録した統合担当の文書変更と、未実施の実装/外部操作は別。[追加調査の判断](REPORT_JA.md)と[atomic patch plan](../../plans/2026-10-22-manager-e16-atomic-patches.md)を参照。
