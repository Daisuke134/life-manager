# A5 Task 5 レポート: provider cost attribution と trace anchor

## 結果

DONE。期間集計をprovider/SKU/operation/unit/loop/ownerで分け、trace status件数、distinct run/occurrence/release件数、最新trace anchorを追加しました。欠損identityは`unattributed`、不明金額は引き続き`null`です。API DTOとbrowser validatorは明示allowlistを使い、raw `meta`とprovider payloadを返しません。

`panel-api.js`自体は変更していません。既存経路がtenant-scoped RPC結果を`presentPanelSection`へ渡すため、projectionの変更先は`panel-presentation.js`です。RPCのtenant/期間引数は既存APIテストと今回の契約テストで確認しています。

## RED

実装前に追加した3件だけを実行しました。

```sh
node --test --test-name-pattern='COST-03|ledger period projection attributes cost groups and exposes only safe latest trace|PANEL-A5: browser renders loop/owner grouping and newest trace' lib/usage-summary-migration.test.js lib/panel-api.test.js lib/panel-ui.test.js
```

```text
✖ ledger period projection attributes cost groups and exposes only safe latest trace
✖ PANEL-A5: browser renders loop/owner grouping and newest trace
✖ COST-03 period summary separates costs by runtime loop and trace
ℹ tests 3
ℹ pass 0
ℹ fail 3
```

失敗理由は期待どおりで、API DTOのtrace属性が`undefined`、browser validatorが拡張DTOを拒否し、SQLの`RETURNS TABLE`に`loop_id`がありませんでした。

## GREEN

```sh
set -o pipefail
node --test --test-reporter=spec lib/usage-summary-migration.test.js lib/panel-api.test.js lib/panel-ui.test.js | tail -n 14
```

```text
✔ COST-03 period summary separates costs by runtime loop and trace
ℹ tests 110
ℹ pass 110
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
```

最初の全focused runでは、旧4次元DTOを前提にしたmigration/APIの完全一致assertionが3件失敗しました。既存fixtureと契約assertionを新しいallowlistへ更新し、最終runは110件すべて通過しました。

## Privacy evaluator とdiff

```sh
npm run eval:panel-privacy
```

```text
Panel privacy eval: api=177 browser=63 recipes=19 channels=9 judge=deterministic
```

`git diff --check`はexit 0、出力なしです。

## 自己review

- RPCは`uid = p_tenant_id`、`ts >= p_period_start`、`ts < p_period_end`を維持します。unit、loop、ownerでgroupingし、runごとの分割はしません。
- producerのID境界に合わせてloop/owner/run/occurrenceをallowlistし、releaseは40/64桁の小文字hexに限定します。最新anchorは`ts DESC`の最初のtrace-bearing eventです。
- trace status件数の合計をevent件数と照合し、全linked/all unlinked/混在をそれぞれ`linked`/`unlinked`/`partial`にします。異常なcount/status/IDは期間projectionをfail-closedにします。
- 金額の既存nullable sumとsettled/unknown/not-applicable判定は変更していません。unattributed fixtureでestimate/settledの`null`を確認しています。
- API DTOは`meta`やprovider payloadを列挙せず、安全なtrace IDだけを投影します。browserは同じstatus/count/ID条件を再検証し、loop/owner/anchorをescapeして描画します。
- 既存`usage-event.js`のproducerを再利用し、追加instrumentationは入れていません。

Supabaseへのmigration適用、production変更、push、merge、deployは依頼範囲外のため実施していません。

## Commit と実行環境

- Branch: `feat/cfo-a5-cost-visibility-20261007`
- Commit: `a551db6aa4` — `feat(cfo): attribute API costs to runtime traces`
- Model/effort: この実行環境からは観測できません。

## Fix round 1/5: generated browser regex escaping

### Finding and change

fresh read-only reviewerが、`panel-ui.js`のouter HTML template literalでregex中の`\s`と`\.`が生成時に消え、`auth-json`が`auth.json`のwildcardに誤一致してDTO全体を拒否すると指摘しました。template内の両escapeを二重化し、生成後regexが`\s`と`\.`を保つよう修正しました。raw metadata・allowlist・escapingは変更していません。

### RED

```sh
node --test --test-name-pattern='PANEL-A5: generated browser accepts auth-json and rejects auth.json trace IDs' apps/life-manager/lib/panel-ui.test.js
```

```text
✖ PANEL-A5: generated browser accepts auth-json and rejects auth.json trace IDs
ℹ tests 1
ℹ pass 0
ℹ fail 1
AssertionError: Got unwanted exception. Actual message: "invalid ledger payload"
```

生成されたbrowser validatorが有効な`auth-json` IDを拒否することを確認しました。

### GREEN と最終確認

```sh
node --test --test-name-pattern='PANEL-A5: generated browser accepts auth-json and rejects auth.json trace IDs' apps/life-manager/lib/panel-ui.test.js
```

```text
✔ PANEL-A5: generated browser accepts auth-json and rejects auth.json trace IDs
ℹ tests 1
ℹ pass 1
ℹ fail 0
```

```sh
node --test apps/life-manager/lib/panel-ui.test.js
```

```text
ℹ tests 44
ℹ pass 44
ℹ fail 0
```

`npm run eval:panel-privacy`もPASS（api=177、browser=63、recipes=19、channels=9、judge=deterministic）。`git diff --check`はexit 0、出力なしです。

### Commit

- `6dbdb02876` — `fix(cfo): preserve escaped runtime trace regex in panel`
- 変更対象: `apps/life-manager/lib/panel-ui.js`、`apps/life-manager/lib/panel-ui.test.js`
- Model/effort: この実行環境からは観測できません。
