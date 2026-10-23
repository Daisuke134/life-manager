<!-- startup-context-version: 2026-10-20.1 -->
<!-- startup-context-digest: 45f79b184d1048bc643a0db1cf6f1d928f8a426077ac0e489fcaf5bcaa1435ea -->
# Life Manager

**An open-source AI manager that keeps working on your Mac.**
Find work, create and sell digital products, and take care of recurring tasks through your own accounts.

[日本語](README.ja.md) · [Setup guide](docs/getting-started.md) · [Agent catalog](docs/agents.md)

> Early development. Available features and setup requirements vary by agent;
> the entire catalog is not yet a finished, plug-and-play product.

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

## What can you use it for?

- **Work:** freelance opportunities, proposals, and job applications.
- **Digital products:** prompts, articles, eBooks, stickers, and product marketing.
- **Opportunities:** events, accelerators, fellowships, and grants.
- **Money:** revenue, expenses, payouts, and configured investment workflows.
- **Follow-through:** scheduled tasks and reports of verified outcomes.

See [each agent's availability and prerequisites](docs/agents.md) before connecting it.

## Learn more

- [Get started](docs/getting-started.md)
- [Explore the agents](docs/agents.md)
- [Report an issue](https://github.com/Daisuke134/life-manager/issues)

Prefer hosted? [Explore the cloud service](https://aniccaai.com/lm).

- **License:** [MIT](LICENSE)
