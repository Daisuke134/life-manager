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

The current focused test module is
`tests/test_ampersand_sdk_setup.py`. The original RED log was captured before
that rename as `tests/test_ampersand_integration.py`; its private log is kept
unchanged to preserve the original test-first evidence.

The source-boundary guard remains FAIL because its canonical host path
`/home/agent/Projects/life-manager-main` is unavailable. That check is not
relaxed. No SDK was installed in this worktree and no runtime/provider call was
made; cloud execution does not establish host installation or runtime state.

## Mandatory CI fixture follow-up

The adjacent loop contract failure was a test-oracle gap; it does not establish
the cause of the original macOS CI signal sequence or a production runtime
defect. The terminal-exit fixture now records successful signal origin, rejects
post-exit drain signals when group observation is unavailable, and accepts an
ignoring owned child stopping only when owned-leader SIGKILL escalation was
recorded. The controlled parent writes its TERM marker and remains alive until
that escalation. The same fixture retains the exact detached process identity,
different PGID, return-code, grace and cleanup assertions.

On Linux/Python 3.12.14 with pytest 8.3.5, the controlled regression first
failed against the old survival oracle: result 124 and TERM marker were
observed, while the owned child had stopped (Linux retained it as a zombie).
The RED log is
`/workspace/scratch/manager-ampersand-sdk-pin-20261023/ci-fixture-red-actual.log`.
After adding signal-origin capture, the regression passed and recorded owned
SIGTERM followed by owned SIGKILL, with no post-exit drain. The focused
terminal matrix, regression, timeout, cancellation, and normal-exit checks
passed 17 tests, with 224 deselected and no skips; final log:
`/workspace/scratch/manager-ampersand-sdk-pin-20261023/ci-fixture-focused-final.log`.
An earlier full focused run had one observed-group timeout case exceed the
existing 2-second bound by about 6 ms. The isolated case passed, then the full
focused set passed without changing the bound; the earlier log remains at
`/workspace/scratch/manager-ampersand-sdk-pin-20261023/ci-fixture-focused.log`.
After the final focused run, an audit of 94 recorded owned/detached fixture
identities found zero live matching processes; Linux zombie entries counted as
stopped.
Pytest used an existing scratch environment and a scratch copy of the tracked
import-only `gig_release.py` because the default environment lacks pytest and
the current sparse working view omits `skills/`; sparse settings were not
changed. Mandatory macOS CI still needs to validate the integrated head. This
test-only correction does not claim to reproduce or explain the actual CI
signal timing on Darwin.
