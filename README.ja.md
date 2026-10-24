<!-- startup-context-version: 2026-10-20.1 -->
<!-- startup-context-digest: 45f79b184d1048bc643a0db1cf6f1d928f8a426077ac0e489fcaf5bcaa1435ea -->
# Life Manager

**Mac上で複数の事業を動かす、オープンソースのAIマネージャーです。**
自分のアカウントを使い、顧客探し、商品の制作、コンテンツ公開、収益管理を進めます。

[English](README.md) · [導入ガイド](docs/getting-started.md) · [エージェント一覧](docs/agents.md)

> 初期開発中です。利用できる機能と必要な設定はエージェントごとに異なります。
> 詳しくは[エージェント一覧](docs/agents.md)をご覧ください。

## 動かす事業

| 事業 | 収益化の方法 |
|---|---|
| 契約仕事 | ココナラ・Lancers・CrowdWorks・Mercorで案件を受注。 |
| モバイルアプリ | アプリ販売・サブスクリプション。 |
| アフィリエイト・CPA | 紹介料や、登録・購入などの成果に応じた報酬。 |
| 執筆 | 有料記事・ニュースレター・執筆受託。 |
| デジタル商品 | プロンプト・電子書籍・LINEスタンプの販売。 |
| AIサービス | AIスキル・サブスクリプション・APIの販売。 |
| 投資 | 設定した株式売買戦略の実行。 |

求人応募、助成金・イベント探し、経理も支援します。
[各事業の利用範囲と必要な設定](docs/agents.md)を確認できます。

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

## 詳しく見る

- [導入ガイド](docs/getting-started.md)
- [エージェント一覧](docs/agents.md)
- [不具合を報告する](https://github.com/Daisuke134/life-manager/issues)

クラウド版は[こちら](https://aniccaai.com/lm)から確認できます。

- **ライセンス：** [MIT](LICENSE)
