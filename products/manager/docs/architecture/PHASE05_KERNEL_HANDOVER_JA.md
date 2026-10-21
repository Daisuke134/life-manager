# Manager — Phase 04 → Phase 05 開発ハンドオーバー

更新: 2026-10-21 JST。研究用ManagerはLife Managerとは別製品であり、別ランタイム・別権限・別のデータ境界を維持する。

## 現在本当に動くもの

**P0: 科学・測定・CIの研究層**は実装済み:
- 出典、原論文、限界、ベンチマークのレジストリと権利分類。
- 一般確率・条件付き確率、Brier・TVD・Wasserstein、較正ビン、実験割付・spillover・潜在結果の教育/検証コード。
- HeartSteps公開CSVの監査と元の論文との選別不一致を記録。H005は科学的スキップ、元推定法の再現を主張しない。
- SocSci210 17元データファイル・210研究・2,901,390観測回答を使った170/40分割。48万超の未見回答から同一符号の頻度/多数派を測定。簡易回答符号の意味が異なるため人間行動モデルの妥当性とは別。
- 40未見研究の全データによる観測群別TVD・Brier、study-levelブートストラップ、seen研究だけで構築したLOOエラー警告境界、意味未整備時ABSTAIN。
- MiniLM公開凍結encoder＋seen側のみ学習したheadを同一800未見個票で2基準と実測比較（CI 39561547086）。SmolLM2-135Mを別の320未見個票で同一基準と比較し、有効出力率42.5%という失敗を保存（CI 39562677909）。いずれも元Socrates 8B/14B原実験の再現ではない。
- ZOZO Open Bandit Dataset実測6コホート60,000クリック機会をIPS/SNIPS測定、反実仮想の重み不安定（ESS=2.078）を特定。
- UCI Bike Sharing実測時系列holdout 2011年365日→2012年366日。
- 正規Concordiaを架空の2代理人×4イベントで実行した技術統合。人間の行動への一致度は未測定。
- GitHub Actions実行と個人情報を含まない結果JSONのみを公開。**Phase04 S001–S008の狭義研究・実装タスクは8/8検証済み、科学Gate1は未達。**

## 現在まだ動いていないもの

**一般目的の自律Managerループは未実装。** 研究の比較表とシミュレーターが、自ら許可を取得したり外部施設を変更したり苦しみを減らしたりすることはない。現在 `manager_core/config.py` は外部書込・投稿・送金・機器操作をfail-closedで禁止。実際の場の受益者が存在するとは報告してはならない。

## Phase05 K001–K014 — 完全な実装順序

| Task | コンポーネント | 核となる契約 | 本当の完了基準 |
|---|---|---|---|
| K001 | `models/source.py` | 公開出典URL、ライセンス、ハッシュ、機微性、日時 | 不明な出典や機微性未判定を拒否 |
| K002 | `models/observation.py` | 時刻、単位、対象、値と欠損 | 同じ数字でも単位・時点が違うと別観測 |
| K003 | `models/problem.py` | 課題、複数因果仮説、独立根拠 | 自分の仮説だけで原因確定を拒否 |
| K004 | `models/intervention.py` | 行動候補・費用・リスク・NO_ACTION | 選択肢に常に何もしないを含む |
| K005 | `forecast.py` | 予測分布と処置効果を別に扱う | Brier/TVDとATE誤差を混同しない |
| K006 | `state_machine.py` | 明示的状態遷移と失敗状態 | 実行不明を成功状態に遷移させない |
| K007 | `authority.py` | 権限発行者・権限範囲・期限・予算・取消 | 正当な委任範囲を超える行為を拒否 |
| K008 | `outbox.py` | 永続的な予約とidempotency_key | リトライ10回でも外部効果最大1回 |
| K009 | `reconcile.py` | あり/なし/不明の外部状態 | UNKNOWNなら外部照合前に再送しない |
| K010 | `verifier.py` | 実行者以外の独立計測 | ツール戻り値SUCCESSだけでは採点不可 |
| K011 | `evaluator.py` | 対照・事前登録・CI・害・費用 | 単なる成功回数から因果純便益を確定しない |
| K012 | `learning.py` | 候補モデルversion・holdout・rollback | 改善失敗時に旧版へ安全復元 |
| K013 | `audit.py` | source→decision→action→receipt→readback監査 | 第三者が記録を再確認可能 |
| K014 | クロスドメイン検証 | 金融と環境の模擬アダプターに共通核 | 領域追加で核の権限・証拠ロジック変更0 |

最初の実装はK001、K002、K003、K004、次にK006/K007/K008/K009/K010を先にTDDで進め、外部操作はoffline契約テストのみに制限する。科学的なモデル誤差はK005/K011/K012で研究から接続する。

## 監査可能なBlessing（将来の実世界改善）

**Observation → Competing hypotheses → NO_ACTION/Alternatives → Forecast → Authority → Idempotent execution → independent readback → preregistered causal comparison → policy learning → public evidence card**。

証明レベル:
- P0 = 文献、研究、統計比較、シミュレーション。
- P1 = 正当な外部効果の実行証拠。
- P2 = 外部の独立した実世界の変化。
- P3 = 対象への実質的便益を示す実測。
- P4 = 適切な比較対象に対する因果的な純改善、費用・害・不確実性込み。
- P5 = 別の人口・地域・領域でも再現したP4。

**透明性はP4の前提であって、P4の代用品ではない。** 便益が存在しない時は `NOT_MEASURED` と記録し、成功0件と不明の区別を保持。

## 総113タスクの現況（2026-10-21のGitHub台帳）

- Done **45**。Phase00=6、01=8、02=12、03=9+1科学skip、04=8、Phase07=1、11=1。
- Todo **65**。Phase05 K001–K014=14、Phase06の残7、Phase07=1、Phase08=8、Phase09=16、Phase10=6、Phase11=7、Phase12=6。
- Blocked **2**: F004は実行主体と資金権限、F007は物理設備運営主体と測定・実行権限。障壁があるということは第三者権限を勝手に拡大してよいという意味ではない。
- Skipped **1**: HeartSteps H005。元研究の解析用study.dayフィールド復元が不十分なため、元RCTの完全再現は行っていない。

**高優先度の追加作業:** 科学Gate1の独立RCT効果と意味一致の人間行動予測、Y001–Y003のYC W27申請物の実測デモ、C002/Y008の英語記事とスライドをサイト実公開し外部リンクで検証。

## 出典と証拠

[統合Phase04研究報告](../verification/PHASE04_FINAL_REAL_DATA_EVIDENCE_JA.md) / [210研究の実測値](../research/socsci/PHASE04_REAL_210_STUDY_COUNTS.json) / [MiniLM同一800回答](../research/socsci/PHASE04_S005_REAL_PRETRAINED_METRICS_2026-10-21.json) / [SmolLM同一320回答](../research/socsci/PHASE04_REAL_40_STUDY_SAME_SAMPLE_OPENMODEL_METRICS.json) / [ZOZOオフポリシー実測](../research/open_bandit/PHASE04_REAL_AB_OPE_REPORT_JA.md)。

**注意**: 8/8研究工程完了＝世界最高のマネージャー完成ではない。研究・推論・適法な外部実行・独立結果測定という各工程を順に接続する必要がある。
