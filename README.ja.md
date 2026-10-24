<!-- startup-context-version: 2026-10-20.1 -->
<!-- startup-context-digest: 45f79b184d1048bc643a0db1cf6f1d928f8a426077ac0e489fcaf5bcaa1435ea -->
# Life Manager

**Mac上で事業を自ら作り、運営する。人手なしで収益化を目指すオープンソースのmoney printerです。**

必要なアカウントを初回接続した後は、エージェント自身が事業機会を探し、事業を作って運営し、商品・サービスを立ち上げ、顧客対応を行い、人を介さず収益を生み出します。

> **初期開発中：** 下記の事業すべてで完全自律運転や利益はまだ実証されていません。現在の機能は[エージェント一覧](docs/agents.md)をご確認ください。

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

案内に従ってChatGPTにログインし、利用するサービスを接続します。Dockerは不要です。

[導入手順、Macのスリープ防止、エージェント状態の確認 →](docs/getting-started.md)

- [不具合を報告する](https://github.com/Daisuke134/life-manager/issues)
- **ライセンス：** [MIT](LICENSE)
