# Life Manager Product Marketing Context

This document is the semantic source of truth for product and fundraising copy. Exact URLs, dates,
metrics, and evidence live in `startup-context.json` and must not be copied here as independent facts.

## Product Overview

Life Manager is one proactive general agent for a person's work, income opportunities, money, body, mind,
and everyday life. It chooses worthwhile priorities inside the authority the customer delegates, carries
out ongoing workflows without daily task prompts, checks external outcomes, and reports what actually
happened. A user-defined task or goal is not required to start.

The product has self-hosted and managed Cloud run modes, plus agent-client integrations. The paid Cloud
target is Google identity signup plus one informed setup authorization, then an always-on agent in a
tenant-isolated Maritime VM. It uses the verified signup email where a provider supports it, reports
results by email, and does not request Google Calendar as a prerequisite. Google identity does not grant
Gmail inbox access; verification mail requires a separately disclosed tenant mailbox or explicit mailbox
permission. This complete Cloud journey is not yet end-to-end verified.

### Cloud-first income workflow (product target)

The first intended Cloud income workflow is Capafy Publisher work: the agent evaluates and prepares useful
Skills, submits only through an eligible customer's single Publisher account, follows official review,
checks published and sales records, and reports verified outcomes and costs. It is an LLM-driven browser
workflow grounded in observed page state; deterministic code protects tenant isolation, secrets, budgets,
Stop, receipts, and replay safety. The agent does not create duplicate accounts or invent customer facts.

The current Capafy Publisher Agreement v1.2 requires legal acceptance, age and supported-region/sanctions
eligibility, accurate identity and contact details, one Publisher Account per person or entity, a public
support email, and a non-refundable US$0.99 application fee. It also requires accurate payout/tax details
and human review of every Skill. Whether payout details can be deferred is unconfirmed. One-time setup
authorization can remove daily Life Manager prompts; it cannot bypass an eligibility, identity, fee, or
other provider gate. Capafy review is controlled by the platform, and sales are uncertain. Do not promise
automatic approval or earnings.

Current Maritime source only observes redacted public text, searches public GET forms, navigates allowlisted
public pages, and follows safe links from the latest observation. It cannot register or log in to Capafy,
read verification mail, publish, read sales, or confirm payouts. The registration-to-earnings path is still
in development.

### Current public website offer

The public `aniccaai.com/lm` readback still leads with Google Calendar travel-time planning and the old
USD 29/month, seven-day card-required trial. The same-origin `/maritime` route is not live. This describes
the currently published page, not the Life Manager Cloud product definition or the Capafy-first Cloud
target. Do not route Cloud acquisition to a broken or misleading entry point.

## Target Audience

The first user is a busy founder or professional whose calendar, applications, health routines, money,
and follow-ups are fragmented across services. The broader audience is anyone who knows what would improve
their life but repeatedly loses momentum between intention and execution.

For Cloud, start with global professionals and creators who want to turn useful work into measurable income
but do not want to manage an agent's tasks every day. Capafy Publisher availability and eligibility vary by
country. A smartphone-first interface is the intended customer surface; the agent's workspace runs in the
Cloud tenant, not on the customer's phone.

## Core Pain / Job to Be Done

People do not need another dashboard that only describes their problems. They need a trusted system that
keeps their life moving: find the next worthwhile action, execute it within delegated boundaries, preserve
receipts, and report what actually happened. The job is to reduce the agency gap without hiding uncertainty.

For Cloud, the immediate job is to close the gap between choosing an income opportunity and repeatedly
shipping, distributing, verifying, and improving the work. A static dashboard or chat that waits for a new
task each day does not solve the follow-through problem.

## Physical / Mental / Financial Organs

- Daily Organ coordinates schedules, applications, priorities, and completed actions.
- Physical / Mental Organ supports routines, wellbeing, and continuity of care.
- Financial Organ builds a complete view of assets, liabilities, cash flow, spending, income opportunities,
  and risk-managed investing.

The organs share one user, memory, calendar, evidence ledger, and reporting experience. Telegram is an optional channel. A lead agent
coordinates specialist agents; deterministic code handles money arithmetic, state transitions, and receipts.

## Differentiation

Life Manager is positioned as a manager, not a chat assistant. It does not stop at suggestions: where the
user has delegated authority, it performs the action, verifies the result, records the evidence, and reports
it in language a non-technical person can understand. Where action is unsafe or unauthorized, it fails closed
and creates a concrete recovery task instead of inventing success.

For Cloud, the customer authorizes a bounded workspace once; the agent should then choose permitted next
actions, use its browser to observe and act, verify results, and report through email without daily task
prompts. Every external action needs an auditable receipt, and unknown outcomes stop blind retries. Provider
eligibility, human review, marketplace sales, and settlement remain external facts; never turn a proposed
action or a review-pending listing into an earnings claim.

## Alternatives / Competition

Alternatives include personal-finance dashboards, budgeting apps, calendar assistants, health trackers,
human executive assistants, robo-advisors, and isolated autonomous-agent demos. Each solves one surface.
Life Manager's approach is to connect those surfaces through one action ledger and one manager experience,
while reusing proven rails and open-source components instead of rebuilding every integration.

## Objections

- **Can it be trusted with sensitive data?** Use a tenant-isolated Cloud workspace, request the least
  privilege, separate read and trade permissions, keep an auditable ledger, and never expose credentials in
  reports or public artifacts. Google identity is not Gmail inbox permission.
- **Will it claim actions it did not complete?** No. A successful action requires a receipt or an independently
  verifiable result. Attempts without evidence are reported as incomplete.
- **Will it guarantee wealth or investment returns?** No. It can measure spending, surface opportunities,
  enforce risk limits, and execute an approved strategy, but it cannot guarantee returns.
- **Is this several unrelated products?** No. Connector, Job Hunter, CFO, and investment loops are specialist
  capabilities inside one Life Manager product and one ordered execution plan.

## Customer Language

Founder-reported language for Cloud Travel, not yet validated as customer research: “I keep looking at my
Google Calendar again and again,” “I search Google Maps every time I need to go somewhere,” and “I stress
about forgetting to include travel time.” External copy can use this lived experience, but must not present
it as a customer testimonial or quantified market research.

## Brand Voice

Direct, calm, accountable, and specific. Lead with the real-world outcome. Prefer “registered for this event
and added it to your calendar” over internal terms such as “runner succeeded.” Every action report should say
what happened, where, when, what evidence exists, and what comes next, with tappable links when available.

## Current Proof and Unknowns

The repository and Telegram entry point are public. Self-hosted and Cloud components exist in source, but
there is no verified Capafy signup-to-earnings Cloud journey. The public `/lm` page remains Calendar-first,
and same-origin `/maritime` is not live. No Cloud billing entitlement, completed publisher onboarding,
approved publication, user sale, payout, or customer MRR is verified. User count, revenue, retention,
production investing performance, a public Cloud demo, and founder video must be treated as unknown until
current evidence supports each claim. Old Anicca traction is not Life Manager traction.

## Fundraising Goals

Use accelerators and aligned investors to improve distribution, integrations, security, and the peer network
around Life Manager. Applications must describe the current product truthfully, adapt to each program's actual
thesis, and track submission, confirmation, reply, meeting, and outcome as one evidence-backed funnel.

The company target is USD 10,000 Cloud subscription MRR; the Capafy-first Cloud price and trial are
undecided. Capafy customer sales/proceeds are not Anicca MRR. Measure the full funnel from Cloud signup and
consent through isolated VM activation, verified provider work, official review/sales readback, delivered
reports, subscription invoices, renewals, refunds, costs, and cancellations. Keep customer sales, settled
payouts, cash received, Cloud subscription revenue, and operating costs separate. The target is not achieved
or forecast until measured.
