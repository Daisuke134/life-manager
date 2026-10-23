# Draft: Claude for Open Source

- Program: https://claude.com/contact-sales/claude-for-oss (fetched 2026-10-23). 6 months of Claude Max 20x for open source maintainers and contributors.
- Deadline: not stated.
- Eligibility tracks on the page: 500+ dependent repos / 100+ dependent packages / 200,000+ monthly downloads; listed core contributor of a recognized foundation; 100+ merged PRs into repos you don't own in 12 months; 20+ unique external contributors in 12 months; OpenSSF criticality score 0.4+. **Life Manager has not been measured against these and is not expected to meet them.** The page adds: "Don't quite fit? If you maintain something the ecosystem quietly depends on, apply anyway and tell us about it." This draft is for that path.
- Form fields were not captured.
- Status: **draft only, not submitted.** Ledger key `claude.com` was FREE on 2026-10-23.
- Fact sources: `README.md`, `docs/getting-started.md`, `docs/agents.md`, `AGENTS.md`.

## Project

Life Manager — https://github.com/Daisuke134/life-manager (MIT License)

## Tell us about it

Life Manager is an open-source AI manager that keeps working on your Mac. It runs long-lived, self-improving agent loops that do real work through the user's own accounts: freelance proposals and delivery support on Coconala, Lancers and CrowdWorks; paid articles on note and Substack; agent listings on the Capafy marketplace; and release and marketing loops for the iOS apps Anicca and Honne. One always-on Mac mini runs everything, and the default brain is the user's ChatGPT subscription through Codex, so a user needs no separate API key.

The project is small, but it is a complete, MIT-licensed reference for something many people are trying to build: agents that run real businesses unattended and report only verified outcomes. Its loop definitions (`skills/<loop>/SKILL.md`), evidence rules, and worktree-to-release promotion contract are all public and installable with one command.

## How Claude Max would be used

- Claude Code is already used in the project's development workflow alongside Codex (the repository carries `CLAUDE.md` project instructions). Max would let the maintainer run review and self-improvement passes on Claude without rationing.
- Add and maintain a documented path for running Life Manager loops with Claude as the agent, so users are not tied to one provider.
- Publish the results (setup guide, compatibility notes) in the repository.
