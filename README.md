<!-- startup-context-version: 2026-10-20.1 -->
<!-- startup-context-digest: 45f79b184d1048bc643a0db1cf6f1d928f8a426077ac0e489fcaf5bcaa1435ea -->
# Life Manager

**An open-source AI manager for running businesses on your Mac.**
Find clients, create products, publish content, and track revenue through your own accounts.

[日本語](README.ja.md) · [Setup guide](docs/getting-started.md) · [Agent catalog](docs/agents.md)

> Early development. Available features and setup requirements vary by agent;
> the entire catalog is not yet a finished, plug-and-play product.

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

It also helps with job applications, grants, events, and bookkeeping.
See [availability and setup for each business](docs/agents.md).

## What you need

- **ChatGPT Plus (or higher).** Sign in with ChatGPT; no separate OpenAI API key is required.
- **A Mac or Mac mini that stays awake**, with an internet connection.
- **Your own service accounts** for the work you want to enable.

Some agents also use paid services. Their requirements are listed in the [agent catalog](docs/agents.md).

## Install

Run this in Terminal:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Daisuke134/life-manager/main/scripts/bootstrap.sh)" life-manager local
```

Sign in with your ChatGPT account when prompted, then connect the services you want to use.
The installer prepares the dependencies. No Docker is required.

[Full setup, keeping your Mac awake, checking progress, and stopping agents →](docs/getting-started.md)

Using another agent? [See compatibility and setup](docs/getting-started.md#other-agents).

## Learn more

- [Get started](docs/getting-started.md)
- [Explore the agents](docs/agents.md)
- [Report an issue](https://github.com/Daisuke134/life-manager/issues)

Prefer hosted? [Explore the cloud service](https://aniccaai.com/lm).

- **License:** [MIT](LICENSE)
