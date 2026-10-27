# Anicca YouTube quota cadence

## Goal

Prevent repeat YouTube upload-quota failures by allowing one post per channel per JST day, with both channels posting after 16:30 JST.

## Scope

- Keep `@anicca-ai` on its existing 19:45 JST execution slot.
- Keep `@life-manager-m4p` on its existing 20:15 JST execution slot.
- Remove earlier due slots from both YouTube lanes while preserving their integrations, content packs, and publication flow.
- Leave Instagram untouched. The latest Postiz readback for the `@anicca.ios.jp` lane has only `PUBLISHED` rows and no retryable error to replay.

## Acceptance

- Focused tests assert one exact slot per YouTube lane and reject a run before that slot.
- Focused tests pass and the change is pushed in a dedicated PR.
- No manual post is resubmitted while the provider quota is exhausted.

## Current cursor

The source cadence now keeps one post per YouTube channel after 16:30 JST. The focused test passes 17/17. The change is ready for its PR; no live scheduler or provider state has been changed.
