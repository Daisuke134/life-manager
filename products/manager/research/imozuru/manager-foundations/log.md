# log: imozuru research dig 2026-10-20

## 0周目：2つの異なる探索経路
- 概念・実装から探す: generative agents, SocSci210, Concordia, Simile validation, JITAI; Web＋Firecrawl Researchを利用。
- 実世界の結果から逆に探す: randomized field experiments, HeartSteps, Opower, cash transfers, effect estimates; Web＋Firecrawl Researchを利用。
- 上記は自分で別方向に調査。imozuruの独立サブエージェント2本を起動したものではない。
- 発見した人・場・用語をmapへ記録。検索結果の抜粋を、原著を開かずに確証扱いしない。

## 1周目：原著の取得・引用連鎖
- HeartSteps公刊論文（PMC）→執筆研究者の公開GitHubデータ（klasnja/HeartStepsV1）→README内に引用されたLiaoら(2020)の強化学習・QianらのMRT方法論へ。
- SocSci210の研究者README→過去のGenerative Agents（同一Joon Sung Park）→Google DeepMindのConcordia原著／公開実装と比較。
- Simile公式confidence method（TVD, 5-fold）→同じ問題を反証方向から検討したLi・Ji (2026)原著（descriptive≠causal）。
- Larooij/Törnberg reviewでvalidationの中心問題と専門領域の場を確認。
- 6/6主張に原著の短い行指定抜き書きを対応させた。引用の内容が全文の一部であることを明示する。

## 停止・未到達・制限
- 暫定停止: 学習順序を決めるための6主張に一次資料位置がついた。公開CSVそのものの集計・実験結果の独立再現は**未実施**。
- ローカル環境はgithub.comのDNS接続不可。スキルのCLIと原文自動fetch、OpenAlex chain.pyの実行は未実施。GitHub連携とFirecrawlで外部原著と引用先を辿った。
- 完全な公開データのライセンス・個人レコードの扱いは、実データをローカルへ取り込む前に改めて監査する。
- 新規Web記事やブログは未公開。ユーザーの発表予定は仮であり日程・所属は未確認。

## 2026-10-20 追加作業：imozuru公式report.pyの実行
- https://github.com/MaryCache/imozuru のREADME, `skills/imozuru/SKILL.md`, `scripts/report.py` を、連携済みGitHubアプリを通じて原著者リポジトリから取得。
- report.pyは上流blob SHA `493b759fcee8328c3dcfc61ba21148afe5957040` と `git hash-object` が完全一致するようにオフラインコピーした。MITライセンスは同梱。
- 前回のmap.mdに対応する原著7抜粋を元の短文ファイルに残し、原著者の `report.py --check` を実行して **7/7 正確な行指定抜き書きとして一致**。さらに公式のHTMLレポートを生成した。
- 検索（資料の有効性/現実のRCT vs LLM社会シミュレーションの因果忠実度）という2経路で別々に検索。HeartSteps元論文、元データREADME、SocSci210 README、Li & Ji反例、JITAI設計、Concordia実装、Simile自社校正の一次資料を実際に開いた。
- 元論文やGitHubファイル自体はFirecrawl/GitHubアプリ側で読み込み、引用先も手動で追跡した。**imozuru公式fetch.py / chain.py はインストール・実行していない**。このコンテナのDNS接続が無効。**imozuruの全文取得・完全なサブエージェント並列運用まで達成したと称さない**。
- 残された主張：実際の予測モデルが現場介入の**因果効果を汎用的に当てられる**証拠はまだ不十分。反証可能な追加研究課題として継続。
