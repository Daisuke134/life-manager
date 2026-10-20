# R006 - 一次資料・公開データ・オープンソースの利用権確認

**調査日:** 2026-10-20 (JST)  
**実装責任:** Manager専用製品。Life Managerとは別の実行環境。  
**成果物:** [`docs/research/source-rights.json`](research/source-rights.json)  
**状態:** R006研究レビュー。**これは法的助言や現場データ利用の包括的承認ではない**。

## なぜ調べるのか

Managerの哲学は、公開情報を観測し、実世界の苦しみを減らす介入を科学的に評価すること。ここで次の権利は別物だ。

1. **閲覧**: ブラウザで読める。公開されていること自体はライセンスではない。
2. **研究利用**: 研究のために分析・モデル比較に使用できるか。目的・入手元・研究参加者の同意も考慮する。
3. **再配布**: 原文、コード、学習データ、生の研究参加者レコード、モデル重みを公開してよいか。
4. **製品利用**: 商用Managerの一部として使えるか。帰属表示、付随規約、プライバシー、API契約、モデル固有の条件を満たすか。
5. **現実世界の実行権**: 上記すべてを満たしても、他者に金銭や環境操作を行う権限は**別途必要**。

`source-rights.json`では不明なことを`hold`にしている。公開性を理由に`allowed_with_conditions`へ自動格上げしない。

## 一次資料ごとの調査結果

### 1. HeartStepsの公開データ（研究データ）

- 公式: https://github.com/klasnja/HeartStepsV1
- ライセンス原文: https://github.com/klasnja/HeartStepsV1/blob/main/LICENSE
- GitHubライセンスBlob SHA: `10fabd90118f7ce38bb2e4753e105e744442a429`
- **確認:** リポジトリのLICENSEは **Creative Commons Attribution 4.0 International (CC BY 4.0)**。適切な帰属表示、ライセンスURL、変更表記などの条件が付く。
- **判断:** 過去の実験の方法・要約統計を学ぶことは可能。研究データのローカル分析は条件つき。参加者レコードの**生データをGitHubや記事へ再配布しない**のをManagerの運用上の方針とする。
- **保留:** ライセンスが個々のデータ権限・同意・プライバシー制約の全てを消すわけではない。`users.csv`は参加者属性・アンケートを含む。最小列・目的限定・再識別防止が必要。商用・大規模利用は確認前に許可しない。
- 研究論文（別の著作物）: https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/ 。本文は雑誌社の出版モデルで著作権表示があり、**CC BY 4.0を論文本文まで拡張しない**。
- 解析コード（別のリポジトリ）: https://github.com/StatisticalReinforcementLearningLab/HeartstepsV1Code 。公開で閲覧できるが確認したルートのtreeではLICENSEを見つけられなかった。**コピー・再配布を許可済みと扱わない**。方法を独自実装するのと原著コードをそのまま製品に含めるのは違う。

### 2. SocSci210（複数研究由来の行動予測データ）

- 研究者のREADME: https://github.com/akaashkolluri/socrates/blob/main/README.md
- 公式配布データ: https://huggingface.co/datasets/socratesft/SocSci210
- Dataset Card: https://huggingface.co/datasets/socratesft/SocSci210/raw/main/README.md
- README Blob SHA: `e8101f17f2a9d150e899dc6c472f13a3fdccf750`
- **確認:** 著者のREADMEは、原データが複数研究の派生物であり、**それぞれの原ソースのライセンスが残る**と明記。データが公開・ダウンロード可能でも全210研究に共通する再配布・商用許諾があると断言できない。
- **追加の注意:** Hugging Face閲覧画面には参加者属性、調査刺激、回答が表示される。個人情報・機微に関連する変数を含み得る。一般公開状態と個人について詳細予測・プロファイリングをする許可は別物。
- **判断:** 方法、データ構造、分割定義を確認して学習する。各研究の元データ規約とプライバシー条件が明確になるまで、**全レコードのローカル取得・再配布・商用利用はhold**。ソース論文の数値を引用し「Managerが再現した」と言わない。

### 3. Socratesのモデル重み（データとは別の権利）

- モデルカード: https://huggingface.co/socratesft/socrates-qwen2.5-14b-sft
- 実際のQwen2.5-14BベースのLICENSE: https://huggingface.co/Qwen/Qwen2.5-14B-Instruct/blob/main/LICENSE
- **確認:** ベースのQwen2.5-14B-InstructにはApache-2.0のLICENSEがある。しかし派生モデルのカードは**別サイズのQwen2.5-72Bのライセンスへのリンク**を提示している。どの追加条件が派生重みに適用されるか、本文だけでは一貫して確定できない。
- **判断:** 学術参考のモデル説明は可能。重みの再配布・製品組込は権利関係を解消するまでhold。14BのApacheライセンスだけで派生モデル全体を承認しない。
- Meta Llamaベースの派生モデルは**Meta Llama 3 Community License**に従う。MIT/Apacheとは異なる許諾・ガイドライン・利用制限がある。ベースは同意・アクセスが必要な場合がある。 https://huggingface.co/meta-llama/Meta-Llama-3-8B-Instruct

### 4. Concordia（シミュレーションソフトウェア）

- 公式: https://github.com/google-deepmind/concordia
- LICENSE: https://github.com/google-deepmind/concordia/blob/main/LICENSE
- LICENSE GitHub Blob SHA: `6b0b1270ff0ca8f03867efcd09ba6ddb6392b1e1`
- **確認:** **Apache License 2.0**。
- **判断:** ライセンス文面・原著帰属・改変の表示・適用される通知の維持などの条件を満たす限りコードの改変・再配布・商用組込が可能。ただし依存ライブラリ、モデルAPI、使用するデータセットの権利は別審査。
- ソフトウェアのライセンスがあることは、Concordiaのシミュレーションが現実の因果効果を予測できることの証明にはならない。

### 5. imozuru（自分自身の一次資料探索に使うスキル）

- 公式: https://github.com/MaryCache/imozuru
- LICENSE: https://github.com/MaryCache/imozuru/blob/main/LICENSE
- LICENSE GitHub Blob SHA: `7798918c7c5ba50cebc026459c5fc87b0bb63c5d`
- **確認:** **MIT License**、著作権表示は2026 MaryCache。
- **判断:** ライセンスと著作権・許諾表示を残して改変・再配布・商用利用は可能。ただしimozuruが取得する論文・PDF・動画・記事がMITライセンスになるわけではない。
- ソース調査の成果としてGitHubへ保存するのは**URL、原著の版、短い抜き書きと位置、独自の研究ノート**。第三者の原文全文をpublic repositoryへミラーしない。

## R006時点の製品ポリシー

| 使い道 | 原則 | 理由 |
|---|---|---|
| 出典のURL・DOI・研究方法・独自の評価表 | 出典を付けて保存 | 再現・検証可能性 |
| CC BYデータの必要最小限の研究分析 | 個別の権利・プライバシー条件を確認後 | ライセンスと研究参加者の権利は独立 |
| SocSci210全量データの一括取得 | **保留** | 原研究ごとのライセンス・倫理確認が未完了 |
| モデル重みの製品同梱・公開配布 | **保留** | モデル別・派生別ライセンス要確認 |
| Concordia/imozuruのコードの合法的再利用 | 条件つき利用可能 | 元のOSSライセンスを維持 |
| 大量の論文PDFをpublic GitHubへ直接アップロード | **しない** | 公開閲覧は再配布許諾と異なる |
| Manager自身の研究レポートPDF | 公開可能な素材のみで作成して保存可能 | オリジナルの要約・比較・出典リンク |
| 他者の資金や設備へ現実介入 | 明示権限が揃うまで不可 | 情報アクセスから実行権限は生じない |

## 次にこれをどう使うか

- `R007`: Evidence Registryの全項目に `source_id` と `rights_state` を追加する。出典が無い数値は受理しない。
- `H001`: HeartStepsの機微を含みうる参加者列の必要性を個別評価する。公開Gitにはraw dataを置かない。
- `S001`: SocSci210のデータ取り込みより先に各studyの許諾・個人情報リスクを確認する。未知40研究の評価分割を破壊しない。
- `K001`: 実世界Observation Storeにライセンス/同意/契約・機微情報・出典スナップショットの検査を追加する。

**確認レベル:** ライセンス原文、各研究チーム・著者README、HFモデル/データカードを開いた一次資料レビュー。個々の全研究の権利や臨床倫理まで調査完了したわけではない。
