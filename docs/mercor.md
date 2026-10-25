# Mercor on your Mac

[Get started](getting-started.md) · [Agent catalog](agents.md)

Use your own Mercor account to find suitable contracts and handle replies.
You need ChatGPT Plus or higher and a Mac that stays awake. Applications also need
a finalized resume PDF.
This setup is in development; a complete run on a separate clean Mac remains unverified.

## Prepare your work profile

An existing Job Hunter profile can be reused. Otherwise, save the following as
`mercor-profile.json` outside the checkout. Replace every example with your own
information. Compensation amounts are annual base salary in yen.

```json
{
  "version": 1,
  "candidate": {
    "name": "Your name",
    "application_email": "you@example.net",
    "target_role_families": ["Software engineering"],
    "location_preferences": ["Remote"],
    "compensation_floor_jpy": 4000000,
    "compensation_target_jpy": 5000000
  },
  "materials": {
    "resumes": {"engineering": "/absolute/path/to/your-resume.pdf"}
  },
  "facts": [
    {
      "id": "project-1",
      "claim": "Describe work you have actually done.",
      "evidence": "A link or reference supporting this claim."
    }
  ]
}
```

For reply-only setup, keep your name, application email, and verified facts;
the resume and application preferences are not required.

Use the same email as your Mercor account. Supply a real absolute path to your PDF
and evidence for your work claims. Protect the input file:

```bash
chmod 600 /absolute/path/to/mercor-profile.json
```

## Install and sign in

From your Life Manager checkout:

```bash
./install.sh mercor install --profile /absolute/path/to/mercor-profile.json
```

The installer prepares the Mac runtime and ChatGPT sign-in when needed. No separate
OpenAI API key is required. Sign in to <https://work.mercor.com/explore> in the
prepared Mercor browser, complete any official account requirements, then rerun
the command. The signed-in email must match your work profile.

Your profile and copied resume stay in private directories outside the checkout.
Existing conflicting or damaged settings are preserved and reported. To reuse an
imported profile, rerun `./install.sh mercor install` without `--profile`.

| Workflow | Required setup |
|---|---|
| Applications | Work facts, resume, ChatGPT sign-in, matching Mercor session, and Gmail authorization for that email |
| Replies | Work facts, matching Mercor session, Gmail authorization for that email, and Telegram settings |
| Paid work | Account binding is still pending; this workflow remains `setup_required` |

Authorize the email in your profile with `gog auth add YOUR_EMAIL --services gmail`.
Use your own Google OAuth client if `gog` requires one. For replies, save your own
`TELEGRAM_BOT_TOKEN` and `JOB_SEARCH_TELEGRAM_CHAT_ID` in
`~/.config/anicca/job-search/telegram.env` and set the file mode to `600`.
Missing settings leave the affected workflow waiting; they do not enable another account.

After activation, ready workflows can submit applications or send replies using the
information you supplied. The installer itself does not apply, reply, or deliver work.

## Check progress

```bash
./install.sh mercor plan
./bin/lm-loop status mercor-revenue-application
./bin/lm-loop status mercor-revenue-reply
./bin/lm-loop status mercor-revenue-paid
```

`plan` checks local inputs without changing files, signing in, or starting workflows.
Live account and Gmail checks remain outstanding until installation. Resolve the
listed missing setup and rerun the installer. An existing running workflow keeps
its current work until it can adopt the new release.

Installation does not prove a contract, delivery, or payment. Check the official
Mercor result. For keeping your Mac awake or stopping a workflow, use the
[Mac setup guide](getting-started.md).
