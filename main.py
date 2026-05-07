import logging
import os

from dotenv import load_dotenv
from telegram import Bot, BotCommand, Update
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
import db
from utils import should_reply

logging.basicConfig(format="[%(levelname)s] %(message)s", level=logging.WARNING)
logger = logging.getLogger(__name__)
load_dotenv()


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = await db.save_message(update.message)
    text = str(message)
    logger.warning(text)

    if not should_reply(update, context):
        return

    await update.message.set_reaction("👀")

    # urls = []
    # for k, v in update.message.parse_entities().items():
    #     if k.type == MessageEntityType.URL:
    #         urls.append(v)
    # text += await crawler.crawl(urls)

    history = await db.get_recent_messages(message.chat_id)
    result = agent.run(message, history)
    sent_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=markdownify(result),
        parse_mode="MarkdownV2",
    )

    await db.save_message(sent_message)


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
    await db.init_db()
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
