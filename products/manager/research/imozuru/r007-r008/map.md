# map: manager-evidence-and-behavior-simulation

問い: R007/R008を過剰にせず作り、Expected Parrot等の先行成果と正確に比較するには何を固定すべきか。

## 要る主張
1. 知見の場: 査読誌、arXiv原著、著者GitHub、各社公式ドキュメントへ到達。
2. 実験結果とモデル予測と企業報告の分類は同一ではない。
3. Expected ParrotはAI研究だけでなく人間による検証も提供する。
4. 記述的な予測一致は因果効果の一致を保証しない。
5. 公開された出典は許可、再配布権、実行権限とは異なる。
6. 既存の調査・シミュレーション基盤を再利用し、今回の自作は小さなJSON契約に限定できる。

## 用語
population synthesis, agent-based model, response distribution, operational validation, causal effect, holdout, calibration, evidence provenance.

## 人
Park・Bernstein・Liang（Generative Agents / 関連研究）、Kolluri・Wu（Socrates）、Klasnja・Murphy（HeartSteps）、Larooij・Törnberg（総説）、Robin Horton・John Horton（Expected Parrot）、Binzほか（Centaur）、Chopra（AgentTorch）。所属・役職は原典で確認した範囲以外を推定しない。

## 場
Expected Parrot公式・EDSL GitHub、Simile公式、Aaru公式、arXiv、PMC、Nature、Artificial Intelligence Review、Google DeepMind GitHub。

## 原文（sources/）
全文の再配布を避けた短い抜粋6件。元の原文URL・節は各ファイル冒頭。report.pyは抜粋の位置のみ照合する。

## 次の手がかり
Persuade Labの正確な識別子、EDSLの既存ベンチマーク用adapter、AgentTorchの導入前のライセンス・依存確認、Centaur/Psych-101のデータ利用条件。追加調査を最初の実装必須条件にはしない。
