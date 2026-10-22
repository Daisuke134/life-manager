<!-- startup-context-version: 2026-10-20.1 -->
<!-- startup-context-digest: 45f79b184d1048bc643a0db1cf6f1d928f8a426077ac0e489fcaf5bcaa1435ea -->
# Life Manager

**Life Manager is an AI manager for body, mind, and money.** It chooses work, carries out ongoing workflows, checks external results, and reports receipts. Setting goals or budgets is not a required onboarding step; Telegram is optional. The hosted experience is still being built.

[Product](https://aniccaai.com/lm) · [Telegram](https://t.me/LifeManagerBotbot?start=lp) · [Cloud status](https://aniccaai.com/lm) · [Source](https://github.com/Daisuke134/life-manager)

## Run locally

On macOS with Git, jq, Node.js/npm, and Python 3:

~~~bash
git clone https://github.com/Daisuke134/life-manager.git
cd life-manager
LIFE_MANAGER_INSTALL_DAEMON=0 ./install.sh
./bin/lm-loop status all
./bin/lm-loop doctor
~~~

This prepares an isolated local runtime and checks its state without registering a daemon. The default installer can start only the Agent Economy loop, and only when its required credentials are ready; it does not start all agents. The installer does not install or sign in to Codex. Other loops require their provider setup, credentials, and sometimes KYC or browser login. A fully unattended first run on a fresh computer is not yet proven.

Use ./install.sh plan --loop <id> to see a loop's prerequisites before setup. Follow that loop's own guide before enabling external actions. Life Manager's pipeline inference uses Codex only.

## What it manages

Life Manager coordinates daily work, physical and mental wellbeing, and financial opportunities through specialized agents. It is open source and self-hostable; the paid monthly cloud target is an always-on manager and is still being built. Local and cloud use the same core and evidence contracts. Life Manager does not guarantee wealth or investment returns, and it does not report an attempted action as complete without a receipt.

## What the revenue evidence says

Operator-reported, sanitized Capafy seller snapshot (raw provider receipt is private): **$102.75 gross sales, $76.18 creator earnings, 32 non-trial purchased units, 74 free trials, and $0 paid out**. This is an account snapshot, not MRR or net profit; active subscriptions are not joined in the current readback. [See the dated evidence and limits](docs/evidence/capafy-seller-snapshot-20261021.md).

The open-source goal is 10,000 GitHub stars. Stars, installs, retained users, paid conversions, and settled revenue are tracked as separate outcomes.

## Evaluation

The [economic autonomy benchmark](docs/evals/lm-economic-autonomy.md) uses synthetic fixtures to test accounting and evidence rules. It does not prove that a live agent earned money. Production outcomes require provider receipts and settled revenue evidence.

## Links

- **Product:** <https://aniccaai.com/lm>
- **Repository (whole product):** <https://github.com/Daisuke134/life-manager>
- **Agent Economy:** [status and evidence](docs/agent-economy.md)
- **License:** [MIT](LICENSE)

Life Manager is the product. Anicca is the company name only when a form explicitly asks for it.
