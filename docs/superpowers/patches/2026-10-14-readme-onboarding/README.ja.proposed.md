<!-- startup-context-version: 2026-10-08.1 -->
<!-- startup-context-digest: 5b8e34cf01a7cf7589fc6049c080b3eb8458ec28b98103abc2ade395e8d0f90c -->
# Life Manager

> レビュー用の短縮案。READMEの構成案であり、未完成の起動機能を実装したものではありません。

[English](README.en.proposed.md)

**Life Managerは、あなた以上にあなたの人生全体を管理するAIです。**

身体・心・お金を支える、先回りする人生のマネージャー。気にかけるべきことを見つけ、頼む前に行動し、最後までやり遂げます。日々の予定や習慣づくりから、仕事を見つけて納品し、収入を育てるところまで。

人生を管理する手間を減らし、時間・心の余裕・収入を増やす。そのケアを誰もが受けられるようにし、人間、そしてすべての生き物の苦しみを減らすことが使命です。

## 始める

[Life Managerを開く](https://aniccaai.com/lm) · [Telegramで使う](https://t.me/LifeManagerBotbot?start=lp)

Self-hostの現行bootstrap例はApple Silicon Mac向けCoconala betaです。

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Daisuke134/life-manager/main/scripts/bootstrap-coconala.sh)"
```

専用browserで公式account設定を済ませ、同じcommandを再実行します。独立した新しいMacでの全経路受入は未完です。下の全agentを扱う統一起動入口は整備中です。

## Agentと起動範囲

下のcommandはrepo checkoutと必要設定がある状態を前提にします。本番ownerの存在だけでは、新端末での導入や収益を証明しません。

| Agent | 現行入口 | 範囲 |
|---|---|---|
| Gig — Coconala | `./install.sh coconala` | 公開beta。公式account設定が必要、新端末の全経路検証は未完 |
| Gig — Lancers | — | 本番ownerあり。公開installerは未完成 |
| Gig — CrowdWorks | — | 本番ownerあり。公開installerは未完成 |
| Gig — Mercor | — | 公開installer未完成。Paidは現在human submission待ち |
| PromptBase | — | 公開installer未完成 |
| Writer | — | 公開installer未完成 |
| Affiliate | — | 公開installer未完成 |
| Investment | `LIFE_MANAGER_INVESTMENT_MODE=paper python3 skills/alpaca-investment/run.py` | 直接runner。provider資格情報が必要 |
| Agent Economy | `./install.sh` | 一citizenを初期化。全agentの起動ではない |
| Job Hunter | `./install.sh job-hunter` | guided beta。profile/Gmail/browser設定が必要 |
| Fundraiser | `./install.sh fundraiser` | 既存端末用activation。依存/browserが必要 |
| Connector | `./install.sh connector` | 既存端末用activation。portable設定は未完成 |
| Self-Build / Product Improvement | — | 公開installer未完成 |
| Mobile App Loops | `node apps/life-manager/scripts/mobile-product-bootstrap.js --opportunity-file opportunity.json` | workspace/assets準備。後続の公開工程は別 |
| eBook | — | 公開installer未完成 |
| Capafy | — | 本番ownerあり。公開installerは未完成 |
| LINE Sticker | — | 公開installer未完成 |
| CFO | `bash skills/cfo/run.sh` | 有限runner。選択した財務sourceの接続が必要 |

Freelancer/Upworkのadapterはありますが、本番ownerと公開installerは未登録です。対応状況はagent guideへ記録し、稼働製品として扱いません。

## 起動前に必要設定を確認する

```bash
./install.sh plan --loop capafy
```

これは計画の表示で、インストールではありません。既定の`./install.sh`はAgent Economyの初期化、`start-local.sh`はそのcompute runtime入口です。

## データとaccount

資格情報、session、runtime state、receiptはGit外に保存します。利用者自身のprovider accountを接続し、本人確認・payout要件は公式手順で処理します。

## 開発

[Runtime guide](https://github.com/Daisuke134/life-manager/blob/main/docs/loops/README.md) · [Offline economic checks](https://github.com/Daisuke134/life-manager/blob/main/docs/evals/lm-economic-autonomy.md)

offline caseは契約と会計の検証です。本番性能や収益の実績として扱いません。

## North Star

```
Reduce suffering.
No killing (Pāṇātipātā veramaṇī).
```

MIT · https://github.com/Daisuke134/life-manager
