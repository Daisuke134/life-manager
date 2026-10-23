# V001 — 固定済み診断の評価契約対応

2026-10-23 UTC。既存3診断の版・対象・採点者・権利・split・分母を一つのmetadataへ結合した限定受入。新しい評価実行・事前登録・runtime機能ではない。V001全体はtodoのまま。

## 解消したこと

[評価契約](../../experiments/behavior-model/v001-evaluation-contract-v1.json)は `e1e27153d3c12bc8c2fea54677bf10d8de17e8a5` で実装。22942 bytes、SHA256 `f0b0644e52a92516a05273cf7cb663a5ef056f0646ecb0ec28e61f97b870a8a8`。

| 採用slice | 使う既存部分・役割 | 採点と受入範囲 |
|---|---|---|
| INTIMA | 元のmodel列はprompt generator。local Qwen3-1.7Bは応答generator。上流judgeの正確な版/prompt/parserは未確認 | input受入と32入力×3条件の生成診断のみ。96行はNOT_SCORED/null。コード別subsetを論文scoreと比較しない |
| HelpSteer2 | native Qwen3-0.6Bのcandidate NLL評価。生成judgeは使わない | 元候補への人の選好に対する固定dev8比較。pair/group、16 candidate forward、completion-token NLLの単位を分ける。NO_ACTIONの棄権はresponse refusalではない |
| XSTest | 元Mistral応答と元human goldを完全一致で結合。配布string labelとlocal Qwen judgeを区別 | 元応答の拒否3分類限定。配布algorithm再実行ではない。local runの未完了/UNKNOWNと、この設定の不採用を既存receiptへ結ぶ。新しい応答へgoldを移植しない |

source/dataset/adapter/model/tokenizer/scorer/judge版を、既存protocolと公開receiptのimmutable commit/path/hashへ対応付けた。参照13件、artifact別の権利record3件。権利の第二定義を作らず、完全recordのcanonical hashで既存条件へ結ぶ。INTIMAのprivate凍結protocolとselectionはopaque evidence ID/hashと公開receiptから参照し、private本文・個票を転載しない。

これは過去の凍結済み実験を後から対応付けたもの。新契約自体が結果観測前に登録されていたとは記さない。元protocol・実行・失敗・指標は変更せず、新しい結果台帳も作らない。

## 保持した境界

- 人物/研究/時間axisは各sliceのavailable fields、理由、group/train/test/cutoff=null、必要用途HOLDを明示。空の分割を漏洩0と見なさない。prompt hashは人IDではなく、retrieved_at/local mtimeは観測時刻ではない。
- native dataset splitと、実験上のdevelopment roleを分ける。HelpSteer2 devはraw train由来のdev8で、未見final testではない。train案27/32 NOT_READY、学習用途HOLD、final16モデル採点NOT_RUNを保持。
- assigned、attempted、completed、valid、failed、UNKNOWN、NOT_RUN、ABSTAIN、refusalを各単位で定義。未評価/分母0=null、失敗・中断を誤答・正常完了へ補完しない。
- XSTestのモデル有効集合とfull450 ruleを分ける。partial refusalをrisk3classへ写像しない。モデル設定不採用から全Qwen系列の否定へ一般化しない。
- 評価input/output/ラベルを学習・few-shot・retrieval・checkpoint選別へ流用しない。権利の用途拡張、training readiness、モデルの採用・昇格は別判断。
- 既存wrapperのempty `EvidenceBundle` → `reproduction_manifest`を対応付けるだけ。Source hash一致は認証ではなく、P0 / NOT_MEASURED / can_execute=false、P1–P3 MISSING / P4 INCOMPLETEを保持する。

## 検証した範囲

実装者のbounded stdlib検証112/112 PASS。JSON重複key/構文、13参照の現bytesと指定commitの一致、3完全rights recordのcanonical hash、元source/protocol/receiptの結合、private INTIMA metadata hash、原registry/旧snapshot/80done rowsの保存を確認した。

rootは別のbounded checkで13参照を指定commitから読出し、現在bytesとの一致を確認して既存 `Source.verify_content` を適用。3rights record/revisionと全9 unavailable axes、13保護ファイル、旧private INTIMA protocol/selection、他lane SSOT suffixの不変を照合した。既存OutcomeBenchのempty exportも実呼出しし、P0/NOT_MEASURED/参照0を確認。任意ML packageのimportはなし。

Fresh combined task reviewはHEAD `e1e27153d3c12bc8c2fea54677bf10d8de17e8a5`で0 findings / SPEC PASS / QUALITY Approved。一次資料と独立metadata checkによる13refs、3rights record、2private metadata hash、3empty wrappers、13保護ファイルを確認した。rootは全reportを読み、限定mappingとして受け入れた。

private checker初稿では、旧done-row hashのJSON separator形式と、説明metadataのcompletion keyをrawと誤認する仮定を修正した。旧snapshot/元artifact/実験結果はこの修正で変更していない。hash照合は元出典の真正性・包括的権利・PII非含有・数値NLL/生成parserの独立再現を認証しない。

変更はmetadataのみで、runtimeコード・権利manifest・既存protocol・旧receipt・registryを変更していない。新しいソーステスト、全suite、CI、model/tokenizer、推論、学習、weight再hash、download、network、本番作用は再実行していない。前段のCI成功を新JSONの意味検証と取り違えない。

cloud source guardはcanonical host path不在による実FAIL/exit2を保持。既存の明示的cloud source作業指示とverified origin/common Git/専用worktreeの範囲で進め、guardの改変やPASS置換はしていない。

| 私有検証証拠 | SHA256 |
|---|---|
| 実装者112check記録 | `5fb7b5ed39b1e0594cc370a6e3507894d8267e84e86eed0bfeb08ceb621c99f2` |
| root別実装binding確認 | `a4ab32ff4bd381f0698e8e1c03b2903f87826defeaa40c9f8ef12c815b6fb232` |
| root既存OutcomeBench実export | `fe1b6326c4d8d5fd472bda3aa67e12f797466cc83d84f77b3fb168ada7bd568b` |
| fresh combined task review | `da8890a266b3e8a3df14b3fc39834e960e3ad51364fc6f371ac84930fcae516d` |

## 残る受入

今回閉じるのは「既存診断の採用scope/モデル役割/採点/refusal/null/split availabilityを一つへ対応付ける」gap。実際のperson/study/time holdoutが得られたという証拠は増えていない。現在のliteral holdout要件の全充足を宣言せず、V001/V002/V003と原113件=80done/23todo/10skippedを保持する。

既存S003 SocSci210の170/40 study split、S008 Bikeの日付split、HeartStepsの37 participant clusterはそれぞれ別の対象・constructの証拠。3診断の人/時間一般化を単独では示さない。既存資料限定のreadinessでは現有raw保有も未確認で、全環境にデータが存在しないという結論ではない。

次は、用途に適合したholdoutの実key/観測時刻・利用条件・元responseへのbindingを成立させる。圧力/依存/害の評価と人参照、V002同条件比較の全受入は別に残る。独自adapterのoptimizerを先に開始して依存を迂回しない。Mac/GPUや全世界のcredential不在をblockerとして仮定せず、利用可能な公開資料・既存CPUを再利用する。

[実装・受入plan](../plans/2026-10-23-v001-evaluation-contract.md)、[親model plan Task2](../plans/2026-10-23-behavior-transformation-model-plan.md)、[主仕様の残23件](../MANAGER_PRODUCT_SPEC.md)に結ぶ。新記事・書籍の制作は本体の後段を維持する。
