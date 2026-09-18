# Mercor detail-page budget

## Goal

Keep the model-led Mercor pass inside the deterministic twelve-detail-page
contract. Once twelve detail pages have been opened, remaining cards must be
recorded as card-only observations and must not be opened.

## Scope

- Update `apps/job-search-loop/prompts/mercor-pass.md` only.
- Add prompt contract assertions in
  `apps/job-search-loop/tests/test_mercor_pass_contract.py`.
- Preserve candidate ranking, human-gate, submission-fence, and official
  readback rules.

## Implementation and verification

1. Add failing assertions for the explicit thirteenth-page prohibition.
2. Add the prompt sentence tying the twelve-page budget to card-only records.
3. Run the full Mercor contract test (`45 passed, 2 subtests`).
4. Merge, cut immutable release, apply the Mercor application owner, and verify
   the next terminal receipt has no bounded-scan overflow.
