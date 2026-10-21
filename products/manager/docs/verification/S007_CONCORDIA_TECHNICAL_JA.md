# Manager S007 — Concordia社交エージェント実行の技術検証（科学的妥当性ではない）

2026-10-21 JST. **Concordia本体のモックエージェント統合に限る**。

## 何を実行できたか

- 原典: [google-deepmind/concordia](https://github.com/google-deepmind/concordia)、固定commit `7128586aa8c1073bfa09dcb3781cea21e1a49229`、Apache-2.0。これをGitHub Actionsで一時checkout。
- 最初の `daisyworld` 技術試験: [39537485934](https://github.com/Daisuke134/life-manager/actions/runs/39537485934)、6モックticks。惑星の玩具シナリオなので社交モデル検証ではない。
- 追加社交テストの最初の `Concordia Island` 実行: [39544741919](https://github.com/Daisuke134/life-manager/actions/runs/39544741919) **FAIL**。上流READMEに記載された同梱Brecksvilleペルソナが、その版のGit treeに存在せずFileNotFoundError。
- 上流`IslandConcordiaSimulation`、`AgentConfig`、`FastMockLanguageModel`を独自の薄いラッパーから直接使用する方法に変更。架空エージェント2体・4ticks・実際のConcordiaコアが出力したイベント4件。**Hosted GitHub Actions [39545009858](https://github.com/Daisuke134/life-manager/actions/runs/39545009858) SUCCESS**。元ソース上流コードをManagerにコピーしない。
- CIから生成した `simulation/simulated_agent_log.html` と `simulation/simulation_summary.json` を、独立の `real_world_validation/verification.json` と**別フォルダ**に保存。[GitHub artifact](https://github.com/Daisuke134/life-manager/actions/runs/39545009858/artifacts/12320782740) （保持14日）。
- 実装 `scripts/concordia_island_mock.py`、ワークフロー `.github/workflows/manager-concordia-social-sandbox.yml`。APIキー不要、外部アクション不可、ライフマネージャのデータと接続なし。

## どの範囲では成功していないか

- 実行は生成エージェント**ソフトウェアの技術統合**を証明するにとどまる。モックモデルがJSON形式の応答を返せず上流で `Modality Parsing JSON Error` 警告が複数回観測されている。記憶内容・内省の質・長期間相互作用の正しさを合格判定していない。
- 人間被験者・SocSci210回答者の行動の再現は **0件**。現実世界の独立検証も0件、実際の因果効果推定はなし。実行した4イベントを4人の行動や4件の社会的便益と数えない。
- モデル予測の正しさ、意思決定への有用性、個人や集団への一般化、第三者を対象に介入する権利は**証明されていない**。

## 科学とエンジニアリングの境界

元タスクS007が要求する「Concordiaを独立したサンドボックスで**動かし**、生成ログと現実検証ログを**別のスコア**に保存する」という実装受け入れ基準は達成した。S006の実証結果を必要とせずソフトウェアの実行自体は先に試験できるため、依存関係を権利監査R006と学習/評価スプリット保護S003に明示変更できる。ただし人間行動シミュレーションの科学的成功は**未達**のまま別の科学ガード（S002, S004, S005, Gate1）に残る。科学と工学のラベルを交換しない。

**今後の強化:** 実際の言語モデルで正しいJSON/内省を試験するには、モデル使用権とコスト・評価設計、許諾された独立した人間行動の評価対象が必要。モックでは合格にしない。
