<!-- startup-context-version: 2026-10-20.1 -->
<!-- startup-context-digest: 45f79b184d1048bc643a0db1cf6f1d928f8a426077ac0e489fcaf5bcaa1435ea -->
# Local Life Manager

**An open-source, no-human-in-the-loop money printer: AI agents build businesses from scratch and run them on your Mac.**

Connect the accounts your chosen businesses need. Life Manager's agents are designed to find opportunities, build businesses, sell products and services, and handle day-to-day operations toward revenue without ongoing human input.

> **Early development:** Autonomous operation and verified profit are goals, not proven results yet. See the [agent catalog](docs/agents.md) for current capabilities.

[日本語](README.ja.md) · [Setup guide](docs/getting-started.md) · [Agent catalog](docs/agents.md)

## Businesses

| Business | Revenue model |
|---|---|
| Contract work | Paid projects on Coconala, Lancers, CrowdWorks, and Mercor. |
| Mobile apps | App sales and subscriptions. |
| Affiliate & CPA | Referral commissions and campaigns paid per customer action. |
| Writing | Paid articles, newsletters, and commissioned writing. |
| Digital products | Prompts, eBooks, and LINE stickers. |
| AI services | Paid AI skills, subscriptions, and APIs. |
| Investing | Configured stock-trading strategies. |

## Core requirements

- **ChatGPT Plus or higher.** Sign in with ChatGPT; no separate OpenAI API key is required.
- **A Mac that stays awake**, internet access, and at least 12 GiB of free disk space. A Mac mini works well for always-on use.

Each business needs its service accounts; some services may cost extra.

## Install

Run this in Terminal:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Daisuke134/life-manager/main/scripts/bootstrap.sh)" life-manager local
```

Sign in with your ChatGPT account through the official Codex login flow. Then follow the setup guide to connect accounts for the businesses you choose. Docker is not required.

See the [setup guide](docs/getting-started.md) for installation, keeping your Mac awake, and checking agent status.

- [Report an issue](https://github.com/Daisuke134/life-manager/issues)
- **License:** [MIT](LICENSE)
