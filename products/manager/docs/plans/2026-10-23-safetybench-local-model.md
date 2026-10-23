# SafetyBench local model implementation and verification plan

The [design](2026-10-23-safetybench-local-model-design.md),
[prospective scope](../specs/2026-10-23-safetybench-local-model-execution.md) and
[scientific protocol](../../experiments/behavior-model/safetybench-local-qwen3-clp-protocol-v1.json)
define the existing V002 lane. Implementation science is adopted; actual runtime
acceptance is pending, inference NOT_RUN. This document grants no model call.
The [parent plan at its preparation revision](https://github.com/Daisuke134/life-manager/blob/02ebc1553ac8edf2e73f0e507eb5c4c396f8da68/products/manager/docs/plans/2026-10-23-behavior-transformation-model-plan.md)
remains the broader research context; no task/status registry changes are made.

1. Author exact literal prompt/token/logit fixtures and a fake native-library
   boundary. Observe missing-producer RED. Exercise real source loading,
   recorded scorer contracts, journal replay, filesystem failures and config
   validation with small authored data; never load real ML in unit tests.
2. Implement only the frozen thin producer and protocol, explicit infer/finalize
   CLI, attribution and source documentation. Preserve the old MCQ core, CLI,
   protocol, rights and all 11,435 assignments. Reuse the existing private atomic
   writer, native verifier, FD silencing and recorded scorer.
3. Verify the focused tests and whitespace checks. Independently review exact
   prompt/label behavior, no gold at the native boundary, native CPU/eval/BF16
   arguments, context overflow, interruption, private durability, source closure,
   terminal/reap binding and all-gold denominators. Passing authored tests alone
   do not authorize inference.
4. The root controller owns full-suite verification, official CI, source review,
   exact-source integration and later actual resource admission/config. Preserve
   the source-boundary FAIL2 and its standing cloud exception truthfully. Freeze
   code, packages, native source, eight model pins, wrapper/watchdog, actual
   evidence, paths and exact argv in private root 0400 config before one attempt.
5. Only after root acceptance, run one monitored source-order inference attempt
   under the fixed 10,800s / 6,442,450,944-byte policy. Reuse the already completed
   input-only audit; verify weights only inside this monitored attempt. No new
   installs/network, parallel ML, retries, resume or budget extension.
6. After the child and wrapper are terminal and reaped, root supplies the exact
   terminal receipt plus independent wrapper-reap receipt. Run deterministic
   no-model finalization once, preserving interrupted/failed/unrun rows and
   separate all-gold/valid denominators. Keep raw artifacts private; report
   aggregates, coverage, seven states, controls, category metrics, elapsed time,
   sampled RSS and limits without claiming full coverage or human benefit.

The CLI requires `--mode infer|finalize --execution-config-path ABS
--code-version FULL_SHA`; finalize additionally requires
`--terminal-receipt-path ABS`. Every other input/output/budget comes from config.
Infer is one attempt. Finalization is terminal reconciliation and one existing
scorer call with no ML imports, not a second model attempt or a resume route.
Any CLI failure prints only `SAFETYBENCH_LOCAL_MODEL_UNAVAILABLE` and exits 2.

The strict config uses kind `manager.safetybench-local-qwen3-clp-execution.v1`,
acceptance status
`ACCEPTED_ONE_OFFLINE_SAFETYBENCH_CLP_ATTEMPT_WITH_TERMINAL_FINALIZATION`,
`accepted_actions=["infer","finalize"]`, and deployment `can_execute=False`.
Its input/output names and exact source closure are defined by the producer's
`INPUT_KEYS`, `OUTPUT_KEYS` and `SOURCE_FILES`; `CONFIG_KEYS` rejects additional
mutable override fields. The interpreter retains the exact absolute
`sys.executable` spelling so a standard venv link preserves package context;
`python_executable_sha256` independently pins its resolved regular binary.
This narrow interpreter exception does not permit symlinks in config, evidence,
source, native implementation, inputs or outputs. Config pins science one way. Separate external review,
CI, scope, source-boundary disposition and actual resource evidence are local
operator assertions checked against real file hashes, not cryptographic proof
of authority.

The wrapper-reap receipt has schema `manager.safetybench-local-wrapper-reap.v1`,
terminal-receipt SHA256, wrapper-source SHA256, wrapper PID/argv/cwd/returncode,
`reaped=True`, `own_pid_absent=True`, and an empty remaining-process-group list.
Root writes it only after actually waiting/reaping the wrapper. The unchanged
watchdog receipt separately proves the child disposition. No model-controlled
completion flag substitutes for these terminal checks.

The broader goal remains active. P0/NOT_MEASURED, model HOLD and U004 draft with
zero participants/interventions remain; this lane does not establish behavior
change, clinical validity, welfare, pristine holdout generalization or AGI.
