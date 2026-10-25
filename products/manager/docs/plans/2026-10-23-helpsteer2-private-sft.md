# 有限private SFT sourceをmainへ導入する

この計画はoffline研究codeと固定metadataの導入範囲を示す。Manager/agent完成を先に進め、記事はその後にする。順序・状態は[単一SSOT](../../../../docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md)だけで管理する。

[用途限定scope](../specs/2026-10-23-finite-private-sft-research-start.md)、[凍結SFT protocol](../../experiments/behavior-model/helpsteer2-private-sft-protocol-v1.json)、[train27/dev8/final16 manifest](../../experiments/behavior-model/helpsteer2-train27-manifest-v1.json)、[用途rights](../research/source-rights.json)を一組として扱う。元research commitは`d255c6bd5e8d7e3ac38cae0a587bf213590cc27b`。protocol/manifestは元bytesを保ち、PENDING/HOLDはfreeze時のsnapshot、現在の実行authorityは別の外部evidenceである。

## 実装と検証

既存mainと同一の9共通sourceを維持し、欠落9のimport closure、既存dev CLI、既存6テストを導入する。stdlibのsynthetic fixture/fake native boundaryだけをCIで使う。torch/transformers/PEFT/TRL/datasets/accelerateをCIへinstallせず、原corpus/weights/adapter/private configをGitへ入れない。native trainingは標準PEFT/TRL/SFTTrainerとcompletion_maskを再利用し、新trainer・optimizer loop・model serverを作らない。

将来の実装ownerはactual current mainから専用worktree/branchを使い、意味のある既存focused tests、mainのowned-cycle/workflow回帰、source boundary、secret checks、fresh-context reviewを同じ統合treeで確認する。全check完了・失敗0・exact head不変を確認し、通常PRを`bin/merge-when-green <pr>`で統合する。CI workflow変更はREVIEWのhigh tierで確認する。source PRでは本番owner/canary/model推論を起動せず、実runtimeの昇格は別の受入・実証で扱う。

## 実行と結果の境界

source import/mergeから実行権限は発生しない。新main commit/cwd/codeへ古い外部0400 configを再利用せず、historical research実行receiptを新commitへrehashしない。科学protocol自体のstatusを書き換えて架空のPASSを作らない。過去の一attempt結果もsource-versionに結びつく私有aggregateとして保持する。

固定adapter評価の新core/CLI/testはSFT導入単位と分け、[評価sourceの導入計画](2026-10-23-helpsteer2-fixed-adapter-eval.md)で扱う。G7実行には固定artifact/評価科学定義/別用途rights/code/CI/resourceと別のactual受入が必要で、未実行を0や正答へ変換しない。旧dev8-only rightsをtraining/final評価へ広げない。full V002/V003、V004/D016、真正な未見評価/安全性/人便益の受入はmodel採用・運用の別条件で、offline sourceのmain導入条件へ戻さない。source統合をdeploy/製品採用/Manager完成とは呼ばない。
