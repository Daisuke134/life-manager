# map: manager-public-behavior-interventions

問い: 公開情報だけで行動予測・介入評価に必要な基礎とオープン実装を集められるか。
最初の検索語: behavior simulation / causal intervention / public randomized trial / JITAI / SocSci210 / imozuru

## 要る主張
- [x] 研究分野の中心的な「場」と、シミュレーション検証の課題が原著に存在する — sources/larooij-2025-validation.md:5
- [x] 公表済みの実世界介入研究には、実際の歩数効果と公開データがある — sources/klasnja-2019-heartsteps.md:5; sources/heartstepsv1-2023-readme.md:5
- [x] 公開行動予測データには、学習／評価の分割定義が含まれる — sources/kolluri-2025-socsci210.md:5
- [x] 人間らしい出力の再現性と介入効果の再現性は同一ではない — sources/li-ji-2026-simcausal.md:5
- [x] 社会シミュレーション基盤は既存の公開実装を活用できる — sources/concordia-2026-readme.md:5
- [x] 分布予測の誤差と信頼度を実測データで評価する実践例がある — sources/simile-2026-confidence.md:5

## 用語
- ABM/GABM (エージェントベース社会シミュレーション) — https://github.com/google-deepmind/concordia
- JITAI/MRT (介入タイミング・微小無作為化試験) — https://pmc.ncbi.nlm.nih.gov/articles/PMC5364076/
- TVD (回答分布間距離) — https://www.simile.com/blog/confidence
- ATE/Causal effect (介入効果) — https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/
- calibration / out-of-distribution validation (校正・未知環境評価) — https://pmc.ncbi.nlm.nih.gov/articles/PMC12627210/

## 人
- Predrag Klasnja, Susan Murphy — HeartSteps・微小無作為化試験
- Joon Sung Park, Michael Bernstein — Generative Agents・SocSci210・Simile
- Maik Larooij, Petter Törnberg — social simulation review
- Zonghan Li, Feng Ji — descriptive vs causal fidelity, 2026 preprint
- Akaash Kolluri, Shengguang Wu — SocSci210

## 場
- ACM UIST / arXiv / Stanford HAI — simulation and human behavior
- Annals of Behavioral Medicine / PubMed Central — MRT・JITAI
- JASSS (Journal of Artificial Societies and Social Simulation) — ABM validation
- GitHub / Hugging Face / Stanford project sites — public code, data, model and splits

## 原文（sources/）
| 資料の種類・題名 | ローカル保存分 | 原文URL | 取得と追跡 |
|---|---|---|---|
| 〔論文〕Larooij 2025 validation | sources/larooij-2025-validation.md:5 (短い抜き書きのみ) | https://pmc.ncbi.nlm.nih.gov/articles/PMC12627210/ | 1周目; citation trail/作者の公開文書 |
| 〔論文〕HeartSteps effect in the field | sources/klasnja-2019-heartsteps.md:5 (短い抜き書きのみ) | https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/ | 1周目; citation trail/作者の公開文書 |
| 〔本人〕HeartSteps repository records | sources/heartstepsv1-2023-readme.md:5 (短い抜き書きのみ) | https://github.com/klasnja/HeartStepsV1 | 1周目; citation trail/作者の公開文書 |
| 〔本人〕SocSci210 unseen-study data splits | sources/kolluri-2025-socsci210.md:5 (短い抜き書きのみ) | https://github.com/akaashkolluri/socrates | 1周目; citation trail/作者の公開文書 |
| 〔論文〕Simulation predictions may not be causal | sources/li-ji-2026-simcausal.md:5 (短い抜き書きのみ) | https://arxiv.org/html/2604.02458v1 | 1周目; citation trail/作者の公開文書 |
| 〔公式〕Existing generic simulation library | sources/concordia-2026-readme.md:5 (短い抜き書きのみ) | https://github.com/google-deepmind/concordia | 1周目; citation trail/作者の公開文書 |
| 〔本人〕Simile real-data calibration | sources/simile-2026-confidence.md:5 (短い抜き書きのみ) | https://www.simile.com/blog/confidence | 1周目; citation trail/作者の公開文書 |
| 〔本人〕imozuru original workflow | sources/imozuru-2026-readme.md:5 (短い抜き書きのみ) | https://github.com/MaryCache/imozuru | 1周目; citation trail/作者の公開文書 |

## 次の手がかり
- HeartSteps READMEに引用されたLiao et al. (2020) Personalized HeartSteps の本文と解析コードを追跡・再現する
- SocSci210のmetadata/participant_mapping.jsonと各ソース利用条件を確認する
- HeartStepsの公開CSVを権限あるネット接続環境で入手し、参加者単位・時系列構造を確認する
- Simileのvalidation blogは自社公表。独立した複数研究で同じ結果かを検証する
- Li・Ji (2026) の未査読プレプリントについて、追試／批判／公開再現コードを探索する

### 出典保存の制限
- この環境では外部GitHubのローカルcloneがDNS制限で失敗した。imozuru本体のスクリプトはインストールしていない。
- 原著はブラウズとGitHub公式連携で読み、ローカルには著作権上の安全を重視した短い正確な抜粋のみ保存。原著全文はURLを参照する。
- 公式imozuruの動作を完全に再現したとは主張しない。研究地図・追跡・行指定照合のみの適用。

## 2026-10-20の追加引用・反証経路
- MRT実験設計の原典: https://pmc.ncbi.nlm.nih.gov/articles/PMC4732571/ — Microrandomized Trials: An Experimental Design for Developing Just-in-Time Adaptive Interventions
- 後続研究・原著(方法の厳格化): https://pmc.ncbi.nlm.nih.gov/articles/PMC9755932/ — Microrandomized Trials for JITAI
- Li & Ji(2026) LLMのdescriptive vs causalの比較 https://arxiv.org/html/2604.02458v1 — 通常の回答分布が合っても効果予測は別の評価が必要
- 介入ベンチ用研究者の元データ: https://github.com/klasnja/HeartStepsV1 と CC BY 4.0 LICENSE
- SocSci210分割仕様: https://github.com/akaashkolluri/socrates (data splits study-wise)。モデルだけで因果効果が評価済みとは言えない
- 未到達: 総称「世界の苦しみ」の一律に妥当性のある測定指標、両分野で高精度に因果効果を予測できる公開基盤は今回の探索で確認できず
