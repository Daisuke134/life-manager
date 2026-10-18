#!/usr/bin/env python3
"""tg_user.py — read + post Telegram as a USER (MTProto/Telethon), not a bot.

WHY: a bot token (openclaw's telegram channel, TELEGRAM_BOT_TOKEN) is structurally
send-only + read-NEW-incoming-only — it can NOT read a chat's history or its own
outgoing messages (core.telegram.org/bots/api; docs.telethon.dev botapi-vs-mtproto).
To verify that loop reports actually landed in Dais's chat, and to read the chat like
Dais does, we need a MTProto USER session. This is that sidecar.

CONFIG (never printed): ~/.cloak/telegram-user.json = {"api_id":int,"api_hash":str,"session":str}
  api_id/api_hash come from https://my.telegram.org (API development tools). The "session"
  is a Telethon StringSession minted ONCE by `login` (phone + 5-digit code, +2FA if set);
  after that every read/send is zero-human-input.

USAGE:
  tg_user.py login                       # one-time: prompts phone + code, saves StringSession
  tg_user.py dialogs [limit]             # list recent conversations (find the right entity)
  tg_user.py read <entity> [limit]       # read history (entity = 'me' | @username | chat_id)
  tg_user.py window <entity> <start> <end>  # every message in an RFC3339 window + complete flag
  tg_user.py send <entity> <text>        # post a message
Reads emit JSON to stdout. Secrets are never printed.
"""
import asyncio, json, os, sys

CFG_PATH = os.path.expanduser("~/.cloak/telegram-user.json")


def _load_cfg():
    if not os.path.exists(CFG_PATH):
        return {}
    try:
        return json.load(open(CFG_PATH))
    except Exception:
        return {}


def _save_cfg(cfg):
    os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
    tmp = CFG_PATH + ".tmp"
    json.dump(cfg, open(tmp, "w"))
    os.chmod(tmp, 0o600)
    os.replace(tmp, CFG_PATH)


def _creds(cfg):
    api_id = cfg.get("api_id") or os.environ.get("TG_USER_API_ID")
    api_hash = cfg.get("api_hash") or os.environ.get("TG_USER_API_HASH")
    if not api_id or not api_hash:
        print(json.dumps({"ok": False, "error": "no api_id/api_hash — get them from "
              "https://my.telegram.org and put in " + CFG_PATH}), file=sys.stderr)
        sys.exit(2)
    return int(api_id), str(api_hash)


def _entity(e):
    # numeric chat/user id vs @username vs 'me'
    if e in ("me", "self"):
        return "me"
    try:
        return int(e)
    except ValueError:
        return e


async def _resolve(cl, entity):
    # Telethon cannot resolve a raw numeric peer id unless its access_hash is cached.
    # Warming get_dialogs() populates that cache so read/send by chat_id just works.
    ent = _entity(entity)
    if isinstance(ent, int):
        try:
            return await cl.get_entity(ent)
        except (ValueError, TypeError):
            async for d in cl.iter_dialogs():
                if d.id == ent:
                    return d.entity
            raise
    return ent


async def _client(cfg, require_session=True):
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    api_id, api_hash = _creds(cfg)
    sess = cfg.get("session") or ""
    if require_session and not sess:
        print(json.dumps({"ok": False, "error": "no session — run: tg_user.py login"}), file=sys.stderr)
        sys.exit(3)
    return TelegramClient(StringSession(sess), api_id, api_hash)


async def cmd_login(cfg):
    from telethon.sessions import StringSession
    cl = await _client(cfg, require_session=False)
    await cl.start()  # interactive: prompts phone + code (+2FA) on first run
    cfg["session"] = StringSession.save(cl.session)
    _save_cfg(cfg)
    me = await cl.get_me()
    await cl.disconnect()
    print(json.dumps({"ok": True, "logged_in_as": getattr(me, "username", None) or me.id,
                      "session_saved": CFG_PATH}))


async def cmd_login_send(cfg, phone):
    # Step 1 of headless login: request the code. Telegram delivers a 5-digit code to the
    # user's existing Telegram app. Persist the intermediate session + phone_code_hash so
    # step 2 (login-code) can complete sign_in in a separate process.
    from telethon.sessions import StringSession
    cl = await _client(cfg, require_session=False)
    await cl.connect()
    sent = await cl.send_code_request(phone)
    cfg["session"] = StringSession.save(cl.session)
    cfg["_login_phone"] = phone
    cfg["_login_code_hash"] = sent.phone_code_hash
    _save_cfg(cfg)
    await cl.disconnect()
    print(json.dumps({"ok": True, "code_sent_to": phone,
                      "next": "relay the 5-digit code -> tg_user.py login-code <code>"}))


async def cmd_login_code(cfg, code, password=None):
    # Step 2: complete sign_in with the relayed code (+2FA password if the account has one).
    from telethon.sessions import StringSession
    from telethon.errors import SessionPasswordNeededError
    phone = cfg.get("_login_phone"); code_hash = cfg.get("_login_code_hash")
    if not phone or not code_hash:
        print(json.dumps({"ok": False, "error": "run login-send <phone> first"}), file=sys.stderr)
        sys.exit(3)
    cl = await _client(cfg, require_session=True)  # loads intermediate session from login-send
    await cl.connect()
    try:
        await cl.sign_in(phone=phone, code=str(code), phone_code_hash=code_hash)
    except SessionPasswordNeededError:
        if not password:
            await cl.disconnect()
            print(json.dumps({"ok": False, "need_2fa": True,
                              "error": "account has 2FA — run: login-code <code> <2fa_password>"}), file=sys.stderr)
            sys.exit(4)
        await cl.sign_in(password=password)
    cfg["session"] = StringSession.save(cl.session)
    cfg.pop("_login_phone", None); cfg.pop("_login_code_hash", None)
    _save_cfg(cfg)
    me = await cl.get_me()
    await cl.disconnect()
    print(json.dumps({"ok": True, "logged_in_as": getattr(me, "username", None) or me.id,
                      "session_saved": CFG_PATH}))


async def cmd_dialogs(cfg, limit):
    cl = await _client(cfg)
    await cl.connect()
    out = []
    async for d in cl.iter_dialogs(limit=limit):
        out.append({"id": d.id, "name": d.name, "is_user": d.is_user,
                    "is_group": d.is_group, "unread": d.unread_count})
    await cl.disconnect()
    print(json.dumps({"ok": True, "dialogs": out}, ensure_ascii=False))


async def cmd_read(cfg, entity, limit):
    cl = await _client(cfg)
    await cl.connect()
    msgs = await cl.get_messages(await _resolve(cl, entity), limit=limit)
    out = [{"id": m.id, "date": m.date.isoformat() if m.date else None,
            "sender_id": m.sender_id, "out": bool(m.out), "text": (m.raw_text or "")[:500]}
           for m in msgs]
    await cl.disconnect()
    print(json.dumps({"ok": True, "entity": entity, "count": len(out), "messages": out}, ensure_ascii=False))


async def cmd_window(cfg, entity, start, end, cap=2000):
    # Every message after `start` (exclusive) up to `end`, oldest first, all pages.
    # complete=True only once history is proven read past `end` (a later message, or
    # the end of history with `end` already in the past) and the cap was not hit.
    from datetime import datetime, timezone
    since = datetime.fromisoformat(start.replace("Z", "+00:00"))
    until = datetime.fromisoformat(end.replace("Z", "+00:00"))
    cl = await _client(cfg)
    await cl.connect()
    out, complete = [], False
    async for m in cl.iter_messages(await _resolve(cl, entity), offset_date=since, reverse=True):
        if m.date > until:
            complete = True
            break
        if len(out) >= cap:
            break
        out.append({"id": m.id, "date": m.date.isoformat(), "sender_id": m.sender_id,
                    "out": bool(m.out), "text": m.raw_text or ""})
    else:
        complete = until < datetime.now(timezone.utc)
    await cl.disconnect()
    print(json.dumps({"ok": True, "entity": entity, "start": start, "end": end,
                      "complete": complete, "count": len(out), "messages": out}, ensure_ascii=False))


async def cmd_send(cfg, entity, text):
    cl = await _client(cfg)
    await cl.connect()
    m = await cl.send_message(await _resolve(cl, entity), text)
    await cl.disconnect()
    print(json.dumps({"ok": True, "sent_id": m.id, "entity": entity}))


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1]
    cfg = _load_cfg()
    if cmd == "login":
        asyncio.run(cmd_login(cfg))
    elif cmd == "login-send":
        if len(sys.argv) < 3:
            print("usage: tg_user.py login-send <phone>"); sys.exit(1)
        asyncio.run(cmd_login_send(cfg, sys.argv[2]))
    elif cmd == "login-code":
        if len(sys.argv) < 3:
            print("usage: tg_user.py login-code <code> [2fa_password]"); sys.exit(1)
        pw = sys.argv[3] if len(sys.argv) > 3 else None
        asyncio.run(cmd_login_code(cfg, sys.argv[2], pw))
    elif cmd == "dialogs":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        asyncio.run(cmd_dialogs(cfg, limit))
    elif cmd == "read":
        if len(sys.argv) < 3:
            print("usage: tg_user.py read <entity> [limit]"); sys.exit(1)
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        asyncio.run(cmd_read(cfg, sys.argv[2], limit))
    elif cmd == "window":
        if len(sys.argv) < 5:
            print("usage: tg_user.py window <entity> <start_iso> <end_iso>"); sys.exit(1)
        asyncio.run(cmd_window(cfg, sys.argv[2], sys.argv[3], sys.argv[4]))
    elif cmd == "send":
        if len(sys.argv) < 4:
            print("usage: tg_user.py send <entity> <text>"); sys.exit(1)
        asyncio.run(cmd_send(cfg, sys.argv[2], sys.argv[3]))
    else:
        print(f"unknown command: {cmd}"); print(__doc__); sys.exit(1)


if __name__ == "__main__":
    main()
