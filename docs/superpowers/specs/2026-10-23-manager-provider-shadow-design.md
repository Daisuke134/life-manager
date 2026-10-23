# Catalog provider shadow — design (2026-10-23)

Manager本体の公開文脈とモデルの比較を、既存部品で一つ接続する。実装上の呼称はP0 shadow caller。原113件の新taskでも、人の便益の受入でもない。所有者は本体優先、既存成果の再利用、実装判断の委任、確認待ちせず継続を明示している。以下の選択は実装者の判断であり、個別のユーザー選択を創作しない。

## Approaches

1. **採用:** 既存 `plan_catalog_change` の検証経路をそのまま呼び、legacyの公式リンク／ラベル修正だけを `CheckpointedProvider.initial` と既存baselineへ渡す明示opt-in callable。独自collector、eval engine、DB、schedulerを追加しない。
2. 定期plannerへ全runのモデル推論を追加する案は、current-page cue／候補なしに無意味な課金を増やし、未評価の判断を実行へ結ぶため採用しない。
3. 別agent framework／会話serverを作る案は、現adapterとcheckpointが同じ機能を持つため採用しない。

## Contract

`manager_core.owned_provider_shadow.run_catalog_shadow` は、所有者が既に取得したexact `PrivateCheckpoint`、client、Pages checkout、非公開planning workspace、固定main source SHA、run ID、明示budget／絶対期限を受け取る。`enabled=False` が既定。disabledではplanner/providerとも呼ばない。新しいownerの取得やprovider clientの自動作成はしない。

有効時は既存plannerを呼ぶ。served／checkout一致、公式source、権利、静的criteria、browser検証はその既存経路に依存する。型の構築だけを出典や実browser検証の証拠とはしない。候補なし、source不明、未検証、synthetic context、current-page cueはproviderへ送らない。既存 `prepare_owned_change` を現在時刻で再計算し、公開promptの検証も行う。内部のrelease packetを比較結果へ返さず、送信・publisherは呼ばない。

有効な同じ公開contextに既存 `no_action_baseline`、`rule_baseline` とproviderを適用する。baseline moduleは研究head `546a9d4446a91be94220c99112775309ef6d24b6` から変更せず再利用する。独自の正解ラベル、統計的優位、人の便益は作らない。

operation IDはprotocol、model／instructions、静的baseline/candidate digest、action/target、固定sourceのID/URL/content hashへ結ぶ。run ID、観測時計、scope期限をIDに含めない。同じoperationの既存session intentはRESERVED／UNKNOWN／BOUNDいずれも自動再送しない。bodyや観測時刻が変わっても既存operationを新IDへ逃がさず、reconcileが必要と返す。source内容・候補bytesが変わった別案件は別IDとする。

返すのは固定schema `manager.catalog-shadow.v1` の比較記録だけ。status、reason、operation ID、実prompt hash、bundle/source hashes、baseline receipts、任意のprovider receipt、session/turn/status/usageを区別する。`proof_level=P0`、`authorized_execution=false`、`causal_support=false`、`human_outcome=NOT_MEASURED`、`action_writes=0`。settled costはnull。モデルの失敗／不正JSON／未知をbaselineの成功に置換しない。内部packet、秘密、raw exception／provider error bodyは返さない。

checkpoint failureやfenced object、割込みは伝播し、後続送信しない。UNKNOWN sessionは保持する。全callerが同じ既存checkpoint leaseを使う前提。callableの構築はplatform identityではなく、独立writerへのprovider-side CASは主張しない。

## Scope and acceptance

source-only callableと注入fakeによる契約検証、通常main PR／CIまで。定期workflowの変更はverifyのtest module一覧のみ。運用経路への有効化、SDKの実install、live model比較、人の便益、U002の実面談、U003の選定は今回の受入に含めない。SDK／secret／budget不足を全体host blockerへ一般化しない。実候補がない間は課金推論を行わない。
