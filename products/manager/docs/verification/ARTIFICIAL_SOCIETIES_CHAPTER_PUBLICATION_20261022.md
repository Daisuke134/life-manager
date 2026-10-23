# Artificial Societies章：公開と検証記録

2026-10-22 UTC。公開研究を再利用する設計変更と日本語mini-chapterの公開記録。新しいTODO正本ではなく、E16/原113件の受入状態を変更しない。Managerは仏教的AIエンティティ／デジタル仏陀として記述する。人への便益は `NOT_MEASURED`。

## 最新の章改訂公開（2026-10-23）

2026-10-23 UTC。既存日本語章へ、レビュー済みのB/C診断結果を含む改訂を反映。下記は公開・配信・読戻しの記録であり、人への便益を示すものではない。

- Canonical source PR [life-manager #8584](https://github.com/Daisuke134/life-manager/pull/8584)（merge `730954fe82ad5c3b0ee4fc08e1a8ca331f341efe`、source head `c4a91cadd1dab14497a62cce42bce9f55a4aa0f1`）。
- 公開package PR [life-manager #8590](https://github.com/Daisuke134/life-manager/pull/8590)（merge/content revision `a1c7489a64ce043cabc84a76f9c924b6513fd813`、package head `3863f71b77c676a38228a4d65ec8d5c6fc928e85`）。canonical記事とmanifestの厳密比較、既存package検証（67記事/34 media）を確認。
- 配信bridge PR [anicca-products #569](https://github.com/Daisuke134/anicca-products/pull/569)（head `214338c00bd3dc7a634f5744ed5affea7c6a866c`、merge `df4a9606f4050b6b07dae3555af5e34cf7e1d8f4`）。既存installer/code revision `9a60b49e4bd4d288a491f0fb026af74e933c7eba`とchecksumを維持し、content revision pinのみを更新。
- [Netlify Deploy run39886664886](https://github.com/Daisuke134/anicca-products/actions/runs/39886664886)はbuild、deploy、既存の決済経路smokeを含めSUCCESS。smokeはsite、`/lm` handoff、life-call health、Stripe/Checkout/legacy Payment Link経路を確認。
- [公開章](https://aniccaai.com/blog/manager-artificial-societies-open-behavior-research-ja)のHTTP 200と[official release receipt](https://aniccaai.com/blog/manager/release.json)を独立GETで確認。receiptはcode revision `9a60b49e4bd4d288a491f0fb026af74e933c7eba`、content revision `a1c7489a64ce043cabc84a76f9c924b6513fd813`、67記事/34 mediaを記録する。改訂章のSHA256は`b6d65176539d04be5efb6c9a627ea675af9452563f2944dddb0d577c21ab4cc0`。更新前の保存receiptと比べ、変更は対象記事hashのみ。他の66記事hashと34 media hashはすべて不変。
- 公開本文のreadbackで、Bのpaired 95%区間が0を含み優越性未確立、Cの126対応列/84 QuestionIDは構造検査でありaccuracy未算出・生成来歴とtraining exposure unknownであること、汚染を認定していないことを確認。simulation code linkは`tianyipeng-lab/Digital-Twin-Simulation` revision `f1eed510c9a4fb47aaa9bb46e178aaa2d9224623`。Twin-2K-500 datasetと`TianyiPeng/Twin-2K-500-Mega-Study`の研究コードを区別する既存記述も確認。
- 改訂版PDF `/workspace/library-files/Manager-Artificial-Societies-20261023-ja.pdf`は11ページ、SHA256 `d0eea2c68a655df1231666c91077505753cb8385ae6a5d4f7bb009a0b6e2d160`。これは検証済みのローカルartifactで、website bridgeから配信したPDFではない。

公開と技術的読戻しを確認した記録であり、人間の行動変化、福祉改善、または介入効果を主張しない。source-boundary guardはcloud上でcanonical pathが不在のためFAILのまま記録し、PASSとは扱わない。

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

Canonical修正PR [life-manager #8552](https://github.com/Daisuke134/life-manager/pull/8552)はrendererのinline classとそのmodule hashだけを変更する。本文、図、fenced code、installer/checksum、content pinは保持。既存11 tests、67記事/34mediaのhash検証、全67記事の旧新renderer差分、fresh独立review 0 findingsを確認。以下の正常なmain統合・code pin更新・本番390/1280pxの読戻しまで完了した。

この修正の初回Security Scan run39822885257は12ジョブ・PR上14checksが全成功した後も、全体REST状態が`in_progress`のまま残った。通常cancelは409「not in progress」、rerunは403「already running」、公式force-cancelも409となり、これはcredential不足とは記録していない。sourceと受入条件を変えずPRをreopenし、同じhead `8ed373b79b16e0ffb313b959fec52b4569a5d4b3`の[新しい実行run39826084015](https://github.com/Daisuke134/life-manager/actions/runs/39826084015)が正常完了した。元の不整合をPASSに書き換えず、新実行の成功・全14checks合格を確認し、既存`bin/merge-when-green`でmainへ統合した。

## 最終公開と本番の独立確認

- Canonical code revision: `9a60b49e4bd4d288a491f0fb026af74e933c7eba`（PR #8552のmain統合）。配備済み旧codeとのmodule差分がrenderer class/hashだけであること、installerがbyte-identicalであることを再確認。
- Content revision: `a69a8a4a66e5b2f032c13efcc6bef18c446cf448`を保持。最新の配信側landing treeへこの正確な2pinsで既存installerを適用するdry-runも成功。
- Publishing bridge: [anicca-products #557](https://github.com/Daisuke134/anicca-products/pull/557)、main `5741efa4a50f22a317f75ca09c16aaefec8b4d06`。既存2workflowのcode pinだけを更新。Landing PR build run39827890715と全登録checksの成功後、exact headを固定して統合。
- [Netlify Deploy run39828574157](https://github.com/Daisuke134/anicca-products/actions/runs/39828574157)はbuild/deploy/決済経路smoke/全後処理までSUCCESS。
- 18:12:59UTCの未認証public GETで[release.json](https://aniccaai.com/blog/manager/release.json)の両revision、67記事/34mediaのmanifest、旧65記事/33media保持、一覧リンク、図bytesのhashを照合。記事本文は、固定sourceから既存installerでstageしたrendererによる**描画HTML全体と完全一致**。12主節・52参照URL・18,441文字表示も確認。
- 描画HTML SHA256: `021f32b9f6ba12ddd44f5273faf7cbd420419225ea9e33148a181f812b39e125`。

同時刻のclean Chromium確認（DOMへのclass injectionなし）:

| viewport | 文書幅 | 40桁IDの表示 | 結果 |
|---:|---:|---|---|
| 390px | 390px | 全文字保持、computed `word-break: break-all` | 横はみ出し解消 |
| 1280px | 1280px | 全文字保持、computed `word-break: break-all` | 横はみ出しなし |

スマホの該当ID部分とPCの実画面も確認した。これは記事公開・表示の検証であり、E16本番サイクル、A–F実装、人間への介入・便益の実証ではない。

## 設計と引継ぎ

[main固定版の再利用方針・atomic A–F](https://github.com/Daisuke134/life-manager/blob/a69a8a4a66e5b2f032c13efcc6bef18c446cf448/docs/research/manager/2026-10-22-open-behavior-reuse-plan.md)を参照。A–Fは計画であり未実装。企業提携/NDA/私有Rothko weightsを初期研究の依存から外し、公開人間データ・既存採点・単純baseline・研究単位holdoutから始める。所有siteは実行・readback・復旧の試験面。歴史研究の再採点や記事公開を、自分たちの新しい介入や人の便益として数えない。

取得した生データ、ブラウザ画面、詳細のprovider receiptはGit外のprivate scratchに保持し、この文書には検証の要点と公開識別子だけを載せた。source-boundary guardはcloudでcanonical `/home/agent/Projects/life-manager-main`不在のFAIL。所有者の明示したcloud source編集許可で進めたが、guardを変更せずPASSと記録していない。E16未配備と既知のfixture時刻エラーは[ローカルCodex引継ぎ](../handoffs/2026-10-22-manager-local-codex-handoff.md)に残す。
