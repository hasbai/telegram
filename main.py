import logging
import os

from telegram import Message, MessageOrigin, Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from telegramify_markdown import markdownify

import ai
from context import ContextManager

logging.basicConfig(format="[%(levelname)s] %(message)s", level=logging.WARNING)
logger = logging.getLogger(__name__)


def should_reply(update: Update, context) -> bool:
    message = update.message
    chat_type = message.chat.type  # 'private' / 'group' / 'supergroup' / 'channel'
    text = message.text or ""

    # 1. 单聊：直接回复
    if chat_type == "private":
        return True

    # 2. 群聊：检测 @mention
    bot_username = context.bot.username  # e.g. "MyBot"

    # 方式一：消息实体中有 mention，且 mention 的是本 bot
    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                print("mention:", entity)
                mentioned = text[entity.offset : entity.offset + entity.length]
                if mentioned.lstrip("@").lower() == bot_username.lower():
                    return True

    # 方式二：用户回复了 Bot 发出的消息
    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.id == context.bot.id:
            return True

    return False


def format_message(message: Message) -> str:
    if not getattr(message, "text"):
        return ""
    text = message.text
    sender = message.from_user.first_name
    print("text:", text)
    # if message.parse_entities():
    #     print(message.parse_entities())
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

    with ContextManager(context) as history:
        history.append({"role": "user", "parts": [{"text": text}]})

        if not should_reply(update, context):
            return

        await update.message.set_reaction("👀")

        reply = None
        reply_text = ""
        async for chunk in ai.call_ai_throttled(history):
            reply_text += chunk
            if not reply:
                reply = await update.message.reply_text(
                    markdownify(reply_text), parse_mode="MarkdownV2"
                )
            else:
                await reply.edit_text(markdownify(reply_text), parse_mode="MarkdownV2")

        history.append({"role": "assistant", "parts": [{"text": reply_text}]})


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception(context.error)


if __name__ == "__main__":
    app = ApplicationBuilder().token(os.environ.get("BOT_TOKEN")).build()

    app.add_handler(MessageHandler(filters.TEXT, callback=handle_message))
    app.add_error_handler(error_handler)

    app.run_polling()
