import logging
import os

from dotenv import load_dotenv
from telegram import Bot, BotCommand, Message, MessageOrigin, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegramify_markdown import markdownify

import agent
import message_db
import store
from utils import should_reply

logging.basicConfig(format="[%(levelname)s] %(message)s", level=logging.WARNING)
logger = logging.getLogger(__name__)
load_dotenv()


def format_message(message: Message) -> str:
    if not getattr(message, "text"):
        return ""
    text = message.text
    sender = message.from_user.first_name

    if message.forward_origin:
        if message.forward_origin.type in [MessageOrigin.CHANNEL, MessageOrigin.CHAT]:
            origin = message.forward_origin.chat.title
        else:
            origin = message.forward_origin.sender_user_name
        sender += f" (Forward from {origin})"
    if message.reply_to_message:
        text += f"\n(Reply to {format_message(message.reply_to_message)})"
    return f"{sender}: {text}"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await message_db.save_message(update.message)
    return
    text = format_message(update.message)
    logger.warning(text)

    with store.ContextManager(context) as c:
        c.add_chat(text)

        if not should_reply(update, context):
            return

        await update.message.set_reaction("👀")

        # urls = []
        # for k, v in update.message.parse_entities().items():
        #     if k.type == MessageEntityType.URL:
        #         urls.append(v)
        # text += await crawler.crawl(urls)

        result = agent.run(c.history)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=markdownify(result),
            parse_mode="MarkdownV2",
        )

        c.add_chat(f"{context.bot.first_name}: {result}", role="assistant")


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    info = (
        f"👤 *用户信息*\n"
        f"ID：`{user.id}`\n"
        f"姓名：{user.full_name}\n"
        f"用户名：@{user.username or '无'}\n"
        f"会话类型：{chat.type}\n"
    )
    await update.message.reply_text(info)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception(context.error)


async def set_commands(bot: Bot):
    await bot.delete_my_commands()
    await bot.set_my_commands(
        [
            BotCommand("info", "用户信息"),
            BotCommand("chat", "聊天"),
        ]
    )


async def post_init(app: Application):
    bot: Bot = app.bot
    await message_db.init_db()
    await set_commands(bot)
    agent.init(name=bot.first_name, username=bot.name)


if __name__ == "__main__":
    app = ApplicationBuilder().token(os.environ.get("BOT_TOKEN")).build()

    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("chat", handle_message))
    app.add_handler(MessageHandler(~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    app.post_init = post_init

    app.run_polling()
