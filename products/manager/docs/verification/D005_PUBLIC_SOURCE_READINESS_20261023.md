# D005 — 公開測定のsource監査と未充足の受入条件

2026-10-23。元D005は「屋内測定と外気・気温・湿度を時刻・単位付きで接続」「無効・欠測・校正外を自動排除し元データへ遡る」。F008は受入済みだが、**D005はtodoを維持する**。以下は実際に取得した公開測定の監査であり、環境改善・健康便益・D006以降の受入ではない。

## UCI SML2010

[公式dataset](https://archive.ics.uci.edu/dataset/274/sml2010)、DOI [10.24432/C5RS3S](https://doi.org/10.24432/C5RS3S)、[配布ZIP](https://archive.ics.uci.edu/static/public/274/sml2010.zip)を取得した。datasetはCC BY4.0。ここでは帰属と出典を伴う最小の集計事実だけを記し、居住・行動のraw行を転載しない。

- ZIPは206991 bytes、SHA256 `c270da7bca968dba4c117c3580b56d49a5031afea5cbf483951aa21f174545fa`、2026-10-23T09:51:12.687778Z取得。
- 配布2fileは2764行と1373行、計4137の一意なUTC時刻。同じ公表行に屋内2室と屋外の温湿度がある。元の1分測定を集約した15分平均で、第二file内に30分間隔が2箇所ある。欠けた時点やfile間の空白を補間しない。
- 1-based列3/4は屋内温度、8/9は屋内RH、22は実測屋外温度、23は屋外RH。列5のWeather_Temperatureは予報であり、実測外気温へ読み替えない。温度は°C、RHは%。
- 選択した温湿度6列は4137行すべてfinite、RHは定義域0–100%内。しかし器固有の校正・適用範囲・品質flagは未提供。**範囲内という事実を校正済みの認定にせず、校正受入行数は0のまま**。

rootも原本5件と両配布memberのbytes/hash、4137行、列数・UTC・間隔・finite/RH範囲を独立再計算した。関連論文DOI10.3390/en6094639は方法の参考になるが、配布fileとの正確なbindingや校正を独立認証するものにはしない。

## NIST NZERTF Year1

[公式配布面](https://pages.nist.gov/netzero/data.html)から、[dictionary](https://s3.amazonaws.com/nist-netzero/NZERTF-Data-Dictionary.docx)、[hourly metadata](https://s3.amazonaws.com/nist-netzero/2014-data-files/Metadata-hour.csv)、[Year1品質log](https://s3.amazonaws.com/nist-netzero/Log_NZERTF_Year1_ForDataRelease.xlsx)、[NIST TN1854](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=917208)等、計8sourceを取得した。施設の温湿度は実測であり、simulated familyは模擬居住負荷の意味。Managerの架空fixtureや人の臨床結果とは区別する。

- [hourly CSV](https://s3.amazonaws.com/nist-netzero/2014-data-files/All-Subsystems-hour.csv)はHTTP206で先頭131072 bytesだけを取得。全体36858939 bytesのhashではない。prefix SHA256は`51163ffe7fd3787b3478e60df018f21bf566389cf67e0b0d18a23b9ead18024c`。356列のheader、完全30行と末尾182列の不完全行があり、末尾は測定として扱わない。
- 3列`IndEnv_RoomTempKitchenTemp`、`IndEnv_KitchenRH`、`OutEnv_OutdoorAmbTemp`を同一行・offset付き時刻で結べる。温度は°C、RHは公表descriptionのfraction0–1、hourly Average。raw値・offset・集約粒度を保持し、瞬間値や1分値へ変更しない。
- RHは30行中16行が公表範囲1を超える。残り14行は範囲内だが、異常の解消・修理・適用版を証明する説明は見つからない。7月2日6行（CSV物理line26–31）だけを選んで有効な校正済み系列とは認定しない。
- TN1854の物理p19は試験前の温度浴校正、p27–28は室内温度/RH generatorによる実校正、p32は屋外温度浴−20〜50°Cとlinear regressionを記す。これはメーカーaccuracyだけの推定ではない。一方、表の屋内13–30°C/0–100%RHというmeasurement range、屋外instrument range−18〜50°C、実施した校正浴の範囲は別の事実として保存する。
- log `Notes!E8`は7月1日の3つの欠測区間を記すが、RHの修理・再校正とは記さない。7月2日のentry不在を無故障の認証にはしない。公式の毎日midnight reset警告もあり、hourly平均のcoverage・枠の始点/終点を推測しない。

独立source preflightとrootは8件のretained bytes/hash、30完全行、不完全末尾、RH範囲外16件を確認した。**限定P0 source接続の準備には使えるが、原D005の受入を支持する有効性の根拠は不足**という独立判定を保持する。rawや連絡先を再配布せず、public/open/freeを未確認のCC licenseや全面再配布許諾に置き換えない。

## 修復した既存コードと次に必要な根拠

`physical_outcomes.py`の既存quality判定は、有限値と一緒に保存された`missing_reason`を利用対象から除外していなかった。研究source commit `2db1339cf99f316c754c4e405af60ce94450297b`で、`None → MISSING_VALUE`を維持し、それ以外の明示flagを`SOURCE_QUALITY_FLAG`として除外する。元の値・source・flag・全readingを保持し、その行をframes/pairs/記述的比較へ使わない。

実装前の回帰REDは12 tests中1 failure、修復後12 GREEN。workerの全suiteは968実行・5 skip・失敗0、rootも12 focused・import境界・113件view整合を独立確認した。新テストは架空のoffline fixtureによるソフトウェア検証で、NIST実測を既存analyzerへ接続した証拠ではない。このmoduleは研究branchのみで、本番mainへ旧5-module closureを昇格していない。

次に必要なのは、当該RH異常の影響範囲・有効に使える区間を説明するsource側の品質情報や訂正版、または同じ最小scopeで品質・校正の適用を確認できる別の測定source。元D005へPM2.5、屋外RH、6channel、実機serial、formal certificate、raw係数の全公開を新しい必須条件として追加しない。

既存のCalibration/PhysicalSessionDesignへ架空の有効日、対照・actuator、事前protocolを埋めない。source取得時刻を2013年へ戻さない。将来の最小接続は同じSourceと品質排除を再利用し、原行・時刻・単位・校正/quality根拠・除外理由・未確定を保持する。現時点のコード修復とsource監査を、人の改善や原D005完了へ変換しない。

cloudのsource-boundaryはcanonical checkout不在のFAILを保持しており、別hostのPASSへ付け替えていない。既存単一owner・定期planner・schema・model呼出し・配信状態・記事制作・外部連絡は変更していない。

## 修復を含む全体CIのexact-head証拠

[research CI39941440653](https://github.com/Daisuke134/life-manager/actions/runs/39941440653)はsource head `782f4535a7ac87eed82c44d12e16f5ae23633e24`でSUCCESS。E01 receipt6件、Ampersand P0 regression21件、原113件view整合・import境界が成功し、全suiteは942実行・6 skip・失敗0、27.256秒。取得した公式logは30560 bytes、SHA256 `d0f0c711c1f970a7f273bda05329a59ce7075810774476f2aa4c18422ee5de1e`。local workerの968実行・5 skipとは別の実測として保存する。

このrunはD003/D011のsource同期と品質flag修復を含むが、その後の説明文commitを検証したrunではない。source/testの同一性と文書の更新を分けて記録する。原D005の測定有効性・人への効果をこのCIから認定しない。
