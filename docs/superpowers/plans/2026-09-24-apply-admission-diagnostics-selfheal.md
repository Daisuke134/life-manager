# Apply admission diagnostics and self-healing plan

## Scope

This change owns only the shared non-Paid admission boundary used by Apply loops.
It does not modify Paid implementations, Paid registry entries, Paid runtime state,
provider sessions, or production loop scheduling.

## Evidence

- A SQLite backup of the live admission store accepts new occurrence-scoped
  CrowdWorks and Lancers Apply wakes and returns `fifo_wait`.
- The same backup returns the expected retained `effect_unknown` fence for
  owner-scoped Coconala and Mercor Apply wakes.
- Therefore the persisted database is not presently reproducing the generic
  `resource_admission_unavailable` result. The remaining defect is that the
  runtime receipt discards whether enqueue or claim failed and which bounded
  exception class crossed that boundary.

## Implementation

1. Add focused failing tests for enqueue and claim failures.
2. Record only a bounded `phase` and `error_class` in the private admission
   receipt; never persist raw exception messages.
3. Run the focused tests and the existing admission/runtime regression suites.
4. Update the architecture spec with verified evidence and the next cursor,
   then commit and push the isolated branch.

## Acceptance

- An unavailable enqueue records `phase=enqueue` and a safe error class.
- An unavailable claim records `phase=claim` and a safe error class.
- The worker entrypoint never starts on either failure.
- Existing typed busy outcomes and effect fences remain unchanged.
