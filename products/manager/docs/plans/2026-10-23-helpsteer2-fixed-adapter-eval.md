# 固定adapter比較のoffline source導入

この文書は、SFT source導入に続く固定adapter評価codeの範囲と検証を示す。Manager/agent完成を先に進め、記事はその後とする。順序・状態は[単一SSOT](../../../../docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md)で管理する。[SFT source導入計画](2026-10-23-helpsteer2-private-sft.md)と[用途scope](../specs/2026-10-23-finite-private-sft-research-start.md)を継承し、新しいtask台帳は作らない。

## 固定した科学定義とsource

[評価科学protocol](../../experiments/behavior-model/helpsteer2-fixed-adapter-eval-protocol-v1.json)のSHA256は`cb7d6cebf90549e8fa17b8cb393efaa00cdcd4783d9cb4edaf3da343533ac2f9`。元research sourceは`3694f80c39e6cd164a1a9a299e922d85bc75897c`で、protocol bytesは変更しない。[親SFT protocol](../../experiments/behavior-model/helpsteer2-private-sft-protocol-v1.json)と[27/8/16 manifest](../../experiments/behavior-model/helpsteer2-train27-manifest-v1.json)を同じ固定SHAで再利用する。[source-rights](../research/source-rights.json)には別用途record `helpsteer2-private-fixed-adapter-eval24-v1`を加え、旧dev/SFT/XSTest recordとその権限は維持する。評価recordはPRIVATEな固定adapter/元候補比較用途だけで、product/live/公開raw・weightsや新training権限を含まない。

`manager_core/helpsteer2_fixed_adapter_eval.py`と薄い`scripts/evaluate_helpsteer2_fixed_adapter.py`は、既存17sourceに新2sourceを加えた19のruntime import closureを使う。既存completion_mask/mean-NLL/JSON/hash/private checkpoint・標準native Qwen/PEFTを再利用し、新engine/framework/optimizer/generation/runtime ownerを作らない。SFT train CLIは評価の19closureから除くが、既存SFT source自体を削除・改変しない。

対象は同じ公開元候補のdevelopment8/final16を別々に扱う有限比較。NO_ACTION・短候補rule・native base・単一固定adapterを、科学定義の同順序・mask・96 model-forward assignmentsと分母で比較する。rule/NO_ACTIONのNLLはnull、NO_ACTION accuracyはnull。欠測・unknown・未実行・失敗を0や正答へ変換しない。原corpus/private per-ID結果、weights/adapter/private execution configはGitへ入れない。

## 実行authorityと結果の分離

科学protocolのPENDING、未artifact、final未採点等の表記はfreeze時のsnapshotであり、現在の実行状態を宣言しない。現在の状態はsource-versionに結びつく別のactual acceptance/receiptで確認する。実使用後の同じfinal16を新しい未見holdoutへ戻さず、QC内容曝露・person/study/time/semantic independence未確立も保持する。protocolを書き換えて過去の未見性や架空のPASSを作らない。

source import・main merge・条件付き用途rightsだけでは新G7 runを許可しない。実行にはその時点のsource/cwd/code/CI/review/resources、固定artifact/training receipt/exposure、別のroot-owned0400 G7 decision/configが必要である。後続code/CI/artifact/startのhashは外部config/receiptから科学protocolへ一方向に結び、科学protocol/rightsへ逆pinしない。historical research実行のreceiptを将来main commitへrehashせず、古いconfigを新commitへ転用しない。再学習・retuning・追加attemptをこの導入から開始しない。

sourceの正しさはmodel改善と別に評価する。改善がない結果や悪化も保持し、点推定だけでmodelを採用しない。public aggregateは別途sanitized receiptのreview・実source採択を経て扱い、本source導入は新しい実測aggregateを作成・exportしない。人便益/苦しみ減少はNOT_MEASURED、行動変容/害/圧力/依存はnull。full V002/V003・V004/D016、真正な未見評価/安全性・実運用の受入は別条件で、offline code landingの一律前提に戻さない。

## 検証と通常統合

既存`test_helpsteer2_fixed_adapter_eval.py`をそのまま導入し、既存focused6と同じCI verify stepに1moduleだけ追加する。stdlibのfictional pairs/fake native boundaryで、protocol/rights/parentの差替え拒否、same-mask/paired/null分母、partial failure、private checkpoint/CLI、標準adapter状態復元の境界を検証する。optional ML install・data/model download・実training/scoringはCIへ追加しない。

実装ownerはPR1の通常main統合後にactual mainとsource authorityを再確認し、専用worktree/branchでこの限定patchを適用する。focused tests、必要なowned-cycle/workflow回帰、source boundary・secret checks、fresh-context reviewを同じtreeで実施し、通常PRのexact headで全check完了/失敗0を確認後、`bin/merge-when-green <pr>`で統合する。CIのpermissions/schedule/publish/dispatch/ownerは変更しない。source PRで本番ownerやcanary/model推論を起動せず、runtime採用は別受入に残す。
