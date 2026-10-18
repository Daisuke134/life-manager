# マネージャー 世帯人口v0（8B）

## 目的と範囲

本人が8Aの次の「6B」を実装し、図・記事・スライド・カルーセルに再利用する成果を要求した。直前の段階名に沿い8Bを意味すると解釈する。Rhode Islandの2020–2024 ACS 5-year PUMS住宅/個人記録を結び、世帯を壊さず複製した仮想人口を作る。調整前後・整数化前後の誤差、人数・所属の整合を測る。8Aの6セル結果は変更せず、行動予測/因果効果/実地便益は未実行とする。進捗の正本は統合SSOTのみ。

再標本化、深層モデル、LLMという候補のうち、今回は既存見本の世帯再標本化とIPFによる調整を採る。世帯内関係をコピーして保つ最小の基準実装で、新しい組み合わせを学習して生成するモデルではない。BN等との実測比較は後続。8Aのartifact/hash/CLI/test方式と固定CPU依存を再利用する。Python3.12、ipfn1.4.4/NumPy2.4.4/pandas2.3.3、追加の有料API/GPU/本番変更なし。既存MITで公開可能なソース・再実行手順・結果解説を保存し、raw/runはGit外へ置く。第三者コードはコピーしない。

## 一次資料と取得

- 住宅 https://www2.census.gov/programs-surveys/acs/data/pums/2024/5-Year/csv_hri.zip （CSV名psam_h44.csv）
- 個人 https://www2.census.gov/programs-surveys/acs/data/pums/2024/5-Year/csv_pri.zip （psam_p44.csv）
- 辞書 https://www2.census.gov/programs-surveys/acs/tech_docs/pums/data_dict/PUMS_Data_Dictionary_2024.pdf
- 公式集計 https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b11016.dat
- 定義 https://api.census.gov/data/2024/acs/acs5/groups/B11016.json

2026-10-18に公式ZIP/PDF/header/全行を読解。2024はSTATE列（旧STではない）。ZIP同梱ReadMeは2026-03-05作成、PUMSの秘匿処理、住宅WGTPと個人PWGTP、空き家とGQの違いを明記。PUMS/ACSは同じ調査由来で、比較を独立調査による実証と呼ばない。住宅ZIP hash90fd8f5d577260ebbafbcf8231506a4aa644d3902d2303d4d109db8153a48238、個人ab856a1c287f9930d0886a8b2e733313b08d7a6f07114e4e3bbf711337d7fa24、辞書929c2752995b0af1c16d5c64de8cdc43b4aa7d388ee2d45b4b4df90fecce1dff。資料更新は別snapshotとし、過去hashへ偽装しない。

fetchは各ZIP最大64MiB、CSV member最大128MiB、行数最大100万。ZIPを展開せず期待したmemberだけ読む。重複member/不正header/破損/上限/別州/不完全ファイルはfail。B11016は8MiB内にRI行がなければfail。入力manifestはURL/bytes/SHA256/取得時刻/期間/州を含む。既存snapshotを上書きしない。オフライン読込でも全hashと定義を検証する。

## 個人と世帯の契約

frozen dataclassをpopulation/households.pyへ置く。

- Person(serialno:str, order:int, age:int, sex:int, relationship:int, weight:int)。order1..20、age0..99（top-codeあり）、sex1/2、relationship20..38、weight1..9999。IDは空でない英数字32文字以下。
- Household(serialno:str, size:int, hht:int, weight:int, persons:tuple[Person,...])。size1..20、hht1..7、weight1..9999。personのserialno一致、人数=size、order重複なしで1..size、reference person（RELSHIPP20）が一人。家族世帯HHT1..3はsize>=2、HHT4/6はsize1、HHT5/7はsize>=2。個人をばらばらに抽出しない。
- HouseholdControls(total:int, family:tuple[int,int], size:tuple[int,int,int])。非負整数、各合計=total>0。家族世帯は単身にならないのでfamily[0] <= total-size[0]。

住宅はRT=H/STATE44、TYPEHUGQ1でNP>0だけ対象。NP0空き家、TYPEHUGQ2/3のGQ placeholderは除外して件数記録。住宅serialnoは全件一意。個人RT=P/STATE44は全件(order,serialno)一意。GQ個人RELSHIPP37/38を除外し、その件数を記録。通常個人に住宅がなければfail。各対象世帯に全員が揃わない、空き家に人がいる、GQと通常世帯の所属が矛盾すればfail。WGTPは世帯の複製重み、PWGTPは元PUMSの個人年齢構成の診断用であり、同じ重みとして置換しない。

## 入力と評価表の分離

B11016の対象はhouseholds。E001総数、E002家族総数、E009非家族総数。家族サイズ2/3+はE003とsum(E004..E008)。非家族サイズ1/2/3+はE010/E011/sum(E012..E016)。親合計一致を検査、family×sizeの順に6セル(0,family2,family3plus,nonfamily1,nonfamily2,nonfamily3plus)。0は定義上の構造的ゼロ。

prepareは世帯見本、周辺制約(total/family/size)、採点用referenceを別ファイルへ保存。モデルには制約とPUMS見本だけを渡す。B11016交差セルはscoreだけが読む。PUMS見本自体には世帯の組み合わせがあり、公開交差表も人が確認できるため、盲検/将来予測ではなく回顧的な再構成。初期のサイズ区分は1/2/3+に固定し、評価成績を見て変更しない。単一州の実装検証であり地域転移を実証しない。

## 方法、整数化、出力

baselineはWGTPをtarget totalへ比例スケールする。calibratedはWGTPのfamily×size重み集計へ既存ipfnのNumPy backendを適用し、familyとsizeの周辺制約へ合わせる。tolerance1e-10、max1000。残差を独立検査。構造的ゼロを残し、標本にないsupportへepsilon/仮想家族を追加しない。軸のtarget0を除いて復元、不可能なsupportや非収束は明示的エラー。

調整後の各世帯重みはWGTP×(当該セルの調整後値/元セルの合計)。同じ世帯セル内の相対重みを保つ。次にTRS（truncate–replicate–sample）：各重みの整数部分を採用し、残りの必要世帯数を端数に比例して復元抽出する。NumPy Generator seed20261018、並べ方はserialno順で固定。総世帯数はtarget整数へ厳密一致するが、他の周辺制約と総人数は必ずしも一致しない。baseline/calibratedを同じseedで比較する。seed20261018..20261027の10回について整数化誤差の幅も記録し、良いseedを選ばない。

出力households.csvはsynthetic household_id/seed_serialno/size/hht/state、persons.csvは新しいperson_id/household_id/source order/age/sex/relationshipを持つ。世帯を複製すると所属する全員を複製し、新IDを付ける。実在名簿や実住所の再現としない。最大100万世帯・500万人の出力上限。CSVは行単位で原子的に保存してhashを残し、完了manifestを最後に保存。検証は行を再読しIDの一意性、所属、人数、元記録の属性維持、構造的ゼロを確認する。

## 評価と成果物

段階をbaseline weighted、calibrated weighted、baseline integer、calibrated integerで別表示。B11016の6セルとのTVD、周辺制約の最大差/total、総世帯数、総人数、age3群の割合を出す。年齢割合は元PUMSのPWGTP加重値と診断比較するが、独立データの検証ではない。replicate weightsによる推計誤差の伝播は今回未実装。GQを含む全人口の数字へ混在させない。世帯内の全員へ同じ複製回数を使うことによる個人分布の差を明示する。

reportはstage=empirical_household_synthesis、population_fidelity=measured、behavior_prediction/policy/execution/field=not_run、paid_model_calls0。調整がbaselineより悪くてもそのまま記録し、好成績を受入条件にしない。raw/input/prepared/合成人口CSV/完全reportはGit外。Gitには小さいfixture、仕様、コード、MIT、再実行コマンド、公開用の集計記録、生成説明図と実測グラフ、記事、6枚のスライド/カルーセル素材と出典を置く。投稿/応募/メール送信は今回行わない。

## CLIと受入条件

- fetch-households --out DIR → housing.zip/persons.zip/b11016.dat/source.json。
- prepare-households --input DIR --out DIR → households.jsonl/controls.json/reference.json/manifest.json。
- synthesize-households --prepared DIR --method baseline|calibrated --out DIR → weights.json、households.csv、persons.csv、manifest.json。referenceを開かず、prepared manifestもreferenceのhashを検査する目的では開かない。
- score-households --prepared DIR --run DIR --run OTHER_DIR --out DIR → report.json/report.md。2方式を要求。全hash、設定、入力、コードを照合し、CSVを再読して採点する。

オフラインsuite、公式fetchからの一貫実行、同入力/seedでのweightsとCSV bytes一致、8Aの29テスト維持、独立whole-branch reviewを実施する。結果と理解は別状態とし、8Bの学習済みを先取りしない。
