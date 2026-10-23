# Ampersand SDK setup pin

## Goal

Make the existing Ampersand adapter reject missing or unsupported OpenAI SDK
versions before it constructs a client, and provide an optional exact-version
dependency declaration.

## Scope and boundary

`make_client` retains its public signature, lazy SDK import, API-key and timeout
validation, base URL, zero retries, and timeout pass-through. After validating
the caller inputs, it reads installed `openai` distribution metadata and
requires exactly version `3.24.0`. Missing and mismatched distributions produce
the same static `SessionFailure`; version metadata and raw exceptions are not
included in the message.

The SDK stays optional for offline imports and deterministic Manager paths.
`requirements-ampersand.txt` pins only the direct dependency, not its complete
transitive environment. This setup work does not install dependencies, add a
provider call, enable inference, change a workflow or schedule, add secrets,
or establish that any runtime has the SDK installed.

## Verification record

The clean-tree baseline passed 404 Manager tests. Before the production change,
the five focused tests produced two expected failures: an incompatible SDK
version and missing distribution metadata both reached client construction.
The focused RED/GREEN logs and final full-suite log are retained outside Git at
`/workspace/scratch/manager-ampersand-sdk-pin-20261023/`.

After implementation, all six focused setup tests passed and the full Manager
suite passed 410 tests with no skips. `python scripts/check_boundaries.py`
passed. `git diff --check` passed. This checkout has no standalone loop-contract
gate script; the full suite includes the existing provider, session, budget,
deadline, and owned-provider contract tests.

The source-boundary guard remains FAIL because its canonical host path
`/home/agent/Projects/life-manager-main` is unavailable. That check is not
relaxed. No SDK was installed in this worktree and no runtime/provider call was
made; cloud execution does not establish host installation or runtime state.
