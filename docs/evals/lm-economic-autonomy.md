# Reproduce the LM-EAB economic-autonomy contract checks

LM-EAB currently provides a deterministic, offline evaluator for economic and
autonomy records. The checked-in cases are synthetic fixtures. This command
checks the evaluator contract; it does not execute an agent or earn money.

## Run from the repository root

Use Node.js. No API keys, provider accounts, browser, or package installation
are required for these checks.

```sh
node --test apps/life-manager/eval/economic-autonomy/*.test.js
node apps/life-manager/eval/economic-autonomy/run.js --cases apps/life-manager/eval/economic-autonomy/cases.jsonl
```

The CLI emits JSONL: one `economic_autonomy_run` record followed by one
`economic_autonomy_score` per case. It verifies fixture hashes, the corpus
contract, and every expected result. A mismatch exits nonzero.

## Read the result

- `case_set_sha256` identifies the exact corpus bytes; each case also pins its
  fixture bytes with `input_sha256`. Record the repository commit when sharing a run.
- `eligible` means the supplied records pass the evaluator's evidence and
  autonomy gates. It does not mean the agent made money.
- `reason_codes` explains failed gates. Read these before interpreting money
  fields; an ineligible score is not a verified profit claim.
- Money fields use integer minor units in the record's currency. Never add
  different currencies or call one-time receipts MRR.
- `self_funded` is a separate outcome. A valid zero-revenue case can be eligible
  while remaining unprofitable and not self-funded.

## What this can demonstrate

The fixtures exercise evidence validation, accounting boundaries and autonomy
gates. Their model, release/toolchain identifiers, timestamps and receipt
references are test data, not observations of a live model or provider. Fixed
run timestamps support deterministic output; they do not measure runtime.

Both `tuning` and `held_out` fixtures are public. The latter is a corpus label,
not a secret test set or proof of protection against training contamination.
This corpus does not yet establish representative agent performance, live
profitability, human-free onboarding or comparative model rankings.

For case authoring and scoring semantics, read the adjacent
[`records.js`](../../apps/life-manager/eval/economic-autonomy/records.js),
[`score.js`](../../apps/life-manager/eval/economic-autonomy/score.js) and
[`cases.jsonl`](../../apps/life-manager/eval/economic-autonomy/cases.jsonl).
The canonical implementation status remains in the
[Life Manager SSOT](../superpowers/specs/2026-09-25-life-manager-unified-ssot.md).
