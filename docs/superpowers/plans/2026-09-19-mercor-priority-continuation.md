# Mercor priority continuation

## Goal

Keep a candidate-local truthful-answer blocker from ending a Mercor pass before
all priority query IDs have a durable inspected or card-only record.

## Scope

- Update `apps/job-search-loop/prompts/mercor-pass.md` only.
- Add prompt contract assertions in
  `apps/job-search-loop/tests/test_mercor_pass_contract.py`.
- Preserve the submission fence and human-gate boundaries.

## Verification

1. Red test for the explicit candidate-local continuation rule.
2. Prompt update requiring remaining priority candidates and card-only records.
3. Full Mercor contract tests.
4. Merge, release, targeted apply, and natural wake verification with no
   `priority_scan_incomplete` terminal.
