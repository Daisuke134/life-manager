---
name: life-manager
description: Reads your Google Calendar and phones you ~15 minutes before each event (Telnyx + Gemini Live, voice = Charon) telling you to leave so you arrive on time. Auto-inserts travel-time blocks, asks by email when a location is unknown, and notifies stakeholders (with your approval) if you're running late. Use when the user mentions life manager, wake-up calls, calendar reminders, never being late, travel time, or scheduling calls before events.
---

# Life Manager

A self-contained skill that runs your day so you're never late. It works the same locally (your own keys) or in the cloud (managed keys, paid subscription) — the ONLY difference is the calendar/gmail transport (local = `gog` CLI, cloud = Composio) and who holds the API keys.

## What it does
| part | behaviour |
|---|---|
| **planner** | lists your calendar and schedules a Charon phone call 15 / 10 / 5 min before EVERY event, escalating tone (calm → firm → harsh) |
| **travel** | compares consecutive events' locations and auto-inserts a `🚆 移動` travel block with the real transit time |
| **ask** | when an event's location is unknown, emails you the question and writes your reply back onto the event |
| **notify** | if you haven't left by departure time, asks your approval then notifies the people you're meeting |
| **call** | the real two-way phone call (Telnyx Call Control + Gemini Live native-audio, voice = Charon) |

## Install (OpenClaw — the executor)
```bash
git clone https://github.com/Daisuke134/life-manager ~/life-manager
cd ~/life-manager/call/lib && npm i          # the call bridge needs `ws`
cp ~/life-manager/.env.example ~/life-manager/.env   # fill it in
```
Then point your scheduler at it (OpenClaw is just an executor):
```bash
openclaw cron add --name life-plan --every 10m --tools exec \
  --message "Use exec to run: LIFE_ENV_FILE=$HOME/life-manager/.env node $HOME/life-manager/planner.js"
```

## Config
All config comes from `.env` / `LIFE_ENV_FILE` / process.env (see `.env.example`). No dependency on any host runtime — state lives under `LIFE_DATA_DIR` (default `~/.life-manager`).

## Local vs cloud
- **Local**: you hold the keys, `gog` talks to your Google account, `openclaw` runs the calls.
- **Cloud**: managed keys, Composio talks to your Google account via OAuth, the server runs the calls — pay a subscription, manage your life from anywhere.
