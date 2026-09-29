# The Coconala loop

> **Current onboarding boundary:** the Coconala package is a public beta. The public
> Terminal command, dependency/Codex preparation, dedicated browser, official account
> gates, six-job activation, zero-listing Storefront publisher, `gog` email and clean-HOME
> contract are implemented. Independent clean-Mac full E2E acceptance is still open. The
> owner completes Coconala's official account/SMS/eKYC/bank ceremony. Sales and bank arrival
> remain receipt-based outcomes, never guaranteed setup results.

### Product status

This is the only marketplace money loop currently offered as a one-command OSS public beta.
All four business lanes and their two supporting jobs are public. `gog` email onboarding
has real send/inbox readback and the clean-HOME Terminal contract is verified. Upwork,
Mercor, and other marketplace loops are not advertised as installable
OSS products yet, even where internal components exist.

### Accepted onboarding flow (external acceptance pending)

1. On a clean Mac, run the one-line bootstrap (or run `./install.sh coconala` from an
   existing checkout):

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Daisuke134/life-manager/main/scripts/bootstrap-coconala.sh)"
   ```

   It installs Homebrew/Git only when missing, creates or fast-forwards
   `~/life-manager`, and starts the Coconala setup directly in Terminal. It never deletes
   or replaces a non-Git directory.
2. The installer runs `codex login` when the CLI is not authenticated. It does not ask
   for language, timezone, skills, categories, prices, or a notification channel.
3. It opens Coconala in the dedicated agent browser profile at
   `~/.cloak/profiles/gig-daily-driver` and shows the whole checklist once.
4. In that browser, the owner completes account or login, email, SMS, seller
   information, required consents, smartphone eKYC, and bank registration.
5. The owner returns to Terminal and runs the same command once. Life Manager attaches
   to the same browser session, receives no password, and verifies every official state.
6. Life Manager starts Browser, Apply, Reply, Storefront, Paid, and Release Watcher.
7. Storefront imports existing listings or creates the first truthful listing when the
   official count is zero; the other lanes then operate without ordinary approval gates.

From there, launchd keeps the dedicated browser and all four business lanes running while
the Mac is on. The same browser profile and private session vault survive normal browser
restarts. If Coconala expires the login, the flow reopens the official login page in that
same profile, verifies recovery, and resumes; it never creates a replacement account.

That is the complete normal setup. Do not create a listing manually, install Python
packages, edit JSON, configure launchd, or give Life Manager a Coconala password.
Terminal is the setup and status surface. Official Coconala email remains active. Life
Manager reports use the existing `gog` Gmail transport after Google OAuth and a real
send/inbox readback; SMTP and Telegram are not part of the public default.
Using that same Gmail address for Coconala signup avoids entering two addresses. If an
authenticated Gmail account already exists in `gog`, setup asks no email question.

### Deferred external acceptance

After the code-owned OSS UX is complete, independent clean-device owners validate this
README without private coaching or copied credentials/configuration/browser/state. That
evidence is not a current coding task and does not guarantee income or time to first sale.

Four background jobs that run a [Coconala](https://coconala.com) seller account
around the clock: they read the job board and apply, keep the storefront honest,
answer buyers who ask questions before they buy, and work the orders that get
paid for. They run on one Mac, as launchd user agents, driving one logged-in
browser. There is no marketplace API key or hosted service; the optional local
semantic proxy is a private machine credential, never part of the package.

Everything the loop needs is in this folder. `scripts/` is the code, `schemas/`
the shapes it makes a model answer in, `config/` the catalogue and the job
definitions, `agent-runner/` the engine that talks to the model, `evals/` the
replays, `tests/` the tests.

| lane | job label | every | what it does |
|---|---|---|---|
| apply | `ai.anicca.hf-gig-apply-direct` | 60s | Reads the public job board, proves which postings the installed AI/Mac/tool system can deliver, and submits an application with a proposal. |
| storefront | `ai.anicca.hf-gig-storefront-direct` | 60s | Reads the seller's own listings and their view/inquiry counts, and edits the ones people look at and never contact. |
| negotiate | `ai.anicca.hf-gig-reply-detector` | continuous, 30s discovery | Watches talkrooms opened *before* purchase and answers the buyer's questions and estimate requests with two independent workers. |
| paid | `ai.anicca.hf-gig-paid-direct` | 300s | Works orders that have been paid for: reads the requirement, builds or reviews the deliverable, and decides whether it is good enough to hand over. |

Two more jobs support them:

| job label | what it does |
|---|---|
| `ai.anicca.hf-gig-browser` | Keeps one Chromium alive on a debugging port. All four lanes share it, because the login lives in its profile. |
| `ai.anicca.hf-gig-release-watch` | Fast-forwards this checkout to `origin/main` and moves idle lanes onto the new code. |

The AI system is the delivery workforce. The owner's personal free time, manual skill,
sleep, health, or workload does not cap Coconala throughput. Independent profitable work
runs concurrently up to measured compute, browser/tool, deadline, platform, cost, and
quality limits. Job Hunter is different: because the human becomes the employee, that
loop alone must use the person's real employment facts and availability.

### Autonomous operating contract

Each application, inquiry, and purchased order has an isolated owner and private project
root. That owner reads the complete relevant DM, talkroom, attachment, listing, and prior
effect history. Reusable skills, account references, browser sessions, and tools are shared;
customer context, artifacts, history, and state are not. Secrets remain resolver references
and are opened only by the adapter that needs them.

Independent project owners work concurrently both inside one lane and across lanes. A shared
authenticated browser or account is not an account-wide queue: each owner uses its own tab,
target, client identity, URL, project state, and evidence root, so unrelated sends and
readbacks may proceed at the same time. Only two attempts for the same exact entity and
effect identity contend, through effect-key compare-and-swap/fencing rather than a global
browser lock. Parallel work must never mix two customers' context. The model chooses the
work plan and tools; deterministic code owns target identity, hashes, receipts, effect
fencing, and replay detection. This is the `P0-four-lane-parallel` contract.

### Owner lifetime and closure

An owner is durable project state, not a forever-running process. One bounded wake may
plan, build, send, read back, or observe an external wait and then exit. A later official
event resumes the same owner from its checkpoint. A revision, provider wait, buyer review,
or temporary failure never creates a replacement owner and never closes the project.

| state | process behavior | owner behavior |
|---|---|---|
| `ACTIVE` | Run the next bounded step, then exit | Retain ownership and checkpoint every verified effect |
| `WAITING_EXTERNAL` | Exit with no polling process | Resume on a later official event or scheduled observation |
| `AWAITING_BUYER` | Exit after exact submission readback | Resume on buyer revision, acceptance, or cancellation |
| `TERMINAL_PENDING_REPLAY` | Run one observe-only wake | Permit no new effect; prove duplicate effect zero |
| `CLOSED_COMPLETED` | No worker capacity | Official completion and replay-zero are immutable |
| `CLOSED_CANCELLED` | No worker capacity | Official cancellation and replay-zero are immutable |

`CLOSED_COMPLETED` requires the exact deliverable/provider effect, fresh pre-submit review,
Coconala seller readback, and buyer acceptance or official transaction completion when the
contract requires it. `CLOSED_CANCELLED` requires the official Coconala cancellation state,
not a cancellation request or support conversation. Both require a later observe-only wake
with effect zero. Closing releases execution capacity and the active browser target; it does
not delete customer context, artifacts, state, effect keys, or receipts. Those records become
an immutable tombstone that makes every replay a no-op. A new marketplace order receives a
new owner identity; a pre-terminal revision resumes the existing owner.

The lifecycle copies three proven OSS patterns without adding their runtimes as dependencies:

| reference | pattern reused | decision |
|---|---|---|
| [Temporal Python samples](https://github.com/temporalio/samples-python) `e652a4d0` | Stable child identity, durable signal wait, cleanup on cancel, bounded history continuation | Copy the state-machine pattern; do not add a Temporal server/SDK |
| [LangGraph](https://github.com/langchain-ai/langgraph) `f09cfe8f` | One `thread_id` per isolated owner, checkpoints and pending writes survive a failed step | Reuse existing project files/ledgers as checkpoints; do not add another state store |
| [Hatchet](https://github.com/hatchet-dev/hatchet) `89d130f3` | Entity-keyed concurrency, durable events, explicit completed/cancelled terminal states, stale invocation rejection | Key fencing by marketplace entity/effect; do not add Hatchet/Postgres |

### Paid no-human production boundary

The account owner performs only Coconala's mandatory official setup or recovery ceremonies,
such as account registration, SMS/eKYC, bank registration, and a provider-required login
challenge that no existing authorized session can satisfy. Those ceremonies are an explicit
`NEEDS_OWNER_CEREMONY` product state, never hidden Paid work and never a successful delivery.
After setup, normal Paid operation has no human approval gate and no foreground Codex/customer
work path.

For every purchased order, the launchd-selected project owner must resolve authorized skills,
accounts, sessions, and tools; perform the provider work; build the exact deliverable; repair
every actionable finding from a fresh isolated reviewer; submit once; and obtain official
provider/Coconala readback. The effect receipt records the durable owner/run identity. A user,
Codex, ad-hoc script, or uncheckpointed browser action cannot satisfy an acceptance gate.

The owner never buys quality by fabricating identity, attendance, consent, physical presence,
credentials, or completion. Apply normally rejects such work before purchase. If a legacy paid
order exposes an unsupported requirement, its project owner autonomously selects a truthful,
authorized disclosed-agent alternative when one satisfies the same buyer outcome; otherwise it
negotiates a supported scope or completes official cancellation. It does not wait for a person to
perform the work and does not submit a low-quality proxy.

Paid no-human acceptance requires varied real production orders to reach
`CLOSED_COMPLETED` or `CLOSED_CANCELLED` with owner-attributed provider effects, fresh QA,
exact seller readback, terminal official state, restart/resume evidence, and next-wake effect
zero. Tests, one successful message, one manually rescued order, and process liveness are not
that proof.

Apply prioritizes work the installed AI/Mac/tool system can demonstrate it can deliver well,
especially software, landing pages, writing, research, and strategy. It normally rejects work
whose success depends on a human meeting, undisclosed personal participation, unsupported
desktop-only operation, or prolonged browser labor with no reliable adapter. This is a
model judgement grounded in the complete posting and current capability evidence, never a
buyer-name, category, or keyword rule.

Before any buyer-visible submission, a fresh isolated reviewer checks the exact current
requirements against the exact artifact or message. The producing owner repairs actionable
findings before the fenced adapter sends once. Completion requires the intended provider
effect, exact Coconala seller readback, buyer acceptance or transaction completion when the
contract requires it, and a later wake with duplicate effect zero. Model success, process
liveness, tests, and a local artifact are not completion.

The four lanes form one revenue system: Apply and Storefront acquire demand, Reply
converts it without exposing internal process details, and Paid fulfills it. Revenue
targets are measured from official contract, fee, payout, and bank receipts. Application
volume, listing publication, pending balance, and model estimates never count as the monthly
cash target and no income amount is guaranteed.

---

## What you need before you start

| | why |
|---|---|
| A Mac, Apple Silicon, macOS 14 or newer | The jobs are launchd user agents and the browser build is a macOS app bundle. |
| A **ChatGPT subscription** | The installer installs the Codex CLI when missing, opens `codex login`, and verifies the resulting session. |
| A Coconala registration email, Japanese mobile phone, accepted identity document, and matching domestic bank account | Enter these only on official Coconala/eKYC pages opened by the installer. Storefront creates the first listing when none exists. |
| Internet access and macOS administrator access during setup | The installer prepares Homebrew, Git, Python, the private venv, CloakBrowser, and the six jobs only when missing. |

Owner status and official outcome receipts are available in Terminal with
`./install.sh coconala outcomes`. Coconala continues sending its own account and buyer
mail to the registered address. Life Manager email reports require a configured outbound
`gog` Gmail account; their absence never blocks the four lanes.

The semantic reply lane is tool-less. If the machine has a local CLI proxy, put
its token in `~/.cli-proxy-api-key` and keep the loopback provider enabled in the
private install configuration; the existing `claude-direct` slot then uses the
healthy local `gpt-5.3-codex-spark` route before trying the other providers. This
file is never committed or sent to the marketplace. A machine without that file
falls through to its normal Codex/Claude/Hermes candidates, and no provider is
given browser or send tools by this fallback.

---

## Advanced/manual recovery

The normal one-line Terminal flow above is the public onboarding. The remaining sections are
for recovery, custom notification adapters, operator overrides, qualification and
uninstall; a normal owner should not need them.

### 1. Get the code

```bash
git clone https://github.com/Daisuke134/life-manager.git ~/life-manager
cd ~/life-manager
```

### 2. Tell it about your machine

Everything machine-specific lives in one file. Create it, and put in it only the
things that differ from the defaults:

```bash
mkdir -p ~/.config/anicca/gig
cat > ~/.config/anicca/gig/install.json <<'JSON'
{
  "GIG_NOTIFY_EMAIL": "you@example.com",
  "GIG_GOG_ACCOUNT": "you@example.com",
  "GIG_GOG_BIN": "/opt/homebrew/bin/gog",
  "GIG_BROWSER_FINGERPRINT": ""
}
JSON
```

Every key and its default is listed under [Configuration](#configuration). If
you are happy with all of them, an empty `{}` is a valid file, and so is no file
at all.

### 3. The browser

The lanes drive [CloakBrowser](https://github.com/CloakHQ/CloakBrowser), a Chromium
whose fingerprint is patched at the C++ source level. `pip install cloakbrowser`
installs the wrapper; the ~200 MB browser binary downloads on first use and caches
itself under `~/.cloakbrowser/chromium-<version>/`. The free tier needs a GitHub
sign-in at [cloakbrowser.dev/free](https://cloakbrowser.dev/free) to pick which
binary you get.

```bash
pip3 install cloakbrowser
python3 -c "from cloakbrowser import launch; b = launch(headless=True); b.close()"
ls ~/.cloakbrowser/          # chromium-<version>/ should now exist
```

**The version matters, and today you will get a newer one than is qualified here.**
CloakBrowser currently ships Chromium 150/151; the loop was qualified on 145.
`scripts/launch_gig_browser.sh` carries a TLS compatibility switch bounded to 145 and
146, because newer Chromium offers ML-KEM by default and on at least one real network
path the larger ClientHello is dropped — the browser completes TCP and then returns
`ERR_TIMED_OUT` while `curl` on the same machine is fine.

Outside that range the switch is not applied and the launcher says so on stderr. It
still starts, because plenty of networks never drop that ClientHello and there is no
reason to block those. **If the site loads under `curl` but not in this browser**, that
warning is your answer:

```bash
# after qualifying it on your own network
GIG_BROWSER_TLS_COMPAT=force  # set it in ~/.config/anicca/gig/install.json
```

Do not widen the `145|146` case on faith. Qualify the major you actually have, against
the real site, and record what you measured.

### 4. Start the browser and log in — the one manual step

```bash
python3 skills/earn/gig/scripts/gig_release.py activate --jobs ai.anicca.hf-gig-browser
```

That launches Chromium with a debugging port on `127.0.0.1:9223` and a profile
at `~/.cloak/profiles/gig-daily-driver`. Open it, go to coconala.com, and **log
in once, by hand**. Solve whatever it asks you — that is the point of doing it
yourself.

The session then lives in that profile directory. The lanes never see your
password; they attach to the browser that is already logged in. Cookies are
snapshotted to `~/.cloak/vault/gig-daily-driver/` so a browser restart can
restore the session instead of asking you again.

Leave this browser running. It is the only thing standing between the loop and
a login prompt.

### 5. Describe what you sell

Seller listing IDs, contracts, copy and images are private runtime data and are
not shipped in this repository. Put the bundle outside the checkout and set these
flat keys in `~/.config/anicca/gig/install.json`:

```json
{
  "GIG_STOREFRONT_ROOT": "/absolute/private/storefront-bundle",
  "GIG_STOREFRONT_TARGET_SERVICE_ID": "your-target-id",
  "GIG_STOREFRONT_GALLERY_SERVICE_ID": "your-gallery-id",
  "GIG_STOREFRONT_PRESENTATION_SERVICE_ID": "your-presentation-id",
  "GIG_STOREFRONT_SCOPE_SERVICE_ID": "your-scope-id"
}
```

The root contains `scorecard.json`, `families.json`, `contracts/listings/*.json`,
`contracts/new-listing.json`, six files under `contracts/mutations/` named
`title.json`, `body.json`, `scope.json`, `package.json`, `faq.json`, and
`price.json`, plus `assets/image-contract.json` and
`assets/gallery-contract.json` with every referenced asset below `assets/`.
The lane validates the complete bundle before it leases the browser.

### 6. Start the lanes

```bash
python3 skills/earn/gig/scripts/gig_release.py activate
```

This cuts an immutable release of the current commit under
`~/gig/releases/life-manager/<sha>/`, atomically publishes it as
`~/gig/releases/life-manager/current`, writes the four launchd jobs through that
stable path, loads them, and reads their arguments back from `launchctl`. The
one-time load installs a stable definition; later releases move only `current`.

To also keep them following `main` by themselves:

```bash
python3 skills/earn/gig/scripts/gig_release.py activate --jobs ai.anicca.hf-gig-release-watch
```

### 7. Watch it work

```bash
python3 skills/earn/gig/scripts/gig_release.py status
launchctl kickstart gui/$(id -u)/ai.anicca.hf-gig-storefront-direct
```

Then look at what it actually did, not at whether the process exited:

```bash
tail -1 ~/gig/apply-direct/wakes.jsonl      | python3 -m json.tool | head -20
tail -1 ~/gig/storefront-direct/wakes.jsonl | python3 -m json.tool | head -20
cat ~/gig/evidence/paid-direct-live/latest.json | python3 -m json.tool | head -20
ls -t ~/gig/evidence | head
```

A lane that exits 0 and observed nothing is not working. `observed`,
`official_services_read` and `replied` are the numbers that mean something.

### Latest public-package verification

Clean remote clone `f0984456d9d6e9bab44f876f05f3423d6cd138c5` passes the OSS
self-contained contract (11/11), the public Apply and Negotiate suites (131/131),
both production-entrypoint compilation checks, and scoped tree/history secret scans
with zero findings. This verifies the package already used by an authenticated seller;
it does not close the separate new-account onboarding boundary stated at the top.

---

## Configuration

`~/.config/anicca/gig/install.json` overrides these. Nothing here is a secret;
no lane reads a credential from its environment.

| key | default | what it is |
|---|---|---|
| `PYTHON` | `/opt/homebrew/bin/python3` | The interpreter the jobs run. Must have `websockets`. |
| `GIG_STATE_DIR` | `~/gig` | Everything the loop remembers: ledgers, evidence, order workspaces, locks. |
| `GIG_LOG_DIR` | `~/gig/logs` | launchd stdout/stderr for each job. |
| `GIG_BRAKE_DIR` | `~/gig/state` | Where an operator brake file stops a lane. See below. |
| `LIFE_MANAGER_HOME` | `~/.local/state/life-manager` | Shared state directory for this repo's loops. |
| `CDP_PORT` | `9223` | The debugging port the shared browser listens on. |
| `CDP_DAILY_DRIVER_PROFILE` | `~/.cloak/profiles/gig-daily-driver` | The Chromium profile that holds your login. |
| `SESSION_VAULT_DIR` | `~/.cloak/vault/gig-daily-driver` | Cookie snapshots used to restore the session after a restart. |
| `GIG_BROWSER_FINGERPRINT` | *(empty)* | Fingerprint seed passed to the browser build. |
| `GIG_NOTIFY_EMAIL` | *(empty)* | Preferred owner-report recipient. When set, all four lanes use email. |
| `GIG_GOG_ACCOUNT` | *(empty)* | Gmail-scoped `gog` OAuth account used to send owner reports. |
| `GIG_GOG_BIN` | `/opt/homebrew/bin/gog` | `gogcli` executable installed by normal setup when missing. |
| `GIG_REPORT_CHAT` | *(empty)* | Optional legacy Telegram fallback when email is unset. |
| `GIG_SANDBOX_DENY` | *(empty)* | Colon-separated absolute paths the sandboxed paid builder must not read — other checkouts, other loops' state. Must be absolute; a relative entry is refused rather than silently ignored. |
| `GIG_STOREFRONT_ROOT` | *(empty)* | Absolute private seller-bundle root; Storefront refuses to start without it. |
| `GIG_STOREFRONT_TARGET_SERVICE_ID` | *(empty)* | Listing used for the target image/FAQ experiment. |
| `GIG_STOREFRONT_GALLERY_SERVICE_ID` | *(empty)* | Listing whose gallery contract is applied. |
| `GIG_STOREFRONT_PRESENTATION_SERVICE_ID` | *(empty)* | Listing bound to title/body/package mutations. |
| `GIG_STOREFRONT_SCOPE_SERVICE_ID` | *(empty)* | Listing bound to the scope mutation. |

The job definitions themselves are `config/launchd-jobs.json`. Editing that file
and re-running `gig_release.py activate` is how you change a schedule, an
argument, or an environment variable — not by editing the plists in
`~/Library/LaunchAgents`, which are generated and will be overwritten.

---

## What it will not do

These are enforced in code, not by convention.

- **Formal delivery needs the buyer's own words as evidence.** Ticking 正式な納品
  is the irreversible step, so `validate_queue_contract()` in
  `scripts/coconala_formal_delivery_browser.py` refuses to drive toward it unless
  the queue carries an approval whose identity equals the newest message in the
  room, whose side is `buyer`, with a real message id and a 64-character content
  hash. No approval, no delivery — `formal_buyer_approval_evidence_required`.
  A pass also cannot escalate to formal at send time if it was not prepared as
  formal (`presend_action_escalation`), and a subscription room, which has no such
  checkbox at all, is refused outright.
- **It leaves hand-worked orders alone.** `OWNER_WORKED_TALKROOMS` in
  `scripts/paid_direct.py` lists orders that a person is handling. The lane still
  observes them so the backlog stays honest, and stops before any effect.
- **An operator brake stops a lane cold.** `scripts/gig_brake.sh raise --owner
  NAME --reason TEXT` writes a brake file; each lane refuses to start while it is
  held, and refuses to start if the brake file exists but cannot be read.
- **The paid builder runs sandboxed.** When it inspects or produces files it runs
  under `sandbox-exec` with a profile that denies it the release it runs from,
  the other orders' workspaces, and whatever else `GIG_SANDBOX_DENY` names. A
  profile that fails to compile stops the step; it never falls back to running
  unsandboxed.

---

## Known limits

Honest list. These are measured, not suspected.

- **The reference Mac has completed Reply production acceptance.** A natural
  reconciliation read all 140 official inbox cards over five terminally proven
  pages (`30/30/30/30/20`), freshly read all 140 threads, and reused none. It found
  no reply to send, two prior estimates to confirm, and 138 no-send conversations
  (`observe 102`, `stop_contact 15`, `semantic_failed 11`,
  `officially_unrepliable 10`). Both estimates were read back as already delivered,
  so the pass made zero reply or estimate effects. Later natural traffic produced
  five verified replies; each has one verified intent and seller-side readback,
  `duplicate_effect=0`, and a durable Telegram `reply_verified` receipt (provider
  message IDs `30152`, `30379`, `30428`, `30583`, and `30625`). Three fresh samples
  completed in 42, 109, and 8 seconds. This evidence accepts Reply only; it does
  not accept Paid or Storefront.
- **The reference Mac has completed Storefront production acceptance.** Release
  `ead7fd657` recovered a confirmed gallery contract after bounded evidence GC,
  loaded the Storefront job with a real 512 MiB disk floor, and completed two
  successive natural listing updates. The first changed only service `4312985` body;
  the second did not replay it and changed only service `4302213` title. Each wake had
  one hash-sealed contract, matching official before/after service identity,
  `effect=1`, `readback=1`, and `duplicate=0`. Durable Telegram receipts are provider
  message IDs `30741` and `30746`. This evidence does not accept Paid.
- **The paid lane's feedback digest is not stable.** The window that assembles
  the latest buyer feedback has been observed regressing to older concatenated
  text within the same day, which means the digest a builder would act on cannot
  currently be trusted to be the newest one.
- **The feedback cycle patch only fires once per project.** `_feedback_cycle_patch()`
  in `scripts/delivery_project.py` is wired, but the caller guards it on the
  project's `state.json` not existing yet, so it runs at bootstrap and never
  again. Do not loosen that guard before the digest above is stable: an unstable
  digest plus a live cycle is how a builder would act on stale instructions
  against a real customer's site.

---

## Keeping it running

`gig_release.py watch` is what the release watcher runs. It fetches `main`, builds
the immutable release, and atomically moves `current`. Stable jobs resolve it on
their next natural process start without a deploy-time reload. A legacy
SHA-specific loaded definition is migrated once at a natural gap.

Old releases accumulate under `~/gig/releases/`. They are ~50 MB each. Keep the
current and previous release for rollback; never delete the `current` target or a
release still used by a live process.

Upgrade with `git pull --ff-only` followed by
`python3 skills/earn/gig/scripts/gig_release.py activate`. To inspect generated
plists without loading them, add `--dry-run`. To uninstall, boot out the six
`ai.anicca.hf-gig-*` labels shown above and remove their matching files from
`~/Library/LaunchAgents/`; private state under `~/gig`, the browser profile and
`~/.config/anicca/gig/install.json` remain yours and are not deleted automatically.
