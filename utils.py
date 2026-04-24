from telegram import Update
from telegram.ext import ContextTypes


def should_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
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
                mentioned = text[entity.offset : entity.offset + entity.length]
                if mentioned.lstrip("@").lower() == bot_username.lower():
                    return True

    # 方式二：用户回复了 Bot 发出的消息
    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.id == context.bot.id:
            return True

    return False
