# AnnoMI — 既存資料から会話品質を学ぶための現物監査

2026-10-24 UTCの初回現物監査。既存の数値forecast研究とは別用途で、全会話の意味内容を精読したものではない。後日追加した限定offlineラベル評価の実施状況は、末尾の別節に記録する。人介入・行動効果・苦しみの低減は評価していない。

## 出典と現物

Zixiu Wu、Simone Balloccu、Vivek Kumar、Rim Helaoui、Ehud Reiter、Diego Reforgiato Recupero、Daniele Riboniの[ICASSP2022原著](https://doi.org/10.1109/ICASSP43922.2022.9746035)。[著者所属機関の配布PDF](https://aura.abdn.ac.uk/server/api/core/bitstreams/f0e68470-1d5e-4781-bb15-d8ddd9518e27/content)は5ページ、166,250 bytes、SHA256 `636a68fe5c257fcf1b3077f7424f6d9515b26208362e5e2b08e24971d217b31e`。Methodsのデモ映像・許諾・注釈者/IAAの記述を確認した。2023拡張論文はEhud Reiterを含まない6著者で、同じ7著者と仮定しない。[拡張原著 DOI10.3390/fi15030110](https://www.mdpi.com/1999-5903/15/3/110)の選択Methods/評価設計/Data Availabilityを追加読取した。取得テキストは最大65,000文字で、全論文読了とはしない。

[著者repo](https://github.com/uccollab/AnnoMI)の固定commitは`42936645ec3857a9c84ab296a36a3c34b779ef49`。README SHA256 `45fd4a9e30e3cf0f727f120159a8042eefc0dacdf1c4fe576859a4bfd815948c`。取得treeの3ファイルはREADME、simple/full CSVのみで、明示LICENSE fileはなく、GitHub license metadataもnullだった。一方、2022原著はPublic Domain license、2023原著Data Availabilityはfull版について明示的にPublic Domain Licenseと宣言する。この一次資料による宣言を記録し、license file不在を「利用禁止」と読み替えない。Public Domainを別の具体的なCC0/SPDX契約に書き換えず、原動画等を含む全用途の包括保証とも言わない。現在は原著参照と私有schema/集計監査に使用した。

| artifact | 実監査 | SHA256 |
|---|---|---|
| AnnoMI-simple.csv | 2,386,609 bytes、9,699行、11列、133 transcripts、119 source-video groups（YouTube116 / Vimeo3）。therapist4,882 / client4,817。high110 / low23 transcripts | `b178db3b0b9858a0fa4ed670dabeccd63e975ba67e141d7ae16f2e8214f78e61` |
| AnnoMI-full.csv | 3,795,371 bytes、13,551行、18列。unique transcript/utterance pairsは同じ9,699。annotator10人 | `3b60fec5e9d83cbb18ade0e412fb9afaef3b81724748a5d715f844bdd7432c9f` |

428発話がそれぞれ10回注釈され、それらは7 transcriptsに対応した。他9,271発話は1回の注釈。追加3,852行は新しい人/発話ではない。同じpairの本文不一致は0。原著の7共通transcripts・126単独注釈という設計と対応する。simple版のmain therapist behaviour/client talk typeをfull版の複数注釈428発話と照合すると、最多票候補から外れるラベルは0。同数票は各4/10発話で、全員一致とはしない。現実の患者133人や13,551件の独立した行動変化として扱わない。ID/本文は公開成果物へコピーしない。

## 学ぶものと、別に測るもの

simple/fullにはtherapistのreflection/question/therapist input等と、clientのchange/neutral/sustain talkがある。これは会話内の注釈であり、翌日の行動・持続・苦しみの低減を観測したgoldではない。high/lowはデモの品質区分で、映像のタイトル/説明等を基にしており、治療効果の比較群ではない。

2023原著は複数注釈を公開しつつ、解析・実験では多数決に集約すると明記する。原著が13,551行を独立発話として評価したと批判しない。2023原著のbaselineはutterance-level stratified5-fold CV、Macro F1等を用いる。原著再現と、Managerが将来主張する新しい対話への一般化は別の問い。新研究では同じ発話のannotator rows、同じ会話、同じ映像をsplit間へ漏らさない単位が必要になる。人物/actorの同一性や新しい人口への一般化は今回確認していない。動画視聴や外部の人物情報への照合は行わない。

**直接再利用した部分:** simple版のtherapist/client high-level labelsを、動画単位split・train-fold majority比較・未知/拒否/失敗を隠さない分類評価へ一度だけ使用した。full版の複数注釈は、合意/不一致を扱う方針なしに別例へ水増ししない。標準scikit-learn TF-IDF/logistic regressionを使い、専用trainerや学習済みadapterは作っていない。次のAnnoMI分析を自動許可するものではない。

**この資料からはできないこと:** 人に配信した際の行動効果や苦しみの軽減を認定すること、change talk分類の高得点を介入policyの便益へ昇格すること。offline evaluator内では分類器を各foldの学習部分へfitしたが、その重みは保存せず、生成/Manager modelのfine-tuningや運用runtimeへの組込はしていない。

## 限定offline評価の権利範囲と公開境界

原著がデータセットをPublic Domainと宣言していることを根拠に、固定revisionのsimple CSVを使う今回の**私有環境での集計専用研究**を実施候補として扱う。この判断は公開可視性やGitHubのlicense metadata nullを包括的な利用許諾へ読み替えるものではない。データセット内の動画・発話者・第三者素材の権利、同意、再識別可能性は別途検証していない。Managerのsource-rights.jsonはSafetyBenchが記録hashで固定しているため、このsource固有の判断をそこへ挿入しない。SafetyBenchの既存bindingを変更せず、今回のscopeを本監査書と凍結evaluation designに直接記録する。

許容範囲は、hash一致を確認した`AnnoMI-simple.csv`をクラウドの非公開scratch領域で一度処理し、動画単位splitの会話内ラベル分類と比較baselineを調べ、行・文章・transcript/video IDを含まない集計だけをManager repoへ記録すること。生CSV、行予測、人物/動画識別子、学習重みのrepo追加/配布、外部動画取得、製品利用、live persuasion/intervention、効果・臨床便益・苦しみの低減主張はこの判断に含まれずHOLDとする。集計結果から話者同一性や新しい人々への一般化も推論しない。次のversion・source・目的では権利と倫理範囲を再評価する。

今回の[固定評価設計](../../experiments/behavior-model/annomi-dialogue-evaluation-design-v1.json)と[実結果receipt](../verification/ANNOMI_DIALOGUE_EVALUATION_V1.md)では、5-fold stratified source-video group holdoutとtrain-fold majorityを比較した。YouTube/VimeoのIDをplatform別に正規化し、video-group交差fold漏洩は0。exact normalized utteranceは126文字列/2,415行が複数video groupに再出現し、見た/見ていない文章のOOF結果を分けて記録した。それでも同じ元話者が異なる動画に登場した場合の漏洩や集団一般化までは解決しない。Therapist macro-F1はmajority .1226→TF-IDF/logistic .6976（Δ+.5750、group-bootstrap 95% CI [.5508,.6007]）、clientは.2611→.5017（Δ+.2405、CI [.2112,.2706]）。client accuracyは.6440→.5904へ下がっており、単一accuracyで優位としない。

これはラベル分類の有限offline評価を完了した記録で、実際の説得/介入成功、選択・実行・持続、苦しみ/機能、臨床便益の評価ではない。各fold内で古典的なTF-IDF/logistic-regression分類器をfitしたが、重みを保存せず、生成モデル/Manager modelのfine-tuningや製品組込、live useは行っていない。AnnoMI部分sliceは完了したが、広いV002全体は未完のまま。
