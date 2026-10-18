# 調査の根拠と読解範囲

確認日2026-10-18。`fetch-manifest.json`と`code-manifest.json`は取得URL、HTTP結果、内容SHA256を記録する。原文全体と第三者コードはGit外の `/workspace/artifacts/manager-context-research-20261018/` に保存。第三者の全文を自社MITコンテンツとして再配布しない。

- MiroFish: GitHub APIでmain HEADを確認。README、graph_builder、oasis_profile_generator、simulation_runner、report_agent、config、pyproject、LICENSEを取得し、グラフ構築、人物設定生成、外部プロセス起動、報告ツール、接続条件と依存を読解。SHAは7657031ac01184afe2cb220f5ee3545573b5e843。過去メモと同じSHAを今回再確認した。英語READMEの推測名2種類は404だったため、実在するREADME.mdを使った。実行・有料API接続なし。
- Goodfire: 指定エッセイの概要、言語モデルの節、SwiGLUの符号の例、説明を試験する方法、限定条件を読解。公式研究一覧で2026-10-15と著者Nick Cammarataを確認。全図/1,000ニューロンの独立検査、性能主張の再現はしていない。研究仮説として紹介し、普遍的なsuperpositionの否定としない。
- Numerai: 公式トップ、Unity記事を再確認。統合予定と確認日の状態を区別。前日のAPIメタデータ確認と公開コード読解は既存Unity記事へリンクし、今回の新たな学習・取引実績にしない。
- Transformer: Attention Is All You Need本文、nanoGPTのCausalSelfAttention/MLP/Block/forward/cross-entropy/AdamWを読解。nanoGPTはnanogpt-pin.jsonのSHAへ固定。nanoGPTのMLPはGELUでありSwiGLUの実装例とはしていない。
- 2026年のLanguage Model Circuits Are Sparse in the Neuron BasisはarXiv概要・著者・掲載コメントを確認。Goodfireの将来の技術論文と同一としない。Toy Models of Superpositionは原論文の位置づけを確認。
- Simile公式はsimile.aiからwww.simile.comへリダイレクト。創業者とgrounding/検証の説明を再確認。Aaru公式研究と創業者紹介も再確認。自社公表の成績を今回再現したとはしない。
- AI Economist、Generative Agents、自己報告ベース個人シミュレーション、OASIS、AgentSocietyは原論文の概要と公開メタデータを読解。ConcordiaはGoogle DeepMindの原論文紹介を確認。これらすべての全文/最新の商用コードまで読んだとの主張はしない。
- 歴史はMIT/MIT Press/Brookingsの書誌・著者による紹介を利用。Banksは著者自身のエッセイ再掲、Asimovは出版社紹介、ForsterはSF Encyclopediaの書誌解説。全文の作品分析や直接の思想的影響関係の証明ではない。Gutenbergの34089はThe Celestial Omnibusであり、The Machine Stops原文の根拠には使っていない。

`transformer_math_demo.py`は標準ライブラリだけの説明用計算。解析勾配と有限差分の誤差<1e-8、更新で損失低下をassertし、出力をJSONへ保存。人工の三候補を使う算数モデルで、Transformer全体の学習・人口予測ではない。

Web検索は取得済みページで確認できる範囲を補完した。最新の全研究を網羅したとはしない。write-like-meのsearch/retrieveツールは今回catalogになく、本人の明示用語・既存日本語指針を使い、取得した文体見本があるとはしない。verification skill再取得はcloud skill availability変更により失敗したため既読とはしない。
