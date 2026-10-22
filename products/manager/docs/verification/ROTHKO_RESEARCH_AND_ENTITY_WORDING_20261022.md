# Rothko公開code実行・Manager呼称更新の検証

2026-10-22 UTC。対象差分のbaseは`45704d3d243142117eacbfefcafe65c028c79fe3`。ユーザー指定のRothkoを調査し、Managerの呼称を仏教的AIエンティティ／デジタル仏陀へ修正した。runtime behaviorや元のタスク状態を変更していない。

## 研究の実行証拠

- [報告](../research/societies/ROTHKO_2026-10-22_JA.md)、[機械可読receipt](../research/societies/ROTHKO_REPRODUCTION_20261022.json)。4つの公式公開repoを固定commitでclone、全clone clean。
- AS Benchmarkはfrozen lock/Python3.12.14で66test合格/9skip。公開metricから7,128cellを再構築し、元scorecardとのJSON内容一致。semantic SHA256は`a509a03767e3e8487027525ff625463f9740fc4d4182e295953bd6e9a589f786`。
- group alignmentはPython3.14.6、実効2workers、元科学パラメータ/seed/sweep変更0。principal元13cells＋診断1、48.889秒/3図。ABM元28cells＋診断1、114.889秒/6図。全9図生成・目視、元cell一致/error output0/notebook format検証を確認。
- 見つかった上流の色説明逆転、closed-formと一部数値のずれ、監視撤回時の明示resetを報告。toy数値模型をRothko推論・人間便益・安全性証明へ置換していない。

## 仕様・公開原稿の確認

- README、既存仕様、first wedge、全工程view、atomic plan、local handoff、landscapeを更新。原task名/ID/依存/状態と旧証跡は保持。`tasks.json`はbaseとbytewise一致。
- 英日home原稿の既存`#research`だけを変更。section外はbaseとbytewise一致。他の製品、founder情報、人口合成の過去記録、navigation/metadataは変更していない。
- route-manifestの変更は英語2route・日本語1routeの3hash参照。全9entryの実ファイルSHA256一致。
- 既存Playwright/ChromiumでローカルpreviewをEN/JA×viewport1280/390pxで実描画、4/4PASS。entity用語の表示・Manager欄の横overflowなしを確認、JA mobile screenshotを目視。これは本番websiteの公開readbackではない。
- 関連relative link/fence/JSON整合と`git diff --check`合格。READMEに元からあった不存在のvision画像リンクを、実在するentity仕様への導線に修正。
- `python scripts/check_boundaries.py`: PASS。`python scripts/make_roadmap.py --check`: PASS113tasks。既存`test_eba_landscape_sources.py`: 4/4PASS。

## 独立review

fresh-context reviewer: `gpt-6.1-sol`、high、read-only、1pass。**1 findings (0 blocking)**、唯一Nitのshallow clone後の固定commit取得を、明示的`git fetch --depth 1 origin <sha>`＋detached checkoutへ修正。修正読戻し済み、未解決0。レビューは実receipt、全元cell不変、図とrunner hash、科学的な限界、呼称、HTML変更境界とmanifest/task byte identityを独立照合した。

## 残る状態を隠さない

Mac専用source guardは、このcloudではcanonical`/home/agent/Projects/life-manager-main` unavailableによりexit2。ユーザーのcloud source編集許可で継続し、guardを編集/偽装して合格とは扱っていない。

元WIPはPython694tests中1error/skip5のまま。新fixture00:00と既存context12:00の不一致をlocal handoffに診断済み。この研究/docs変更をruntime修正や全suite合格と呼ばない。直前の検証済み9ea03355aは684tests OK/skip5。

Rothko本体のweights/local推論・認証済みRadiant実行・原human dataからの全再採点は未実施。通常MCPアクセスは403。main merge、E16配備、website公開、売上、採用/YC、人の便益もこの作業で完了したとは記録しない。ローカルCodexは更新済みhandoffから既存E16を続ける。
