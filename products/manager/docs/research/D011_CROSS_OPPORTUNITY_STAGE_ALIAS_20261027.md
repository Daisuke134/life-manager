# D011 — 異なる案件の募集・納品・承認を「決済証憑」に偽装した場合の検知

**2026-10-27 JST · Manager research only · P0 synthetic security regression.** Canonical status: `docs/roadmap/tasks.json`. D011 original acceptance is **todo**; H005 remains **blocked**. No new original task was declared done, and no external person, account or payment was accessed.

## 問い → 仮説 → 反証（imozuru）

**問い：** 同一案件の中で投稿・納品・承認と決済証憑が独立しており、複数案件間でも「決済証憑どうし」のURLやSHA-256が異なる場合、決済証憑は独立と判断できるか。

**反証対象 H0：** できる。既存 `preflight_receipt_portfolio` は決済 vs 同じ案件の前段証拠を比較し、決済 vs 他案件の決済証拠を比較する。ところが**案件Aの承認文書を案件Bの決済資料として再ラベル**すると、上記の二種の比較だけでは検知されない。

**検証可能な限定命題 H1：** 任意の案件の決済sourceが**別の案件**の募集・納品・承認sourceと、`source_id`、フラグメントを除いた一次URL、またはSHA-256のいずれかで一致した場合、保守的に `RECEIPT_REUSES_OTHER_OPPORTUNITY_STAGE_EVIDENCE` として `REVIEW_REQUIRED` にする。これは支払の真正性や重複請求の事実を認定するものではない。同じ公開元帳ページに合法的な複数取引が載る可能性もある。

**反証テスト：** 完全に架空のjob_a/job_bとpublic source metadataで、案件Aのposting/delivery/approvalを案件Bのsettlementに各1回使用する。ソースIDのみ、URL（異なるfragment）のみ、SHA-256のみの衝突を分け、入力順序も逆にする。前段資料のみを異なる案件間で共有したときは誤って決済重複にしない。出力にはURL・金額・案件IDを含めない。

## 一次資料（official locator、確認日 2026-10-27）

1. Stripe, *Receive Stripe events in your webhook endpoint*, https://docs.stripe.com/webhooks — 「Handle duplicate events」ではイベントIDと対象オブジェクトID/イベント種別の照合、署名検証の項目では発行元の認証が必要とされる。Managerはこれらの発行元認証を実装していないため、匿名メタデータの非重複を「入金認証」と読み替えない。
2. GitHub Docs, *REST API endpoints for repository attestations*, https://docs.github.com/en/rest/repos/attestations — 署名、署名者、時刻の検証が必要。ソフトウェア成果物の出所は決済機関からの着金証明ではない。
3. Open Collective, *Transaction Pairs, Groups & Perspectives*, https://documentation.opencollective.com/advanced/ledger/transaction-pairs-groups-and-perspectives — 元帳はcredit/debitの対応や表示の視点により行数が異なる。単一URLは単一決済に対応すると決めつけない。

これらは他社の設計上の注意を示す一次資料。**案件横断の前段資料との比較ルール自体はManager独自の保守的な仮定**であり、一次資料がこのコードを必須としているという主張ではない。原文・ソースコード・人物データの複製は行っていない。

## 変更と限界

- `manager_core/opportunity_receipt_portfolio.py`: 元の上限128件、既存のwithin-record/cross-receipt判定を保持し、案件横断の前段証拠エイリアスをscreen。標準ライブラリのみ、読み取り専用、外部送受信なし。
- `tests/test_opportunity_receipt_portfolio.py`: 架空データで3ステージ×3衝突タイプ×2入力順序、receipt欠落の他案件、既存の陰性コントロールを検証する。CIを読んだ時点でのみ成功を宣言する。
- 絶対条件：`provider_transaction_identity_verified=false`、`independent_payment_verified=false`、`verified_income_minor=null`、`can_execute=false`、`beneficiary_effect=NOT_MEASURED`。D011の実入金・所得・人間／動物の苦痛軽減を一切認定しない。

**残る原受入れ条件：** 正当な公開決済証拠の実在性、署名／発行者／取引ID、取消・返金・二重計上、真の受取の外部照合。外部個票や認証情報を取らない限り、この原タスクは `todo` のまま。

**検証予定：** `cd products/manager && python3 -m unittest tests.test_opportunity_receipt_portfolio -v && python3 -m unittest discover -s tests -v && python3 scripts/check_boundaries.py && python3 scripts/make_roadmap.py --check`。 hosted CIの結論・コミットとsource readbackを別途照合する。

## Hosted CI & independent readback (2026-10-27 JST)

Implementation commit: https://github.com/Daisuke134/life-manager/commit/61b0d06ca945aeb55d09c6f6bd20f13454279fe8

- [Manager Independent Offline Research](https://github.com/Daisuke134/life-manager/actions/runs/40422285572): **success**. Its hosted job logs show the two new tests passing, `Ran 541 tests`, `OK (skipped=5)`, and `PASS 113 tasks; task JSON untouched`.
- [Manager EBA v0 Open Benchmark](https://github.com/Daisuke134/life-manager/actions/runs/40422285492): **success**. The offline benchmark job independently ran 541 tests with 5 skipped.
- [Manager Phase06 Digital Environment](https://github.com/Daisuke134/life-manager/actions/runs/40422285602): **success**. Browser/environment checks are technical checks, not field welfare measurements.
- Independently read back implementation, tests and this note through the GitHub connector at the implementation commit; confirmed new reason code and tests. Registry remains 113 original items: **69 done, 41 todo, 3 blocked**; D011 is `todo`, H005 is `blocked`.

These results cover the synthetic P0 guard only, not verified transaction identity, independent received income, actual downstream effect or reduced suffering. Any subsequent registry-only commit must be verified separately.
