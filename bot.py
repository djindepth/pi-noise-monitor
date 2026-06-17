import json
import os
import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ---------------------------------------------------------------------------
# Settings — replace with your bot token from BotFather
# ---------------------------------------------------------------------------
TOKEN    = "YOUR_TELEGRAM_BOT_TOKEN"
LOG_FILE = "/home/pi/noise_logs/events.json"

# Persists the authorized chat ID between restarts
CONFIG_FILE = "/home/pi/noisedetector/bot_config.json"

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def load_events():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE) as f:
        return json.load(f)

def is_authorized(update: Update) -> bool:
    cfg     = load_config()
    allowed = cfg.get("allowed_chat_id")
    if allowed is None:
        return True   # not locked yet — allow /start to register
    return update.effective_chat.id == allowed

# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg     = load_config()
    chat_id = update.effective_chat.id
    if "allowed_chat_id" not in cfg:
        cfg["allowed_chat_id"] = chat_id
        save_config(cfg)
        print(f"Bot locked to chat_id {chat_id}")
        await update.message.reply_text(
            "✅ NoiseDetector bot activated!\n"
            "You are now the only authorized user.\n\n"
            "Try /status or /help."
        )
    elif cfg["allowed_chat_id"] == chat_id:
        await update.message.reply_text("Already registered. Try /status or /help.")
    else:
        await update.message.reply_text("Unauthorized.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return

    events      = load_events()
    today       = datetime.date.today().strftime("%Y-%m-%d")
    today_events = [e for e in events if e["timestamp"].startswith(today)]
    last        = events[-1] if events else None

    lines = ["✅ Pi is online"]
    lines.append(f"📊 Today: {len(today_events)} event{'s' if len(today_events) != 1 else ''}")
    if last:
        dt    = datetime.datetime.strptime(last["timestamp"], "%Y-%m-%d %H:%M:%S")
        label = dt.strftime("%b %-d, %H:%M")
        lines.append(f"🔊 Last event: {label} ({last['peak_db']} dB)")

    await update.message.reply_text("\n".join(lines))


async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return

    events       = load_events()
    today        = datetime.date.today().strftime("%Y-%m-%d")
    today_events = [e for e in events if e["timestamp"].startswith(today)]

    if not today_events:
        await update.message.reply_text("No events today 🔇")
        return

    lines = [f"📋 Today's events ({len(today_events)} total):"]
    for e in today_events[-25:]:
        lines.append(f"  {e['timestamp'][11:16]}  {e['peak_db']} dB")
    if len(today_events) > 25:
        lines.append(f"  …and {len(today_events) - 25} earlier")

    await update.message.reply_text("\n".join(lines))


async def yesterday_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return

    events      = load_events()
    yesterday   = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    yest_events = [e for e in events if e["timestamp"].startswith(yesterday)]

    if not yest_events:
        await update.message.reply_text("No events yesterday 🔇")
        return

    lines = [f"📋 Yesterday's events ({len(yest_events)} total):"]
    for e in yest_events[-25:]:
        lines.append(f"  {e['timestamp'][11:16]}  {e['peak_db']} dB")
    if len(yest_events) > 25:
        lines.append(f"  …and {len(yest_events) - 25} earlier")

    await update.message.reply_text("\n".join(lines))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text(
        "NoiseDetector commands:\n\n"
        "/status — Pi health + today's event count\n"
        "/today — list today's events\n"
        "/yesterday — list yesterday's events\n"
        "/help — this message"
    )

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("status",    status))
    app.add_handler(CommandHandler("today",     today_cmd))
    app.add_handler(CommandHandler("yesterday", yesterday_cmd))
    app.add_handler(CommandHandler("help",      help_cmd))
    print("NoiseDetector bot started.")
    app.run_polling()

if __name__ == "__main__":
    main()
