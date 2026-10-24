<!-- startup-context-version: 2026-10-20.1 -->
<!-- startup-context-digest: 45f79b184d1048bc643a0db1cf6f1d928f8a426077ac0e489fcaf5bcaa1435ea -->
# Life Manager

**The open-source, no-human-in-the-loop money printer that builds and runs businesses on your Mac.**

After you connect the required accounts, Life Manager's agents build and run businesses themselves: finding opportunities, launching offers, serving customers, and generating revenue without a human in the loop.

> **Early development:** Full autonomy and verified profit are not yet proven across the businesses below. Check the [agent catalog](docs/agents.md) for current capabilities.

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
- **A Mac that stays awake**, with internet and at least 12 GiB of free disk space. A Mac mini works well for always-on use.

For each business you enable, connect your own service accounts. Some services may cost extra.

## Install

Run this in Terminal:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Daisuke134/life-manager/main/scripts/bootstrap.sh)" life-manager local
```

Follow the prompts to sign in to ChatGPT and connect the services you want to use. Docker is not required.

See the [setup guide](docs/getting-started.md) for full installation, keeping your Mac awake, and checking agent status.

- [Report an issue](https://github.com/Daisuke134/life-manager/issues)
- **License:** [MIT](LICENSE)
