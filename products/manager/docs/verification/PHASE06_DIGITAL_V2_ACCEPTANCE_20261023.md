# Phase06 v2 — 技術P2の個別受入記録

E01–E16は[限定実稼働能力の総合受入](E16_DEPLOYED_ACCEPTANCE_20261023.md)で完了。下のFは指定順に個別判定する。状態の正本は `../roadmap/tasks.json`。根拠となる[版付き結果](PHASE06_DIGITAL_V2_RESULT_20261022.json)のv5はcommit `254f83b98` に固定され、各taskのcompletion receiptでそのSHA256を保持する。

## F005 — 所有公開面の実配信

**受入: 技術P1/P2のみ。** finance `61909d20220fcf14132a6f5f459ce19796f1fc2d`、parent `d33d251ec0b82bf541a727ead7d1ede39f0a8216`、Pages39893109952成功、03:07:59 UTCの独立7 GETとimmutable bytes一致を照合。変更は許可7パス内に限られる。他の6ファイルもsource-version footer等で変化しており、それらのbyte不変を主張しない。

公式NO_ACTION39882336050はMISSING_TYPED_CANDIDATE／writes=0。後続のNOT_DUEは別のscheduler判断。最終fresh39909274852は保存済みoccurrenceの照合後NOT_DUE／writes=0、現在tip=faf18b3不変。これを新規positive canaryに数えず、finance初回UNKNOWN／writes=nullを保持する。人の便益はNOT_MEASURED。

## F006 — 版付き報告

**受入: 版付き技術報告。** 結果JSON v5にbaseline d33d、finance／mentalの各parent・SHA・時刻、NO_ACTIONとNOT_DUEの別記録、欠測・費用・害を照合した。技術criterion／厳密byte verifierは公開main3402fcfb30302e5dd2ef2d9b4fd0797771e761ad（02:48:54 UTC）で、baseline観測02:46の後、介入03:05／04:03より前に固定。結果報告は05:10以後の事後作成であり、人間試験の事前登録と呼ばない。human n／効果量／CIはnull、P3/P4はNOT_MEASURED、費用実請求UNKNOWN、害UNKNOWN_HARMSを保持した。

## F008 — 別テーマのP2と復元可能性

**受入: 別テーマの技術P2と可逆性。** 固有URL mental.html、元commit374cb9ac73d1bd703e44c452e8d5c7ae60d9ad7f／parent finance61909d2、Pages39898291117、04:05:49 UTCの独立7 GETを照合。native P1は1 commit_occurrence、P2は26,866 HTML byte。実rollback c6d5de0はmental cueを除去しfinanceの全7ファイルへ復元した。fresh resume後の新faf18b3では06:03:29 UTCにfinance／mental両cueを再確認。元のmental初回UNKNOWNを保持し、過去と現在の配信を別occurrenceとして扱う。2施設／2人間試験、精神的便益、臨床効果を認定しない。

## F009 — 共通kernelの統合

**受入: 未判定。** F006／F008受入後、共通kernelと独立した外部readback、NO_ACTION／replay、限界を統合して判定する。

## 全項目で保持する境界

同じsite・owner・bundleに属する2ページの技術再利用であり、独立した人間試験2件ではない。P3/P4、理解・賛成・意図・行動・持続・苦痛低減は未測定。人の観測n、効果量、95% CIはnull、費用実請求はUNKNOWN、害はUNKNOWN_HARMS。旧F004/F007/H005はskippedで、Gate 1独立RCT再現はUNMETを保持する。
