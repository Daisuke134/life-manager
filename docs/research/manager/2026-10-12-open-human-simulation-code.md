# 人間・人口シミュレーションの公開実装：コード調査

2026年10月12日。Aaru・Simileの公式ページ、ウェブ検索、研究者の公開リポジトリを確認し、下記6件を取得した。主要ファイルの静的な読解であり、依存関係の導入、モデル推論、追加学習、性能比較は実施していない。

## 公式製品と研究コード

Aaru・Simileの現行製品本体を丸ごと公開した公式実装は、今回の調査では確認できなかった。StanfordHCI/genagentsはJoon Sung Parkらの「Generative Agent Simulations of 1,000 People」に対応する研究コード。Simileの研究的背景を学ぶ資料にはなるが、現行商用製品の再現版とは扱わない。

公開されているコード、公開モデル重み、公開データ、公開論文は、それぞれ異なる。コードがあっても、元の非公開データがすべて入手できるとは限らない。

## 取得して読んだ実装

|リポジトリ|固定コミット|読むファイルと処理|確認した利用条件|
|---|---|---|---|
|[StanfordHCI/genagents](https://github.com/StanfordHCI/genagents)|`96854071ef4c2d79c93144c973c7820722d52bab`|`genagents/genagents.py`の`GenerativeAgent`、`genagents/modules/interaction.py`の`categorical_resp`、`genagents/modules/memory_stream.py`の`retrieve`。人物の記録を検索し、既存の言語モデルへ質問とともに渡す|コードMIT。実インタビューに基づく千人超の完全な人物群はREADME上で非公開。公開の人口属性ベースの人物群と同一視しない|
|[akaashkolluri/socrates](https://github.com/akaashkolluri/socrates)|`8c9aef227ab1a5b315e797c811a122a12d8bb88a`|READMEはデータ、学習済み重み、学習方法への案内。リポジトリ内に独自の完全な学習処理があるわけではなく、LLaMA-Factoryを使うと説明|データの元資料と基盤モデルの条件を継承。全資産を一括した無制限の商用許諾とは扱わない|
|[ActivitySim/populationsim](https://github.com/ActivitySim/populationsim)|`21881f0094680afbe11e2839124dfca10e61a2d2`|`populationsim/steps/initial_seed_balancing.py`、`populationsim/balancing/single_balancer.py`、`populationsim/steps/integerize_final_seed_weights.py`。標本世帯の重みを人口統計へ合わせ、整数の世帯数へ変換する|BSD-3-Clause|
|[UDST/synthpop](https://github.com/UDST/synthpop)|`6fb13991c9d3ede2d8cf80512bd1102e37b98971`|`synthpop/zone_synthesizer.py`、`synthpop/synthesizer.py`。世帯・個人の集計と標本から合成人口を作る|BSD系の3条項。旧依存環境の互換性は未検証|
|[AgentTorch/AgentTorch](https://github.com/AgentTorch/AgentTorch)|`86bb57e8a19ad6a52396875777f3c7b74264ada1`|`agent_torch/core/runner.py`の`Runner.step`。観測、行動、状態遷移を時間ごとに実行して履歴を保存する。モデル側が規則や学習対象を供給する|AGPL-3.0。モデル例の学習スクリプトには作者固有の絶対パスが残るため、すべての例がそのまま動くとは確認していない|
|[microsoft/TinyTroupe](https://github.com/microsoft/TinyTroupe)|`a6244b358a1fe1c71bf751f7ba0f8dfa368ec5a4`|`tinytroupe/agent/tiny_person.py`の`TinyPerson.act`と`listen`。刺激、記憶、言語モデルによる行動生成を組み合わせる|MIT。実験的な人物シミュレーションであり、人口全体の予測精度は別に検証する|

## genagentsの処理を追う

`GenerativeAgent.categorical_resp`から、`interaction.py`の`categorical_resp`へ進む。質問文を検索の手掛かりにし、`_main_agent_desc`で自己説明と関連記録を組み立てる。`MemoryStream.retrieve`は埋め込みによる関連性等を使って記録を選ぶ。回答用のテンプレートと選択肢を作り、`simulation_engine/gpt_structure.py`の`chat_safe_generate`、`gpt_request`でモデルを呼び、回答を解析する。

この処理は人物ごとの文脈を変える方式。人物を読み込むたびに言語モデルの重みを追加学習する処理ではない。

## Socratesのモデルを確認する

[socratesft/socrates-qwen2.5-14b-sft](https://huggingface.co/socratesft/socrates-qwen2.5-14b-sft)の`config.json`と`README.md`を取得。基盤は`Qwen/Qwen2.5-14B-Instruct`、構成名は`Qwen2ForCausalLM`、追加学習はSFT、資料はSocSci210。DPO版とLlama 3の8B版への案内もある。モデル重みそのものは今回はダウンロードしていない。

SFTは、人間の回答を学習例としてモデルを追加学習する方法。genagentsのように人物の記録を入力へ足す方法と、モデルの重みを変更する方法は区別する。

[LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory)の`src/llamafactory/train/sft/workflow.py`と`src/llamafactory/train/dpo/workflow.py`も取得して読んだ。モデルとデータを読み、学習処理を構成し、`trainer.train`へ渡す。取得した現行ファイルの読解であり、Socratesの元実験と同一バージョン・同一設定で再現したことにはならない。

## 学ぶ順番

最初は人口の重みの意味をPopulationSimで読む。次にgenagentsで、記録検索と回答生成の処理を読む。その後にSocratesで、追加学習と未使用の研究への汎化評価を読む。最後にAgentTorchで、複数の主体の行動と環境の状態が時間に沿って変わる処理を読む。

これらの実装から、Aaruの非公開ネットワーク構造やSimileの現在の学習設定を推定して断定しない。人口生成、回答生成、行動モデルの学習、社会の時間変化を、それぞれの公開実装で具体的に学ぶ。
