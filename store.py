from smolagents.models import ChatMessage
from telegram.ext import ContextTypes


class ContextManager:
    MAX_CONTEXT_LENGTH = 100

    def __init__(self, context: ContextTypes.DEFAULT_TYPE):
        self.context = context

    def __enter__(self):
        if "history" not in self.context.chat_data:
            self.context.chat_data["history"] = []
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.context.chat_data["history"] = self.context.chat_data["history"][
            -self.MAX_CONTEXT_LENGTH :
        ]

    def add_chat(self, content: str, role: str = "user"):
        self.context.chat_data["history"].append(ChatMessage(role, content))

    @property
    def history(self) -> list[dict]:

        return self.context.chat_data["history"]


BOT_NAME = "Saki"
BOT_USERNAME = "saki_main_bot"
