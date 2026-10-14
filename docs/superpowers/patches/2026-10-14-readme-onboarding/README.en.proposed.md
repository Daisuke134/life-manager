<!-- startup-context-version: 2026-10-08.1 -->
<!-- startup-context-digest: 5b8e34cf01a7cf7589fc6049c080b3eb8458ec28b98103abc2ade395e8d0f90c -->
# Life Manager

> Review preview. This replaces README layout only; it does not implement missing startup routes.

[日本語](README.ja.proposed.md)

Life Manager runs agent workflows for your life and work, keeps durable state, and verifies real-world results. Local and hosted runs share this repository.

## Start

[Open Life Manager](https://aniccaai.com/lm) · [Use Telegram](https://t.me/LifeManagerBotbot?start=lp)

For self-hosting, the current bootstrap example is the Coconala beta on an Apple Silicon Mac:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Daisuke134/life-manager/main/scripts/bootstrap-coconala.sh)"
```

Complete the official account setup in the dedicated browser, then rerun the same command. Independent fresh-Mac acceptance is pending. A universal one-command launcher for every row below is still being built.

## Agents and current startup coverage

Commands below assume a repository checkout and the listed setup. “Production owner” does not establish fresh-device installation or revenue.

| Agent | Current entry | Scope |
|---|---|---|
| Gig — Coconala | `./install.sh coconala` | Public beta; official account setup; fresh-device E2E pending |
| Gig — Lancers | — | Production owners exist; public installer pending |
| Gig — CrowdWorks | — | Production owners exist; public installer pending |
| Gig — Mercor | — | Public installer pending; Paid currently requires human submission |
| PromptBase | — | Public installer pending |
| Writer | — | Public installer pending |
| Affiliate | — | Public installer pending |
| Investment | `LIFE_MANAGER_INVESTMENT_MODE=paper python3 skills/alpaca-investment/run.py` | Direct runner; provider credentials required |
| Agent Economy | `./install.sh` | Initializes one citizen; does not start all agents |
| Job Hunter | `./install.sh job-hunter` | Guided beta; profile/Gmail/browser setup |
| Fundraiser | `./install.sh fundraiser` | Existing-host activation; dependencies/browser required |
| Connector | `./install.sh connector` | Existing-host activation; portable setup incomplete |
| Self-Build / Product Improvement | — | Public installer pending |
| Mobile App Loops | `node apps/life-manager/scripts/mobile-product-bootstrap.js --opportunity-file opportunity.json` | Workspace/assets bootstrap; later lifecycle stages separate |
| eBook | — | Public installer pending |
| Capafy | — | Production owners exist; public installer pending |
| LINE Sticker | — | Public installer pending |
| CFO | `bash skills/cfo/run.sh` | Finite runner; connect selected financial sources |

Freelancer and Upwork adapters exist, but their production owners and public installers are not registered. Their current integration status belongs in the agent guide, not an implied working-product claim.

## Check setup without starting a loop

```bash
./install.sh plan --loop capafy
```

This produces a plan, not an installation. The default `./install.sh` initializes Agent Economy; `start-local.sh` launches its compute runtime.

## Data and accounts

Credentials, sessions, runtime state, and receipts stay outside Git. Connect your own provider accounts. Official identity and payout requirements remain provider-specific.

## Development

[Runtime guide](https://github.com/Daisuke134/life-manager/blob/main/docs/loops/README.md) · [Offline economic checks](https://github.com/Daisuke134/life-manager/blob/main/docs/evals/lm-economic-autonomy.md)

The offline cases verify contracts and accounting. They are not live performance or revenue results.

## North Star

```
Reduce suffering.
No killing (Pāṇātipātā veramaṇī).
```

MIT · https://github.com/Daisuke134/life-manager
