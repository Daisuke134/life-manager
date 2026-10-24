# Grant / accelerator drafts — 2026-10-24 (claude-6)

Status: drafted, not submitted. Ledger rows: `elevenlabs.io/startup-grants`, `aws.amazon.com/activate`, `nvidia.com/startups` in `ledger/APPLICATIONS.md`.
Applicant identity (name, email, company, country) comes from `~/.config/anicca/job-search/profile.json` at submit time; it is not copied here.
Revenue, MAU and funding figures are left as `[fill from official readback]`: fill them only from App Store Connect / RevenueCat / Stripe readback, never estimate.

## Shared facts (verified 2026-10-24)

- Company/brand: Anicca AI (aniccaai.com). Self-funded, no outside funding.
- Life Manager: open-source AI manager for running businesses on a Mac. Public repo https://github.com/Daisuke134/life-manager.
- AI Monk Index: live remote MCP server `https://aniccaai.com/.netlify/functions/ai-monk-mcp` (6 read-only tools, `initialize` answers protocol 2025-06-18). Official MCP Registry `io.github.Daisuke134/ai-monk-index` v0.4.11; Glama connector page live.
- Live iOS apps (App Store): Anicca (id6755129214), For Better Sleep: Sleep Reset (id6762143790), Thankful: Gratitude Journal (id6759514159), Honne (id6759667221).
- Current voice/video stack: HeyGen avatar video for AI monk content. ElevenLabs is not used in production today (it appears only in affiliate review content).

## 1. ElevenLabs Grants — https://elevenlabs.io/startup-grants

Program facts (official page): 12 months of free usage (stated "680+ hours of Agents usage, $5,500+ in value"); eligibility requires a monetized product use case; no fixed deadline stated.

- Product: Anicca AI — mindfulness and sleep iOS apps plus an AI monk content channel.
- Use case (planned, state it as planned): guided sleep-reset and gratitude audio inside For Better Sleep and Thankful, and narration for AI monk short videos currently made with HeyGen.
- Monetization: App Store subscriptions on the four live apps. Revenue last 30 days: [fill from official readback].
- Why voice: audio sessions are the core of a sleep app; a natural voice is what users pay for.
- Plan for 12 months: ship audio sessions in For Better Sleep first, measure trial-to-paid change in RevenueCat, then extend to Thankful.

## 2. AWS Activate Founders — https://aws.amazon.com/startups/credits

Program facts (official page): self-funded tier, starts at $1,000 in credits (select participants up to $5,000). Requires pre-Series B, founded in the last 10 years, an AWS account on the Paid Tier plan, and a company website.

- Prerequisite to check before submit: AWS account on Paid Tier. Not verified in this pass; if no such account exists, this row stays drafted.
- Website: https://aniccaai.com
- Stage: self-funded, pre-seed.
- Use: hosting Life Manager Cloud (aniccaai.com/lm) backend and the AI Monk Index data refresh jobs, currently on Netlify functions.

## 3. NVIDIA Inception — https://www.nvidia.com/en-us/startups/

Program facts (official page): free; any funding stage; no fees, deadlines or cohorts. Apply at https://programs.nvidia.com/phoenix/application.

**Blocked (2026-10-24 13:40 JST, application page read):** membership requires an officially incorporated company and two contacts with non-alias business email (gmail.com and info@-style aliases are rejected). `docs/team/specs/funding-pipeline.md` L7 records that `company.legal_name=Anicca` is not proof of incorporation, so this cannot be submitted truthfully until the company is incorporated and a personal @aniccaai.com mailbox exists.

- Company description: Anicca AI builds Life Manager, an open-source AI agent that runs small online businesses on a local Mac (contract work, apps, content, digital products), and AI Monk Index, a public research MCP server.
- AI focus: agent orchestration, on-device and hosted LLM inference, AI video/voice content.
- Website: https://aniccaai.com · GitHub: https://github.com/Daisuke134/life-manager
- Funding: self-funded. Employees: [fill from profile].
- Ask: cloud credits and technical training for inference cost reduction.
