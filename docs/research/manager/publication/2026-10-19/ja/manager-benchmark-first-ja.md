# Andon Labsから学ぶベンチマークを起点にしたAI開発

良いベンチマークには、AIが成功を語るだけでは変わらない世界があります。資源、時間、制約、操作、結果を、AIの文章の外に置きます。

Andon LabsのVending-Benchは、その具体例です。エージェントは長期間の自販機経営で判断と状態管理を行い、結果を帳簿で問われます。ただし時系列には注意が必要です。AndonはYC Winter 2024。公式の説明ではVending-Benchの着手はlate 2024、公表は2025年です。このベンチマークがYC採択の原因だったとは言えません。学べるのは、評価の仕事からAnthropicとの実設置の提案、Project Vendへ進んだ経路です。

シミュレーションは、失敗を安く再現する場所です。現実の設置は、模型に入っていなかった対人関係、運用、道具、人間の支援費用を露わにします。両方が必要です。

Managerでは、事業の利益だけでは足りません。健康、時間、経済的な安心、アクセスを支える環境が目的です。AI自身の売上が増えても、人の生活が悪くなるケースを検出する必要があります。

評価は予測、介入選択、実行、現実の成果に分けます。行動モデルは反応を予測する。政策は同じ予算で構造変更を比較する。実行は外部状態と失敗復帰を確認する。成果は独立した測定と対照で調べる。

agent、environment、evaluatorも分離します。agentは道具で観測と操作をするが、採点式の変更や資源の創作、自分での成功認定はできません。数値環境が資源と状態遷移を持ち、評価器が固定条件で記録します。

Inspectのdataset/solver/scorer分離、METRの長期課題評価、Melting Potの未見社会環境、AI Economistの主体と制度plannerの分離は参考になります。すべてを一度に導入する必要はありません。

収益の仮説は、評価環境、モデル比較report、運営者へのshadow検証を買ってもらうことです。公開ランキングや大量の合成データだけでは支払意思の証拠になりません。検証には、動くコード、再現できる実行、公平な基準、役に立つ失敗分析が必要です。新しい基盤モデルを作らなくても始められます。成功したと言うだけでは通らない世界と評価を作ります。

出典: [Andon YC](https://www.ycombinator.com/companies/andon-labs)、[Why we built Pion](https://www.andonlabs.com/blog/why-we-built-pion)、[Vending-Bench](https://arxiv.org/abs/2502.15840)、[Project Vend](https://www.anthropic.com/research/project-vend-1)、[Inspect](https://inspect.aisi.org.uk/tasks.html)、[METR](https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/)、[Melting Pot](https://github.com/google-deepmind/meltingpot)、[AI Economist](https://github.com/salesforce/ai-economist)。
