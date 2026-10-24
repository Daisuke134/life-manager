# AnnoMI — 既存資料から会話品質を学ぶための現物監査

2026-10-24 UTC。新しい学習/モデル採点/人介入は行っていない。既存の数値forecast研究とも別用途。これは有限な現物監査で、全会話の意味内容を精読したものではない。

## 出典と現物

Zixiu Wu、Simone Balloccu、Vivek Kumar、Rim Helaoui、Ehud Reiter、Diego Reforgiato Recupero、Daniele Riboniの[ICASSP2022原著](https://doi.org/10.1109/ICASSP43922.2022.9746035)。[著者所属機関の配布PDF](https://aura.abdn.ac.uk/server/api/core/bitstreams/f0e68470-1d5e-4781-bb15-d8ddd9518e27/content)は5ページ、166,250 bytes、SHA256 `636a68fe5c257fcf1b3077f7424f6d9515b26208362e5e2b08e24971d217b31e`。Methodsのデモ映像・許諾・注釈者/IAAの記述を確認した。2023拡張論文はEhud Reiterを含まない6著者で、同じ7著者と仮定しない。[拡張原著 DOI10.3390/fi15030110](https://www.mdpi.com/1999-5903/15/3/110)の選択Methods/評価設計/Data Availabilityを追加読取した。取得テキストは最大65,000文字で、全論文読了とはしない。

[著者repo](https://github.com/uccollab/AnnoMI)の固定commitは`42936645ec3857a9c84ab296a36a3c34b779ef49`。README SHA256 `45fd4a9e30e3cf0f727f120159a8042eefc0dacdf1c4fe576859a4bfd815948c`。取得treeの3ファイルはREADME、simple/full CSVのみで、明示LICENSE fileはなく、GitHub license metadataもnullだった。一方、2022原著はPublic Domain license、2023原著Data Availabilityはfull版について明示的にPublic Domain Licenseと宣言する。この一次資料による宣言を記録し、license file不在を「利用禁止」と読み替えない。Public Domainを別の具体的なCC0/SPDX契約に書き換えず、原動画等を含む全用途の包括保証とも言わない。現在は原著参照と私有schema/集計監査に使用した。

| artifact | 実監査 | SHA256 |
|---|---|---|
| AnnoMI-simple.csv | 2,386,609 bytes、9,699行、11列、133 transcripts、119 video URLs。therapist4,882 / client4,817。high110 / low23 transcripts | `b178db3b0b9858a0fa4ed670dabeccd63e975ba67e141d7ae16f2e8214f78e61` |
| AnnoMI-full.csv | 3,795,371 bytes、13,551行、18列。unique transcript/utterance pairsは同じ9,699。annotator10人 | `3b60fec5e9d83cbb18ade0e412fb9afaef3b81724748a5d715f844bdd7432c9f` |

428発話がそれぞれ10回注釈され、それらは7 transcriptsに対応した。他9,271発話は1回の注釈。追加3,852行は新しい人/発話ではない。同じpairの本文不一致は0。原著の7共通transcripts・126単独注釈という設計と対応する。simple版のmain therapist behaviour/client talk typeをfull版の複数注釈428発話と照合すると、最多票候補から外れるラベルは0。同数票は各4/10発話で、全員一致とはしない。現実の患者133人や13,551件の独立した行動変化として扱わない。ID/本文は公開成果物へコピーしない。

## 学ぶものと、別に測るもの

simple/fullにはtherapistのreflection/question/therapist input等と、clientのchange/neutral/sustain talkがある。これは会話内の注釈であり、翌日の行動・持続・苦しみの低減を観測したgoldではない。high/lowはデモの品質区分で、映像のタイトル/説明等を基にしており、治療効果の比較群ではない。

2023原著は複数注釈を公開しつつ、解析・実験では多数決に集約すると明記する。原著が13,551行を独立発話として評価したと批判しない。2023原著のbaselineはutterance-level stratified5-fold CV、Macro F1等を用いる。原著再現と、Managerが将来主張する新しい対話への一般化は別の問い。新研究では同じ発話のannotator rows、同じ会話、同じ映像をsplit間へ漏らさない単位が必要になる。人物/actorの同一性や新しい人口への一般化は今回確認していない。動画視聴や外部の人物情報への照合は行わない。

**直接使う候補:** 会話内の分類/annotation fidelityを学ぶ有限offline研究。まず既存simple版の高level labelsを再利用するsource-specificな小さな評価契約、動画/会話単位split、class baseline、未知/拒否/誤りを固定する。full版の複数注釈は、合意/不一致を扱う方針なしに別例へ水増ししない。通常のPEFT/TRLや既存分類scorerを再利用し、専用trainerを作らない。

**この資料からはできないこと:** 人に配信した際の行動効果や苦しみの軽減を認定すること、change talk分類の高得点を介入policyの便益へ昇格すること。今回、新しいdata/scorer/modelをManagerへ組み込んだり、次の学習を開始したりしていない。
