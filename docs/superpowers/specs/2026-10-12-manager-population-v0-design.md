# Manager 人口と評価 v0

2026-10-12。既存の [aggregate-first設計](2026-10-12-manager-aggregate-first-design.md) の最初の実装範囲を固定する補足。ユーザーは同設計の説明後、Superpowers writing-plansで実装順を明確にすることを依頼した。実行状態と唯一のTODO正本は [統合SSOT](2026-09-25-life-manager-unified-ssot.md#manager-implementation-plan-20261012)。Manager全体を独立した小規模アプリへ置き換える提案ではない。

## 目的と実装範囲

公開の集団統計から人口の重みを構築し、入力に渡していない交差表へどれだけ一致するかを再現可能に測る。Population/Evidence/Evaluatorの基礎を作る。行動予測、環境変更、実行、field成果は次のサブプロジェクトで接続する。モデルAPI、大規模学習、受益者UI、外部作用はv0へ含めない。

公開ビジョンは[Manager for the universe](2026-10-12-manager-universe-design.md)。すべての生命と宇宙全体が最終対象。人口v0は最初の部品であり、製品の最終対象や規模を定義しない。

IPF algorithmは既存OSS `ipfn==1.4.4` のNumPy backendを利用する。wheel SHA256 `a0b5f3c9c5de8c71207cc88f1e51b68135d482a50d7035c58f3e202d33a6b026`、MIT、Git参照commit `fa57b905291e4125c6e4f7ddacc8770218ad024e`。`numpy==2.4.4`, `pandas==2.3.3`をCPU依存として固定する。ゼロtargetの軸を除いてsolverへ渡し、戻り値を元shapeへ復元する。libraryのconverged flagだけでは採用せず、normalized marginal残差を独立に計算して<=1e-10を確認する。max_iterationはlibraryのinclusiveループを踏まえ `max_iterations-1` を渡し、実iteration数を検査する。

## データと確認した取得経路

米国ACS 2024 5-year Detailed Table B17001（2020–2024の推計）。対象はpoverty statusを判定できる人口で、全人口そのものではない。年齢×貧困状態の集計を使う。incomeそのもの、健康、行動、実地効果へ解釈しない。

公式URL: `https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b17001.dat`。

2026-10-12のpreflightでpublic download HTTP200、state GEO_IDの52行、header、52地域の詳細セル/総数一致を確認。取得したstate extract SHA256は `316b602beb75129605d91ca7a9c440a37df7bc9c02271d86d3eb39cf25559a9d`。元ファイル全体のhashではなく、先頭から読んで州行を抽出した結果のhash。原資料が更新されたら新しいsnapshotとして扱い、過去reportを上書きしない。

Census APIのgroup metadataはキーなしで取得できたが、実データqueryはmissing_key.htmlへredirectした。APIをkeylessとして実装しない。公式Summary Fileは別の公開配布経路。metadataは `https://api.census.gov/data/2024/acs/acs5/groups/B17001.json` を参考にし、mappingと対象定義をsource noteへ保存する。

B17001Eは人種別の別表。ファイル名の末尾eをestimateの意味として付けない。必要headerは `GEO_ID` と `B17001_E001`〜`B17001_E059`、`B17001_M001`〜`B17001_M059`。MOEは保存するが、依存するセルのMOEを単純加算して正確なCIにしない。

## 固定した対象・分割・セル順

州GEO_IDは正規表現 `^0400000US[0-9]{2}$` のみ。US50州+DCはFIPS `01,02,04,05,06,08,09,10,11,12,13,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,44,45,46,47,48,49,50,51,53,54,55,56`。PR72は取得するがv0対象外。重複/不足はfail。52行が揃う前に8MiBを超えるかEOFならfailし、不完全な結果を成功snapshotとして保存しない。入力は取得済みextractを使うoffline modeも持つ。

開発6州: `06,12,17,36,48,53`。validation4州: `04,13,25,37`。test41地域: 対象51から上記10を除いた集合。分割はFIPSで固定し、行順に依存しない。地域間の独立/無作為抽出を仮定した全国一般化CIは出さない。

6セルの順序は `(below_child, below_adult, below_senior, above_child, above_adult, above_senior)`。childは18歳未満、adultは18〜64、seniorは65以上。男女を合計する。

- below_child: E004–E009 + E018–E023
- below_adult: E010–E014 + E024–E028
- below_senior: E015,E016,E029,E030
- above_child: E033–E038 + E047–E052
- above_adult: E039–E043 + E053–E057
- above_senior: E044,E045,E058,E059

六セル合計はE001、belowはE002、aboveはE031に一致する。欠測/負のsentinel/nonfiniteは0へ補完しない。破損・異なる表・単位の変更はfail。MOEの欠測はその値をunknownとして保持し、estimateが欠測なら対象行は有効値として使わない。v0の完全な51地域reportは必要estimateの不足でfailし、部分実行はcoverageを付ける別modeとして将来設計する。

## 方法と公平な入力

開発6州のjoint countsだけを合計し、seedを作る。各対象地域からは年齢3群と貧困2群のmarginals、およびtotalだけを再構築側へ渡す。validation/testのjoint countsは独立score側へ分離する。

比較するmethod:

1. **independent**: 対象のrow/column marginalsの積。
2. **ipf**: 開発seedを対象のmarginalsに合わせる。row scaling→column scalingを交互に適用。正規化marginal residual `<=1e-10`、最大1000iteration。収束しなければexplicit error。seedは全6セルpositiveであることを要求し、ゼロsupportへ架空の微小値を追加しない。targetのゼロmarginalはそのrow/columnを0にする。

IPFは未知の関係を発見する保証ではない。実観測のheld-out jointとの誤差を比較し、independentより悪ければそのまま報告する。公開資料が誰にも見えないというblind/prospective実験ではなく、method inputから評価セルを分離するretrospective reconstruction。

## 部品と型の責任

配置は既存greenfield設計通り `apps/manager/src/manager/`。population専用型は `population/contracts.py`、既存設計のWorldState/Intervention等の汎用契約をこの段階で全部作らない。全recordはfrozen dataclass。runtime type/値の検証を行う。

- `SourceRef(url:str, table:str, period:str, universe:str, acquired_at:str, extract_sha256:str)`。
- `JointTable(geo_id:str, source:SourceRef, counts:tuple[float,float,float,float,float,float], total:float)`。
- `Marginals(geo_id:str, source:SourceRef, poverty:tuple[float,float], age:tuple[float,float,float], total:float)`。
- `FitResult(geo_id:str, method:str, counts:tuple[float,float,float,float,float,float], iterations:int, max_residual:float, seed_sha256:str|None, target_source_sha256:str)`。
- `PopulationScore(geo_id:str, method:str, tvd:float, max_cell_error_pp:float, poverty_rate_error_pp:tuple[float|None,float|None,float|None])`。age群が0人なら該当rateはNone。

## 出力と受入条件

同じoffline input/設定から同じ数値結果を再生成できる。timestampはmetadataで数値比較から除く。reportはper-region TVD、最大cell誤差pp、年齢群別貧困割合誤差pp、unweighted mean/max、人口加重meanを区別。推計されたreferenceに対する差であり真の人口との確定誤差ではない。推計誤差は別の限界として記載する。

reportに `stage=empirical_reconstruction`、`population_fidelity=measured`、`behavior_prediction/policy/execution/field=not_run`。測定された結果が悪くてもreport generationは成功し得る。良い成績を受入条件にしない。

manifestはsource/extract/split/config/code hash、method、numerical settings、wall time、seedの開発対象、invalid counts、参照セルへの入力非アクセスを記録。paid model calls=0。実費のないtoken costを推測しない。fetch/prepare/reconstruct/scoreを別CLIにし、reconstruct commandはreference pathを受け取らない。

Python >=3.12。stdlibと、上記の固定ipfn/NumPy/pandas CPU依存を使う。新しいprovider、GPU、paid API、scheduler、live environment adapterは追加しない。unittest offline gateと実資料を使うexplicit integration runを分ける。raw/run outputはGit外へ保存し、small public fixtures/schema/mappingだけsourceへ。

## 2026-10-18 データ選定の根拠と次段階

第8単元の資料比較は [データ選定記事](../../research/manager/articles/2026-10-18-manager-dataset-selection-ja.md) に記録。人口v0には引き続き2020–2024 ACS B17001を使う。年齢×貧困の公開交差集計を採点用に隠し、周辺集計だけから復元する。既存の51地域、6/4/41分割、単純独立法/IPF比較を変更しない。地域分割と評価セルの非アクセスは答えの混入を防ぐ条件であり、周辺集計と交差集計が独立に採取されたことを意味しない。

次の世帯人口部品の第一候補は、同じ2020–2024 ACS 5-year PUMSの住宅・個人ファイル。小規模な読解・実装対象にRhode Islandを推奨。公式配布先のcsv_hri.zip/csv_pri.zipの存在を確認したが、データ本体・世帯部品はまだ未取得/未実装。人口v0の6セル処理へ混在させず、世帯部品のスキーマと受入条件を別途具体化する。

PUMSではSERIALNOによる所属、SPORDER、AGEP、RELSHIPP、NP、WGTP/PWGTPなどを辞書で確認し、通常世帯と空き家・集団居住施設の扱いを定義する。世帯単位の分割と整数化前後の誤差を検査する。PUMAは公開用の粗い地理で、実住所ではない。PUMS推計とACS詳細表は元調査が重なり、加重推計も完全一致しない場合があるため、別ファイルとの比較を完全独立の実証と呼ばない。

ATUS/NHTS/BRFSSは、生活時間/移動/健康という用途別の追加候補。SocSci210は反応予測の候補、HeartStepsは介入評価の教材候補であり、この人口v0への採用ではない。異なる調査の人物を年齢などの一致だけで同じ実在個人として結合しない。データ利用と再配布の条件、対象母集団、期間、地理、重み、欠測、精度、出典の重なりを記録する。貧困状態を苦しみそのものと扱わず、人口精度から実地便益を主張しない。
