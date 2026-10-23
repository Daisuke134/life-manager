# Getting started on a Mac

[README](../README.md) · [日本語README](../README.ja.md) · [Agent catalog](agents.md)

Run Life Manager on a Mac that stays awake, using your ChatGPT subscription and your own
service accounts. Docker is not required. This is early software; some agents need extra setup.

## What you need

- A Mac or Mac mini that stays awake, with internet access. The installer accepts Apple Silicon
  and Intel; Coconala's public beta targets macOS 14 or newer.
- ChatGPT Plus or higher. Sign in through the official `codex login` flow; no separate OpenAI
  API key is required for this subscription path.
- Your own accounts for the agents you select. Some services require email, SMS, KYC, a payout
  account, a resume, or an official login. Paid provider requirements appear in the [catalog](agents.md).
- Permission to install missing Homebrew dependencies, including administrator access when
  Homebrew requires it.

Codex usage limits depend on your ChatGPT plan; see the [official plan guide](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan).

Credentials, browser sessions, personal data, and receipts stay outside the Git checkout and
immutable releases. The installer does not copy the developer's accounts or route work through
another person's Mac Mini.

## Keep your Mac awake

In System Settings, prevent automatic computer sleep while the Mac is connected to power.
The display can still turn off. Keep a MacBook connected to power with its lid open for
continuous work.

For a temporary session, macOS also provides:

```bash
caffeinate -i
```

Leave that Terminal command running while you want to prevent idle sleep. Press `Control-C`
to end it; closing its Terminal session also ends that protection. It does not keep work
running after the Mac is shut down. `man caffeinate` documents the native command.

## Install

Run in Terminal as the macOS user who will own the jobs:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Daisuke134/life-manager/main/scripts/bootstrap.sh)" life-manager local
```

The bootstrap creates or updates `~/life-manager`, installs missing dependencies, and delegates
to the local installer. The installer checks your Codex session, opens official login if needed,
and verifies authentication before registering jobs. It prepares private host bindings, builds
an immutable release from public `main`, and uses the existing managed runtime for the catalog
and its shared support jobs. Follow the provider setup relevant to your accounts afterward.

Re-running preserves private state. Existing active jobs finish before their release is replaced;
`waiting` during release adoption means installation is incomplete. Inspect the named job and
its next action before retrying. An installed scheduler does not prove an application, sale,
delivery, payout, or other provider outcome.

`LIFE_MANAGER_CHECKOUT` selects another checkout destination. An existing destination must have
the correct Life Manager origin, a clean `main` branch, and no unpublished local commits.
The bootstrap refuses incompatible or modified directories instead of replacing them.
Without the `local` argument, it opens the existing local setup screen.

## From a clone

```bash
git clone https://github.com/Daisuke134/life-manager.git
cd life-manager
./install.sh local
```

The following commands have different scopes:

```bash
./install.sh local plan
./install.sh local prepare
./install.sh local apply --release /absolute/path/to/complete/release
```

- `plan` lists agents, jobs, prerequisites, and external owners without changing your home directory.
- `prepare` installs dependencies and creates private host bindings without registering jobs.
- `apply` reuses a complete immutable release; it does not build one from an arbitrary worktree.

To install one product, use its catalog ID:

```bash
./install.sh local install --agent gig-coconala
```

The IDs and prerequisites come from
[`product-loop-catalog.json`](../apps/life-manager/config/product-loop-catalog.json).
For the isolated Agent Economy setup without registering its daemon:

```bash
LIFE_MANAGER_INSTALL_DAEMON=0 ./install.sh
```

## Connect an individual agent

From the checkout, these guided setup paths remain available:

| Agent | Command | Setup details |
|---|---|---|
| Coconala | `./install.sh coconala` | [Official account setup, seller identity, email, and activation](../skills/earn/gig/README.md) |
| Lancers | `./install.sh lancers` | [Your work profile, Lancers login, and optional storefront](lancers.md) |
| Connector | `./install.sh connector` | [Calendar, Telegram, browser, and event-provider setup](../skills/connector/README.md) |
| Fundraiser | `./install.sh fundraiser` | Applicant profile, Telegram, and provider login when required |
| Job Hunter | `./install.sh job-hunter` | Finalized resume, preferences, Gmail OAuth, Telegram, and official site login |

`./install.sh list` shows the provider onboarding catalog. A zero-effect plan for an individual
workflow lists missing requirements without starting it:

```bash
./install.sh plan --loop connector
```

Coconala is a public beta; independent clean-Mac full acceptance remains open. Job Hunter is
pre-release, with its Workday production acceptance still open; the other ATS lanes are not
finished public products. Several agents have host jobs but no complete guided provider setup.
Account registration, identity checks, and provider consent are separate from installing the host.

## Check what is running

```bash
cd ~/life-manager
./bin/lm-loop status all
./bin/lm-loop doctor
./bin/lm-loop status life-manager-connector-native --json
```

Read the layers separately: registered job, loaded/running process, latest terminal event,
and official provider outcome. A zero exit code is not proof that an external action completed.
`setup_required` names missing setup. For a waiting job, inspect its JSON error and next action:
host capacity, missing personal setup, release adoption, and an outstanding official readback
need different remedies. An unverified external action must be read back before it is repeated.
Use the exact job ID instead of starting a second owner. Status and doctor are read-only.

The executable job inventory is [`config/loop-registry.json`](../config/loop-registry.json).
Agent names are product capabilities; one agent can contain several jobs.

## Stop or resume a job

Use the exact job ID shown by status. For example:

```bash
./bin/lm-loop stop life-manager-connector-native
./bin/lm-loop status life-manager-connector-native
./bin/lm-loop start life-manager-connector-native
```

These commands go through `launchctl-safe` and require the owning macOS user's valid GUI session.
If preflight fails, resolve the reported session condition; do not bypass it with raw `launchctl`.
Stopping preserves private data and receipts. Use the agent's own uninstall instructions to
remove its exact installed jobs; deleting the checkout is not an uninstall.

## Cloud and current limits

The [web app](https://aniccaai.com/lm) and [Telegram](https://t.me/LifeManagerBotbot?start=lp)
are hosted entry points. Cloud `/start` currently provisions Agent Economy. Other catalog
workflows need their tenant host adapter and provider setup; they are not automatically enabled.
The complete email-signup → autonomous-work → daily-email journey remains in development.

Apple Silicon/Intel dispatch and local fixture checks do not establish another person's
full Mac/provider acceptance. Follow [the agent catalog](agents.md) for what each capability
needs; do not infer income, successful delivery, or publication from installation.
Installation does not guarantee successful work or income.

## Other agents

**Local (ChatGPT / Codex)** · **Grok Bot** · **Dots** · **Muse**

Local Mac installation is the supported path. A hosted agent can read this repository and its
instructions, but the prompt below does not prove that its integrations or scheduling work.
Hosted platforms need their own account connections and support for any Mac-only steps.

| Where | 1 | 2 | 3 |
|---|---|---|---|
| **Local Mac (ChatGPT subscription)** | Run the install command above | Sign in with ChatGPT (Codex) | Connect the services you want |
| **Grok Bot** | Open a chat with your bot | Paste the prompt below | Approve account connections when asked |
| **Dots** | Open a chat with your agent | Paste the prompt below | Approve account connections when asked |
| **Muse** | Open a chat with your agent | Paste the prompt below | Approve account connections when asked |

Prompt for hosted agents:

```
Clone https://github.com/Daisuke134/life-manager, read AGENTS.md and
docs/getting-started.md, then set up the agents I pick and report results to me here.
```

> The local Mac install is the supported path. Hosted agents follow the same repo instructions,
> but scheduling and Mac-only steps can differ by platform.
