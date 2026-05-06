import asyncio
import os
from datetime import datetime

from pydantic import AliasPath, field_validator, model_validator
from sqlalchemy import JSON, Text, text
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import Column, Field, Relationship, SQLModel
from telegram import Message, MessageOrigin


class UserModel(SQLModel, table=True):
    __tablename__ = "user"

    id: int = Field(primary_key=True)
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
        data["username"] = data.get("username") or data.get("title")
        return data


class MessageModel(SQLModel, table=True):
    __tablename__ = "message"

    id: int = Field(primary_key=True, validation_alias="message_id")
    chat_id: int = Field(
        foreign_key="user.id",
        validation_alias=AliasPath("chat", "id"),
    )
    chat: UserModel | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[MessageModel.chat_id]"}
    )
    user_id: int | None = Field(
        default=None,
        foreign_key="user.id",
        validation_alias=AliasPath("from_user", "id"),
    )
    user: UserModel | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[MessageModel.user_id]"}
    )
    forward_from_id: int | None = Field(
        default=None,
        foreign_key="user.id",
        validation_alias=AliasPath("forward_from", "id"),
    )
    forward_from: UserModel | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[MessageModel.forward_from_id]"}
    )
    created_at: datetime = Field(validation_alias="date")
    updated_at: datetime | None = Field(validation_alias="edit_date")
    text: str | None = Field(default=None, sa_column=Column(Text))
    caption: str | None = None
    reply_to_message_id: int | None = None
    message_group_id: int | None = None
    media_type: str | None = None  # photo/video/audio/document/voice/sticker/…
    raw_json: str | None = Field(default=None, sa_column=Column(JSON))

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

        def _extract_forward_from(message: Message) -> dict | None:
            if not getattr(message, "forward_origin"):
                return
            result = {}
            type = message.forward_origin.type
            if type in (MessageOrigin.CHANNEL, MessageOrigin.CHAT):
                result = message.forward_origin.chat.dict()
            else:
                result = message.forward_origin.sender_user.dict()
            result["type"] = type
            return result

        self.media_type = _detect_media_type(message)
        self.raw_json = message.to_dict()
        self.chat = UserModel.model_validate(self.raw_json.get("chat"))
        self.user = UserModel.model_validate(self.raw_json.get("from"))
        forward_from = _extract_forward_from(message)
        if forward_from:
            self.forward_from = UserModel.model_validate(forward_from)


engine = None
async_session = None


async def init_db() -> None:
    global engine, async_session
    engine = create_async_engine(os.environ.get("DATABASE_URL"), echo=False)
    async_session = async_sessionmaker(engine)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS telegram"))
        await conn.run_sync(SQLModel.metadata.create_all)


async def save_message(message: Message) -> None:
    """Persist a Telegram message (and its photos) to PostgreSQL."""
    db_msg = MessageModel.model_validate(message)
    db_msg.after_construct(message)
    print(db_msg)

    async with async_session() as session:
        await session.merge(db_msg)
        # if message.photo:
        #     # Telegram sends multiple resolutions; take the highest quality one.
        #     best = message.photo[-1]
        #     tg_file = await best.get_file()
        #     photo_bytes = bytes(await tg_file.download_as_bytearray())

        await session.commit()


if __name__ == "__main__":
    asyncio.run(init_db())
