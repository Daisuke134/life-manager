<!-- startup-context-version: 2026-10-20.1 -->
<!-- startup-context-digest: 45f79b184d1048bc643a0db1cf6f1d928f8a426077ac0e489fcaf5bcaa1435ea -->
# Life Manager

**One proactive manager for work, money, everyday responsibilities, body, and mind.**

Life Manager is being built as one product with one shared core. It chooses priorities, carries recurring work forward, and verifies outcomes, including income-generating workflows. Local and Cloud are ways to run it; Grok Bot, Muse, and Dots are intended ways to access the same manager, not separate products.

> **Current state:** The open-source Local setup is documented here. The paid, phone-first Life Manager Cloud is being built to run continuously on an isolated Maritime VM for each customer. Google Calendar travel-time planning is one current hosted workflow, not the whole product. Grok Bot, Muse, and Dots integrations are targets; end-to-end support for them and the full Cloud service has not been verified. Autonomous profit is not proven. See the [agent catalog](docs/agents.md) for current capabilities.

[日本語](README.ja.md) · [Setup guide](docs/getting-started.md) · [Agent catalog](docs/agents.md)

## One Life Manager, multiple ways to run and access it

| Mode or interface | Purpose | Current status |
|---|---|---|
| Local | Run the open-source Life Manager in your own environment. | Setup is documented below. |
| Cloud | Use the paid manager from a phone while its isolated Maritime VM stays online. | Full tenant provisioning and end-to-end use are still in development. |
| Grok Bot, Muse, Dots | Reach the same manager through service-specific adapters. | Integration targets; no end-to-end Life Manager connection is verified yet. |

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

## Local setup requirements

- **ChatGPT Plus or higher.** Sign in with ChatGPT; no separate OpenAI API key is required.
- **A supported local environment** with internet and at least 12 GiB of free disk space.

For each business you enable, connect your own service accounts. Some services may cost extra.

## Install

Run this in Terminal:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Daisuke134/life-manager/main/scripts/bootstrap.sh)" life-manager local
```

Follow the prompts to sign in to ChatGPT and connect the services you want to use. Docker is not required.

See the [setup guide](docs/getting-started.md) for the supported local setup and checking agent status.

- [Report an issue](https://github.com/Daisuke134/life-manager/issues)
- **License:** [MIT](LICENSE)
