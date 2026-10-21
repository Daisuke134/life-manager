<!-- startup-context-version: 2026-10-20.1 -->
<!-- startup-context-digest: 45f79b184d1048bc643a0db1cf6f1d928f8a426077ac0e489fcaf5bcaa1435ea -->
# Life Manager

**Life Managerは、身体・心・お金を管理するAIマネージャーです。** 仕事を選び、継続作業を実行し、外部の結果を確認して、receiptを報告します。開始時の目標・予算入力を必須にしません。Telegramは任意です。Cloud版は開発中です。

[製品](https://aniccaai.com/lm) · [Telegram](https://t.me/LifeManagerBotbot?start=lp) · [Cloud版の現在地](https://aniccaai.com/lm) · [source](https://github.com/Daisuke134/life-manager)

## ローカルで動かす

Git、jq、Node.js/npm、Python 3を用意したmacOSで実行します。

~~~bash
git clone https://github.com/Daisuke134/life-manager.git
cd life-manager
LIFE_MANAGER_INSTALL_DAEMON=0 ./install.sh
./bin/lm-loop status all
./bin/lm-loop doctor
~~~

これは独立したruntimeを準備し、daemonを登録せずに状態を確認します。通常installerが開始できるのは、必要な認証が揃った場合のAgent Economy loopだけです。全agentを一括起動しません。installerはCodexをinstall・loginしません。その他のloopにはprovider account、credential、場合によりKYCやbrowser loginが必要です。新しいcomputerで人の介入なしに初回起動し、収益まで到達する経路は未達です。

./install.sh plan --loop LOOP_ID でloopの前提条件を確認してから、個別のguideに沿って設定します。Life Managerのpipeline inferenceはCodexのみを使います。

## 何をするか

Dailyの仕事、身体と心のwellbeing、Financialの収入機会をspecialist agentが支援します。open sourceでself-hostでき、paid cloud版は常時稼働するmanagerを提供する計画です。LocalとCloudは同じcoreと証拠contractを使います。資産増加や投資収益は保証せず、receiptのない試行を完了として報告しません。

## 売上の証拠

Capafy seller accountのsnapshotは、**gross $102.75、creator earnings $76.18、非trial購入32件、free trial 74件、支払済み$0**です。これはaccount snapshotで、MRRやnet profitではありません。現在のreadbackでは有効購読をjoinできていません。[証拠と制約](docs/evidence/capafy-seller-snapshot-20261021.md)

open sourceの目標はGitHub 10,000 starsです。stars、install、継続利用、有料転換、確定売上は別の指標として追います。

## 評価

[Economic Autonomy benchmark](docs/evals/lm-economic-autonomy.md)はsynthetic fixtureで会計と証拠の規則を検査します。実際のagent収益を証明するものではありません。productionの成果はprovider receiptと決済済み売上で確認します。

## Links

- **製品：** <https://aniccaai.com/lm>
- **リポジトリ（プロダクト全体）：** <https://github.com/Daisuke134/life-manager>
- **Agent Economy：** [statusと証拠](docs/agent-economy.ja.md)
- **License：** [MIT](LICENSE)

Life Managerが製品名です。Aniccaはformが会社名を明示的に求めた時だけ使います。
