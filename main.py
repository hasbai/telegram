import logging
import os

from telegram import Message, MessageOrigin, Update
from telegram.constants import MessageEntityType
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegramify_markdown import markdownify

import ai
import crawler
import store
from utils import should_reply

logging.basicConfig(format="[%(levelname)s] %(message)s", level=logging.WARNING)
logger = logging.getLogger(__name__)


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
    text = format_message(update.message)
    logger.warning(text)

    with store.ContextManager(context) as c:
        c.add_chat(text)

        routing_result = ai.RoutingResult(
            should_respond=should_reply(update, context), is_reply=True
        )
        if not routing_result.should_respond:
            return

        await update.message.set_reaction("👀")

        urls = []
        for k, v in update.message.parse_entities().items():
            if k.type == MessageEntityType.URL:
                urls.append(v)
        text += await crawler.crawl(urls)

        reply = None
        reply_text = ""
        async for chunk in ai.call_ai_throttled(c.history):
            reply_text += chunk
            if not reply:
                if routing_result.is_reply:
                    reply = await update.message.reply_text(
                        markdownify(reply_text), parse_mode="MarkdownV2"
                    )
                else:
                    reply = await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=markdownify(reply_text),
                        parse_mode="MarkdownV2",
                    )
            else:
                await reply.edit_text(markdownify(reply_text), parse_mode="MarkdownV2")

        c.add_chat(reply_text, role="assistant")


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


if __name__ == "__main__":
    app = ApplicationBuilder().token(os.environ.get("BOT_TOKEN")).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("chat", handle_message))
    app.add_error_handler(error_handler)
    app.run_polling()
