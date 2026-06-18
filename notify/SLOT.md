# Slot: `life/notify`  (status: declared)

Reserved by **Foundation** for builder **wf-b:notify**. Spec: 26 B-notify / 27 B-notify.

This directory is the ONLY place that builder edits. The slot is pre-declared in
`skills/registry.json` and pre-wired everywhere (install.sh reads the registry;
the landing nav links the matching route). DO NOT edit `skills/registry.json`,
`install.sh`, or the landing nav — add your implementation files HERE.

## Contract
- Entrypoint the runtime expects: `notify.js`
- When real implementation + E2E verify land, flip this slot's `status` to `"live"`
  in `skills/registry.json` (one-line change, your slot only).

## Until then
Foundation ships only this marker so the dir is git-tracked and `install.sh`
can sync the slot without error. No behaviour yet.
