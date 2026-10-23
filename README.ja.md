<!-- startup-context-version: 2026-10-20.1 -->
<!-- startup-context-digest: 45f79b184d1048bc643a0db1cf6f1d928f8a426077ac0e489fcaf5bcaa1435ea -->
# Life Manager

**Macで継続的な仕事を進める、オープンソースのAIマネージャーです。**
本人のaccountを使い、案件探し、デジタル商品の制作・販売、日々の作業を進めます。

[English](README.md) · [導入ガイド](docs/getting-started.md) · [Agent catalog](docs/agents.md)

> 初期開発中です。利用できる機能と追加設定はagentごとに異なり、
> 全catalogを設定なしで使える完成品には至っていません。

## 必要なもの

- **ChatGPT Plus以上：** ChatGPTでloginして使います。別途OpenAIのAPI keyは不要です。
- **スリープしないMacまたはMac mini：** インターネット接続が必要です。
- **本人のservice account：** 利用したい業務に応じて接続します。

個別agentが使う有料serviceなどの前提は、[agent catalog](docs/agents.md)に記載します。

## インストール

Terminalで実行します。

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Daisuke134/life-manager/main/scripts/bootstrap.sh)" life-manager local
```

案内に従ってChatGPT accountでloginし、使いたいserviceを接続します。
必要な依存はinstallerが準備します。Dockerは不要です。

[導入・スリープ防止・進捗確認・停止の手順 →](docs/getting-started.md)

## 使い道

- **仕事：** freelance案件、提案、求人への応募。
- **デジタル商品：** プロンプト、記事、eBook、スタンプ、製品のmarketing。
- **機会：** イベント、accelerator、fellowship、grant。
- **お金：** 売上、費用、入金の照合、設定した投資workflow。
- **継続：** 定期実行と、確認できた成果の報告。

接続する前に[各agentの利用範囲と必要な設定](docs/agents.md)を確認できます。

## 詳しく見る

- [導入ガイド](docs/getting-started.md)
- [Agent一覧](docs/agents.md)
- [不具合を報告する](https://github.com/Daisuke134/life-manager/issues)

ホスト版は[Cloud service](https://aniccaai.com/lm)から確認できます。

- **ライセンス：** [MIT](LICENSE)
