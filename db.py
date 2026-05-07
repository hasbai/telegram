import asyncio
import os
from datetime import datetime
from typing import Any

from pydantic import AliasPath, PrivateAttr, field_validator, model_validator
from sqlalchemy import JSON, BigInteger, Text, text
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload
from sqlmodel import Column, Field, Relationship, SQLModel, select
from telegram import Message, MessageOrigin


BOT_NAME = "Saki"
BOT_USERNAME = "saki_main_bot"


class UserModel(SQLModel, table=True):
    __tablename__ = "user"

    id: int = Field(primary_key=True, sa_type=BigInteger)
    username: str
    first_name: str | None = Field(default=None)
    type: str = Field(default="user")
    role: str = Field(default="user")  # for LLM

    @field_validator("type")
    @classmethod
    def username_not_empty(cls, value: str):
        if value == "private":
            value = "user"
        return value

    @model_validator(mode="before")
    @classmethod
    def pick_first_non_none(cls, data):
        if not data:
            return
        data["first_name"] = data.get("first_name") or data.get("title")
        data["username"] = (
            data.get("username")
            or data.get("title")
            or data.get("first_name")
            or str(data.get("id"))
        )
        return data


class MessageModel(SQLModel, table=True):
    __tablename__ = "message"

    _reply_to_message: "MessageModel | None" = PrivateAttr(default=None)
    _forward_origin_name: str | None = PrivateAttr(default=None)

    id: int = Field(primary_key=True, validation_alias="message_id", sa_type=BigInteger)
    chat_id: int = Field(
        foreign_key="user.id",
        sa_type=BigInteger,
        validation_alias=AliasPath("chat", "id"),
    )
    chat: UserModel | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[MessageModel.chat_id]"}
    )
    user_id: int | None = Field(
        default=None,
        foreign_key="user.id",
        sa_type=BigInteger,
        validation_alias=AliasPath("from_user", "id"),
    )
    user: UserModel | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[MessageModel.user_id]"}
    )
    forward_from_id: int | None = Field(
        default=None,
        foreign_key="user.id",
        sa_type=BigInteger,
        validation_alias=AliasPath("forward_from", "id"),
    )
    forward_from: UserModel | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[MessageModel.forward_from_id]"}
    )
    created_at: datetime = Field(validation_alias="date")
    updated_at: datetime | None = Field(validation_alias="edit_date")
    text: str | None = Field(default=None, sa_column=Column(Text))
    caption: str | None = None
    reply_to_message_id: int | None = Field(default=None, sa_type=BigInteger)
    message_group_id: int | None = None
    media_type: str | None = None  # photo/video/audio/document/voice/sticker/…
    raw_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    def __str__(self) -> str:
        if not self.text:
            return ""

        sender = self.user.first_name if self.user else "Unknown"
        forward_origin = self._get_private("_forward_origin_name")
        if not forward_origin:
            forward_origin = self._forward_origin_name_from_raw_json()
        if not forward_origin and self.forward_from:
            forward_origin = self.forward_from.first_name
        if forward_origin:
            sender += f" (Forward from {forward_origin})"

        text = self.text
        reply_to_message = self._get_private("_reply_to_message")
        if reply_to_message:
            text += f"\n(Reply to {reply_to_message})"
        return f"{sender}: {text}"

    def _get_private(self, name: str):
        private = object.__getattribute__(self, "__pydantic_private__")
        if not private:
            return None
        return private.get(name)

    def _set_private(self, name: str, value) -> None:
        private = object.__getattribute__(self, "__pydantic_private__")
        if private is None:
            private = {}
            object.__setattr__(self, "__pydantic_private__", private)
        private[name] = value

    def _forward_origin_name_from_raw_json(self) -> str | None:
        if not self.raw_json:
            return None
        origin = self.raw_json.get("forward_origin")
        if not origin:
            return None
        if origin.get("type") in (MessageOrigin.CHANNEL, MessageOrigin.CHAT):
            return origin.get("chat", {}).get("title")
        return origin.get("sender_user", {}).get("first_name") or origin.get(
            "sender_user_name"
        )

    def after_construct(self, message: Message):
        def _detect_media_type(message: Message) -> str | None:
            if message.photo:
                return "photo"
            if message.video:
                return "video"
            if message.audio:
                return "audio"
            if message.document:
                return "document"
            if message.voice:
                return "voice"
            if message.sticker:
                return "sticker"
            if message.video_note:
                return "video_note"
            if message.animation:
                return "animation"
            return None

        def _extract_forward_origin_name(message: Message) -> str | None:
            if not getattr(message, "forward_origin"):
                return
            if message.forward_origin.type in (
                MessageOrigin.CHANNEL,
                MessageOrigin.CHAT,
            ):
                return message.forward_origin.chat.title
            sender_user = getattr(message.forward_origin, "sender_user", None)
            if sender_user:
                return sender_user.first_name
            return getattr(message.forward_origin, "sender_user_name", None)

        def _extract_forward_from(message: Message) -> dict | None:
            if not getattr(message, "forward_origin"):
                return
            type_ = message.forward_origin.type
            if type_ in (MessageOrigin.CHANNEL, MessageOrigin.CHAT):
                result = message.forward_origin.chat.to_dict()
            elif getattr(message.forward_origin, "sender_user", None):
                result = message.forward_origin.sender_user.to_dict()
            else:
                return
            result["type"] = type_
            return result

        self.media_type = _detect_media_type(message)
        self.raw_json = message.to_dict()
        self.chat = UserModel.model_validate(self.raw_json.get("chat"))
        self.user = UserModel.model_validate(self.raw_json.get("from"))
        self.reply_to_message_id = (
            message.reply_to_message.message_id if message.reply_to_message else None
        )
        self._set_private(
            "_reply_to_message",
            MessageModel.from_telegram(message.reply_to_message)
            if message.reply_to_message
            else None,
        )
        self._set_private("_forward_origin_name", _extract_forward_origin_name(message))
        forward_from = _extract_forward_from(message)
        if forward_from:
            self.forward_from = UserModel.model_validate(forward_from)

    @classmethod
    def from_telegram(cls, message: Message) -> "MessageModel":
        db_msg = cls.model_validate(message)
        db_msg.after_construct(message)
        return db_msg


engine = None
async_session = None


async def init_db() -> None:
    global engine, async_session
    engine = create_async_engine(os.environ.get("DATABASE_URL"), echo=False)
    async_session = async_sessionmaker(engine)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS telegram"))
        await conn.run_sync(SQLModel.metadata.create_all)


async def save_message(message: Message) -> MessageModel:
    """Persist a Telegram message (and its photos) to PostgreSQL."""
    db_msg = MessageModel.from_telegram(message)

    async with async_session() as session:
        await session.merge(db_msg)
        # if message.photo:
        #     # Telegram sends multiple resolutions; take the highest quality one.
        #     best = message.photo[-1]
        #     tg_file = await best.get_file()
        #     photo_bytes = bytes(await tg_file.download_as_bytearray())

        await session.commit()
    return db_msg


async def get_recent_messages(chat_id: int, limit: int = 100) -> list[MessageModel]:
    stmt = (
        select(MessageModel)
        .where(MessageModel.chat_id == chat_id)
        .options(
            selectinload(MessageModel.user),
            selectinload(MessageModel.forward_from),
        )
        .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
        .limit(limit)
    )
    async with async_session() as session:
        result = await session.execute(stmt)
        messages = list(result.scalars().all())
        messages.reverse()
        await _attach_reply_messages(session, messages)
        return messages


async def _attach_reply_messages(session, messages: list[MessageModel]) -> None:
    reply_ids = {
        message.reply_to_message_id
        for message in messages
        if message.reply_to_message_id is not None
    }
    if not reply_ids:
        return

    stmt = (
        select(MessageModel)
        .where(MessageModel.id.in_(reply_ids))
        .options(
            selectinload(MessageModel.user),
            selectinload(MessageModel.forward_from),
        )
    )
    result = await session.execute(stmt)
    replies = {message.id: message for message in result.scalars().all()}
    for message in messages:
        if message.reply_to_message_id in replies:
            message._set_private(
                "_reply_to_message", replies[message.reply_to_message_id]
            )


if __name__ == "__main__":
    asyncio.run(init_db())
