#!/usr/bin/env python3
"""Anicca Telegram bot — Live Location sink + Phase 2 onboarding chat.

What it does:
  /start  → start Phase 2 onboarding (name → phone → gcal OAuth →
            Live Location share → optional payout destination)
  /where  → debug: tell the user what location Anicca knows
  /stop   → forget the user's location until they share again
  any user shares Live Location → save lat/lon every 1-5 sec to
      $ANICCA_HOME/state/location/<telegram_user_id>.json
      (lateness_check.get_location() reads it)

Onboarding answers are merged into $ANICCA_HOME/identity/profile.json
(= the same file every other skill reads).

Copied from python-telegram-bot v21 official patterns.
"""
import json
import logging
import os
import re
import time
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from investment_status import build_investment_reply

LIFE_MANAGER_HOME = Path(os.environ.get(
    "LIFE_MANAGER_HOME", str(Path.home() / ".local" / "state" / "life-manager"),
))
ANICCA_HOME = Path(os.environ.get("ANICCA_HOME", str(LIFE_MANAGER_HOME)))
ENV_PATH = ANICCA_HOME / ".env"
PROFILE_PATH = ANICCA_HOME / "identity" / "profile.json"
ONBOARDING_STATE_PATH = ANICCA_HOME / "state" / "onboarding.json"

# Load TELEGRAM_BOT_TOKEN from the env file
for line in ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []:
    if line.startswith("TELEGRAM_BOT_TOKEN="):
        os.environ["TELEGRAM_BOT_TOKEN"] = (
            line.split("=", 1)[1].strip().strip('"').strip("'")
        )
        break

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise SystemExit(
        f"TELEGRAM_BOT_TOKEN not in {ENV_PATH} — "
        "create a bot via @BotFather first."
    )

for line in ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []:
    if line.startswith("NEXT_PUBLIC_STRIPE_LM_URL="):
        os.environ["NEXT_PUBLIC_STRIPE_LM_URL"] = (
            line.split("=", 1)[1].strip().strip('"').strip("'")
        )
        break

# Live Stripe Payment Link for the $29/mo Anicca Life Manager subscription
# (price_1TjytgEeDsUAcaLSFDgoYqyL). Falls back to the known-live link if the
# env var is missing or still points at a test-mode link.
STRIPE_LM_URL = os.environ.get("NEXT_PUBLIC_STRIPE_LM_URL", "")
if "buy.stripe.com/test_" in STRIPE_LM_URL or not STRIPE_LM_URL:
    STRIPE_LM_URL = "https://buy.stripe.com/cNifZhgcC3h44yYeMK2880X"

STATE_DIR = ANICCA_HOME / "state" / "location"
STATE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("anicca-bot")


# ─── onboarding helpers ──────────────────────────────────────────────────


def _load_onboarding():
    try:
        return json.loads(ONBOARDING_STATE_PATH.read_text())
    except Exception:
        return {}


def _save_onboarding(s):
    ONBOARDING_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ONBOARDING_STATE_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=2))


def _patch_profile(updates):
    """Merge `updates` (dot-paths → values) into profile.json."""
    try:
        prof = json.loads(PROFILE_PATH.read_text())
    except Exception:
        prof = {}
    for dotpath, value in updates.items():
        parts = dotpath.split(".")
        node = prof
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(prof, ensure_ascii=False, indent=2))


# ─── command handlers ────────────────────────────────────────────────────


async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    """Phase 2 onboarding entrypoint."""
    user = update.effective_user
    state = _load_onboarding()
    state.setdefault(str(user.id), {})["step"] = "ask_name"
    _save_onboarding(state)
    await update.message.reply_text(
        f"Hi {user.first_name}! I'm Anicca — I watch your calendar and "
        "call you when you're running late, then mail your stakeholders "
        "for you. $29/mo, cancel anytime — ready whenever you are, no "
        "setup required first:\n\n"
        f"{STRIPE_LM_URL}\n\n"
        "Want the full setup (calls + auto-mail) instead of just "
        "browsing? Keep chatting here — ~2 min: name → phone → calendar "
        "link (optional) → location share (optional) → payout pick "
        "(optional). Reply 'skip' on any optional step — you can always "
        "finish it later with /connect or /payout.\n\n"
        "First: what name should I call you in calls and emails?"
    )


def save_location(user_id: int, location, msg_date) -> None:
    """Write the latest Live Location fix to disk."""
    record = {
        "user_id": user_id,
        "lat": location.latitude,
        "lon": location.longitude,
        "tst": int(msg_date.timestamp()) if msg_date else int(time.time()),
        "accuracy_m": location.horizontal_accuracy,
        "heading": location.heading,
        "live_period": location.live_period,
        "received_at": int(time.time()),
    }
    out = STATE_DIR / f"{user_id}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    log.info(
        "saved location user=%s lat=%.5f lon=%.5f acc=%sm",
        user_id, record["lat"], record["lon"], record["accuracy_m"],
    )


async def on_location(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    """Save first-message location silently."""
    msg = update.effective_message
    if not msg or not msg.location:
        return
    save_location(update.effective_user.id, msg.location, msg.date)


async def on_edited_location(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    """Live-location updates arrive every 1-5s as edited_message."""
    msg = update.edited_message
    if not msg or not msg.location:
        return
    save_location(update.effective_user.id, msg.location, msg.edit_date or msg.date)


async def cmd_stop(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    """Manual disconnect."""
    user_id = update.effective_user.id
    f = STATE_DIR / f"{user_id}.json"
    if f.exists():
        f.unlink()
    await update.message.reply_text(
        "Stopped. Your location file was deleted. Share Live Location "
        "again any time to resume."
    )


async def cmd_where(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    """Debug — show what location Anicca knows."""
    user_id = update.effective_user.id
    f = STATE_DIR / f"{user_id}.json"
    if not f.exists():
        await update.message.reply_text(
            "I don't know where you are yet. Share your Live Location first."
        )
        return
    r = json.loads(f.read_text())
    age = int(time.time() - r["received_at"])
    await update.message.reply_text(
        f"Last fix:\n"
        f"  lat: {r['lat']:.5f}\n"
        f"  lon: {r['lon']:.5f}\n"
        f"  accuracy: {r['accuracy_m']}m\n"
        f"  age: {age} sec"
    )


async def cmd_help(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    """List every command the bot understands."""
    await update.message.reply_text(
        "Commands:\n"
        "  /start    begin (or resume) onboarding\n"
        "  /where    show what location I currently know\n"
        "  /status   show daemon + cron health\n"
        "  /invest   show investment setup and loop status\n"
        "  /subscribe  get the $29/mo checkout link\n"
        "  /connect  link Google Calendar/Gmail (if you skipped it)\n"
        "  /payout   set or change your payout destination\n"
        "  /reset    clear your onboarding state to start over\n"
        "  /stop     forget your location\n"
        "  /help     this message"
    )


async def cmd_invest(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    """Show the truthful local investment onboarding/runtime state."""
    reply = build_investment_reply(LIFE_MANAGER_HOME)
    markup = reply.get("reply_markup")
    if markup:
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(**button) for button in row]
            for row in markup["inline_keyboard"]
        ])
    await update.message.reply_text(reply["text"], reply_markup=markup)


async def on_invest_callback(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    """Close the optional signup prompt without creating account state."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Investment Loop\n\n今回は開始しません。準備できたら /invest を送ってください。"
    )


async def cmd_status(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    """Quick health snapshot — daemons + last call time + wallet status."""
    msg_lines = ["🩺 Anicca status\n"]
    # Location freshness
    f = STATE_DIR / f"{update.effective_user.id}.json"
    if f.exists():
        r = json.loads(f.read_text())
        age = int(time.time() - r["received_at"])
        msg_lines.append(f"📍 Location: fresh {age}s ago")
    else:
        msg_lines.append("📍 Location: not shared yet")
    # Last lateness call
    log_path = ANICCA_HOME / "skills" / "anicca-life-manager" / "state" / "run.log"
    last_call = None
    if log_path.exists():
        for line in reversed(log_path.read_text(errors="ignore").splitlines()):
            if "placed lateness call sid=" in line:
                last_call = line[-60:]
                break
    if last_call:
        msg_lines.append(f"📞 Last call: {last_call}")
    else:
        msg_lines.append("📞 Last call: none yet today")
    # Profile completeness
    try:
        prof = json.loads(PROFILE_PATH.read_text())
        completed = sum(1 for k in ("identity.name", "identity.phone",
                                    "identity.googleAccount")
                        if _get_dot(prof, k))
        msg_lines.append(f"👤 Profile: {completed}/3 onboarding answers filled")
    except Exception:
        msg_lines.append("👤 Profile: not yet created")
    await update.message.reply_text("\n".join(msg_lines))


def _get_dot(d, dotpath):
    node = d
    for p in dotpath.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(p)
    return node


async def cmd_subscribe(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    """Send the live Stripe checkout link for the $29/mo LM plan."""
    await update.message.reply_text(
        "Anicca Life Manager — $29/mo, cancel anytime. Calls you, mails "
        "your stakeholders when you're late, watches your calendar:\n\n"
        f"{STRIPE_LM_URL}"
    )


async def cmd_connect(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    """Re-prompt for Google Calendar/Gmail linking at any time (after a skip)."""
    state = _load_onboarding()
    state.setdefault(str(update.effective_user.id), {})["step"] = "oauth_link"
    _save_onboarding(state)
    await update.message.reply_text(
        "Let's link Google Calendar and Gmail now.\n\n"
        "On your laptop, run:\n\n"
        "    gog auth login\n\n"
        "A browser opens, sign in, then paste the account email "
        "back here so I can pin it."
    )


async def cmd_payout(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    """Re-prompt for payout destination at any time."""
    state = _load_onboarding()
    state.setdefault(str(update.effective_user.id), {})["step"] = "ask_payout"
    _save_onboarding(state)
    await update.message.reply_text(
        "Pick a payout destination (= where I send your 10% share):\n\n"
        "  1) Stripe Connect Express (Japan bank, T+3-5d)\n"
        "  2) Wise (same-day Zengin)\n"
        "  3) Crypto wallet (paste a 0x address)\n"
        "  4) Skip — decide later\n\n"
        "Reply 1 / 2 / 3 / 4."
    )


async def cmd_reset(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    """Clear onboarding state to restart."""
    state = _load_onboarding()
    state.pop(str(update.effective_user.id), None)
    _save_onboarding(state)
    await update.message.reply_text(
        "Onboarding state cleared. Send /start to restart."
    )


# ─── onboarding state machine for plain-text replies ─────────────────────


async def on_text(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    """Drive the Phase 2 onboarding state machine on non-command text."""
    msg = update.effective_message
    if not msg or not msg.text:
        return
    user = update.effective_user
    state = _load_onboarding()
    user_state = state.get(str(user.id), {})
    step = user_state.get("step", "greet")
    txt = msg.text.strip()

    if step == "ask_name":
        _patch_profile({"identity.name": txt})
        user_state["step"] = "ask_phone"
        _save_onboarding(state)
        await msg.reply_text(
            f"Got it, {txt}. Next: your phone number with country code "
            "(e.g. +81 80 0000 0000). This is the number I will call."
        )
        return

    if step == "ask_phone":
        phone = re.sub(r"[^\d+]", "", txt)
        _patch_profile({"identity.phone": phone, "contact.phone": phone})
        user_state["step"] = "oauth_link"
        _save_onboarding(state)
        await msg.reply_text(
            "Saved. Next up is Google Calendar + Gmail (= your schedule "
            "and apology mails when you're late) — self-serve connect for "
            "this is coming very soon.\n\n"
            "Reply 'skip' for now (recommended) and I'll mail you the "
            "connect link the moment it's ready — everything else "
            "(the calls, the subscription) works without it today."
        )
        return

    if step == "oauth_link":
        if txt.lower().strip() in ("skip", "later", "no laptop"):
            _patch_profile({"identity.googleAccount": None})
            user_state["step"] = "ask_location_share"
            user_state["oauth_skipped"] = True
            _save_onboarding(state)
            await msg.reply_text(
                "No problem — continuing without calendar for now. "
                "Send /connect any time once you're at a laptop.\n\n"
                "Last required step: share your Live Location.\n\n"
                " 1. Tap the paperclip 📎 (bottom-left of this chat)\n"
                " 2. Tap 'Location'\n"
                " 3. Tap 'Share My Live Location for...'\n"
                " 4. Pick 'until I turn off' (or 8 hours)\n\n"
                "Send me 'done' once you have shared, or 'skip' to do this "
                "later."
            )
            return
        if "@" not in txt:
            await msg.reply_text(
                "That doesn't look like an email. Paste the Google "
                "account you used (e.g. person@example.com), or reply "
                "'skip' to do this later."
            )
            return
        _patch_profile({"identity.googleAccount": txt,
                        "contact.personalEmail": txt})
        user_state["step"] = "ask_location_share"
        _save_onboarding(state)
        await msg.reply_text(
            "Linked. Last required step: share your Live Location.\n\n"
            " 1. Tap the paperclip 📎 (bottom-left of this chat)\n"
            " 2. Tap 'Location'\n"
            " 3. Tap 'Share My Live Location for...'\n"
            " 4. Pick 'until I turn off' (or 8 hours)\n\n"
            "Send me 'done' once you have shared, or 'skip' to do this "
            "later."
        )
        return

    if step == "ask_location_share":
        if txt.lower().strip() in ("skip", "later", "no"):
            user_state["step"] = "ask_payout"
            user_state["location_skipped"] = True
            _save_onboarding(state)
            await msg.reply_text(
                "No problem — you can share it any time by tapping 📎 → "
                "Location → Share My Live Location.\n\n"
                "Optional last question: when I earn money I send you 10%. "
                "Where do I send it?\n\n"
                "  1) Stripe Connect Express (Japan bank, T+3-5d, 5min KYC)\n"
                "  2) Wise (same-day Zengin, light KYC)\n"
                "  3) Crypto wallet (paste a 0x address, instant USDC)\n"
                "  4) Skip — decide later\n\n"
                "Reply 1 / 2 / 3 / 4."
            )
            return
        loc_file = STATE_DIR / f"{user.id}.json"
        if not loc_file.exists():
            await msg.reply_text(
                "I don't see your live location yet — tap 📎 → Location → "
                "Share My Live Location, then send 'done'. Or reply 'skip' "
                "to do this later and keep setting up the rest."
            )
            return
        user_state["step"] = "ask_payout"
        _save_onboarding(state)
        await msg.reply_text(
            "Got your location. ✓\n\n"
            "Optional last question: when I earn money I send you 10%. "
            "Where do I send it?\n\n"
            "  1) Stripe Connect Express (Japan bank, T+3-5d, 5min KYC)\n"
            "  2) Wise (same-day Zengin, light KYC)\n"
            "  3) Crypto wallet (paste a 0x address, instant USDC)\n"
            "  4) Skip — decide later\n\n"
            "Reply 1 / 2 / 3 / 4."
        )
        return

    if step == "ask_payout":
        choice = txt.lower().strip()
        broker_state_path = (
            ANICCA_HOME / "skills" / "anicca-fuel-broker" / "state" / "broker.json"
        )
        try:
            broker = json.loads(broker_state_path.read_text())
        except Exception:
            broker = {}
        if choice in ("1", "stripe"):
            broker["payout_destination"] = "stripe_connect"
            reply = (
                "Stripe Connect Express picked. I'll mail you the KYC "
                "link when wallet > 3 mo runtime."
            )
        elif choice in ("2", "wise"):
            broker["payout_destination"] = "wise"
            reply = "Wise picked. I'll mail you the signup link when ready."
        elif (choice in ("3", "wallet", "crypto")) or txt.startswith("0x"):
            if txt.startswith("0x") and len(txt) >= 42:
                broker["payout_destination"] = txt[:42]
                reply = (
                    f"Wallet {txt[:10]}… pinned. I'll send USDC there "
                    "when ready."
                )
            else:
                await msg.reply_text(
                    "Paste a 0x... address on the next line (Base mainnet)."
                )
                return
        else:
            broker["payout_destination"] = None
            reply = "OK, no payout destination set. /payout later when you decide."
        broker_state_path.parent.mkdir(parents=True, exist_ok=True)
        broker_state_path.write_text(json.dumps(broker, ensure_ascii=False, indent=2))
        user_state["step"] = "done"
        _save_onboarding(state)
        await msg.reply_text(
            reply + "\n\n"
            "Onboarding complete. ✅\n"
            "I watch your calendar and call when it is time. "
            "/where to debug, /stop to disconnect."
        )
        await msg.reply_text(
            "One more thing — I only actually call you and mail your "
            "stakeholders on the paid plan ($29/mo, cancel anytime):\n\n"
            f"{STRIPE_LM_URL}\n\n"
            "Subscribe now and I'll start watching your calendar today. "
            "/subscribe any time to get this link again."
        )
        return

    # Outside the state machine — friendly nudge
    await msg.reply_text(
        "Send /start to begin onboarding, or /where to see what I know."
    )


# ─── main ────────────────────────────────────────────────────────────────


def main() -> None:
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("where", cmd_where))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("invest", cmd_invest))
    app.add_handler(CallbackQueryHandler(on_invest_callback, pattern=r"^invest:later$"))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("connect", cmd_connect))
    app.add_handler(CommandHandler("payout", cmd_payout))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.LOCATION, on_location))
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, on_edited_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    log.info("Anicca bot starting (long polling)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
