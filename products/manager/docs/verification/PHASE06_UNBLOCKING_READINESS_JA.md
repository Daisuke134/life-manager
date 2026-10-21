# Manager Phase06 — F004/F007ブロッカー解消の進捗と外部証拠

**日付：2026-10-21 JST**  
**判定：公開屋内実測データへの接続・権限証拠の機械的な点検・公式窓口への問い合わせ草案まで実施。実運営者・施設所有者の許可は未取得。**  
**正式タスク台帳は変更しない：113件 = 63 done / 47 todo / 2 blocked / 1 scientifically skipped。** F004・F007は依然 blocked、F005・F006・F008・F009は todo。科学 Gate1 未達、実世界の純便益は NOT_MEASURED。

## 1. 今回の具体的な新成果

- `manager_core/adapters/public_indoor_air.py`: AirGradientの**実際の公開・同意済み屋内センサーデータ**に固定URLで GET。プライバシー配慮のため位置座標や生locationIdを保持・返却せず、公開PM2.5の集計、計測時刻、SHA256、出典、欠測数と使用権レビュー要件だけを出力。実環境変更権限は付与しない。
- `manager_core/field_readiness.py`: F004に必要な12種類、F007に必要な10種類の外部権限・資金・物件・同意・測定資料の不足を表示。仮に全資料欄を偽装して埋めても **AWAITING_INDEPENDENT_VALIDATION** とし、`can_execute` は常に `false`。認証・権限の自己発行は不可能。
- `pilot/PHASE06_AUTHORITY_READINESS.json`: 署名や個人/銀行/建物住所を含まない公開準備テンプレート。**初期値 NOT_VERIFIED / NO_ACTION**。
- `scripts/phase06_public_indoor_readback.py`: 実公開APIの匿名集計とP0証拠、`scripts/check_phase06_authority.py`: 不足条件を確認できるCLI。
- [具体的な資金運営者・室内所有者獲得手順](../../pilot/PHASE06_BLOCKER_REMOVAL_RUNBOOK.md) は実行順・代替経路・検証条件を固定。

## 2. GitHubホスト環境で観測した実際のAPIデータ

取得: `GET https://map-data.airgradient.com/map/api/v1/indoor/measurements/current?pagesize=2&page=1`。2026-10-21T11:50:48Zの近傍で取得した公開opt-in室内センサー2件のサンプル平均 PM2.5 = **2.8 µg/m³**、欠測0、ハッシュ `1977296d2ecf9f2424dfb77763c91bca1184e40cf43697e8794970bea04a93c3`。オリジナルの生センサーID・正確な位置・匿名化座標は公開成果物に保存しない。

同じ2件が世界や東京都の代表値という意味ではない。**処置対象の部屋のデータではなく、処置を行った証拠でもない**。平均値はP0の外部観測の能力デモでありP2介入結果ではない。AirGradientはオプトイン匿名化を説明するが、データライセンスはソース単位で追跡し再利用前に確認する。<https://www.airgradient.com/documentation/kb/global-indoor-air-quality-dataset/>、<https://www.airgradient.com/documentation/kb/data-obfuscation-for-indoor-data-sharing/>。

実際のGitHub Actions: [39594386170](https://github.com/Daisuke134/life-manager/actions/runs/39594386170) とソース偽装の回帰修正後 [39595101996](https://github.com/Daisuke134/life-manager/actions/runs/39595101996) の **272テスト・実API取得・finance既存取得・境界検査・ロードマップ検査すべて成功**。

## 3. Red → Green の不正入力検証

- [初期 RED](https://github.com/Daisuke134/life-manager/actions/runs/39593983111): 7テストはモデル、センサーアダプター、権限資料が存在しないため失敗。
- [初期 GREEN](https://github.com/Daisuke134/life-manager/actions/runs/39594251086): 272テストと外部金融既存パイプライン成功。
- [提供元偽装 RED](https://github.com/Daisuke134/life-manager/actions/runs/39595034939): 別提供元文字列をAirGradientだと扱えるバグを再現、272中1件失敗。
- [修正後 GREEN](https://github.com/Daisuke134/life-manager/actions/runs/39595101996): 提供元厳格照合、272テスト成功、屋内公開実データ読戻しも成功。

## 4. F004を本当に解消する最短の道

Open Collectiveの**既存の合法的なFiscal Host**に資金の所有・会計・送金を保持してもらい、Managerには同意済みの募集ページ文言など狭い操作だけ許可する。F004の正当な解除には *実在の運営主体と国・法的権限、資金の所在と利用上限、委任の真正性、拒否/取消方法、対象と受益者の同意、測定権と第三者の実受領証拠* が必要。自己作成したAI署名や当社のテストgrantは使えない。

参考：
- Open Collective Fiscal Host [公式](https://documentation.opencollective.com/fiscal-hosts/fiscal-hosts)
- [テスト用staging](https://staging.opencollective.com/) で仮資金の操作フローを予行練習できるが本物のF004ではない
- [正式な問い合わせ窓口](https://opencollective.com/contact)

F002の20対20団体は現実の被験者/実際の検出力が確保されたものではなく「提案設計」。1案件の実操作と別ソースの読戻しはP1/P2の技術検証に有用だが、RCTの因果結果P4は主張できない。

## 5. F007を本当に解消する最短の道

所有者から明示的に許可を受けた小さな室内で、持ち運べる空気清浄機＋独立したPM2.5センサー＋騒音計＋電力計を用いる。固定空調を改造しない。居住者/労働者の安全同意、停止スイッチ、温湿度/外気/在室/扉の開閉の共変量、測定器の校正と第三者読戻しが必要。意図的に煙や有害PMを発生させない。

使える既存基盤：
- [AirGradient ONEとHome Assistant](https://www.home-assistant.io/integrations/airgradient)
- [AirGradient公開屋内API](https://www.airgradient.com/documentation/kb/global-indoor-air-quality-dataset/)
- [EPA低価格センサーの校正・設置・限界](https://www.epa.gov/indoor-air-quality-iaq/low-cost-air-pollution-monitors-and-indoor-air-quality)

**公開AirGradientの他人の部屋には操作権限がない。** 既存室内の読取能力ができても、実際の許可サイト・センサー・同意は埋まっていないためF007はBlockedのまま。

## 6. 外部への問い合わせ

Open Collectiveの公式窓口`support@opencollective.com`、AirGradient公式`support@airgradient.com`宛てに、実権限獲得と屋内センサーについて過大な表現をせず問い合わせ内容を用意。接続されたGmailで**送信操作はFORBIDDEN**、下書きは両方成功。よって **送信完了/相手の回答/承認済みとは報告しない**。ユーザーのプライベートGmailリンク・IDはこの公開GitHub報告には保存しない。

## 7. 次の実際の権限成立と工程

**F004**：partnerの口座/権限/基金書類を独立確認→署名の検証と実予算の制約を専門家が評価→**F005**：小額の許可済み実操作→外部P1/P2読戻し→**F006**：事前比較、損益・害・置換の因果報告。

**F007**：部屋の所有者の許可＋屋内独立計測の校正と止める権限確認→**F008**：安全な条件下でランダム化された介入試験、PM2.5 µg/m³とkWh/dBを同時観測→**F009**：両領域の真正なP2+結果を同一kernelで比較。権限が得られなくても研究・試験・データ観測・準備コードを進めるが、外部実施と福利は捏造しない。

**科学的Gate1 未達成。Manager起因の実介入0。確認された受益者純改善 NOT_MEASURED。Phase06 F004/F007 BLOCKEDは維持。**
