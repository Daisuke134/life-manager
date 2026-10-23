<!-- startup-context-version: 2026-10-20.1 -->
<!-- startup-context-digest: 45f79b184d1048bc643a0db1cf6f1d928f8a426077ac0e489fcaf5bcaa1435ea -->
# Life Manager

**Macで継続的な仕事を進める、オープンソースのAIマネージャーです。**
自分のアカウントを使い、案件探し、デジタル商品の制作・販売、日々の作業を進めます。

[English](README.md) · [導入ガイド](docs/getting-started.md) · [エージェント一覧](docs/agents.md)

> 初期開発中です。利用できる機能と必要な設定はエージェントごとに異なります。
> 詳しくは[エージェント一覧](docs/agents.md)をご覧ください。

## 必要なもの

- **ChatGPT Plus以上：** ChatGPTにログインして使います。別途OpenAIのAPIキーは不要です。
- **スリープしないMacまたはMac mini：** インターネット接続が必要です。
- **自分のサービスアカウント：** 利用したい業務に応じて接続します。

各エージェントが使う有料サービスなどの条件は、[エージェント一覧](docs/agents.md)に記載します。

## インストール

ターミナルで実行します。

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Daisuke134/life-manager/main/scripts/bootstrap.sh)" life-manager local
```

案内に従ってChatGPTにログインし、使いたいサービスを接続します。
必要なソフトウェアは自動で準備します。Dockerは不要です。

[導入・スリープ防止・進捗確認・停止の手順 →](docs/getting-started.md)

ほかのエージェントから使う場合は、[互換性と手順（英語）](docs/getting-started.md#other-agents)をご覧ください。

## 使い道

- **仕事：** フリーランス案件、提案、求人への応募。
- **デジタル商品：** プロンプト、記事、電子書籍、スタンプ、製品の宣伝。
- **機会：** イベント、起業支援、奨学金・助成金への応募。
- **お金：** 売上・費用・入金の照合、設定した投資業務。
- **継続：** 定期実行と、確認できた成果の報告。

接続する前に[各エージェントの利用範囲と必要な設定](docs/agents.md)を確認できます。

## 詳しく見る

- [導入ガイド](docs/getting-started.md)
- [エージェント一覧](docs/agents.md)
- [不具合を報告する](https://github.com/Daisuke134/life-manager/issues)

クラウド版は[こちら](https://aniccaai.com/lm)から確認できます。

- **ライセンス：** [MIT](LICENSE)
