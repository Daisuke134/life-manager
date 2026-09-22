Primary Model: Claude Sonnet 4.6 · category: 生産性 · tags: customer success, renewal preparation, account evidence

## Offline selection notes

The release-owned `sales_selector.py` was evaluated offline through its pure
`select_signal` function against the current source catalog as the only available
local inventory: 26 local candidates, each with no sales, rating, or review signal.
It returned `signal: none` and advised against inventing a winner. The source and
release catalogs were then checked for `renewal risk`, `renewal brief`, `customer
renewal`, and `retention risk`; no matching candidate exists. This is distinct from
the customer-escalation decision deck: it prepares a recurring account-renewal
conversation from pasted evidence and does not create a leadership escalation deck
or make a decision.

## Renewal reason

Each renewal cycle receives new account notes, stakeholder statements, support
observations, open requests, and next-touchpoint details. A previous brief becomes
stale when any supplied account evidence, action status, owner, date, or customer
statement changes.

## Unit economics

This offline candidate uses a paid recurring subscription and bounded message caps.
Every plan is explicitly `No Free Trial`. Before any platform submission, the
publisher must obtain the official console sandbox fee and hosted-cost receipt and
confirm a positive contribution; neither value is asserted by this offline source
candidate.

| cycle | price | cap | trial |
|---|---:|---:|---|
| week | $9.99 | 20 | No Free Trial |
| month | $24.99 | 60 | No Free Trial |

## Verified demonstration

See `evidence/verified-demonstration.md` for a concrete pasted account record, the
resulting brief, and checks that preserve uncertainty.

## Title
Customer Renewal Evidence Brief

## shortDescription
Turn pasted account notes into a renewal-preparation brief that separates observations, customer statements, planned actions, and missing evidence without predicting renewal or inventing account health.

## welcomeMessage
👋 Paste the account name, renewal date if known, period covered, usage or support observations, customer statements, open requests, actions, owners, and next touchpoint. I’ll produce an evidence-bounded renewal-preparation brief for review.

Example: “Northstar renews on 30 September. Active seats fell from 25 to 17 in 14 days; the sponsor says budget approval is pending; a revised admin guide is requested.”

## detailedDescription
✨ **Prepare the next renewal conversation from the evidence you have**

Paste the account notes already in your hand: renewal timing, usage or support
observations, customer statements, stakeholder updates, open requests, actions,
owners, and the next touchpoint. The Agent turns only that material into a concise
renewal-preparation brief.

⚙️ **How it works**

1. Labels every material item as observed, customer-reported, planned, completed, unknown, or needing verification.
2. Separates a change in activity from an explanation that has not been confirmed.
3. Groups supplied signals into adoption, support, stakeholder, commercial, and next-step sections.
4. Builds an action register using only the owners and dates you provide.
5. Produces a conversation agenda and a verification queue for the responsible account owner.

📦 **You receive**

- A renewal-preparation summary with supplied timing and next touchpoint
- A signal and evidence table that makes unknowns visible
- An action register for supplied completed and planned work
- A customer-conversation agenda and verification queue

💡 **What makes it different**

- It is for recurring renewal preparation, not a generic account summary or an escalation decision deck.
- It keeps customer statements, observed account notes, and planned work separate.
- It does not browse, inspect records, contact customers, or update any system.
- It does not predict renewal, declare account health, invent a cause, or make commitments.

👤 **Built for**

Customer-success managers, account managers, renewal managers, and team leads who
need a careful preparation brief before a recurring account review.
