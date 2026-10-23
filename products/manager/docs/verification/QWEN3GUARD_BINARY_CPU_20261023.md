# Qwen3Guard native binary refusal — 実CPU診断

2026-10-23 UTC。公開された専用モデルをnative仕様のまま、元Mistral450応答に一度だけ適用した。**450件すべての出力が規定形式を満たし、採点処理は完了した。** ただし再接続で元の監視プロセスが終了し、監視の空白がある。全期間の資源監視の準拠を認定せず、モデルの自動判定への採用はHOLDとする。新しいManager応答の人手評価、未見一般化、安全性、行動変容、人の便益の実証ではない。

## 結果と判断

元の3classからfull_refusal49→Yes、full_compliance374→Noを派生した**primary423件**で一致を測る。native binary policyの独立した人手goldではない。partial27件にはbinary正誤を与えない。

| 方策 | primary一致 / 有効423 | Yes recall | Yes precision | balanced accuracy |
|---|---:|---:|---:|---:|
| QWEN3GUARD_NATIVE_BINARY | 377/423（89.13%） | 20/49（40.82%） | 20/37（54.05%） | 68.14% |
| RELEASED_STRING_RULE | 383/423（90.54%） | 12/49（24.49%） | 12/15（80.00%） | 61.84% |
| NO_ACTION | accuracy=null、450棄権 | null | null | null |

同じprimary423 IDでのpaired正誤は、両方正解361 / modelのみ16 / ruleのみ22 / 両方不正解24。差model−ruleは−6/423（−1.42 percentage points）。拒否の検出は8件増えたが、元full_complianceをYesとした誤検出は3→17件へ増えた。特定の指標だけで優位や同等性を結論しない。**今回の結果から自動refusal judgeへ採用しない。** 系列全体や他用途を否定する判断ではない。

| gold / model予測 | Yes | No |
|---|---:|---:|
| Yes（元full_refusal） | 20 | 29 |
| No（元full_compliance） | 17 | 357 |

modelのYes F1は0.465116、No precision0.924870 / recall0.954545 / F1 0.939474。ruleの混同行列は同じ軸で`[[12,37],[3,371]]`。全450 coverage=450/450、primary coverage=423/423。全450でattempted/generation_started/generation_completed/VALID各450、UNKNOWN/NOT_RUN/FAILED/INVALID_LABEL/LENGTH_LIMIT/CONTEXT_OVERFLOW各0。NO_ACTIONはall450 ABSTAIN、分類coverage0、conditional agreement=null。

partial27はmodel Yes15 / No12 / nonvalid0。これにaccuracy・recall・混同行列を作らない。ruleのpartial分布Yes4/No23は配布判定の投影であり、partialに独立binary goldがある意味ではない。旧3classの85.11%や未完了271件のaccuracyと、このbinary値を直接比較しない。

## 事前固定と再利用

- [protocol](../../experiments/behavior-model/xstest-qwen3guard-binary-protocol-v1.json)は予測前のcommit `291d6bcf26809f0f33d14e84d95ec158290721df`で固定。SHA256 `58c15f812202236e92b27bd704ea37f3803288749f03c1fcb4039f58600cec7f`。途中のprompt/label/partial扱い/予算変更、retry/resumeは0。
- 実行source `42e3281a14d6f98360b6d9ff34587c22afc032e2`。[adapter](../../manager_core/xstest_binary_refusal_eval.py) / [明示CLI](../../scripts/evaluate_xstest_binary_refusal.py)。既存のexact CSV join、Source、rights/model hash検証、OutcomeBench、標準HF、own-process監視を再利用。新runtime/trainer/production接続なし。
- Model [Qwen/Qwen3Guard-Gen-0.6B](https://huggingface.co/Qwen/Qwen3Guard-Gen-0.6B/tree/fada3b2f655b89601929198343c94cd2f64d93cc)、revision `fada3b2f655b89601929198343c94cd2f64d93cc`。固定metadataでは751,632,384 parameters、native BF16 weight1,503,300,328 bytes / SHA256 `4f3ce47ebd968cddb67de08d8764f8ede7c410a7d1fb9e08145a4c7a2f2e5c0f`。
- Gen/baseの実LICENSEをApache-2.0として確認。両LICENSE SHA256 `832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e`。GitHub評価codeのlicenseはUNKNOWNのため使用しない。8 native assetsを実行前に照合し、guarded loaderも検査する。
- [XSTest固定source](https://github.com/paul-rottger/xstest/tree/d7bb5bd738c1fcbc36edd83d5e7d1b71a3e2d84d)の元応答CSV371935 bytes / `6a146b65a5b96ec8249729bc2db459697175125998d7cbbcc88f7688ecf31dad` と配布rule CSV379544 bytes / `a1ad24b837a13380a88f9748b39663add74cd992d5841db782271490dcbb41d3`をexact join。同じ450の既存hash順・membershipを保持し、補充/除外しない。人物/研究/時間holdoutはUNAVAILABLE、pretraining contaminationはUNKNOWN。
- Native user=元prompt、assistant=元completionだけ。gold・annotation・ruleラベルは入力しない。Safety/Categories/Refusalの全文3行を厳密検査し、RefusalのYes/Noだけを使用。Safetyを拒否/partialへ写像しない。EOS151645/151643、greedy/max128、input+128≤4096、無切断。native template SHA256 `b4230b556815baa1982c0b1eacb181ce965483ee20b1f6e4d9f375294900e02b`。
- CPU BF16/2threads/seed42、torch2.8.0+cpu / transformers4.56.2 / peft0.17.1 / trl0.23.1 / datasets4.1.1 / accelerate1.10.1。offline/local_files_only、trust_remote_code=False、学習処理なし。

## 実行、監視の空白、終了観測

元receiptの実開始は `18:10:22.623978Z`。再接続後の監視が終了を観測した時刻は `19:03:07.404615Z`、元開始から3164.781秒。予定の累積3600秒は延長せず、元の期限`19:10:22.623978Z`内に終了した。

再接続で元の親watcherが失われ、モデル本体は同じPID/PGIDで継続した。最後の元durable checkpointは18:47:04.309879Z。親の消失を18:54:51Zに確認し、18:56:01.103406Zに同じ既存プロセスへ監視を付け直した。正確な途絶開始時刻、空白区間のpeak RSS、全期間の連続監視は**UNKNOWN/UNVERIFIED**。これはインフラ上のprotocol逸脱として保存する。監視再接続はモデルのretry/resumeや別実行ではない。

- 元receiptの`RUNNING`は古いcheckpointとして不変に保存。新しい別receiptは`TERMINAL_ZOMBIE_OBSERVED_RETURN_CODE_UNKNOWN`。結果内の`lane_status=COMPLETED`と区別する。
- 新monitorはorphanの親ではないためwait/reapできず、model_returncode=null / reaped_by_this_monitor=false。rootは終了後のLinux `/proc`で、1個のZ task、RSS0、field52のraw exit code0を別途観測した。これは親のwait成功やPID不在の証明ではない。PID1や他processへsignalを送らず、未reapを隠さない。計算処理は停止している。
- 元監視で観測した最大RSS2,020,655,104 bytes、再接続後2,102,657,024 bytes（約1.958GiB）。後者は全観測値の最大で、空白を含む真の全期間peakではない。6GiBはpolling閾値でkernel hard capではない。観測範囲に閾値超過なし、空白中は不明。環境memory.maxは8GiB。共有cache削除・他process停止なし。
- root引継ぎの開始`.578990`をmonitor実開始と扱ったbriefの44.988ms誤記は、元receiptの`.623978`で訂正した。元/再接続receipt・protocol・結果は書き換えていない。

raw suffix/token IDsと元goldはprivateのみ。checkpoint/receipt/stdout/stderrは0600、元本文や生成文をGitへ含めない。stdout3222 bytesは集計metadata、stderr0 bytes。新規有料API/有料resource追加0、基盤原価はbilling未観測のUNKNOWN。packet captureによる非通信証明は主張しない。

## 権利と検証

[XSTest元artifact監査](../research/2026-10-23-human-reference-artifact-audit.md)と既存の限定private評価権利を継承し、annotation列への個別grantはNOT_EXPLICITのまま。canonical record SHA256 `e3f0f0d53269eb52d54ebd8b2feccf8654cf433dce0fbc746a875fbbdabf434d`。raw再配布、training/few-shot/retrieval/主体の運用データへの転用はしない。ライセンスやPIIの包括的保証ではない。

sourceは17 focused tests、local full1081（skip5）、[公式CI40000835514](https://github.com/Daisuke134/life-manager/actions/runs/40000835514) full1055（skip6）とfocused6/21を実行前に確認した。全1job10steps成功。local/officialの26件差は原因UNKNOWN。既存negative argparse testのstderr usage、Node punycode deprecation warningを保持し、warning0とはしない。最初のroot full-suite実行はcwd/PYTHONPATH不備で失敗し、修正後に既存spec header位置の不具合を13件の回帰確認で直した。最終sourceの全suiteはfail0。

rootは結果の全423 primaryのmatrix/class metrics、paired4区分、partial分布を別stdlib集計で再計算した。独立verifierは46項目PASS、新規source・parser・算術不具合0件（blocking0）を確認した。既知のインフラprotocol偏差1件とbrief時刻転記誤り1件を別計上し、全期間の資源監視の準拠は未認定とした。全450 suffixの厳密形式、exact CSV join/order/hash、class/null指標、paired集計を独立に再計算した。native token IDsからtextへのdecode等価性は、モデル/tokenizer再実行なしには独立検証していない。

cloud source guardはcanonical host path不在の実FAIL/exit2を保持。既存の明示cloud作業許可とcanonical origin/common Git/専用worktreeを確認して継続し、guardをPASSへ変更しない。研究branchのsource受入で、main統合やproduction昇格ではない。

| 私有証拠 | SHA256 |
|---|---|
| results.json | `597f40178d8d1d62eb30450001fd42b39ecca41a8ebe45368ae545a008173596` |
| 元monitorの最後のreceipt | `1f9bcb8214c3adc648324a73ef4da3825dc51180ec40010bc617fb5bfb5cf40a` |
| 再接続monitor receipt | `02c3e1f89a588d7cc98898055e034bbc9c5ffe75183e99590aee0f1cbce8d612` |
| frozen execution config | `af8ebfc55c094631a1d46d5cd30c67790503fd41fa074a358bb1dd4d9e7b0580` |
| stdout | `8b00fd9b849f182143e975b563f82e5f70de2ae50d2bce29dcd09c71d0d04817` |
| stderr（0 bytes） | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| 公式CI job log | `a0444056f89e678f11c777efbab8e712f5d133ab34e9d677aac8a980e8187dff` |
| 独立検証report | `2def9c2eea556f362c70c8376f7826231cfc9f605425d05ea3165445b18ab244` |
| 独立検証JSON | `ea9dbc5accc666c730ceee6ef2a4d06624e040dd7bde3ca37333485aad00de30` |

## 次の作業

[実装・実行plan](../plans/2026-10-23-qwen3guard-binary-diagnostic.md)の一度の有限診断として保存する。P0 / NOT_MEASURED / can_execute=False、原113件=80done/23todo/10skipped、V001/V002/V003 todoを維持。training/optimizer、HelpSteer2 final-test、production activation、人対象作用はNOT_RUN。

次は用途に適したV001設計の受入を明示し、最小独自adapterの研究開始条件を整える。今回のguardの成績を理由にtraining権利や未見評価を成立扱いしない。同じ450で設定を調整して独立testと呼ばない。記事・書籍・新サイト制作は本体/agentの後段へ保留する。
