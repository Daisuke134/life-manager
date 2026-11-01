<!-- startup-context-version: 2026-10-20.1 -->
<!-- startup-context-digest: 7c2a72ae0b66f083c12cafde115cc5079f2e9722807b42e2288aef3f370b170f -->
# Local Life Manager

**AIエージェントが事業をゼロから作り、人の継続介入なしで運営する。オープンソースのmoney printerです。**

利用する事業のアカウントを接続すると、エージェント自身が機会を探し、事業をゼロから立ち上げ、商品・サービスを販売し、日々の運営で収益を生み出す設計です。

> **初期開発中：** 事業の自律運営と確認済みの利益は目標であり、まだ実証されていません。現在の機能は[エージェント一覧](docs/agents.md)をご確認ください。

[English](README.md) · [導入ガイド](docs/getting-started.md) · [エージェント一覧](docs/agents.md)

## 事業と収益モデル

| 事業 | 収益モデル |
|---|---|
| 契約仕事 | ココナラ・Lancers・CrowdWorks・Mercorの有料案件。 |
| モバイルアプリ | アプリ販売・サブスクリプション。 |
| アフィリエイト・CPA | 紹介料や、登録・購入などの成果報酬。 |
| 執筆 | 有料記事・ニュースレター・執筆受託。 |
| デジタル商品 | プロンプト・電子書籍・LINEスタンプの販売。 |
| AIサービス | AIスキル・サブスクリプション・APIの販売。 |
| 投資 | 設定した株式売買戦略。 |

## 基本の要件

- **ChatGPT Plus以上。** ChatGPTでログインします。別途OpenAI APIキーは不要です。
- **スリープしないMac、インターネット接続、12 GiB以上の空き容量。** 常時稼働にはMac miniが便利です。

利用する事業に応じて各サービスのアカウントを接続してください。サービスによって追加料金がかかります。

## インストール

ターミナルで実行します。

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Daisuke134/life-manager/main/scripts/bootstrap.sh)" life-manager local
```

公式CodexログインでChatGPTアカウントにログインします。その後、導入ガイドに沿って利用する事業のアカウントを設定します。Dockerは不要です。

[導入手順、Macのスリープ防止、エージェント状態の確認 →](docs/getting-started.md)

- [不具合を報告する](https://github.com/Daisuke134/life-manager/issues)
- **ライセンス：** [MIT](LICENSE)
