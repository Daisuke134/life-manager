# Slot: `life/travel`  (status: declared)

Reserved by **Foundation** for builder **wf-b:travel**. Spec: 26 B-travel / 27 B-travel.

> Reality (2026-06-16 audit): the *behaviour* ships today as the Python skill
> `~/.openclaw/skills/anicca-travel-fill/` (cron `anicca-travel-fill`, daily 05:00 JST),
> which has inserted real gcal travel blocks (state/travel_filled.json). `travel.js`
> here is the OSS port and is NOT yet wired — keep `status:"declared"` until it reaches
> parity (chained-pair origin + distance gate) AND passes the E2E in this patch.

This directory is the ONLY place that builder edits. The slot is pre-declared in
`skills/registry.json` and pre-wired everywhere (install.sh reads the registry;
the landing nav links the matching route). DO NOT edit `skills/registry.json`,
`install.sh`, or the landing nav — add your implementation files HERE.

## Contract
- Entrypoint the runtime expects: `travel.js`
- When real implementation + E2E verify land, flip this slot's `status` to `"live"`
  in `skills/registry.json` (one-line change, your slot only).

## Until then
Foundation ships only this marker so the dir is git-tracked and `install.sh`
can sync the slot without error. No behaviour yet.
