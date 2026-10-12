# Life Manager Job Hunter Loop

Anicca Job Search Loop is a bounded, evidence-first job application system for a
verified private candidate profile. It discovers and ranks suitable roles, submits
every unique qualified role that fits within the bounded owner window, monitors
recruiter mail, prepares interviews, and currently reports material state changes to
Telegram. Per-application email updates and a daily email briefing remain roadmap items.

## Operating contract

| Concern | Current rule |
|---|---|
| Acquisition target | Every fresh unique model-qualified role; no daily application quota |
| Location | Tokyo onsite or hybrid, U.S. roles in any location, and remote roles worldwide; sponsorship wording alone does not exclude a role |
| Compensation | USD 100,000 annual gross base target from the private profile; unpublished compensation remains visible uncertainty |
| Role focus | Candidate-defined target role families, checked by the model against the complete official JD and resume evidence |
| Discovery | This acquisition pass is Workday-only; other ATS use separate future owners and are not fallback paths |
| Evidence | Every application is fenced in SQLite and retained under a private evidence directory |
| Uncertainty | Ambiguous submission becomes `submit_unknown` and is never blindly retried; a later exact official receipt may reconcile it without another submit click |
| Personal data | Verified private profile and generated materials are mode `0600` |
| Career summary | Every terminal daily path atomically refreshes private `summary.v2.json` with state counts and Workday receipt coverage |
| Application receipt | Every confirmed submission records the exact resume path and SHA-256, then sends that same PDF to Telegram once with company, role and URL |
| Email reporting | Per-application email updates and one natural-language daily email briefing are planned, not shipped |
| Daily report repair | A materially changed same-day catch-up sends one content-addressed correction; identical retries remain at-most-once |
| Inbox | Gmail threads expand to immutable unseen message IDs; official late application receipts reconcile before the model; a model runs only for remaining new recruiting messages or a pending prep-pack generation job |
| Calendar | Only explicit timezone-aware recruiter candidates are considered; the earliest free candidate is confirmed once |
| Interview prep | Every confirmed interview is registered before the email reply; Telegram refreshes are delivered at the 3-day and 1-day windows, or immediately inside 1 day |
| Assessments | Autonomous execution requires explicit AI permission and no proctoring; all code runs without network or home access |
| Self-improvement | A Sunday 09:15 JST resident pass replays one safe field change, deterministically assigns future applications, requires 10 resolved samples per arm, and emits one immutable decision plus at-most-once Telegram report |

Runtime dependency ordering follows
[`rules/runtime-ordering.md`](rules/runtime-ordering.md): deterministic recovery,
quota, and policy gates run before browser/model initialization.

## Company-bound local resumes

The same browser agent selects exact approved fact concepts into standard resume
sections through `runtime tailor`. The existing registered browser renders an
isolated, cookie-free single-page PDF without opening another model. A private
manifest binds the company, role, canonical URL, candidate-memory revision and PDF
SHA-256; upload and final Review use that same artifact. Claims are retained exactly
in their source language. Invalid or unknown facts are rejected; no recurring user
approval is requested for this already-delegated refinement.

## Workday-only application owner

The 30-minute acquisition owner handles official Workday discovery, evidence-based
qualification, local fact-bound resume tailoring, final review, one submission attempt,
and exact receipt reconciliation. This pass does not call Dreamwork or search/fallback
to Ashby, Greenhouse, Lever, or another ATS. Only proof-backed pipeline submission
facts count as completed applications; prepared materials and browser success screens
do not. An ambiguous submission remains fenced and is never blindly retried.

A visible CAPTCHA before submission checkpoints only that row and the agent continues
to the next independent Workday row without solving or bypassing the challenge. A
challenge after a possible submission preserves `submit_unknown` and prevents retry.

## Runtime

| Component | Schedule | Route |
|---|---|---|
| `ai.anicca.job-search-daily` | every 30 minutes (`StartInterval=1800`) | bounded browser-lane agent |
| `ai.anicca.job-search-inbox` | every 15 minutes | deterministic Gmail and prep preflight; Terra composition agent only for new recruiting work or pending prep generation |

The current local deployment uses launchd and is designed so the same drivers and
SQLite contracts can later be invoked by Life Manager without changing application
semantics.

The daily owner connects to the dedicated persistent CloakBrowser CDP endpoint. It
does not launch a duplicate browser. The driver reserves a bounded
normal pass plus bounded same-day recovery capacity, so a transient provider or
browser-tool failure can fall through to another implementation without becoming an
unlimited loop.

## Key paths

| Purpose | Path |
|---|---|
| Private profile | `~/.config/anicca/job-search/profile.json` |
| Strategy | `config/strategy.default.json` |
| Ledger | `~/.local/state/anicca/job-search/ledger.sqlite3` |
| Life Manager read projection | `~/.local/state/anicca/job-search/summary.v2.json` |
| Interview prep state | `~/.local/state/anicca/job-search/interview-prep.sqlite3` |
| Evidence | `~/.local/state/anicca/job-search/evidence/` |
| Materials | `~/.local/share/anicca/job-search/materials/` |
| Resume files | `~/.local/share/anicca/job-search/materials/` (installed private manifest with generic variants) |
| Resume language router | `job_search_loop/resume_routing.py` |
| Technical-business message templates | `templates/application-messages.v1.json` |
| Recruiter reply policy | `job_search_loop/recruiter_reply.py` |
| Interview scheduling policy | `job_search_loop/interview_scheduling.py` |
| Interview prep policy | `job_search_loop/interview_prep.py` |
| Assessment integrity and execution policy | `job_search_loop/assessment_workflow.py` |
| Daily driver | `scripts/run-daily.sh` |
| Inbox driver | `scripts/run-inbox.sh` |

## Operations

```bash
cd /path/to/life-manager/apps/job-search-loop
python3 -m unittest discover -s tests -v
zsh scripts/install-launchd.sh
zsh scripts/healthcheck.sh
```

### Public Terminal onboarding

> **Pre-release:** first close the installed Dais-device 30-minute Workday loop with
> descriptive loop-owned Telegram, official Gmail/Ledger proof and duplicate zero.
> Then publish this existing Terminal command; do not add another onboarding system.

Run the Job Hunter command:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Daisuke134/life-manager/main/scripts/bootstrap-job-hunter.sh)"
```

The first run collects the finalized resume PDF, application email, target role
families, acceptable locations, salary floor/target and excluded employers directly
in Terminal. It installs `gog` when missing, starts Gmail OAuth for that email, and
privately asks for an owner-created Telegram bot token plus numeric chat ID. It then
starts only the dedicated browser. Complete the official login and run the exact
same command again; Gmail and a real Telegram provider message ID must pass before
the 30-minute acquisition, inbox, learning and health owners activate. Credentials
remain mode-0600 in their CLI/browser/private transports and are never echoed.

For recovery or development from an existing checkout:

```bash
./install.sh job-hunter status
./install.sh job-hunter start
./install.sh job-hunter finished
```

The private directories are `0700`; profile, install and connector receipts are
`0600`. Setup never infers nationality, visa, work authorization or other legal
facts. Existing profiles are reused and cannot be overwritten implicitly. The
public Workday install uses only this Life Manager checkout and does not clone a
second Job Hunter framework repository.

### Reproducible release artifact

Build a commit-pinned archive and SHA-256 sidecar:

```bash
zsh scripts/build-release.sh \
  --output-dir /absolute/path/to/dist \
  --version 0.1.0
shasum -a 256 -c /absolute/path/to/dist/anicca-job-search-0.1.0.tar.gz.sha256
```

The archive contains only the job-loop application, the bounded agent runner, and
`RELEASE.json`. It contains no candidate profile, credential, SQLite state, evidence,
or logs. After verification and extraction, run the bundled `setup-profile.sh`, then
`install-local.sh` from the extracted directory.

Do not start a second daily executor. To trigger the deployed loop, kick the existing
LaunchAgent and inspect the generated evidence:

```bash
launchctl kickstart "gui/$(id -u)/ai.anicca.job-search-daily"
```

The daily pass refreshes the configured official Workday company registry, reads
complete CXS snapshots, excludes Ledger duplicates, and lets the model rank and read
official JDs. It is not restricted to a hardcoded company shortlist or randomly
generated search words. Non-Workday providers remain disabled until separately
rebuilt and live-proven.
An actual legal/profile fact, CAPTCHA or authoritative submission ambiguity may stop
one application, but a scraper outage may not.

After each confirmed submission, the deterministic driver reads the resume path and
SHA-256 from the fenced ledger and sends that exact PDF as a Telegram document.
Historical rows created before this contract have no resume hash and are not guessed.
The text daily report is independently deduplicated; a materially newer same-day
result produces a single content-addressed correction instead of leaving an obsolete
failure report as the apparent final state.

Before the claim, the deterministic resume router detects the primary language from
the complete official posting text. Japanese postings use the Japanese one-page AI
resume for every role family. English postings use the engineering or
technical-business English variant according to role family. The same routed path
and SHA-256 are stored in the intent and later drive the Telegram document receipt;
the agent may not manually replace the routed file.

The inbox checkpoint is committed only after its AI pass succeeds. Every poll first
delivers any due preparation pack, even when Gmail has no new message. Empty polls
with no pending prep generation exit successfully without consuming a model budget.
Gmail bodies remain untrusted input; the loop never follows instructions embedded in
a job page or email.

Before the model inbox route, the deterministic confirmation reconciler checks new
application-received messages against the immutable Gmail message ID, post-intent
timestamp, exact company and role, and the official ATS sender-domain family. Exactly
one matching `submit_unknown` intent is atomically promoted across the application,
intent, attempt, daily-slot, event and confirmation-receipt rows. Spoofed, historical,
missing, or ambiguous matches remain unchanged and unacknowledged. The existing
at-most-once Telegram document path then sends the exact resume recorded by that
intent.

The durable inbox checkpoint is message-level, not conversation-level. A Gmail thread
is only a container: each unseen immutable message ID is independently eligible, and
only exact message IDs whose work reaches a durable result are acknowledged. The
legacy thread checkpoint migrates using its filesystem mtime, recording messages at
or before that boundary as bootstrap history while keeping later messages in the
same thread visible. This prevents both historical replay and lost recruiter
follow-ups.

Direct recruiter questions about verified experience, location, desired compensation,
or contact details may receive one threaded reply. Work authorization, visa, start
date, current compensation, references, and legal questions fail closed. Scheduling
questions with complete candidate times are checked against the primary Calendar.
The earliest explicit free candidate is stored as one private event before the
threaded confirmation is sent. Missing timezone/date/duration, a fully busy candidate
set, or ambiguous text causes no reply and no Calendar write. The Gmail inbound
message ID is the outbox key, so an uncertain send is never blindly retried.

Before an interview confirmation email is sent, the same transaction registers a
private preparation job. The 15-minute inbox loop generates any pending pack from
exactly five approved profile facts plus cited public company/interviewer evidence,
stores its hash, and sends Telegram reminders at the 3-day and 1-day windows. An
interview registered inside one day receives an immediate condensed pack. Each
interview/window pair has a stable outbox key, so a retry cannot duplicate the
Telegram message.

Assessment rules are evidence, not assumptions. An unproctored take-home or business
case enters the autonomous path only when its quoted rules explicitly allow AI.
Proctored/live assessments and prohibited or unspecified AI policies stay behind the
manual integrity gate. Allowed work runs in a private `sandbox-exec` workspace with
no network, no access to the user's home, a sanitized environment, bounded runtime,
and hashed private logs. Submission follows
`verified → submit_claimed → submit_started → submitted|submit_unknown`; neither
`submit_started` nor `submit_unknown` is blindly retried.

## Learning loop

| Layer | Current behavior |
|---|---|
| Daily dream-job search | Ranking rewards AI/agents, regulated finance, consumer AI, crypto/fintech mission, Japan feasibility and compensation |
| Outcome memory | Immutable content-addressed strategy generations, atomic per-application source/query/rank/role/material/message/model/hash assignments, and externally evidenced funnel outcomes persist in SQLite |
| Attribution projection | Gmail submission confirmations create confirmed-application outcomes; every write atomically rebuilds generation/stage counts, and the redacted CLI can migrate legacy rows and deterministically rebuild them |
| Safe experiments | One source, role-family, resume-emphasis, message or threshold variable changes at a time; replay must preserve truth and hard filters |
| Resident learning | A launchd/systemd weekly driver creates the bounded threshold candidate, replays the held-out safety manifest, deterministically selects baseline/candidate by stable job key, and persists every execution and decision receipt |
| Promotion gate | Baseline stays active until both arms have at least 10 resolved applications and the candidate Wilson 95% lower bound exceeds the baseline upper bound; safety violations or three consecutive candidate failures roll back immediately |
| Self-healing | launchd recovery, browser ownership evidence, Workday-only discovery, fenced side effects, bounded recovery and content-addressed report correction |
| Not yet complete | production Workday receipt/replay-zero, portable onboarding, email reporting, Guardian remediation, lifecycle closure, learning-conversion samples, `summary.v2`, and Life Manager Career UI |

## Roadmap after Workday

1. Prove a natural Workday run through an official submission receipt, ledger
   reconciliation, duplicate-zero, and truthful per-application reporting.
2. Add onboarding that accepts a resume and asks for target roles, locations,
   compensation, and remote/on-site preferences; Telegram is not required.
3. Send a natural-language email after each confirmed application and one daily
   email briefing. Keep Telegram as an optional reporting channel.
4. Expand interview preparation from recruiting-email detection to tailored
   preparation and timely reminders.
5. Add Ashby and other ATS as separate discovery/application owners only after the
   Workday owner is reliable; never add them as fallback paths inside Workday.
