# Agent catalog

[README](../README.md) · [Mac setup guide](getting-started.md)

Life Manager has **18 user-facing capabilities and one system agent**. These are product
roles, not process counts. The executable jobs and schedules live in
[`config/loop-registry.json`](../config/loop-registry.json); product IDs, requirements, and
host availability live in
[`product-loop-catalog.json`](../apps/life-manager/config/product-loop-catalog.json).
Those manifests remain the machine-readable authority.

## Capabilities and setup boundaries

The Mac fleet installer supplies host bindings and scheduling. It does not supply someone
else's accounts, identity verification, publication profiles, or provider permissions.
A guided path means setup code exists; it does not mean independent fresh-device outcomes
are proven. The table describes the intended work and the current onboarding boundary.

| # | Agent | Work | Prerequisites and current setup |
|---:|---|---|---|
| 1 | Gig — Coconala | Find suitable jobs, apply, negotiate, support delivery, and reconcile provider results | Own Coconala account and official seller/SMS/eKYC/payout setup. `./install.sh coconala`; [public beta guide](../skills/earn/gig/README.md). Clean-Mac full acceptance remains open. |
| 2 | Gig — Lancers | Run the shared application, negotiation, paid-work, and reporting lifecycle | Own Lancers login and work profile. `./install.sh lancers`; [setup guide](lancers.md). Storefront and reporting need their own settings. Clean-Mac full acceptance remains open. |
| 3 | Gig — CrowdWorks | Find suitable projects, apply, and report verified outcomes | Own CrowdWorks login and work profile. Managed host jobs exist; complete public guided provider setup is pending. |
| 4 | Gig — Mercor | Apply for suitable contracts, handle replies, and reconcile outcomes | Own Mercor account and truthful work profile. Complete public guided provider setup is pending. |
| 5 | PromptBase | Create and publish prompt listings with examples; read sales back | Own seller account and publication profile. Complete public guided provider setup is pending. |
| 6 | Writer | Create and sell paid writing, respond to opportunities, and reconcile payments | Own publisher accounts and required browser/API credentials. Complete public guided provider setup is pending. |
| 7 | Affiliate | Find and publish attributable affiliate opportunities | Own affiliate-provider accounts, credentials, and publication channels. Complete public guided provider setup is pending. |
| 8 | Investment | Run risk-gated Alpaca paper, shadow, or live passes and reconcile orders | Own Alpaca credentials and an explicit mode. Finite paper pass: `LIFE_MANAGER_INVESTMENT_MODE=paper python3 skills/alpaca-investment/run.py`. Live trading has its own risk requirements. |
| 9 | Agent Economy | Track agent revenue and receipt-gated compute costs with isolated state | `./install.sh` prepares an isolated citizen. Optional provider credentials enable earning; installation does not fund it from the owner's wallet. [Guide](agent-economy.md). |
| 10 | Job Hunter | Discover qualified jobs, apply, and reconcile confirmations and replies | Resume, real work preferences, Gmail OAuth, Telegram, and official site logins. `./install.sh job-hunter`; pre-release, with Workday production acceptance still open. |
| 11 | Fundraiser | Discover eligible accelerators, fellowships, grants, and investor intakes | Applicant profile, Telegram, and provider login when required. `./install.sh fundraiser`. |
| 12 | Connector | Find events, register, verify results, and report Calendar/Telegram receipts | Calendar, Telegram, and provider login when required. `./install.sh connector`; [guide](../skills/connector/README.md). |
| 13 | Self-Build / Product Improvement | Turn verified feedback and product evidence into reviewed improvements | Repository access, a development agent, and review credentials. Complete public guided setup is pending. |
| 14 | Mobile App Loops | Create, release, improve, market, and measure mobile products through a shared lifecycle | Shared marketing, distribution, measurement, and receipts exist. Opportunity bootstrap can create starter source/assets; build/sign/release orchestration and full guided onboarding remain incomplete. |
| 15 | eBook | Distribute attributed English/Japanese campaigns and reconcile checkout and delivery | Own checkout/PDF-delivery route, social accounts, and distribution credentials. Starter assets exist; complete public guided provider setup is pending. |
| 16 | Capafy | Operate product creation, sales, outcome measurement, and audience growth | Own Capafy account/API credentials and publication profile. Complete public guided provider setup is pending. |
| 17 | LINE Sticker | Create original animated sticker sets, submit them, and read review/sales status | Own LINE Creators Market login and payout setup, fal/Gemini credentials, and Telegram. Complete public guided provider setup is pending. |
| 18 | CFO | Reconcile verified revenue, expenses, balances, payouts, and financial reports | Credentials for connected financial sources only. `bash skills/cfo/run.sh` runs one finite pass; source coverage remains partial. |
| 19 | Host Steward — system agent | Maintain disk capacity, reconcile releases/fences, and reclaim eligible regenerable files | Shared machine support, not another user-facing product. Existing owner-controlled maintenance jobs are part of the host installation. |

## Account and outcome boundaries

The four gig capabilities share an earning lifecycle. A person still completes official
identity, interview, consent, or physical-participation requirements when a marketplace requires
them. An account setup gate is not completed paid work.

Ten product entries still lack a complete guided provider installer. The fleet installer can
prepare their host jobs, while the provider workflow remains `setup_required`. Check the
current catalog and `./install.sh list` instead of treating registration as readiness.

Mobile App Loops do not require an existing app: the opportunity bootstrap creates a product
workspace from repository-owned starter assets. Apple/Xcode/App Store Connect requirements
are checked at the relevant stage. `ready_to_build` does not mean submitted to the App Store,
published, or earning revenue. See the [mobile product registry](../apps/life-manager/config/mobile-products.json).

eBook's publication, checkout, and PDF-delivery receipts are separate. Private avatar/voice IDs
and provider logins are not shipped with the starter assets. See the
[shared marketing implementation](../skills/earn/marketing-engine/README.md).

Local and cloud use the same business core with different host adapters. Only the supported
cloud routes are available today; Cloud `/start` does not activate the entire agent catalog.
The complete hosted onboarding experience and independent all-agent fresh-Mac acceptance
remain unfinished. Fresh Intel hardware is not verified end to end.

A process being healthy proves only its runtime result. Successful applications, delivery,
publication, revenue, and payouts require the appropriate official provider evidence.
