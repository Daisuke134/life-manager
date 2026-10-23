# Draft: OpenAI Codex open source fund

- Program: https://openai.com/form/codex-open-source-fund/ (fetched 2026-10-23)
- Deadline: not stated; "Applications will be reviewed on an ongoing basis". Grants up to $25,000 in API credits.
- Form language: English. Form fields render in JavaScript and were not captured, so the answers below cover the likely questions (project, repo, use of Codex, use of credits).
- Status: **draft only, not submitted.** Ledger key `openai.com` was FREE on 2026-10-23; add a `claimed` row before submitting.
- Fact sources: `README.md`, `docs/getting-started.md`, `docs/agents.md`, `AGENTS.md`.

## Project name

Life Manager

## Repository

https://github.com/Daisuke134/life-manager (MIT License)

## One-line description

An open-source AI manager that keeps working on your Mac: autonomous agent loops that find work, create and sell digital products, and handle recurring tasks through the user's own accounts.

## What the project does

Life Manager runs a set of long-lived agent loops on a single always-on Mac (we run it on a Mac mini). Each loop owns one real-world job and reports only verified outcomes:

- **Contract work:** finds suitable freelance jobs on Coconala, Lancers and CrowdWorks, writes proposals, handles negotiation and delivery support, and reconciles provider results.
- **Paid writing:** creates and sells articles (note paywall, Substack paid posts, aniccaai.com).
- **Agent marketplace:** builds and publishes agents on the Capafy marketplace and runs a separate distribution loop for them.
- **Mobile apps:** shared release, marketing and measurement loops for our iOS apps Anicca and Honne.
- **Follow-through:** fundraising and event discovery, a CFO loop that reconciles revenue and expenses, and a host steward that keeps the machine healthy.

The public catalog lists 18 user-facing capabilities plus one system agent (`docs/agents.md`).

## How it uses Codex

Codex is the brain. The installer signs the user in through the official `codex login` flow with their ChatGPT plan; no separate OpenAI API key is required (`docs/getting-started.md`). Each loop is a skill (`skills/<loop>/SKILL.md`) that Codex executes on a schedule. A self-build loop turns verified feedback and product evidence into reviewed improvements to the same repository, so the system improves its own loops through pull requests rather than hand edits.

## What we would do with the credits

1. Move the evaluation and self-improvement passes (re-running a loop against recorded cases, scoring, proposing a fix) from the subscription session to the API, so they can run in parallel without competing with production loops.
2. Publish the evaluation harness and the per-loop eval cases in the repository so other Codex users can reuse them.
3. Make the one-command installer work for users who prefer an API key over a ChatGPT sign-in.

## Why it matters for open source

Most agent frameworks stop at a demo. Life Manager is a working reference for running Codex-driven agents against real marketplaces with evidence-based reporting (a plan, a test pass or a process exit code is never reported as a business result). Everything, including the loop definitions and their safety rules, is MIT-licensed and installable with one command.

## Contact

(fill from the private applicant profile at submission time; do not commit personal data)
