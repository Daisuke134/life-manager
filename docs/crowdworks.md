# CrowdWorks on your Mac

[Get started](getting-started.md) · [Agent catalog](agents.md)

Connect your own CrowdWorks account to find projects, handle replies and paid work,
and track results. You need ChatGPT Plus or higher and a Mac that stays awake.
End-to-end acceptance on a separate clean Mac remains open.

## Prepare your profiles

Keep these two JSON files outside the Git checkout. The examples are fictional:
replace the name, IDs, categories, rates, and work descriptions with your own information.

Save your work profile as `work-profile.json`:

```json
{
  "version": 1,
  "candidate": {"name": "Your name"},
  "facts": [
    {
      "id": "project-1",
      "claim": "Describe work you have actually done.",
      "evidence": "A link or reference that supports this claim."
    }
  ]
}
```

Save your CrowdWorks profile as `crowdworks-profile.json`:

```json
{
  "version": 1,
  "provider_employee_id": "123456789",
  "display_name": "Your name",
  "occupation": "Exact occupation label",
  "occupation_detail": {"id": "123456789", "label": "Exact detail label"},
  "status": "available",
  "hours_limit": "11-20",
  "min_hourly_wage": 2000,
  "max_hourly_wage": 3000,
  "web_meeting": "available",
  "simple_introduction": "Replace with a short introduction to your own work.",
  "introduction": "Replace with your own experience and the services you offer.",
  "job_categories": ["Exact job category label"],
  "skills": [
    {"name": "Python", "level": "3", "years": 3, "note": "Describe your own experience."}
  ]
}
```

Find your employee ID in the `/public/employees/…` link on your signed-in CrowdWorks
dashboard. Copy the occupation and job-category labels from your own official profile.
For `occupation_detail`, use the numeric value and label of your selected detail on the
official occupation form; do not guess the number or reuse the example ID.

The display name must be at most 12 characters. `hours_limit` accepts `0-10`, `11-20`,
`21-30`, `31-40`, or `41-`. Rates are positive integers in yen, with the minimum no higher
than the maximum. Use `available` or `not_available` for web meetings.
The application workflow currently supports skill durations `3` (1–3 years) and `5`
(5 years or more). Other truthful durations leave applications waiting for setup;
they do not prevent replies or paid-work setup.

`occupation_detail` is needed for applications; replies and paid work can be installed
without it. If your public profile has no avatar, add an `avatar_path` field pointing to
your own JPG or PNG, up to 3 MB. Relative paths are resolved from the JSON file's directory;
keep that image on your Mac after importing. An existing public avatar needs no local image.

Protect both input files before importing:

```bash
chmod 600 /absolute/path/to/work-profile.json /absolute/path/to/crowdworks-profile.json
```

## Install and sign in

From your Life Manager checkout:

```bash
./install.sh crowdworks install \
  --candidate-profile /absolute/path/to/work-profile.json \
  --provider-profile /absolute/path/to/crowdworks-profile.json
```

The installer prepares the Mac dependencies and asks you to sign in with ChatGPT when
needed. No separate OpenAI API key is required. It prepares the CrowdWorks browser;
open <https://crowdworks.jp/dashboard> in that window and sign in with your own account.
Complete any official verification, then rerun the same command.

The installer checks that the signed-in account matches your profile ID. It imports your
profiles privately and starts only workflows whose setup is complete. After activation,
the application workflow can update your public profile and submit applications using
the information you supplied. The installer itself only observes the account and profile.

| Workflow | Required setup |
|---|---|
| Browser | Mac runtime and browser setup |
| Applications | Work profile, matching account, occupation detail, supported skill durations, and an avatar |
| Replies and paid work | Work profile and matching account |
| Reports | Your Telegram destination and bot configuration |

Missing report settings or application details do not stop unrelated workflows.
Existing conflicting, damaged, or linked profile files are preserved; the output lists
the missing setup instead of replacing them. Imported profiles are stored under
`~/.config/anicca/job-search/` and `~/.config/anicca/crowdworks/` with private permissions.

For reports, add your own `TELEGRAM_BOT_TOKEN` to the Mac setup's environment file
(`~/.local/state/life-manager/.env` by default). Set `CROWDWORKS_REPORT_CHAT` to your own
destination in `~/.config/anicca/crowdworks/telegram.env`. Keep both files private with
`chmod 600`; preserve any other settings already in them. Rerun the installer after
setting these values. Reporting remains optional for the other workflows.

## Check progress

```bash
./install.sh crowdworks plan
./bin/lm-loop status crowdworks-revenue-application
./bin/lm-loop status crowdworks-revenue-reply
./bin/lm-loop status crowdworks-revenue-paid
```

`plan` checks local setup without signing in, changing files, or starting workflows.
It leaves the live account check outstanding. `setup_required` lists missing fields;
`waiting` means setup or release adoption is incomplete. Resolve the listed condition and
rerun the installer. A running workflow finishes its current work before release adoption.
To add missing fields after importing, edit your private
`~/.config/anicca/crowdworks/public-profile.json` (or
`~/.config/anicca/job-search/profile.json` for work facts), keep mode `600`, and rerun
`./install.sh crowdworks install` without import flags.

Installation does not prove a successful application, reply, delivery, payment, or sale.
Check the reported official CrowdWorks result. For keeping the Mac awake or stopping an
agent, use the [Mac setup guide](getting-started.md).
