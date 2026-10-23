# HelpSteer2 train27 PRIVATE SFT — 実CPU学習と単一adapter保存

2026-10-23 UTC。**ONE_FINITE_PRIVATE_TRAIN27_ATTEMPT_COMPLETED / ARTIFACT_FROZEN**。既存native Qwen3-0.6Bへ標準PEFT/TRL SFTTrainerで27本の元chosen responseだけをcompletion-only SFTする1回を完了し、private adapterを全11file保存した。これは元候補の選好一致を問うP0研究の訓練・保存段階の実結果である。固定adapterの新規target-model dev8/final16採点は **NOT_RUN / G7 NOT_ACCEPTED**。モデル優位・同等性・一般化・安全性・行動変容・人の便益・AGI/覚り・live採用の認定ではない。

[有限研究scope](../specs/2026-10-23-finite-private-sft-research-start.md)、[実装subplan](../plans/2026-10-23-helpsteer2-private-sft.md)、[親model計画](../plans/2026-10-23-behavior-transformation-model-plan.md)、[prospective評価科学定義](../plans/2026-10-23-helpsteer2-fixed-adapter-eval.md)へ結ぶ。使命は「行動変容を通じて、苦しみを終わらせることを目指す。」。Managerは一つの主体を目指し、人のapp/chat/毎回の操作を通常活動の前提にしないno UIの定義を維持する。

## 実受入から正常終了まで

| 実段階 | UTC / 実結果 |
|---|---|
| G0有限source・評価科学のprospective採択/freeze | 19:59:07.182754Z。学習・adapter作成・新規target-model採点より前 |
| exact-source公式CI | source `d255c6bd5e8d7e3ac38cae0a587bf213590cc27b`、[run40016653728](https://github.com/Daisuke134/life-manager/actions/runs/40016653728)/[job120630338115](https://github.com/Daisuke134/life-manager/actions/runs/40016653728/job/120630338115)、20:07:30Z completed/success |
| 実G0–G6一attempt受入 | 20:09:24.773748Z。exact27 PRIVATE用途・code/CI/review/resourceの有限受入 |
| 外部root所有0400実設定freeze | 20:09:24.775497Z。scienceへ一方向pins。future自身commit/hashをscienceへ逆pinしない |
| 内monitorの実行 | 20:09:45.449559Z→20:11:07.426371Z、81.977秒、EXITED_SUCCESS/return0 |
| 終了直後のsource/terminal proof | 20:12:02.641401Z。source HEAD=d255、full source clean、source18 hash一致 |
| 独立実結果検証 | 20:14:33.290347Z、58checks全一致、0 findings (0 blocking)、SPEC/QUALITY PASS（有限実結果検証のみ） |
| 単一保存adapter固定 | 20:16:39.598466Z。rootが新規target-model dev/final採点前に固定。run/checkpoint/成績に基づく選別なし |

研究branchは `research/manager-e06-cloud-execution-20261022`、canonical originは `https://github.com/Daisuke134/life-manager.git`。source guardはactual **FAIL exit2 / canonical host不在**。既存の明示owner cloud許可による処置を保持し、PASSに置換しない。終了直後のcleanはその時点の実証跡であり、後続の別fixed-eval source作業を学習中の変更とみなさない。

公式full suiteは1097tests / skip6 / 34.600秒、既存localは1123tests / skip5 / 28.094秒。差26の原因はUNKNOWNで一致としない。既存argparse診断・Node deprecation警告も保持する。CI成功を学習・保存・性能の証明にせず、後続実証跡を別に確認した。

## 実学習で確認した段階

exact train27の人の元preferenceが選んだ元応答1本だけを用いた。標準ONE SFTTrainer/train、標準save_model1回、CPU2/BF16 base・FP32 q/v LoRA r8/alpha8/drop0、batch1/accum4/1epochの凍結recipeである。最終resultは `COMPLETED / ARTIFACT_FROZEN`、event_sequence=61、train_returned=true / save_returned=true。

- 初backward前に期待112 trainable tensors・1,146,880要素のnames/shapes/FP32/finiteとoptimizer identity集合を検査したruntime証跡がある。
- 実backward-microbatch完了下限27、optimizer機会7・return7、global_step7、skip観測0/skip-UNKNOWN-return0、last_step_was_skipped=false。7回の数値更新をglobal_stepだけから認定しない。
- 凍結codeは各optimizer前（実backward/clip後）のgradient存在/finiteを要求し、最終finite_gradients=trueと正常train returnに整合する。中間checkpointは上書き式で、全61 eventのappend-only履歴を再構成したとはしない。
- 実消費row順はNOT_OBSERVED、baseのin-memory数値不変はNOT_MEASURED。dev8/final16/excluded5のoptimizer入力除外は凍結loader経路・metadata結合・正常終了に基づく。実batch IDの独立観測とは区別する。

## 数値変化と保存の証拠

runtimeのchanged_adapter_tensors=112は標準PEFT構築直後の実in-memory cloneと訓練後の比較による提供証跡である。初期tensor artifactは保存しておらず、独立reviewerが全112tensor初期差分を復元した結果ではない。

独立safe_open検査では保存112keysの集合・shape・FP32、1,146,880要素、全要素finiteを確認した。標準PEFTのinit_lora_weights=trueのB zero初期化に対して、保存B56tensor全てが非zero（688,128非zero要素）なので、**独立変化下限は56tensor**。A56初期値の再構成や全112の独立変化証明へ拡張しない。本receipt作成自体はJSON/証跡のstdlib読取のみであり、ML/tensor/pickleの再loadはしていない。

標準save return後、凍結sourceは保存tensorのfinite/最終in-memory値一致、全file fsync・adapter directory fsync、最終metadataのtemporary/fsync→replace→directory fsyncを要求する。正常model exit0と外部EXITED_SUCCESSはこの経路に整合し、COMPLETED JSON単独を保存成功の証明にしない。独立検証は過去の全fsync syscallや電源断試験を再観測したものではない。外部monitor receiptにnative最終writerと同じfsync保証を主張しない。

全11fileは非empty・regular・owner一致・single link・0600、対象親dirは0700、追加POSIX ACL xattrなし。tokenizerとtraining_args.binも含む完全inventoryを照合し、training_args.binはbytes/hashのみでpickleを開いていない。

| 保存file | bytes | SHA256 |
|---|---:|---|
| README.md | 5316 | `87e28285137092b48327ad220604c2cf30d76e596b3e3998317b14c3365ab943` |
| adapter_config.json | 907 | `2590184a912b0219978838fdaf7fa9ef521a1c8bcc93a217bddcb9fa5d9ba163` |
| adapter_model.safetensors | 4602248 | `84481574261138b6bf5ac7f683a96b0342e3e02b564c577bbc8694903cd1c81c` |
| added_tokens.json | 707 | `c0284b582e14987fbd3d5a2cb2bd139084371ed9acbae488829a1c900833c680` |
| chat_template.jinja | 4168 | `a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8` |
| merges.txt | 1671853 | `8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5` |
| special_tokens_map.json | 613 | `76862e765266b85aa9459767e33cbaf13970f327a0e88d1c65846c2ddd3a1ecd` |
| tokenizer.json | 11422654 | `aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4` |
| tokenizer_config.json | 5404 | `443bfa629eb16387a12edbf92a76f6a6f10b2af3b53d87ba1550adfcf45f7fa0` |
| training_args.bin | 6417 | `5bf6713fdf6609bbfa81d52b1b63a11c4b78bfe325eee3a7210f8dd52be20529` |
| vocab.json | 2776833 | `ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910` |

inventory canonical SHA256: `9ed8f7e04d9bd601a77e6bad78694d4ed5cfaab3e2b03dd3efad7b890bdc3b7b`。

## 資源・終了・未測定事項

sampled own-process-group peak RSSは3,036,762,112B（2.828205GiB）、6GiB polling threshold=6,442,450,944B以下、wall81.977秒は累積900秒以内。0.05秒sleepにproc scan時間が加わり、共有mappingの二重計数もあり得る。生の全poll系列は保存しておらず、連続peak・完全なpoll gap系列・瞬間的な全child・kernel hardcap遵守を認定しない。実インフラ$費用はUNKNOWNで、$0にしない。

内model childはwait/reaped/absent=true、残group空、return0、TERM=false/KILL=false、retry0。別sessionの外側monitorもparentのactual wait/reaped/absent=true、return0、82.049秒。内外0.072秒差は測定境界の差で、予算延長ではない。stdoutはredacted aggregate256B、stderr0B。1attempt/no retry/resume/延長/network/新有料resourceは設定・launch・監視証跡の範囲で整合し、全host履歴の独立不在証明とはしない。無関係なprocessへsignalを送っていない。既存の別nonchild zombieは本model cleanupと区別し、reapedに読み替えない。

## Private証拠のbasenameとhash

raw/weights/tokenizer/runtime実pathはGit外PRIVATEに保存する。本書はbasename・hash・集計metadataだけを接続する。

| 私有証拠basename | SHA256 |
|---|---|
| whole-preexecution-review-r2.md | `ca1fbe23a8bf2adeab244edc108959db7b6d573a8a060fee6ca6c99e47a0a0a9` |
| official-ci-accepted.json | `b70c23293888511b0580de6b7e5135719473e48368dbbff2934f492e6319da3b` |
| root-preexecution-G0-G6-accepted.json | `e834e6d784b12d73adb96013e6de852307c845e916ea402d769f54075ef37f5a` |
| execution-config-v1.json | `06855d194efcab863050779e137190f21ec2c16df40d6a4d59028855d2d62dd4` |
| root-execution-config-freeze.json | `aaf2a0f9ee45382fc028bb0823e8568d037ebb0204f49af522b75118ab6c2a87` |
| root-actual-launch-v1.json | `7dec61e269f93e676e0aedcad5cbf6d6ae3214571b676f3eb7b63acc23f4ede8` |
| execution-receipt.json | `21d0d2775aa64bbba6ca46c04b9cb11cf728a75436713181166fefb0f017f5a8` |
| result.json | `c1d805188e91c527f784eb8d288839021f7b5d218d97d2961bd6ec7a48f62140` |
| root-posttraining-source-and-terminal-proof.json | `ff99b989207f070b64b7c7f596bddcf9ca737a789b00d885ea0ab9cafc515c2f` |
| actual-result-verification.md | `87ede0de154ccd8a4eded0675e3050b539baf4073c9f58b9cfff208ffb568200` |
| actual-result-verification.json | `0aacb6cbac478d721b6b332b63be806031ae5f6ebb7c6b52e0ad99f6b936f7bf` |
| root-single-adapter-freeze-v1.json | `93f63b8de8cfc0675b388a77425d4159cb00d0259917d849b1ecc6ff99015020` |

不変のtraining science SHAは `eb2e585321d954d507af52b1bf71db9eb3b7ae3150273484909b6aeeae48a53d`、manifest `7547ff63f7c06f8196689b3890288417154012d71e9609d0a3db232eeb0f182e`、train-purpose rights canonical `f41063b9ae281bc5bc1677655cb5a5997b1c9b5de8857ac180480176d71a1be5`。評価science `cb7d6cebf90549e8fa17b8cb393efaa00cdcd4783d9cb4edaf3da343533ac2f9`、評価rights canonical `088f6cc5a17f8ff3c83dfc10b44bca70dbd0855d3dd0c8b1063727ff2271225d`、旧dev-only rights canonical `0b76b970e877dc17a6fc21c18979c9c7efaf4e1e6053c01a9c13577ee2920a41`も変えない。

## 次の固定比較と全体の未完了

単一artifactは上記root freeze時点で固定済み。prospective学習前評価scienceに基づき、別の薄い評価entry/CLI・意味のあるsynthetic tests・独立code review・exact-source公式CI・実resource・外部root所有0400 bindings・実G7判断を採点前に受け入れる。現時点でそのsource作業は進行中で、実装完了・review/CI readyとは扱わない。元候補のbase/固定adapter/短候補rule/NO_ACTIONをdev8/final16別々のassigned/valid/failure/missing/paired分母で比較し、rule/NO_ACTION NLL=null、NO_ACTION accuracy=null。final結果を見てrecipe/候補/閾値/adapterを選別しない。G6はG7権限を生まない。

旧dev4/8対rule4/8、XSTest旧3class・専用native binaryの不採用結果、旧train32=27 retain/5 exclude NOT_READY、補充/除外復帰/split移動なしを保持する。final16は内容QC曝露済み・NOT_PRISTINE、記録上未学習/未モデル採点で、完全盲検ではない。person/study/time UNAVAILABLE、language/family/OOD・paraphrase/pretraining汚染UNKNOWNを成功へ変換しない。用途rightsは既存AI QC採用によるexact27 PRIVATE条件付きAI engineering/research判断で、人の法律/IRB/同意署名や全第三者clearanceを創作しない。

正規[task台帳](../roadmap/tasks.json)は113 IDs=83 done / 20 todo / 10 skipped、V003はstatus=todo / implementation_status=SCOPE_REVISED_ACCEPTANCE_NOT_COMPLETED、全V002/V003の元依存と一般化/安全性受入は未完。今回V003のimplementation_evidenceへ本receiptだけを追記する。V004=[V003,D016]、旧V001/G001/G002有限設計done・運営UNADOPTED/実外部監査NOT_PERFORMED、D014/D015/U004の実研究条件・保護、参加者0/募集なし・臨床未実施と元研究hashは不変。新記事/site/outreachは後段で、公開/送信/production配備は実施していない。sourceのcommit/push/remote readbackはrootの後続作業であり、将来のcommit/refを先取りしない。

**実結果sourceの実採択:** fresh whole actual-result review R1は0 findings / 0 blocking、SPEC・QUALITY・INTEGRATION PASS。私有report `whole-actual-result-review.md` SHA256 `dae542b6e05a3476c4b7810c5611742f0d1febb0957e49b9dfc7e756eb3e091e`。rootは2026-10-23T20:25:52.617521+00:00に有限train/save結果だけを採択し、review済み10文書を実適用した。私有receipt `root-actual-finite-result-source-adoption.json` SHA256 `6487927c24b54b134722565639400a875becde2eef3a7989d608e32fab8c890a`。これは別G7・モデル優位・人の便益や全V003完了の受入ではない。
