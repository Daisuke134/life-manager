# Life Manager Product Marketing Context

This document is the semantic source of truth for product and fundraising copy. Exact URLs, dates,
metrics, and evidence live in `startup-context.json` and must not be copied here as independent facts.

## Product Overview

Life Manager is a personal manager for a person's body, mind, and money. It is built to turn goals into
completed real-world actions, then explain the outcome in plain language with evidence in Telegram.
The local self-hosted runtime and the cloud product are two delivery modes for the same Life Manager core.

### Cloud-first Travel wedge (first commercial path)

The first cloud offer is a Web-first Google Calendar travel-time agent. A visitor opens the public `/lm`
page, connects Google Calendar, grants Google identity and Calendar permissions, and Life Manager scans
eligible events and adds Travel blocks automatically. Calendar is the daily product surface; the Web page
is for connecting and billing, with no dashboard or chat thread. Life Manager does not read Gmail. Events
with unresolved locations or routes stay unchanged instead of receiving guessed travel times. The offer
uses the existing seven-day card-required trial and USD 29/month price after a confirmed Travel block.
Google's identity check is still required; do not describe this flow as login-free or claim that the user
never has to authorize Calendar.

## Target Audience

The first user is a busy founder or professional whose calendar, applications, health routines, money,
and follow-ups are fragmented across services. The broader audience is anyone who knows what would improve
their life but repeatedly loses momentum between intention and execution.

For the Cloud Travel wedge, start with Japanese-speaking professionals who use Google Calendar for
in-person meetings, appointments, classes, and events, and repeatedly check both the event time and route
because they are unsure when to leave.

## Core Pain / Job to Be Done

People do not need another dashboard that only describes their problems. They need a trusted system that
keeps their life moving: find the next worthwhile action, execute it within delegated boundaries, preserve
receipts, and report what actually happened. The job is to reduce the agency gap without hiding uncertainty.

For Cloud Travel, the immediate job is narrower: stop repeatedly checking Calendar and Maps to work out
when to leave. A calendar reminder at the event start does not solve the missed-travel-time problem.

## Physical / Mental / Financial Organs

- Daily Organ coordinates schedules, applications, priorities, and completed actions.
- Physical / Mental Organ supports routines, wellbeing, and continuity of care.
- Financial Organ builds a complete view of assets, liabilities, cash flow, spending, income opportunities,
  and risk-managed investing.

The organs share one user, memory, calendar, evidence ledger, and Telegram experience. A lead agent
coordinates specialist agents; deterministic code handles money arithmetic, state transitions, and receipts.

## Differentiation

Life Manager is positioned as a manager, not a chat assistant. It does not stop at suggestions: where the
user has delegated authority, it performs the action, verifies the result, records the evidence, and reports
it in language a non-technical person can understand. Where action is unsafe or unauthorized, it fails closed
and creates a concrete recovery task instead of inventing success.

For Cloud Travel, the Web connection starts the work and Calendar shows the result. Eligible Travel blocks
are added automatically; uncertain events remain untouched. Do not promise that the product can guarantee
the user will never be late.

## Alternatives / Competition

Alternatives include personal-finance dashboards, budgeting apps, calendar assistants, health trackers,
human executive assistants, robo-advisors, and isolated autonomous-agent demos. Each solves one surface.
Life Manager's approach is to connect those surfaces through one action ledger and one manager experience,
while reusing proven rails and open-source components instead of rebuilding every integration.

## Objections

- **Can it be trusted with sensitive data?** Start locally, request the least privilege, separate read and
  trade permissions, keep an auditable ledger, and never expose credentials in reports or public artifacts.
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

The repository and Telegram entry point are public. Local and cloud components exist, and several specialist
loops have implementation evidence in the repository. User count, revenue, retention, complete personal-bank
coverage, production investing performance, a public demo, and the founder video must be treated as unknown
until the current evidence source verifies each claim. Old Anicca product traction is not Life Manager traction.

The public Web entry and a production retry page are verified. A dedicated test Google identity has not
completed the real OAuth callback or Calendar consent; synthetic tests are not a customer-success claim.
Use the Web funnel report and Stripe as the sources for current Cloud conversion and revenue. Do not infer
MRR, users, or retention from visits, trial offers, or the existence of a $29 price.

## Fundraising Goals

Use accelerators and aligned investors to improve distribution, integrations, security, and the peer network
around Life Manager. Applications must describe the current product truthfully, adapt to each program's actual
thesis, and track submission, confirmation, reply, meeting, and outcome as one evidence-backed funnel.

The Cloud Travel business target is USD 10,000 gross MRR. At the existing USD 29/month price, the plan
requires 345 active paid subscribers; this is arithmetic, not a forecast. Optimize from measured
landing → Calendar authorization → confirmed Travel block → card-backed trial → paid invoice → renewal,
refund, and cancellation cohorts.
