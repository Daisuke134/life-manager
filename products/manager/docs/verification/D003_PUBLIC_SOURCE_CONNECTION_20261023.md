# D003 — 公表支出と別の受益報告のsource接続

2026-10-23。原D003はD002に依存し、「公表された支援先の受益報告と資金移動を別の証拠として接続」、第三者報告のない経済的生活改善を未測定とする。以下は有限な公開source接続の記録で、人の便益・Managerによる送金・収益・因果効果の受入ではない。

## 一次資料と限定した結合

GiveDirectlyの[IATI公表XML](https://aidstream.s3.us-west-2.amazonaws.com/xml/givedirectly-ug.xml)のactivity `US-EIN-27-1661997-Ug-refugees-pilot`は、同activityのdocument-linkで[Uganda pilot report PDF](https://aidstream.s3.us-west-2.amazonaws.com/documents/CashTransfersToRefugeeCommunitiesWhitePaper-20180917030903.pdf)を直接参照する。

| 別々に残す証拠 | 確認した値 | 限界 |
|---|---|---|
| 公表された支援先向け支出 | type4かつ支援先送金と明記された3行、USD 2,903,900＝290390000 minor | 2017-Q4・2018-Q1・Q2の部分記録。入金・commitment・その他経費は含めない。銀行／processorの決済認証ではない |
| 実施団体の別集計 | 所得増の自己申告87%、報告されたfollowup標本484世帯 | 所得設問の有効回答分母と正確な回答実数は不明。87%×484を人数にしない |
| 出典間の関係 | 同一activityから正確なPDF URLへの直接link | same_program_only。厳密調査窓と世帯別送金の対応は不明 |

PDF物理ページ1が2018-09の報告月、6が標本、7が実施団体による収集・執筆とbaseline/controlのない記述的設計、12が所得自己申告の割合。独立第三者の効果評価はない。

XMLは27134 bytes、SHA256 `593556f369b622a49c46459fa324a730a338d8155a05c6bf1d6d143922049345`。PDFは1210032 bytes、SHA256 `6941713ebc2b7f95e171e1150409f389e3c8f2209501b8022dc96ae425bfead8`。取得済み原本のhash・selector・ページを照合した。原本はprivate scratchに保持し、連絡先・人物経験談をGitや実行contextへ取り込まない。

## 再利用した接続と公開snapshot

`manager_core/public_program_disbursement.py`の`connect_published_program`は既存`Source.verify_content`と`evidence.load_verified_trial`の固定artifact方式を再利用する。既存incoming FundingLedgerや厳密な期間契約を変更せず、汎用IATI/PDF ingestionも作らない。

- [固定した非個人packet](https://raw.githubusercontent.com/Daisuke134/life-manager/71c42c559ba416a85e60f10ba510298b4ceea44c/products/manager/docs/research/GIVEDIRECTLY_D003_SOURCE_20261023.json)：7528 bytes、SHA256 `b76f8bbfb6e5a51094e35a3639a40bd0d4638c789fa1d2769a939cd88d2d6989`。
- 09:43:56 UTCのHTTP200で実取得し、公開bytesとreview対象のローカルpacketの一致を確認した。
- Sourceはこのpacket自身の固定URL/hashを指す。upstream原本のURL/hash/取得時刻は別metadataとし、rawのURLへ派生packetのhashを付けない。
- callerがSourceのhashも同時に差し替えても、独立したreview済みsnapshot pinで変更packetを拒否する。これは固定snapshotのallowlistであり、汎用PII検出や原本の真実性の自動認証ではない。
- 出力は支出、別集計、結合根拠、権利、来歴、未知を別欄に残す。P0／NO_ACTION、経済的生活改善・人の便益はNOT_MEASURED、measurement_authenticationはNOT_VERIFIED。verified income/net benefit、費用・返金・置換効果はnullのまま。

IATI registryは`cc-by-sa`と記すが版は未確認。PDF全体の再配布許諾は未確認。対象は出典・帰属を伴う最小限の集計事実とlinkで、raw全文・人物経験談は再配布しない。

## 検証の範囲

worker source `8e292c3f3c26b1fac0c967dc1ee5bff6169ff497`は、実装前の9件RED→実装後の9件GREENを記録した。rootも400件の全suiteを独立実行し、失敗0。Sourceのbyte不一致、callerが再hashした金額・activity・追加privateフィールドの改変、raw URLの誤用、型・size違反を拒否する。Manager import境界・loop契約・product範囲gitleaks・diffcheckも成功した。

独立R1はspec・実装・限定source表示をPASSとし、元D003は通常統合とowner受入後の限定source接続として条件付きPASS。root所有のteam board配置1nitは訂正した。main統合と元台帳の受入は、そのPR／CI／commitの外部証拠に基づき別途記録する。

cloudのsource-boundaryはcanonical path不在のFAILを保持する。別hostのPASSへ付け替えない。新しい推論・支払・公開ページへの作用は行っていない。D004以降、全Manager、世界の苦しみの終結を、このsource接続から完了とはしない。
