# Agent Worktree and Promotion Contract

This repository separates **development** from **production promotion**. A
coding agent owns a source worktree and a branch. Life Manager owns production
owners, immutable releases, browser profiles, admission state and provider
effects. The worktree is not a production sandbox with its own copy of those
external resources.

## Development plane

Each independent task uses one dedicated linked worktree, branch and lease.
The agent may change only its owned source files and private test fixtures. It
runs focused tests, contract tests and provider-free fixtures there. A local
process, a mock provider, an exit code, or a browser screenshot is development
evidence only.

The development plane must not:

- edit another worktree or branch;
- use another loop's browser profile, CDP port, credentials or mutable state;
- edit shared `runtime/`, admission SQLite, release control or the lifecycle
  registry to remove a local blocker;
- point a worktree entrypoint at a production profile to prove that its source
  works;
- merge unfinished provider code merely to make a production wake run.

When a failure is outside the owned source boundary, record the exact owner,
file/function, command, release SHA, occurrence ID, first failing phase and
next readback. Continue independent read-only diagnosis and source tests.

## Promotion plane

Promotion is a separate, ordered operation:

```text
focused test
  -> clean commit/push on task branch
  -> PR review and required checks
  -> merge to origin/main
  -> complete immutable release from that main SHA
  -> targeted loaded-idle apply for one owner
  -> loaded argv/SHA and natural terminal readback
  -> official provider/Calendar readback
  -> replay-zero natural wakes
```

The production owner reads only the immutable release. `~/loops/current` is a
selector, not a source checkout. A loaded or passing process does not prove an
external effect. An effect is verified only by the provider's authoritative
receipt/readback joined to the runtime occurrence and release SHA. Connector
also requires Calendar event exact count 1, durable evidence and two natural
replays with Submit 0 and duplicate 0.

Do not apply or restart sibling owners while promoting a task. If the current
release is incomplete, the promotion owner repairs the release boundary; the
provider owner does not patch the active release or bypass the release cutter.

## No-self-blocking rule

Classify every failure as one of `source`, `test`, `release`, `load`, `browser`,
`admission`, `provider`, `calendar` or `effect`. The agent owns the first two
and fixes them in the task worktree. It may reconcile only its own idle owner
through the existing `lm-loop` path. It never labels a generic no-work result
or a shared capacity result as a provider bug.

`blocked` is reserved for the same diagnosed boundary repeating across three
goal turns after the agent has run the available focused probe, recorded the
owner and exact evidence, and found no safe owned action. A provider no-work
result remains truthful no-work; it is not converted into a guessed Submit.

## Why two planes are necessary

The separation follows GitHub Flow's branch/PR model, Git worktree's linked
working trees, and the Twelve-Factor build/release/run separation. AI coding
agents use the same shape: an ephemeral or isolated workspace researches and
tests a branch, then a human/repository policy promotes the reviewed branch.
The isolation prevents one agent from overwriting another agent's source while
the promotion gates prevent an unfinished source tree from acting on production
state.

References:

- GitHub Flow: <https://docs.github.com/en/get-started/using-github/github-flow>
- GitHub rulesets: <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets>
- Git worktree: <https://git-scm.com/docs/git-worktree>
- Twelve-Factor build/release/run: <https://12factor.net/build-release-run>
- GitHub Copilot cloud agent: <https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent>
- OpenHands SDK workspaces and Agent Server: <https://github.com/OpenHands/software-agent-sdk>
- OpenHands automation ownership: <https://github.com/OpenHands/automation>
- Aider Git integration: <https://aider.chat/docs/git.html>
