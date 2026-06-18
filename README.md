# Life Manager

**Anicca phones you ~15 minutes before each calendar event and tells you to leave, so you arrive on time.** It reads your Google Calendar, auto-inserts travel-time blocks, asks by email when it doesn't know where an event is, and (with your approval) tells the people you're meeting if you're running late. The call is a real two-way conversation — Telnyx Call Control bridged to Gemini Live (native-audio, voice = Charon).

> One self-contained repo. Runs **local** (your keys) or **cloud** (managed keys, paid subscription). OpenClaw — or any scheduler — is just the executor.

日本語: 予定の約15分前に Anicca が電話をかけ、「そろそろ出て」と知らせて遅刻を防ぎます。カレンダーを読み、移動時間ブロックを自動挿入し、場所が不明なときはメールで質問し、遅れそうなら承認のうえ相手に連絡します。

## How it works
```
calendar ──▶ planner ──▶ schedule a call 15/10/5 min before EVERY event (escalating: calm→firm→harsh)
         └─▶ travel  ──▶ compare consecutive locations → insert 🚆 travel block with real transit time
                       └─▶ ask (email) when a location is unknown → your reply is written back
on departure: notify ──▶ not moved yet? → your approval → tell the people you're meeting
at call time: call   ──▶ Telnyx + Gemini Live (Charon) two-way phone call
```

## Install (into OpenClaw, the executor)
```bash
git clone https://github.com/Daisuke134/life-manager ~/life-manager
cd ~/life-manager/call/lib && npm i
cp ~/life-manager/.env.example ~/life-manager/.env   # then fill it in
```
Schedule it (OpenClaw is only an executor — no other dependency):
```bash
openclaw cron add --name life-plan --every 10m --tools exec \
  --message "Use exec to run: LIFE_ENV_FILE=$HOME/life-manager/.env node $HOME/life-manager/planner.js"
```

## Configuration
Everything is read from `.env` (or `LIFE_ENV_FILE`, or process.env) — see [`.env.example`](.env.example). State lives under `LIFE_DATA_DIR` (default `~/.life-manager`). **The code contains zero host-specific paths** — it runs anywhere.

| component | what it talks to (local) | what it talks to (cloud) |
|---|---|---|
| calendar / gmail | `gog` CLI | Composio OAuth |
| phone call | Telnyx + Gemini Live | Telnyx + Gemini Live |
| scheduler / executor | `openclaw` cron | server cron |
| keys | you hold them | managed (subscription) |

The local↔cloud difference is isolated to `adapters/transport.{js,py}` and your env — the life logic (planner/travel/ask/notify/call) is identical.

## Layout
```
config.{js,py}        self-contained config (env, data dir, profile, bins)
adapters/transport.*  calendar+gmail transport: gog (local) | composio (cloud)
planner.js            schedule calls before every event
travel/travel_fill.py location resolution + travel-block insertion
ask/ask-local.js      email the user when a location is unknown; write the reply back
notify/notify.js      late detection + stakeholder notification (with approval)
call/                 Telnyx ↔ Gemini Live (Charon) phone bridge
locate/locate.js      optional live-location motion gate
```

## License
MIT.
