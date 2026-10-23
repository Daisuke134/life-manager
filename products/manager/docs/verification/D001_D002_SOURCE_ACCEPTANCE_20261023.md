# D001／D002 — 資金分類と比較設計のsource受入

F006の版付き技術報告受入後、原タスクの分類実装／比較設計を個別に判定する。実寄付・資金移動・生活改善の発生はこの2件の追加条件にせず、発生したとも主張しない。`program_funding.py`は研究branchの実装であり、現在のmain owned-digital runtimeへ配備した意味ではない。

## D001

**受入: sourceの分類契約のみ。** `FundingReceipt`／`FundingLedger`／`ProgramCosts`と`reconcile_program_funding`でoutside donor、Manager matching、sponsor、unknown、返金・費用を分離。自己matchingを増やしても外部増分は増えず、出典と費用coverageの不明はUNKNOWNのまま残す。`test_program_funding.py`で単位・期間・出典矛盾・二重計上拒否を確認。原依存F006はdone。

## D002

**受入: 未判定。** D001後、同時期の他program比較、負の置換、未観測scopeの扱いを個別判定する。

## 限界

結果はP0／NOT_VERIFIED／NO_ACTIONのまま。入力量・出典・coverageは宣言であり、この型はprovider receiptの独立認証を行わない。人間への因果効果・寄付純増・社会全体の純便益は未測定。D003の公表受益報告と実資金資料の接続、D004以降の追試は未受入。既存の完全な架空例を実案件や実売上に変換しない。
