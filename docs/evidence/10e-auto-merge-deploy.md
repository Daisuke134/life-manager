# 10e guarded auto-merge and production deployment evidence

## Stop boundary

The row remains pending. Three fresh-adversary approaches all stop before merge. PR
[#1092](https://github.com/Daisuke134/life-manager/pull/1092) and error
[#1088](https://github.com/Daisuke134/life-manager/issues/1088) remain open. No deployment,
provider mutation, or issue closure occurs; production remains on successful deployment
`73afe498…`.

Method 3 independently confirms the exact head and complete diff hash, then blocks on three remaining
material boundaries:

- the reviewer runner itself inherits credentials and lacks filesystem/network isolation;
- open-PR uniqueness is limited to the first 100 results rather than all pages;
- the rollback target is a successful deployment but is not proven to be the currently active exact
  commit.

Resume requires a credential-free read-only reviewer sandbox, paginated all-PR discovery, and
active-deployment exact-commit discovery in a trusted promoter outside the candidate.

## Result

Real privacy-safe production error [#1088](https://github.com/Daisuke134/life-manager/issues/1088)
drives the existing D0 into exactly one pull request:
[#1092](https://github.com/Daisuke134/life-manager/pull/1092).

The fresh implementation agent adds a regression test for a hanging Composio calendar request and
the smallest production fix: a bounded abort signal on provider execution. Its implementation
commit is `67f38e33…` and is readable from the PR commit history.

The same PR adds only the missing post-PR promoter. It does not create another intake queue,
developer agent, issue picker, or deployment service.

## Closed promotion guard

Promotion requires all of the following at one exact PR head:

- one open privacy-safe `error` issue and one open PR that closes it;
- base branch `main`, exact local/remote head equality, and GitHub `MERGEABLE`;
- every changed path inside the Life Manager app or the exact 10e evidence/SSOT files;
- blocked actions zero: migration, outreach send, provider-account mutation, secret change, and
  wallet transfer, plus indirect privileged execution;
- fresh full `npm test`, every eval at 100%, and panel privacy;
- fresh artifact-only adversary `PASS` with zero blocking findings;
- clean worktree after review.

Only then may the promoter perform the PR merge. Railway remains source-connected to canonical
`main`; the promoter waits for a production deployment whose live `meta.commitHash` equals the
GitHub merge commit and requires `/health` to return the Life Manager service truth.

## Real refusal proof

The same PR temporarily contains `.github/10e-guard-refusal.txt` at commit `a94208d3`. The real
promoter returns exit `3`, status `refused`, and reason `path_allowlist`; no merge or deployment
occurs. The file is removed in the same PR before final promotion.

The first refusal also reveals a fail-safe false positive: the policy's own blocked-action regular
expressions are classified as actions. Corrective TDD adds a policy-source regression:
RED `5/6`, GREEN `6/6`. Only the four exact regex definition lines in the exact guard module are
excluded; the same tokens in any executable line or other file remain blocked.

## Fresh adversary corrective

The first real fresh-context adversary returns `FAIL` with four blocking findings, so the promoter
stops before merge:

1. rollback readback can rediscover the old deployment instead of proving a new rollback;
2. merge is not atomically pinned to the reviewed head;
3. adversary output is not explicitly bound to the final head;
4. action-name regexes alone do not prevent indirect privileged execution.

Corrective TDD adds provider-interaction tests and changes the guard:

- rollback accepts only a different deployment ID created after rollback begins, with the exact
  previous commit;
- GitHub merge uses `--match-head-commit` with the reviewed SHA;
- the review schema requires `reviewed_head`, and PASS requires an exact SHA match;
- routine D0 changes are restricted to non-privileged `lib/test` capability paths; migration,
  outreach, provider-account, secret, wallet, and privileged-process capabilities are blocked by
  path plus syntax. The promoter bootstrap files are allowed only for exact #1088 / PR #1092 and
  become non-editable to later routine D0 PRs.

Corrective runtime/guard tests are RED `6/10` → GREEN `10/10`. The failed review performs no merge
or deployment.

The second fresh adversary also returns `FAIL` before merge with two blockers:

- candidate tests execute before review with inherited credentials;
- the one-time bootstrap implementation is excluded from action scanning without an immutable
  review binding.

Final corrective TDD moves the fresh review before all candidate execution, binds it to both the
exact head and SHA-256 of the complete binary diff, then runs tests/evals with a mode-700 temporary
HOME and a five-key environment (`PATH`, `TMPDIR`, `HOME`, `CI`, `NODE_ENV`). Routine additions may
not introduce environment-secret access, filesystem access, direct network execution, or privileged
process execution. Bootstrap capabilities are explicit and accepted only for exact #1088 / PR #1092
when the fresh review matches the complete diff hash; later D0 PRs cannot change those paths.

Final focused contracts are RED `8/12` → GREEN `12/12`. Both failed review methods have merge and
deployment side effects of zero.

The method-3 preflight initially refuses because rejection-token fixtures inside the exact bootstrap
test file are classified as production capabilities. Corrective RED `8/9` → GREEN `9/9` excludes
only reviewed, credential-free bootstrap test lines from the production-capability count; bootstrap
runtime/guard source remains inspected and diff-hash bound.

## Rollback and postflight

- Before merge, the promoter records the current successful Railway deployment and verifies current
  production health.
- A failed exact-commit deployment or unhealthy exact deployment triggers one Railway
  `deploymentRollback` to that previously healthy deployment.
- A missing/unhealthy rollback target stops rather than flapping.
- Successful postflight closes #1088 and posts the exact merge SHA, Railway deployment ID,
  deployment commit, health result, adversary result, and guard counts to the public
  [PR #1092 conversation](https://github.com/Daisuke134/life-manager/pull/1092).

The postflight comment is the public provider receipt. It contains no credential, database URL,
local filesystem path, raw provider error, identity, or contact data.

## Verification

- Focused calendar regression plus promoter contracts: `18/18`.
- Guard-outside live refusal: exit `3`, no merge/deploy.
- Final full tests, every eval, panel privacy, changed-path secret/PII scans, and fresh adversary run
  are executed by the exact promoter before merge.
- Production recovery is accepted only when GitHub merge SHA, Railway deployment commit, issue
  closure, and `/health` all read back consistently.

## Reused practices

- GitHub Docs, [Automatically merging a pull request](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/automatically-merging-a-pull-request):
  auto-merge waits until required reviews and status checks pass.
- OWASP, [CI/CD Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html):
  protected branches and least privilege reduce the risk of untrusted code reaching production.
- Railway live GraphQL schema exposes deployment `meta`, `status`, `canRollback`, and the
  `deploymentRollback(id)` mutation used by the existing authenticated CLI.

The implementation copies those guard boundaries and reuses the existing D0, shared fresh-agent
runner, GitHub PR, Railway source deployment, and production health endpoint.
