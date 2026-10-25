# apps/life-manager

This package contains Life Manager's current calendar-and-commute workflow and
Telegram transport. That is one capability within the broader Life Manager
product, which is being built around one shared core for Local and phone-first
Cloud use. Life Manager Cloud targets one isolated, always-on VM per customer.
Its first earning workflow is Capafy; the complete work-to-verified-result and
email-report path still needs end-to-end proof. Cloud sign-in uses Google, and
Google Calendar is optional rather than an onboarding requirement. Grok Bot,
Muse, and Dots still need verified adapters to that same manager.

This package's current workflow calls when it is time to leave, sends the route
once the user is out the door, and asks before telling anyone the user is late.
It does not by itself represent the complete Life Manager product or its Cloud
runtime. The public product entry is `/lm` on Netlify. The Cloud onboarding and
tenant manager run on the existing Railway `life-call` service and should be
served through Netlify same-origin `/maritime` and Google OAuth proxy routes, so
the customer stays on `aniccaai.com`. `LM_MARITIME_WEB_ORIGIN=https://aniccaai.com`
and the Supabase callback allowlist are required before that route can work in
production. Until those host settings and deployment are read back, the live
app still uses the Railway URL directly.

## Read this before you change anything

| You are working on | Read |
|---|---|
| Current TODO order, Local/Cloud recovery and deployment | [Unified SSOT](../../docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md), especially CLD04 for deployment and runtime verification |
| ★ daily organ — wake calls, travel blocks, live location, route, late notice ★ | `docs/superpowers/specs/2026-08-01-lm-daily-organ-design.md` — background design |
| platform (finance, marketing, runtime migration, panel) | `docs/superpowers/specs/2026-07-29-life-manager-finance-marketing-platform-design.md` |

This repository (`Daisuke134/life-manager`) is canonical. External copies of
these specs are not sources of truth.
Runtime state and the single-user BYOK build live under the portable state home
`${LIFE_MANAGER_STATE_HOME:-${XDG_STATE_HOME:-$HOME/.local/state}/life-manager}`;
they are not production source.

## Where the daily behavior lives

| File | Role |
|---|---|
| `scheduler.js` | the 60s loop: escalating wakes at T-15/10/5, 6h horizon |
| `lib/wake-filter.js` | which events deserve a call at all |
| `lib/travel.js` | writes the `[Travel]` blocks into the calendar |
| `lib/late-notice.js` | late detection, attendee notice, live-location teardown |
| `lib/slash-command.js` | Telegram command router |

## Reading live state

Credentials come from `${LIFE_MANAGER_STATE_HOME:-${XDG_STATE_HOME:-$HOME/.local/state}/life-manager}/.env` (`SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`). Never echo them.

```bash
LIFE_MANAGER_STATE_HOME="${LIFE_MANAGER_STATE_HOME:-${XDG_STATE_HOME:-$HOME/.local/state}/life-manager}"
set -a; . "$LIFE_MANAGER_STATE_HOME/.env"; set +a
curl -s "$SUPABASE_URL/rest/v1/lm_wake_log?select=*&order=id.desc&limit=3" \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY"
```

Tables: `lm_users`, `lm_wake_log`, `lm_travel_log`, `lm_ask_log`,
`lm_user_locations`.

**Location freshness is `lm_user_locations.observed_at`.** `updated_at` is not
maintained by the upsert, so reading it reports a live feed as dead.
