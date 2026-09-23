# Verified demonstration — AI Evaluation Failure Triage Brief

## Offline selection record

The release-owned `sales_selector.py` was used without its network-fetching entry
point. Its pure `select_signal` function received the current local source catalog:
28 rows, one for each catalog candidate, all with `sales: 0`, `recentSales: 0`,
`rating: 0`, and `reviewCount: 0`; `company_orders` was `0`. It returned:

```json
{"advice":"No company or Agent-level sales signal is observable. Do not fabricate a winner; use marketplace research for the next differentiated candidate.","company_orders":0,"listings":28,"ok":true,"signal":"none"}
```

No Capafy API, UI, or platform state was called or modified. The local source
catalog was checked for AI evaluation, evaluation failure, failure triage, and
test-case triage. No matching candidate exists. The closest adjacent candidate is
the experiment-readout deck, which summarizes experiments rather than triaging
individual expected-versus-observed evaluation cases.

## Concrete input

```text
Evaluation goal: Extract the total due from invoice text.

Case A
Input excerpt: "Subtotal $1,200.00; tax $40.00; total due $1,240.00."
Expected result: 1240.00
Observed result: 124.00
Prompt excerpt: "Return the total due and preserve decimal precision."
Run note: The reviewer marked this case as high priority.

Case B
Input excerpt: "Total due: EUR 89,50."
Expected result: 89.50 EUR
Observed result: EUR 89,50
Run note: A reviewer wrote, "normalization may be missing."

No model version, dataset version, sampling settings, scoring rubric, failure rate,
code revision, confirmed cause, assigned owner, remediation, or rerun result was
supplied.
```

## Actual output

### Triage summary

The supplied goal is to extract the total due from invoice text. Two evaluation
cases were supplied. Case A has a supplied high-priority reviewer marker and a
numeric mismatch. Case B has a supplied formatting mismatch and an unconfirmed
reviewer hypothesis. The record does not establish a model version, scoring setup,
failure rate, root cause, owner, remediation, or rerun outcome.

### Case table

| Case | Expected behavior | Observed behavior | Stated mismatch | Evidence status |
|---|---|---|---|---|
| A | Return `1240.00` for the supplied total due. | Returned `124.00`. | Returned value differs from the supplied expected value by a decimal place. | expected and observed |
| B | Return `89.50 EUR`. | Returned `EUR 89,50`. | Output retains the supplied comma-decimal formatting rather than the supplied expected normalized form. | expected and observed |

### Hypothesis register

| Item | Classification | Basis | What remains unknown |
|---|---|---|---|
| Decimal precision was not preserved in Case A. | observed mismatch | Supplied expected and observed results | Whether the prompt, extraction behavior, parsing, or scoring setup produced it. |
| Normalization may be missing in Case B. | hypothesis | Reviewer note | Whether normalization is required by the scoring rubric and why the output retained the input format. |
| The same issue affects other invoices. | unknown | No broader results supplied | Case coverage and failure rate. |

### Next-inspection queue

1. Record the model version, prompt version, configuration, and sampling settings used for both cases.
2. Confirm the scoring rubric for decimal precision and currency formatting before treating either output as a regression.
3. Preserve the full inputs and outputs needed to reproduce each supplied case.
4. Ask whether Case A’s high-priority marker has an assigned owner or review deadline.
5. Check whether the reviewer’s Case B normalization statement is a confirmed requirement or only a proposed explanation.

### Evidence ledger

| Material conclusion | Classification | Supplied basis |
|---|---|---|
| Case A expected `1240.00` and observed `124.00`. | observed | Case A record |
| Case A is high priority. | reported | Reviewer marker in Case A run note |
| Case B expected `89.50 EUR` and observed `EUR 89,50`. | observed | Case B record |
| Normalization may be missing in Case B. | hypothesis | Reviewer statement |
| A root cause or fix has been established. | unknown | None supplied |

## Verification notes

1. Every case name, number, currency string, expected result, observed result, prompt excerpt, and reviewer statement in the output appears in the concrete input.
2. The output calls the Case A and B differences mismatches, but does not identify a technical cause or claim a regression.
3. The Case B normalization statement remains a `hypothesis`; the output explicitly asks for the rubric before treating it as required.
4. Model version, configuration, scoring rubric, failure rate, owner, remediation, and rerun result remain unknown because the input did not supply them.
5. The result is text only. It does not execute an evaluation, inspect a repository or dashboard, modify a prompt, or make an external change.
