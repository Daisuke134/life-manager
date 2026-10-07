# Gig paid context reference boundary

## Goal

Keep paid fulfillment inside the contract project while allowing its context compiler to ignore only the known virtual-environment interpreter symlinks under `delivery/runtime/`. Other external source symlinks must fail closed. The `paid_direct.py` consumer must also reject external `read_these_first` paths.

## Evidence

The 2026-10-07 Coconala Paid run for talkroom `18180857` stopped before any external effect with `compiled source reference escapes project`. Its compiled context contained four `.venv/bin/python*` symlinks under `delivery/runtime/` resolving to the system Python installation.

## Acceptance

- `_refs()` excludes only `delivery/runtime/*/.venv/bin/python*` interpreter symlinks whose resolved target is an executable Python runtime, before hashing them.
- Any other external source symlink fails compilation; it is not silently omitted.
- Ordinary project files remain in `source_refs`.
- The consumer rejects explicitly supplied external source and `read_these_first` references.
- This patch changes reference indexing only; it does not edit contract files, browser state, or provider state.

## Progress

- The production context had 11,234 references; exactly four escaped the project after symlink resolution, all `.venv/bin/python*` aliases under `delivery/runtime/`.
- The initial test failed at the external target read. Review then found that broadly skipping outside symlinks could omit customer inputs and that `read_these_first` lacked a consumer-side boundary check.
- The corrected code skips only executable Python symlink aliases under `delivery/runtime/*/.venv/bin`, fails compilation on other external source symlinks, and rejects external `read_these_first` paths. Internal file references and internal symlinks remain supported.
- Fresh read-only review passed after the correction with no remaining findings.
- Verification: 6 focused tests passed; the consumer boundary rejects external references; `lm-loop-contract` passes for 18 product loops / 186 registry jobs; `git diff --check` passes. Provider/browser mutation: 0.

## Remaining

1. Wait for the next natural `paid-work-decision` run after provider capacity recovers. Do not change the Life Manager business-loop model route here.
2. Keep the old Coconala Apply occurrence fenced until a durable run→pass link is found; existing exact-ID readbacks alone do not prove that link.
3. Resume Coconala Storefront only after that Apply fence is safely resolved. Lancers Storefront and CrowdWorks/Mercor Apply/Paid retain their current owner/readback gates.
4. Update the canonical unified SSOT after its active writer releases that file; do not change the global TODO order for this local source fix.

## Production readback

- PR #6932 merged as `599dcf62a167c853e252e64d68128f3d36b8da32`. Main-derived immutable release `6ce816a9d152a40aeaf8c89eae68fb5f60d6b5cd` was created and targeted to `hf-gig-paid-direct`.
- Natural occurrence `hf-gig-paid-direct:18dc48f2effab020-41557` loaded that release and passed the former context-compile failure. It then stopped in `paid-work-decision` because the configured escalation model provider reported capacity unavailable; `effect=0`, no provider message or delivery receipt.
- Current lane remains incomplete: Coconala Apply/Storefront and Lancers Storefront are effect-fenced; CrowdWorks/Mercor have official-readback gates. Freelancer remains retired and Upwork remains an external browser owner. The canonical TODO order is unchanged.

TODO ordering remains owned by `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`.
