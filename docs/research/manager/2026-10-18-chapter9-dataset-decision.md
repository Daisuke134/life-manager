# 第9章のデータ候補と最初の学習課題

調査日: 2026-10-18 UTC。これは調査資料であり、進捗の正本ではない。対象はマネージャーの最初の行動・経験モデル。会社 Ninja の使命は **End suffering**。技術はそのための方法である。ここでは、使命に近く、実際の観測と照合できる最初の課題を選ぶ。

## 提案

最初の候補は、UCL の mindfulness / mentalization スマートフォン介入研究の公開 EMA データ `chfy2` とする。まず列の意味、時刻、介入が提示された条件、記録された応答を再現する。次に、同じ人の次の回答時点における自己報告ストレスを予測する課題と、提示された介入への記録上の応答を予測する課題を分ける。これは採用候補の提案であり、モデルの学習・精度確認・介入実装は行っていない。

この選択は「苦しそうな人に通知を増やす」という設計を検証対象にできる。高い必要性と、支援に応答できる状況は一致しない可能性がある。将来の目的は、本人が望む支援への接続と苦痛の軽減を両立し、不要な通知や回答負担を減らすこと。応答率の向上だけを最終目的にしない。今のデータだけでは、その設計変更の効果は確定できない。

主資料は Jaremba, O’Reilly, Mason, Nolte, Shaikh, O’Driscoll, [Optimizing just-in-time adaptive interventions for interpersonal distress: mechanisms, prediction, and the challenge of engagement](https://doi.org/10.1038/s41598-026-39518-z), Scientific Reports, 2026-02-11（Version of record 2026-03-09）。原試験は O’Driscoll ほか、[JMIR Mental Health, 2025-09-30](https://mental.jmir.org/2025/1/e79296)。対象は不安・抑うつ症状のある成人で、一般住民の無作為標本ではない。公開データと著者コードを確認したため候補に挙げたが、診療判断や自動介入の最初の製品課題として承認したものではない。

## 約5つの最初の対象を比較する

| 対象 | 実際の観測と時間 | 学べる問い・意味 | 今の判断 |
|---|---|---|---|
| 1. 支援提示への応答と次の自己報告ストレス | UCL `chfy2`。人×EMA回答。28日、1日4回の通知。介入提示フラグ、応答フラグ、ストレス等 | 支援を必要とする時と応答できる時を分け、通知負担を考える | 最優先候補。応答記録の厳密な意味と利用可能時刻の確認を先行 |
| 2. mindfulness の実践開始・継続 | 2024年の多施設単回実験に公開データ。2025年の Headspace 支援研究には実際の利用回数・分数がある | 実践を続けられる条件と苦痛の変化を分ける | 前者は翌日継続のデータではなく、後者は著者への申請が必要。即時の翌日継続課題には採らない |
| 3. 日常活動と経験した負担 | ATUS Well-Being Module。人×活動エピソード、1日の日記と選ばれた活動の感情報告 | 家事・ケア・移動等の時間と、経験したストレス・痛み・疲労の関係 | 環境・制度変更の仮説に適する。ただし個人の翌日行動を学ぶ縦断パネルではない |
| 4. 相談・サービス利用の開始 | Understanding Society の人×年次波等。費用・就業・健康・受診の候補情報 | 支援が必要でも接続できない障壁を調べる | 縦断候補だが UK Data Service の登録と利用条件確認が必要。具体的な利用開始項目・波の共通性は未確認 |
| 5. ストレス・睡眠・活動の翌時点予測 | StudentLife の10週・48学生の実生活観測。TILES / SNAPSHOT は別の実生活縦断候補 | 生活条件と次の報告状態、行動の時間的関係を学ぶ | StudentLife 原サイトとデータ許諾の確認が未完。TILES はログイン、SNAPSHOT は研究責任者の事前承認が必要 |

比較は「公開論文がある」「ファイルにアクセスできる」「利用許諾がある」「目的の行動が記録されている」を別々に判定した。原資料の正確な列名を確認する前に、相談開始や実践継続という目的変数を作らない。

## 第9.1節で先に定義すること

人を `i`、回答時点を `t` とする。1行は「ある人の、ある回答時点」の記録である。

- `X_it`: その時点までに分かる自己報告と過去の履歴。
- `D_it`: 介入が提示されたことを表す記録。候補列は `intervention_computation`。
- `A_it`: 提示に対する記録上の応答。候補列は `validation_yesno`。著者コードでは非応答をこの列から作る。
- `Y_i,t+1`: 次の EMA における自己報告ストレス等の経験指標。行動そのものとは分ける。

ここで予測するのは「次に何が記録されそうか」。介入を変えたときに苦痛がどれだけ減るかを示す因果効果とは別の問いである。データの `Engagement` は日常活動・他者との関わりに関する自己報告項目であり、アプリ介入への応答フラグではない。

最初の説明では架空の少数行を使い、「同じ人の時系列」「今までに分かる列」「後から分かる列」を示す。実データから特定の人の履歴を例示しない。次回に進める小さな成果物は、列辞書と時系列の対応図でよい。9.1で高い精度のモデルを求めない。

## 公開データの確認結果

[OSF project API](https://api.osf.io/v2/nodes/chfy2/) は未認証で読め、`public=true` と読み取り権限を返した。プロジェクトの license relationship が指す [license API](https://api.osf.io/v2/licenses/563c1cf88c5e4a3877f9e96a/) は CC BY 4.0 を返す。論文の公開ライセンスからデータの許諾を推測したものではない。出典表示、変更の明示等の条件を維持する。登録・連絡・課金はしていない。

[Data folder API](https://api.osf.io/v2/nodes/chfy2/files/osfstorage/68405bf4153f799cc3d6a43a/) で次を確認した。

| ファイル | 公開サイズ | 確認範囲 |
|---|---:|---|
| `dat_filtered_clean.csv` | 1,073,860 bytes | HTTP 200、ヘッダー1行のみ。個人のレコードは保存・表示していない |
| `filtered_df.csv` | 11,151 bytes | ファイル一覧のみ。被験者属性等の意味は未確認 |
| `EMA proximal v3.R` | 37,700 bytes | [著者コード](https://osf.io/download/7dfpu/) をメモリ上で読み、前処理・目的変数・評価箇所を確認 |
| `EE EMA EMI content.xlsx` | 11,994 bytes | [質問・介入内容](https://osf.io/download/yvcg8/) のみをメモリ上で読み、質問と応答選択肢を確認 |

CSV の列は `ID`, `ID_name`, `timeStamp`, `date`, `beep`, `Group`, `Contact`, `Contact_String`, `Criticism`, `Hostility`, `Overinvovlement`, `Support`, `Warmth`, `Mood`, `Stress`, `Engagement`, `Interaction`, `Assertiveness`, `intervention_computation`, `validation_yesno`, `cont_computation`, `condition` と補助の番号列。`Overinvovlement` は原ファイルの綴りをそのまま記載した。公開されていても `ID_name`, 自由記述に見える列、細かな時刻を成果物へ転載する理由はない。モデルに使う必要も現時点ではない。

著者コードの `prepare_data` は人と時刻を整理する。非応答の分析対象は `intervention_computation==1` かつ最初の観測以外で、`validation_yesno==0` を非応答とする。著者の前処理には欠損した提示・応答フラグを0にする処理がある。再実装では欠損を未知のまま残し、非提示・非応答との区別を先に調べる。

質問ファイルには介入へ進むかを尋ねる Yes/No の入口がある。一方、`validation_yesno` を入口の選択・画面を開いたこと・全手順を終えたことのどれに厳密に対応させるかは、現時点で確定できていない。原試験論文の「完了したエクササイズ」という集計説明だけで、この列を完遂ログと断定しない。当面の名称は「介入への記録上の応答」とする。実際に瞑想していたことを直接測る列とも言わない。

著者の次時点課題は同日の次の有効な回答を使い、その日の最終回答と夜間の境界を除く。翌日の予測とは呼ばない。回答の欠測があれば、次の観測が次の予定通知と一致するとは限らないため、経過時間も検査する。

## 最小の学習・構築サイクル

1. 列辞書、日付解析、`ID×beep` の重複、並び順、欠測、提示フラグと応答フラグの対応を集計する。個人データを表示しない。論文の人数・機会数と一致するかを確認し、相違があれば原因を記録する。
2. 行動側は `D=1` の観測に限定した応答の確率、経験側は次の同日 EMA の `Stress` を別々に定義する。著者の PCA 複合指標は再現用の別課題とし、最初は意味が直接分かる尺度を使う。
3. 応答のベースラインは訓練部分の応答率と単純なロジスティック回帰。ストレスのベースラインは今の値を次も予測する持続モデル、訓練期間の個人平均、線形回帰。複雑なモデルはこの比較の後に考える。
4. 既知の人の将来を測る時間順評価と、未知の人への適用を測る人単位の分割を別々に実行する。後者で個人固有効果を既知として使わない。分割は訓練前に固定し、同じ人の未来から過去へ情報を戻さない。
5. 行動側は Brier score・log loss・PR-AUC・校正、経験側は MAE と持続モデルとの差を見る。人数が少ないため、人を単位にした不確実性も示す。通知を減らせた、苦痛を減らせたという実地成果は別途測定する。

PCA・標準化・補完・閾値・特徴選択を全期間で作ると、未来の情報が訓練へ入る。著者コードには全系列の個人標準化、PCA、個人内分位点を用いる箇所があり、同じ `prediction_data` に対する予測を評価する箇所もある。このコードの読み取り範囲では、独立した将来・他者に対する性能は確認できない。論文の性能値を製品の予測精度として引用しない。PCA の符号にも任意性があるため、苦痛が大きい方向を尺度と照合する。

予測する瞬間も固定する。提示への応答を予測するなら、その提示への実際の応答を特徴に入れない。現在の応答を使う特徴は、応答が観測された後に発行する予測にしか使えない。自己報告ストレスは経験の報告であり、センサーから心を直接読み取った測定ではない。

## 因果効果と使命に近い次の道筋

この研究の群割付は mindfulness と mentalization の比較である。個々の提示をする・しないの割付や、応答する・しないは同じ無作為化ではない。提示は症状に応じて生じ、応答も本人の状態に依存する。提示後にストレスが低下していても、その低下を介入だけの効果とは確定できない。

使命に近い次の実証は、本人が選べる支援の形式・頻度や共有環境を変え、自己報告の苦痛、日常機能、支援への接続、回答・通知の負担を一緒に測ることである。実施するなら適切な研究設計と同意を伴う別の課題になる。現段階のモデルの予測を根拠に、症状のある人へ自動で支援を増減しない。人口全体の環境を変える構想へ進むにも、この小標本から一般住民への移転を検証する工程が残る。

## 他の候補のアクセスと落とし穴

- [2024 multisite mindfulness RCT](https://pmc.ncbi.nlm.nih.gov/articles/PMC11420060/) は37施設・2,239人の単回介入研究。[著者 GitHub](https://github.com/alessandro992/A-large-multi-site-test-of-self-administered-mindfulness) に `MainScript.R` と `finaldata.csv` がある。ヘッダーには `finished`, `progress`, クリック時刻、`group`, `stai1`–`stai20`, `sam1`–`sam3` 等があるが、翌日の実践履歴とは確認できない。GitHub ルートに独立した LICENSE は確認できず、データの再配布条件は OSF 側で改めて確認する。
- [2025 Headspace human-support RCT](https://formative.jmir.org/2025/1/e56963/) は実際のアプリ利用を扱うが、Data Availability は著者への合理的な依頼としている。公開論文・事前登録と、個票利用の許可を混同しない。
- [ATUS WB official files](https://www.bls.gov/tus/modules/wbdatafiles.htm) は2010・2012・2013・2021年を案内する。人と活動番号で core diary と結び、活動の長さ・種類と経験指標を扱える。[利用方法](https://www.bls.gov/tus/other-documentation/howto.htm) は活動用重みを指定する。2010–2013の活動選択の誤りと改訂重みに注意する。分析するなら人単位で分割し、同じ人の活動を訓練と評価に散らさない。1日の活動順序を、翌日までの追跡と読み替えない。
- [Understanding Society SN6614](https://datacatalogue.ukdataservice.ac.uk/studies/study/6614?id=6614) は縦断候補。[Safeguarded access](https://ukdataservice.ac.uk/find-data/access-conditions/safeguarded-access/) には登録と End User Licence が必要。Special Licence や Secure Access はさらに別条件。今回は登録しない。受診項目の利用開始を予測できるかは、波別辞書を確認するまで保留。
- [StudentLife author site](https://studentlife.cs.dartmouth.edu/dataset.html) は今回の取得がタイムアウトした。[解析用 R package](https://github.com/frycast/studentlife) の GPL-3 を元データの許諾として扱わない。原データの利用条件は未確認。小さな EMA データへ進む場合も、Stress の尺度方向と日付境界を辞書で確認する。
- [TILES download](https://tiles-data.isi.edu/download) はログインが必要と明記する。[2025 sleep benchmark preprint](https://arxiv.org/abs/2507.03520) も候補だが、論文公開からデータへの無条件アクセスは推論しない。[SNAPSHOT NSRR](https://sleepdata.org/datasets/snapshot) はデータ申請前に研究責任者の承認が必要。
- [WESAD current UCI page](https://archive.ics.uci.edu/dataset/465/wesad+wearable+stress+and+affect+detection) は15人の実験室データで、ライセンスを元サイト参照とする。検索結果の CC BY 表示だけで判断しない。短い窓をランダム分割すると同じ人・同じ実験区間が混ざる。実験条件の分類を日常の苦痛や翌日行動の予測と呼ばない。
- [HeartSteps V1](https://github.com/klasnja/HeartStepsV1) は CC BY 4.0 を明示する公開の実際の行動・介入データ。37人・6週・1日5機会、`suggestions.csv` は8,274行。`jbsteps30`, `jbsteps30pre`, `avail`, `send` 等を使う短時間の行動・無作為化介入の方法演習には良い。[辞書](https://github.com/klasnja/HeartStepsV1/wiki/Documentation-for-suggestions.csv) を確認済み。ただし歩数を苦痛の軽減と同一視しない。主たる用途を歩数増加へ変更する根拠にはしない。
- [BRFSS official documentation](https://www.cdc.gov/brfss/data_documentation/index.htm) は横断調査と明記する。相談や未受診の集団分布は調べられても、年別ファイルを同じ人の追跡データにはできない。NHTS の移動行動も負担の間接指標になりうるが、今回のストレス・支援応答データより使命との距離が大きく、第一候補へ繰り上げない。

Global Flourishing Study や Personal Suffering Assessment は苦痛・良好な生活の測定候補になる。単一波の公開だけでは行動の時間変化を学べないため、縦断データの利用可能性を別途確認する。

## 第8章との関係

第8Bの Rhode Island 人口再構成には世帯の家族構成・人数の制御があり、行動の観測を生成したものではない。UCL の人と Rhode Island の合成人口には共通の個人IDも検証された移転モデルもない。年齢等が似た人を結び付けても、Rhode Island の住民の行動を観測したことにはならない。このデータで独立した小さな時系列モデルを学び、人口への適用は別の検証課題にする。

## 今回の到達点

公開ページ、OSF の未認証メタデータ、許諾、ファイル一覧、CSVヘッダー、質問ファイル、著者コードを読んだ。個票の学習・集計・効果推定は行っていない。正確な応答フラグのイベント意味、時刻の利用可能性、人数・欠測・機会数の再現が次の確認点である。学習者の理解完了や実装完了としては扱わない。
