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

1. Commit/push and pass PR checks.
2. After merge, wait for the main-derived release and targeted `hf-gig-paid-direct` natural run; confirm the context compiles and re-evaluate any later paid-work gate without bypassing it.
3. Update the canonical unified SSOT after its active writer releases that file; do not change the global TODO order for this local source fix.

TODO ordering remains owned by `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`.
