# Prepared shadow comparison and durable result design

Scope: implement only the existing research specification §1.3.2 item2: [fixed research specification](https://github.com/Daisuke134/life-manager/blob/a6c5354a0/products/manager/docs/MANAGER_PRODUCT_SPEC.md). The user authorized deciding routine details and completing the agent first; this does not authorize live model requests, new spending, or host activation.

Today the shadow wrapper plans again and returns an ephemeral comparison. An existing provider intent prevents another create but cannot restore the comparison. The selected owned maintenance task works with current rules; model usefulness remains unproved. This change makes the optional P0 evaluation and its recovery inspectable without enabling it.

Alternatives considered: leave the ephemeral result unchanged, losing the comparison after restart; reuse the same provider journal/checkpoint and add one optional results table; introduce another execution or memory framework. Root selects reuse of the existing database because it preserves the one-owner and ACK contracts with the smallest new boundary.

The existing wrapper remains. A new function consumes the exact prepared context/assessment/scope rather than invoking planning again. One canonical request-hash helper preserves the existing journal hash protocol. A fixed public projection omits free model reasons, provider identifiers, raw output and arbitrary fields.

Store only completed P0 comparisons, including invalid model output as its actual invalid status. Commit and close locally, checkpoint and receive ACK, then return. On fresh restore the identical input returns the original comparison/run/time with no new client, reservation or request. A changed prompt under the same operation identity returns UNKNOWN/INPUT_BINDING_MISMATCH. An intent without result remains UNKNOWN and never authorizes a new create.

The optional result table is compatible with old snapshots. If present it must bind to the existing provider tables, request identity, body hash and budget state. Malformed state fails and fences the checkpoint; it is not repaired into an empty store. Hash-only records validate local references and current-input binding, not independent remote completion or causal benefit. Cached advice never grants execution authority.

No host/CLI/workflow integration, schedule change, SDK installation, provider call, paid action, new owner, publication, external contact or roadmap status update. Human outcomes remain NOT_MEASURED and the existing 80/30/3 task registry is unchanged.

Acceptance: named RED/GREEN cases in the implementation plan for same-tuple processing, fixed projection, result ACK ordering, restore/create0, input mismatch, intent-only UNKNOWN, ACK loss, corrupted state, legacy compatibility and expired scope. Fresh task reviews and whole-branch review precede normal CI/main integration.
