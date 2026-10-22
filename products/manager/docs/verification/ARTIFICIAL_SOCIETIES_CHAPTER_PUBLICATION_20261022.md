# Artificial Societies章：公開と検証記録

2026-10-22 UTC。公開研究を再利用する設計変更と日本語mini-chapterの公開記録。新しいTODO正本ではなく、E16/原113件の受入状態を変更しない。Managerは仏教的AIエンティティ／デジタル仏陀として記述する。人への便益は `NOT_MEASURED`。

## 公開物

- [日本語章・公開URL](https://aniccaai.com/blog/manager-artificial-societies-open-behavior-research-ja)：18,441文字、12主節、52引用URL。公式掲載25件と公式事例7件を棚卸し、取得できた本文・部分取得・訂正情報を区別。
- [Manager記事一覧](https://aniccaai.com/blog/manager)。
- [独自の概念図](https://aniccaai.com/blog/manager/media/f7bd5ef2c4557afee441645c85f4bb55fa4340768e7f41e23c8a65a6060d4e30.png)。実測値を描いた図ではない。
- 日本語PDFは11ページの実ファイルとして生成し、同sessionの所有者へ配布。公開blogのimage-only契約へPDFを混ぜず、新しい配信基盤を作っていない。

## 最初の正常な公開

1. Canonical source PR [life-manager #8550](https://github.com/Daisuke134/life-manager/pull/8550)、全14checks完了後にmainへ統合。content revision `a69a8a4a66e5b2f032c13efcc6bef18c446cf448`。
2. 既存bridge PR [anicca-products #556](https://github.com/Daisuke134/anicca-products/pull/556)、main `3685f4b5a447fb270bacae9647a2631b66ec6c02`。既存installer/code revision `25eefdf84842b14059800b35667f3520b06ec4c9`を保持し、content pinだけ更新。
3. [既存Netlify Deploy run39821196601](https://github.com/Daisuke134/anicca-products/actions/runs/39821196601)はbuild/deploy/決済経路smokeまで成功。
4. 17:22UTCの独立した未認証GETで、記事本文、全12主節、52引用先、18,441文字の表示、一覧からのリンク、概念図の実bytes、[public release.json](https://aniccaai.com/blog/manager/release.json)を照合。67記事/34mediaのmanifest一致、既公開65記事/33mediaのhash保持を確認。

章本文SHA256: `ddda906d2a7b76d05b6cd9dbf473152960e0d3916aa4bc8c9bbdab2e08f241ad`。

図SHA256: `f7bd5ef2c4557afee441645c85f4bb55fa4340768e7f41e23c8a65a6060d4e30`。

## 公開後に実ブラウザで発見した修正

実サイト390px幅で文書幅460pxとなることを確認。原因は科学的版情報として載せた40桁commit IDのinline code。配信側の既存先例であるTailwind `break-all`の一時的DOM実験では、文字列を保持したまま文書幅が390pxへ収まった。初期の独立previewには独自の折返しCSSがあり、この本番style差を捉えられなかった。

Canonical修正PR [life-manager #8552](https://github.com/Daisuke134/life-manager/pull/8552)はrendererのinline classとそのmodule hashだけを変更する。本文、図、fenced code、installer/checksum、content pinは保持。既存11 tests、67記事/34mediaのhash検証、全67記事の旧新renderer差分、fresh独立review 0 findingsを確認。最終のmain統合・code pin更新・本番390/1280pxの読戻しは、完了後に追記する。

## 設計と引継ぎ

[main固定版の再利用方針・atomic A–F](https://github.com/Daisuke134/life-manager/blob/a69a8a4a66e5b2f032c13efcc6bef18c446cf448/docs/research/manager/2026-10-22-open-behavior-reuse-plan.md)を参照。A–Fは計画であり未実装。企業提携/NDA/私有Rothko weightsを初期研究の依存から外し、公開人間データ・既存採点・単純baseline・研究単位holdoutから始める。所有siteは実行・readback・復旧の試験面。歴史研究の再採点や記事公開を、自分たちの新しい介入や人の便益として数えない。

取得した生データ、ブラウザ画面、詳細のprovider receiptはGit外のprivate scratchに保持し、この文書には検証の要点と公開識別子だけを載せた。source-boundary guardはcloudでcanonical `/home/agent/Projects/life-manager-main`不在のFAIL。所有者の明示したcloud source編集許可で進めたが、guardを変更せずPASSと記録していない。E16未配備と既知のfixture時刻エラーは[ローカルCodex引継ぎ](../handoffs/2026-10-22-manager-local-codex-handoff.md)に残す。
