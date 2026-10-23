# 有限PRIVATE train27 SFTの研究開始scope

> main source導入用の参照文書。以下の研究scope本文・旧snapshot・gate条件を保持し、研究branchのtask台帳リンクだけmainの単一SSOTへ接続する。元sourceはresearch commit `d255c6bd5e8d7e3ac38cae0a587bf213590cc27b`。この文書の追加・source mergeは新しいG6/G7実行許可ではない。科学protocol/manifestのbytesは変更しない。


2026-10-23 / prospective source proposal。**本書だけではsource採択、用途rights、protocol/resource/code受入、G6学習開始、G7評価を許可しない。** R2で設計上の阻害findingは解消したが、そのreviewは実行受入ではない。rootが正規source整合・独立review・実採否を所有する。

## 対象と全体受入の分離

HelpSteer2 exact retained train27の各組から、人の元preferenceが選んだ元応答1本だけを、既存native Qwen3-0.6Bへcompletion-only LoRA/SFTする一回の有限研究を対象とする。estimandは、別に固定した元候補の平均completion-token NLL選択と公開元preferenceとの一致の変化だけである。SFTはpairwise rankingの直接最適化ではなく、改善は保証しない。失敗、部分到達、無変化、悪化も正直な研究結果として保存し、採用と分ける。

読取HEAD `42e3281a14d6f98360b6d9ff34587c22afc032e2` のV001/V002/V003 todo・113 IDs/80 done/23 todo/10 skippedは**過去snapshotのみ**。本SFT scope/結果だけではstatus/件数/全体依存を変えない。別に採択・検証・記録された限定V001設計受入なら、[mainの単一SSOT](../../../../docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md)の現在status/件数を参照し過去snapshotへ巻き戻さない。旧literal条件のUNMET/HOLDは保存し、新用途受入を旧条件達成へ偽装しない。全体V001→V002→V003、V004=[V003,D016]の意味はそのまま保持する。

全V002完了をこの有限routeの一律前提としない。元candidate/goldの正確なsource結合、同条件baseline、不足・測定限界を用途別に受け入れる。dev8のnative base4/8・短候補rule4/8は探索動機に限り、有用性・優位・同等性の証明ではない。本研究は同じnative baseへの有限SFT差を問うためAPI比較を必須としない。全V002のAPI比較要件、API/費用優位は未達のまま残す。

新生成、新応答品質、人/研究/時間/意味family/言語/OODへの外挿、害/圧力/依存/安全性、臨床能力、行動変容、苦しみの減少、AGI、製品/live用途は対象外HOLD。person/study/timeはUNAVAILABLE、language/family/OODはUNKNOWNを保持する。この有限estimandから外すためのN/Aは、それらholdout/OOD detectorの存在・合格を意味しない。列欠落だけをN/Aの理由とせず、exact/canonical交差非重複・元応答/label結合・final隔離は必須とする。

## 固定対象・曝露・権利

[train27 manifest](../../experiments/behavior-model/helpsteer2-train27-manifest-v1.json)はexact27の元row、prompt/両responseのexact/canonical hash、source quality join、preference符号・1-based chosen index/hash、既存token/mask長を結合する。root numeric intakeは27 mappingと54 joinsを解決したmetadataであり、training受入ではない。実token/maskは許可されたruntime構築後に再検証する。選好元候補1本だけをtargetとし、justification、非選好target、dev/final、few-shot/retrievalは禁止。

旧train32は27 retain/5 excludeのNOT_READYで保持し、新27版を別に作る。32は科学的最低Nと証明されていない。補充、除外5復帰、split移動をしない。旧private案のchosen UNKNOWNと一律all-validation-before-import文は歴史として保存し、後者は採用しない。旧strict8 dev-only evaluator/protocol/rightsと実receiptは変更・権限拡張しない。

全56 prompt/112 responseはdevモデル採点前のAI支援適格性QCで内容曝露済みで、final16もpristine/完全未閲覧/人盲検ではない。原選択はpreference/quality閾値を使った。記録上final16は対象モデル未学習・未モデル採点・設定選択未使用だが、全私有領域の履歴監査を主張しない。QC時点/役割/不明reviewer、既知dev成績、QC後の設計変更、不明履歴をmanifest台帳に残し、G7前に再確認する。paraphrase/pretraining汚染はUNKNOWN。hash非重複を意味family独立・未汚染と呼ばない。

[source-rights](../research/source-rights.json)の別用途record `helpsteer2-private-exploratory-sft-train27-v1` は、実root AI engineering/research reviewerの2026-10-23T19:20:38.332175+00:00判断により、exact27 PRIVATE前処理/SFT/私有adapter保管の用途を条件付き受入とした。判断receiptはprivate basename/SHAのみをrecordへ結合する。既存AI QCとmetadata/source-binding reviewを採用して以前のpending manual/root reviewをこの有限用途だけに解決し、新しいhuman/raw-text manual reviewは主張しない。exact reviewed source integrationとprotocol/code/CI/resource/G6は未受入、G7は別pendingで、旧recordは不変とする。CC BY宣言を全第三者/privacy clearanceとせず、ShareGPT/Scale由来、具体的既存QC限界と残存risk、pending root/manual reviewの解決根拠、NVIDIA/CC BY・Qwen/Apache帰属・変更表示を記録する。常に弁護士/IRB必須という条件は加えない。公開raw/weights、広いcommercial training、product/liveはHOLD。具体的問題が出た場合は隔離・別versionとし黙って置換しない。

## 独立したgate

| gate | 実受入に必要な証拠 |
|---|---|
| G0 scope | 正規source整合、旧条件/archive/依存保持、独立review、実root採択。限定V001受入とは別 |
| G1 rights | exact27 PRIVATE前処理/SFT/adapterの新record、CC BY/Apache帰属・変更、残存riskとpending review解決の実root判断 |
| G2 manifest/protocol | 新version/hash、27/8/16・除外5、元gold/choice/hash/source join、exact/canonical交差検査、曝露変更台帳・final隔離 |
| G3 scoped evidence | 元人preference source/join独立照合、dev既知receipt、有限仮説、同入力/分母/失敗/資源比較とnull限界。全V002受入の代替ではない |
| G4 code/recipe | immutable code、base/tokenizer/package/source、mask/LoRA/optimizer/seed/order/tail/save/失敗規約、focused検証/独立review/必要CI。後段期待述語を事前固定 |
| G5 resource | 実host/memory/disk余裕・私有ACL/予定native inventory、累積900s/6GiB RSS polling、own-process watchdog/TERM/KILL/reap、失敗/cleanup/private receipt、network/新有料resource禁止 |
| G6 start | G0–G5の受入evidence hash、独立expected protocol hash、固定scope/保存先へ結合した実root判断。一recipe/初期adapter/一attempt、retry/resume/予算延長なし |
| G7 fixed comparison | 実training/save receipt、完全inventory/hashと最終adapter/全選択凍結、別prospective dev8/final16 protocol/評価用途rights/資源、曝露再確認、独立reviewと別root評価実行判断 |
| G8 full adoption/live | 現全V003の真正な未見評価・優位/安全性、V004/D016の実結果/保護/権限等が別に必要。このrouteは満たさない |

G0単独でG1–G6を受け入れたとしない。source/chosen/rights/protocol/recipe/code等の必須pin/受入欠落・UNKNOWN・不一致は次段階を停止する。一方、用途限定で受け入れた第三者/汚染残存risk、実fit/compute/費用未測定、実row順NOT_OBSERVEDを一律開始禁止にしない。推論1.78GiB/28秒はtraining fit証明ではない。RSS pollingはkernel hard capではなく、空きdiskはcapではない。disk quotaや新強制機構を必須化しない。失敗/不完全保存を成功へ昇格しない。

## G6内の段階別述語

[prospective SFT protocol](../../experiments/behavior-model/helpsteer2-private-sft-protocol-v1.json)が次の順序を固定する。追加のroot確認をruntime観測ごとに要求せず、G7だけ別に残す。

科学protocolはrecipe/data/manifest/rights/native-helper/packageと期待stage述語を固定する静的定義である。実rights/manifestはprotocol freeze前にfinalizeできる。新core/script/watchdog・final source commit・CI・実G0–G6/start/resource受入のhash/判断は、後に作る独立root所有0400 execution config/receiptがprotocol SHAと一方向に結合し、protocol自身へ逆pinしない。protocol内PENDING/HOLDは準備・freeze時のsnapshotであってcurrent実行authorityでも将来実受入を永久拒否するliteralでもない。PREIMPORTは外部実root受入と具体的code/resource/evidence pinsの存在・一致を要求し、consumer built-in SHAで科学protocolのexact bytesを検証する。caller-only hash/再承認で科学定義の差替えを許可しない。この準備は外部config/receiptを作成しない。

1. PREIMPORT: 実scope/G6/用途rights、独立expected protocol hash、source/model/tokenizer/package/code、exact27 source/gold/chosen、recipeと後段期待述語、資源/watchdog/ACL/save/privacyを照合。必須binding UNKNOWNは禁止。実fit/row順/実mask/gradientを架空の事前PASSにしない。
2. POST_NATIVE_LOAD_PEFT_BEFORE_FIRST_BACKWARD: 標準native load/tokenization/PEFT/optimizer構築後に、全train27のprefix一致・full<=256・EOS inclusive・prompt/EOS後/pad除外、adapter-only実names/count/dtypes、初期finite adapter、optimizer集合一致を実測。gradientはまだNOT_RUN。
3. AFTER_BACKWARD_BEFORE_EACH_OPTIMIZER: 実backward/clip後、各step前に固定None方針とfinite gradientを観測。不成立ならそのstepへ進めず実到達receiptを保存する。backwardは実学習試行でありpreflight/testではない。
4. STEP_RETURN_AND_TRAIN_RETURN: optimizer呼出し/return、skip実観測またはUNKNOWN、parameter変化、予定/実到達機会、train returnを別に記録。global_stepは成功更新数・完走・保存成功を証明しない。
5. SAVE_AND_FREEZE: 標準save_model一回の呼出し/return、tokenizer/training_args.bin等の全実inventory/size/hash/ACL/fsync、不完全失敗、最終manifest/hashを別に固定。pickleをloadせず、保存成功をon_train_end/on_saveだけから主張しない。数値無変化は実測陰性として区別する。

標準native PEFT/TRL/SFTTrainerと既存completion_maskを使い、新trainer/optimizer loop/frameworkを作らない。CPU2/BF16、q/v r8 alpha8 dropout0、FP32へ標準昇格するadapter、AdamW2e-4 constant、batch1/accum4/27一epoch/max_steps=-1、7機会(4×6+3)、seed/data_seed42、checkpointなしをprospectiveに固定する。実消費順をcallbackへないrow IDから捏造しない。

G7比較はbase/固定adapter/短候補rule/NO_ACTIONを同じ元候補、dev8/final16別々のassigned/valid/failure/missing/paired分母と共通資源で比較する。rule/NO_ACTIONにdummy model計算をせずNLL=null、NO_ACTION accuracy=null。ABSTAIN/UNKNOWN/NOT_RUN/欠測を正答/0にしない。最終結果によるrecipe/候補/閾値/adapter選択はせず、変更は別versionと別の目的適合holdoutを要する。

## 判断の費用と記録

用途N/Aを誤れば未見人/未来/分布外で破綻し、API省略はより良い/安いAPIを見逃し得る。小27は過学習・大きな不確実性を持ち、第三者由来/QCは権利/privacy見落としを残す。QC後設計はfinal適応を招き得る。一律UNKNOWN拒否は永久停止/架空PASS圧力を生み、逆に必須pin未知を許せば誤学習する。段階混同は虚偽更新/保存成功を生む。各費用を限定claim・実binding・曝露台帳・失敗保存・独立reviewで扱い、結果が弱くても受入基準を後から緩めない。[具体的計画](../plans/2026-10-23-helpsteer2-private-sft.md)に実装/検証/実行の責任を分ける。
