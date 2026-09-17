# Verified demonstration — Incident Update Fact Guard

## Offline selection record

The release-owned `sales_selector.py` was invoked offline through its pure
`select_signal` function with the only available local seller fixture: zero seller
rows and `company_orders=0`. It returned:

```json
{"advice":"No company or Agent-level sales signal is observable. Do not fabricate a winner; use marketplace research for the next differentiated candidate.","company_orders":0,"listings":0,"ok":true,"signal":"none","top_by_proxy":[]}
```

No marketplace or Capafy platform request was made. The source catalog was also
searched for `incident update`, `status update`, `incident communication`, and
`outage update`; no matching catalog candidate existed at the time of this check.

## Concrete input

Audience: customers

Update timestamp: 15:00 UTC

Incident notes:

- Payment retries are still failing for approximately 3% of customers.
- The root cause is unconfirmed.
- A mitigation is scheduled for 16:00 UTC.
- The next verified update is at 16:30 UTC.

## Actual output

### Customer update — 15:00 UTC

Payment retries are currently failing for approximately 3% of customers. The root
cause has not been confirmed.

A mitigation is scheduled for 16:00 UTC. The next verified update is at 16:30 UTC.

### Claim ledger

| statement | status | supplied basis |
|---|---|---|
| Payment retries are affected | confirmed | “Payment retries are still failing” |
| Approximately 3% may experience failed retries | confirmed | “approximately 3% of customers” |
| Root cause is unconfirmed | confirmed | “root cause is unconfirmed” |
| Mitigation is scheduled for 16:00 UTC | planned | “mitigation is scheduled for 16:00 UTC” |
| Next verified update is at 16:30 UTC | confirmed | “next verified update is at 16:30 UTC” |

### Verification queue

- Confirm whether the 16:00 UTC mitigation started or completed before describing it as performed.
- Confirm root cause, affected scope, and resolution status before adding any of those claims.

## Verification notes

The output preserves the supplied uncertainty: it does not name a root cause, call
the mitigation complete, say the incident is resolved, or claim a scope beyond the
supplied approximate percentage. The draft is text only; no external system was
inspected and no update was sent or posted. An accountable incident owner must review
the final wording before use.
