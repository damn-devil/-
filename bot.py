import json
import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ["BOT_TOKEN"]
DATA_FILE = "users.json"
ONLINE_TIMEOUT = 120  # seconds – inactivity timeout before marking offline

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class Tracker:
    def __init__(self, path: str):
        self.path = path
        self.data: dict = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path) as f:
                self.data = json.load(f)

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def register(self, user_id: int, name: str) -> bool:
        uid = str(user_id)
        if uid not in self.data:
            self.data[uid] = {"name": name, "online": False}
            self._save()
            return True
        return False

    def name(self, user_id: int) -> Optional[str]:
        u = self.data.get(str(user_id))
        return u["name"] if u else None

    def touch(self, user_id: int):
        uid = str(user_id)
        if uid in self.data:
            self.data[uid]["last_seen"] = datetime.now().isoformat()
            self._save()

    def is_online_now(self, user_id: int) -> bool:
        uid = str(user_id)
        if uid not in self.data:
            return False
        u = self.data[uid]
        if "last_seen" not in u:
            return False
        last = datetime.fromisoformat(u["last_seen"])
        return (datetime.now() - last).total_seconds() < ONLINE_TIMEOUT

    def set_online_flag(self, user_id: int, online: bool):
        uid = str(user_id)
        if uid in self.data:
            self.data[uid]["online"] = online
            self._save()

    def was_online(self, user_id: int) -> bool:
        return self.data.get(str(user_id), {}).get("online", False)

    def all(self):
        return [(int(k), v["name"]) for k, v in self.data.items()]


tracker = Tracker(DATA_FILE)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    existing = tracker.name(uid)
    if existing:
        await update.message.reply_text(f"Ты уже зарегистрирован как {existing}")
    else:
        await update.message.reply_text("Привет! Напиши своё имя, чтобы я запомнил тебя.")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    existing = tracker.name(uid)

    if existing:
        tracker.touch(uid)
        return

    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Пожалуйста, напиши своё имя.")
        return

    tracker.register(uid, text)
    tracker.touch(uid)
    await update.message.reply_text(
        f"Отлично, {text}! Теперь я буду оповещать других, когда ты онлайн."
    )


async def check_online(ctx: ContextTypes.DEFAULT_TYPE):
    changed = []
    for uid, name in tracker.all():
        now = tracker.is_online_now(uid)
        prev = tracker.was_online(uid)
        if now != prev:
            tracker.set_online_flag(uid, now)
            changed.append((uid, name, now))

    for uid, name, online in changed:
        status = "есть в наличии" if online else "нет в наличии"
        for other_uid, _ in tracker.all():
            if other_uid != uid:
                try:
                    await ctx.bot.send_message(
                        chat_id=other_uid, text=f"{name} {status}"
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить {other_uid}: {e}")


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.job_queue.run_repeating(check_online, interval=30, first=10)
    app.run_polling()


if __name__ == "__main__":
    main()
