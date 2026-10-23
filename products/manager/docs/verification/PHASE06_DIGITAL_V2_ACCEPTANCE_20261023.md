# Phase06 v2 — 技術P2の個別受入記録

E01–E16は[限定実稼働能力の総合受入](E16_DEPLOYED_ACCEPTANCE_20261023.md)で完了。下のFは指定順に個別判定する。状態の正本は `../roadmap/tasks.json`。根拠となる[版付き結果](PHASE06_DIGITAL_V2_RESULT_20261022.json)のv5はcommit `254f83b98` に固定され、各taskのcompletion receiptでそのSHA256を保持する。

## F005 — 所有公開面の実配信

**受入: 技術P1/P2のみ。** finance `61909d20220fcf14132a6f5f459ce19796f1fc2d`、parent `d33d251ec0b82bf541a727ead7d1ede39f0a8216`、Pages39893109952成功、03:07:59 UTCの独立7 GETとimmutable bytes一致を照合。変更は許可7パス内に限られる。他の6ファイルもsource-version footer等で変化しており、それらのbyte不変を主張しない。

公式NO_ACTION39882336050はMISSING_TYPED_CANDIDATE／writes=0。後続のNOT_DUEは別のscheduler判断。最終fresh39909274852は保存済みoccurrenceの照合後NOT_DUE／writes=0、現在tip=faf18b3不変。これを新規positive canaryに数えず、finance初回UNKNOWN／writes=nullを保持する。人の便益はNOT_MEASURED。

## F006 — 版付き報告

**受入: 未判定。** 判定時にbaseline／比較／欠測／費用／害と、技術基準の事前固定・人間outcomeの未測定を個別に照合する。

## F008 — 別テーマのP2と復元可能性

**受入: 未判定。** mentalの過去occurrence、実復元、後続の現在配信を区別して判定する。

## F009 — 共通kernelの統合

**受入: 未判定。** F006／F008受入後、共通kernelと独立した外部readback、NO_ACTION／replay、限界を統合して判定する。

## 全項目で保持する境界

同じsite・owner・bundleに属する2ページの技術再利用であり、独立した人間試験2件ではない。P3/P4、理解・賛成・意図・行動・持続・苦痛低減は未測定。人の観測n、効果量、95% CIはnull、費用実請求はUNKNOWN、害はUNKNOWN_HARMS。旧F004/F007/H005はskippedで、Gate 1独立RCT再現はUNMETを保持する。
