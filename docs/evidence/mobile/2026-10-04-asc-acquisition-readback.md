# ASC Analytics acquisition readback — 2026-10-04

## 取得境界

- production releaseの`collectProduct()`をconfigured productsに限り2026-10-04 11:56:51–11:57:02 JSTにdirect read-only取得した。以下のdata範囲とprocessing_dateは取得時刻とは別のsource日付である。
- snapshot/state persistenceは無く、collectorは一時CSVを削除する。この文書編集でもprovider/GitHub/network/Telegram操作やruntime state書き込みは行っていない。
- Anicca iOS/Honneとも`source_status=measured`、`confidence=official_product_total_no_campaign`。現在のASC acquisition producer設定に含まれるのはこの2productのみで、他4mobile productsにはこの経路のrowが無い。

## Product別の公式合計

| 項目 | Anicca iOS | Honne |
|---|---|---|
| combined data範囲 | 2026-09-30..2026-10-02 | 2026-09-29..2026-10-02 |
| downloads processing_date | 2026-10-03 | 2026-10-03 |
| engagement processing_date | 2026-10-03 | 2026-10-02 |
| first_time_downloads | 1 | 1 |
| total impressions | 16 | 6 |
| unique impressions | 11 | 6 |
| product page views | 0 | 0 |
| campaign metrics | unavailable: not configured | unavailable: 未観測またはprivacy threshold（`campaign_not_observed_or_privacy_threshold`） |

- Anicca iOSのattributionは`unattributed`。campaign単位の計測・投稿帰属は確定しない。
- 方向性のderived ratiosはAnicca iOSで1/11 unique impressions=9.1%、1/16 total impressions=6.25%、Honneで1/6=16.7%。Anicca iOSの両reportのprocessing_dateは同じ2026-10-03だが、snapshotはsource別のdata_from/data_toを保持しておらず、report-level date windowsとcohort alignmentは未確認である。Honneのprocessing_dateはdownloadsが2026-10-03、engagementが2026-10-02。これらはaggregateの方向性比率であり、cohort conversionや投稿に帰属したconversionではない。
- 10月3日のlocal acquisition snapshotはintegrity PASSだが、今回より古く異なるwindowを対象とする。countを同一periodの増減として比較しない。

## Source report / instance参照

| Product / report | report ID | instance ID |
|---|---|---|
| Anicca iOS / downloads | `r3-04c74879-547f-4e35-b231-1fafd485801d` | `05a83079-4489-4ca4-8330-e42d93bd9cb7` |
| Anicca iOS / engagement | `r15-04c74879-547f-4e35-b231-1fafd485801d` | `d97027e4-f0ae-463f-bffb-9bf5c259188a` |
| Honne / downloads | `r3-c7c05836-181e-49cc-ae71-b57b7a0b466e` | `4173092c-0e3a-41f7-8985-fa60baaa8a13` |
| Honne / engagement | `r15-c7c05836-181e-49cc-ae71-b57b7a0b466e` | `774b6d1a-ec5a-4d72-8011-94f5d537597b` |

これらはASC Analyticsのsource参照であり、financial settlement receiptではない。

## Active ASC CLIの検証記録

- GitHub公式`rorkai/App-Store-Connect-CLI`の既存readbackはlatest `5.9.2`、published `2026-10-03T05:11:18Z`。
- `/opt/homebrew/bin/asc --version`は`5.9.2`、commit `08fae4d`。active binaryのSHA256 `6d5064e6ce1bb0c3e3afe35df9b9d69c303bd30bf590bc9148f5d98dc846ab60`は公式macOS arm64 assetと一致する。
- Homebrew metadataはstable `5.8.0`、brew listは`2.5.0`と古い。active binaryは公式assetに一致するstandaloneであり、upgrade/replaceは行わない。この文書更新でGitHub/networkへ再アクセスしていない。

## RevenueCat trendとApple final financial settlement

- 保存済みRevenueCat `subscriptions.json`の最新local report dayは2026-09-26、integrity PASS。Anicca/Honneとも`source_status=unavailable`、reasonは`product_pack_observation_missing`で、MRR/proceeds値は無い。
- より新しいbusiness-outcomes rowsは2026-10-03までRevenueCat availableを記録するが、currency/revenue_definitionは欠落している。保存済みtrend snapshotとこれらのrowsは異なるsource projectionであり、状態を混同しない。
- この11:56–11:57 acquisition read時点ではApple final financial report/receiptを取得していなかった。後続のApple fiscal report readbackと帰属gapは下記follow-upを参照する。
- 金額、product/account/financial receipt IDs、raw provider payload、credentialは掲載しない。source照合用report/instance IDsと公開asset SHAのみ記録する。
- TODO・順序・状態の正本 → [統合SSOT](../../superpowers/specs/2026-09-25-life-manager-unified-ssot.md)。

## 2026-10-04 Apple fiscal FINANCIAL report follow-up

- `/opt/homebrew/bin/asc` 5.9.2を`ASC_READ_ONLY=1`で実行し、公式`FINANCIAL` reportをregion `ZZ`でread-only取得した。Apple docsによるとreport dateはApple fiscal monthであり、`Extended Partner Share`はQuantity×Partner Share（税・Apple commission控除後）を表す。
- Requested fiscal reports `2026-09`, `2026-10`, and `2026-12` each contained one transaction row with a JPY partner-share amount; `2026-11` returned Apple's no-sales-for-date response. Fiscal `2026-12` row period was 2026-08-30..2026-09-26, so it is not the whole calendar month of September. Exact amounts and row identifiers are omitted from this public evidence.
- The latest row title was `Anicca Annual`; the matching local StoreKit file shows this as a display name while its configured product ID differs. The report's Apple Identifier matched none of the 24 IDs in the current read-only ASC app inventory. Therefore the proceeds cannot yet be attributed to an active app in this portfolio or joined to B7, and Apple report proceeds do not prove bank deposit.
- Raw finance report TSV was written only inside a mode-700 private state temp directory for in-memory aggregation, then unlinked and the directory removed. No report amount, Apple Identifier, vendor number, transaction, or provider payload was saved here.
- Primary definitions: [Download financial reports](https://developer.apple.com/help/app-store-connect/getting-paid/download-financial-reports), [Financial report fields](https://developer.apple.com/help/app-store-connect/reference/reporting/financial-report-fields).
