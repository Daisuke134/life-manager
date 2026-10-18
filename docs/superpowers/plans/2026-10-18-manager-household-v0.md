# Manager Household v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rhode IslandのPUMSから世帯単位の合成人口を作り、調整・整数化の誤差を再現可能に測る。
**Architecture:** 既存artifact/CLIの形を使う。入力と契約、重みと整数化、展開と採点を分け、referenceは採点だけに渡す。
**Tech Stack:** Python3.12、既存固定ipfn/NumPy/pandas、stdlib unittest/CSV/ZIP。新依存なし。
**Spec:** docs/superpowers/specs/2026-10-18-manager-household-v0-design.md

## Global Constraints

- STATE44、2020–2024、通常居住世帯のみ。raw/runはGit外。
- 家族×サイズの6セル、サイズ1/2/3+。定義上のfamily1は0。
- 残差1e-10、1000反復、TRS seed20261018、診断seed10本を固定。
- コードは既存MIT、費用API0、behavior/policy/execution/field未実行。
- 同じ実行範囲に記事・説明画像・実測図・6枚の再利用素材を含む。外部投稿なし。

## Review Focus

1. 同じIDの別人/欠員/空き家とGQの混在を成功にしない（Task1で試験）。
2. ZIP重複member/上限/manifest改ざん/並行上書きを拒否（Task1）。
3. support不足や構造的ゼロをepsilonで隠さず失敗（Task2）。
4. TRSの同seed再現、ゼロ重み、並べ替え、総数と人数の違い（Task2/3）。
5. CSV改ざん/孤立個人/重複ID/元属性の不一致/失敗結果の保持（Task3/4）。

## Task 1：出典と所属を読める入力

**Files:** population/households.py、population/pums.py、population/household_sources.py、config/household-v0.json、tests/test_pums.py。
**Interfaces:** Person/Household/HouseholdControls（specどおり）、read_pums(housing_zip:Path,persons_zip:Path)->(tuple[Household,...],dict)、read_controls(path:Path)->(HouseholdControls,tuple[int,...])、fetch_household_sources(out:Path)->dict、verify_sources(directory:Path)->dict。

- [ ] RED：fixture ZIPに親子3人を入れ所属・size・order・headを検証。重複/欠員/別州/負重み/空き家/GQ/誤member/過大member/hash改ざんでPopulationDataError。B11016 leaf fixtureから6セル(0,3,2,4,1,0)、周辺(5,5)/(4,4,2)、総数10。
- [ ] unittest -p test_pums.pyで未実装REDを確認。
- [ ] immutable型、厳密CSV/ZIP読取、公式のbounded fetchを実装。既存no-replace artifact保存を利用。
- [ ] 同テストと8A suiteをPASSさせてcommit。

## Task 2：調整と整数化

**Files:** population/household_fit.py、population/integerize.py、tests/test_household_fit.py。
**Interfaces:** cell_index(household)->int、household_weights(households,controls,method)->tuple[float,...]、integerize(weights,total,seed)->tuple[int,...]。

- [ ] RED：baseline totalと相対重み、calibrated周辺一致・family1zero・セル内比率維持、infeasible support/zero-target拒否・非収束を検証。
- [ ] RED：TRS weights(1.4,1.4,1.2)からtotal4、再実行一致、zero weight複製なし、整数入力不変、負/NaN/total不一致拒否。
- [ ] focused testで未実装REDを確認し、ipfn adapterとTRSを実装。
- [ ] 全suite PASS、commit。

## Task 3：世帯を丸ごと展開し、出力を採点

**Files:** population/household_export.py、benchmarks/households.py、tests/test_household_export.py。
**Interfaces:** export_population(households,copies,out)->dict、audit_population(households,copies,out)->dict、evaluate_households(households,weights,copies,controls,reference)->dict。

- [ ] RED：3人世帯を2組選ぶと2世帯6人、新ID一意、元属性と全員の所属維持、0回選択、上限検査。
- [ ] RED：CSV1行削除/重複/属性書換え/未所属を検査し拒否。異なる既存outputを上書きしない。
- [ ] RED：weightedとintegerの誤差を分け、known fixtureのTVDを手計算assert、person totalsとPWGTP age診断が異なることを検証。
- [ ] focused REDを確認してstreaming CSV/再読audit/評価を実装。全suite PASS、commit。

## Task 4：CLIで結び、公式資料を実行

**Files:** household_cli.py、cli.py、tests/test_household_cli.py。
**Interfaces:** 上記4CLI（spec参照）、既存manager.cli.main()->int。

- [ ] RED：オフラインfixtureでfetch以外を一貫実行。seed/controls/referenceのhash、2方式、not_run、費用0を検査。
- [ ] RED：synthesizeがreferenceを開かない、入力やCSV改ざん/片方式/別snapshot/設定違い/上書き拒否、同seed予測CSV bytes一致。
- [ ] CLI接続を実装、全suite PASS。
- [ ] 公式fetch→prepare→2方式→scoreをGit外で実行し、再現確認。実測で設定を選び直さず、悪化も保存。commit。

## Task 5：説明素材と最終レビュー

**Files:** apps/manager/docs/households-v0.md、README追記、docs/research/manager/articles/2026-10-18-household-v0-results-ja.md、figures/、evidence/、content/。

- [ ] 実測の公開集計を作り、データ→世帯複製→整数化→評価の生成画像、実測matplotlib図を保存して記事へ埋め込む。
- [ ] 6枚のスライド/カルーセルを実画像・編集可能HTML・台本として保存。架空例/実測/将来を区別。
- [ ] 日本語指針と出典条件、MIT、README実行コマンド、全リンクを確認する。
- [ ] 全suite、root test:oss/test:install（失敗は名前と原因を報告）、diff/source-boundary、独立reviewを実施。ImportantはRED→GREEN一回の修正pass。
- [ ] 統合SSOTへ現在/実測/次を記録、branch pushしてremote SHAを照合。main統合/投稿しない。
