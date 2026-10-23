# Draft: GitHub Secure Open Source Fund

- Program: https://resources.github.com/github-secure-open-source-fund/ (fetched 2026-10-23; displays github.com/open-source/github-secure-open-source-fund)
- Deadline: not stated; "Applications are open on a rolling basis and will be considered for all Program Sessions." Selected applicants get a virtual interview.
- Eligibility (from the page): current maintainer of an open source project; team of up to 2 people; commitment from core leaders to take part in the required programming (3-week security education program; funding is tied to security outcomes).
- Form: Microsoft Forms, https://forms.office.com/r/YN3MWEKQ5m (fields not captured; whether sign-in is required is unconfirmed).
- Status: **draft only, not submitted.** Ledger key `github.com/open-source/github-secure-open-source-fund` was FREE on 2026-10-23.
- Fact sources: `README.md`, `docs/getting-started.md`, `docs/agents.md`, `AGENTS.md`.

## Project

Life Manager — https://github.com/Daisuke134/life-manager (MIT License)

## Maintainer

Solo maintainer (Japan). Name and contact are filled from the private applicant profile at submission time.

## What the project is

An open-source AI manager that keeps working on your Mac. Autonomous agent loops, driven by Codex through the user's own ChatGPT sign-in, operate the user's own accounts: freelance proposals on Coconala, Lancers and CrowdWorks, paid articles on note and Substack, agent listings on the Capafy marketplace, and release/marketing loops for the iOS apps Anicca and Honne. It installs with one command on a Mac or Mac mini.

## Why security matters here

Life Manager is an agent that acts with real credentials: marketplace logins, browser sessions, payout and publishing accounts. A mistake does not crash a test; it can leak a session or send something on the user's behalf. The project already keeps credentials, browser profiles and runtime state outside Git (`AGENTS.md`, "Repository and runtime boundaries"), has a `SECURITY.md` with a private reporting path, and runs `gitleaks`, `trufflehog` and a PII grep on every PR (`SECURITY.md`, "CI scans"). What is missing is protection for what the agents do at runtime, not just what lands in Git.

## What we would do in the program

1. **Runtime secret handling:** extend the existing CI scans to agent transcripts, reports and Telegram/chat output, with redaction tests, so a session token cannot leave the private state directory through a loop's own report.
2. **Supply chain:** pin and review the installer's dependencies (`scripts/bootstrap.sh`, `install.sh`), add dependency review and signed releases.
3. **Agent permission boundaries:** write a threat model for agent-driven browser sessions (including prompt injection from marketplace messages and calendar content, already listed as in scope in `SECURITY.md`) and make each loop's allowlist of external effects explicit and testable.

## Commitment

The maintainer commits to attend the 3-week program and to publish the results (policies, CI checks, threat model) in the repository so other agent projects can copy them.
