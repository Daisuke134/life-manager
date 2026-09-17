Primary Model: Claude Sonnet 4.6 · category: 生産性 · tags: incident update, status communication, operations

## Offline selection notes

The release-owned `sales_selector.py` was evaluated offline with no local seller
receipt or seller rows available. It returned `signal: none` and explicitly advised
against inventing a winner. The current repository catalog was then checked for
incident-update, status-update, incident-communication, and outage-update candidates;
none was present. This candidate is deliberately distinct from the existing customer
escalation decision deck: it produces one time-stamped operational update and a claim
ledger, not a leadership decision deck.

## Renewal reason

Every incident cycle brings a different timestamp, affected experience, evidence set,
planned action, and next verification point. A previous update becomes stale when any
of those supplied facts change.

## Unit economics

This is a paid recurring subscription with bounded message caps. Every plan is
explicitly No Free Trial.

| cycle | price | cap | trial |
|---|---:|---:|---|
| week | $9.99 | 20 | No Free Trial |
| month | $24.99 | 60 | No Free Trial |

## Verified demonstration

See `evidence/verified-demonstration.md` for a concrete pasted incident input, the
resulting update, claim ledger, and verification notes.

## Title
Incident Update Fact Guard

## shortDescription
Turn pasted incident notes into a concise, time-stamped status update that keeps observed impact, unknown cause, planned work, and the next verification point clearly separate.

## welcomeMessage
👋 Paste the audience, update time, observed impact, confirmed facts, unknowns, planned or completed actions, and next verified update time. I’ll produce one claim-bounded status update plus a claim ledger for review.

Example: “At 15:00 UTC, payment retries are failing for about 3% of customers. The cause is unconfirmed. Mitigation is scheduled for 16:00 UTC; next verified update is 16:30 UTC.”

## detailedDescription
✨ **Clear status wording when the facts are still moving**

Paste your incident notes: the audience, timestamp, affected experience, confirmed
scope, known facts, unconfirmed explanations, planned or completed actions, customer
guidance, and next verification time. The Agent turns only that material into one
compact update and a claim ledger.

⚙️ **How it works**

1. Labels each supplied statement as confirmed, reported, planned, unknown, or needing verification.
2. Keeps symptoms separate from an unconfirmed cause.
3. Keeps scheduled work separate from a completed mitigation.
4. Produces a time-stamped update in a consistent operational order.
5. Lists unsupported wording and missing facts for the responsible operator.

📦 **You receive**

- One audience-labeled, time-stamped status update
- A claim ledger for every material statement
- A verification queue for unknown scope, cause, outcome, owner, or timing

💡 **What makes it different**

- It is built for recurring operational communication, not a decision deck or a generic summary.
- It prevents a planned action from being phrased as a completed fix.
- It returns text for your team to review; it does not browse, inspect systems, send, or post anything.
- It does not diagnose a cause, declare resolution, or invent scope, timing, or customer guidance.

👤 **Built for**

Incident commanders, support leads, operations teams, and customer-communication
owners who need careful update drafts from the facts already in hand.
