<!-- startup-context-version: 2026-10-20.1 -->
<!-- startup-context-digest: 45f79b184d1048bc643a0db1cf6f1d928f8a426077ac0e489fcaf5bcaa1435ea -->
# Life Manager

**One proactive general agent for work, money, and everyday life.**

Life Manager chooses worthwhile work inside the authority you give it, acts through connected tools,
checks what actually happened, and reports results. The product goal is to keep working after one
informed setup, without daily task prompts. Life Manager is one product with different ways to run.

> **Development status:** The complete Cloud signup-to-verified-earnings journey is still in development.
> Capafy account signup, inbox verification, publishing, sales readback, payouts, Cloud billing, and the
> public Cloud workspace have not been verified end to end. Earnings are not guaranteed. See the
> [agent catalog](docs/agents.md) for current source capabilities.

[日本語](README.ja.md) · [Setup guide](docs/getting-started.md) · [Agent catalog](docs/agents.md)

## One product, several runtimes

| Runtime | What it means | Current status |
|---|---|---|
| **Life Manager Cloud** | Planned paid, phone-first service. Each customer's agent is designed to run in an isolated Maritime VM, use the verified signup email where supported, and report results by email. | The end-to-end earning service and public Cloud route are still in development. |
| **Self-hosted** | Free, open-source Life Manager using the same business core in an environment you operate. | Source and setup guides are available; provider setup and outcome checks vary by workflow. |
| **Agent clients** | ChatGPT/Codex, Grok Bot, Muse, and Dots are runtime targets for the same Life Manager, not separate products. | Compatibility and background execution must be verified for each client; reading this repository alone does not prove a working integration. |

The first Cloud income workflow is intended to use Capafy: prepare and submit useful Skills, meet the
Publisher's setup requirements, and verify the platform's review and sales records. Capafy requires
accurate publisher details, a public support email, and a non-refundable US$0.99 application fee; it
uses automated and human review before publication. A successful submission is not a sale, and sales are not
guaranteed. Life Manager must stop at any eligibility, identity, or other setup gate it cannot complete
with the customer's informed authorization.

Google sign-in provides a verified identity and email address, not access to the customer's Gmail inbox.
If a provider requires inbox verification, Life Manager needs a separately disclosed, tenant-isolated
mailbox or explicit mailbox authorization.

## Workflows

Life Manager is being built to coordinate work, income opportunities, money, schedules, physical and
mental wellbeing, and everyday follow-through through one action and evidence ledger.

| Workflow | Intended outcome |
|---|---|
| Contract work | Find suitable paid projects, apply, deliver, and reconcile provider results. |
| Mobile apps | Create, release, improve, market, and measure apps. |
| Affiliate and CPA | Find and publish attributable opportunities. |
| Writing | Create and sell paid writing and respond to opportunities. |
| Digital products | Create and distribute products such as prompts, eBooks, and stickers. |
| AI services | Publish useful AI Skills, subscriptions, and APIs. |
| Investing | Run explicitly configured, risk-gated strategies. |

Each workflow needs its own provider accounts, permissions, and sometimes paid services. A planned
workflow is not evidence that the provider has accepted work or that revenue was earned.

## Self-hosted setup

For the open-source runtime, run this in a terminal:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Daisuke134/life-manager/main/scripts/bootstrap.sh)" life-manager local
```

Sign in through the official Codex flow, then follow the [setup guide](docs/getting-started.md) to
connect accounts for the workflows you choose. See the [agent catalog](docs/agents.md) for prerequisites
and current limits.

- [Report an issue](https://github.com/Daisuke134/life-manager/issues)
- **License:** [MIT](LICENSE)
