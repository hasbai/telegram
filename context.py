from contextlib import contextmanager


@contextmanager
def ContextManager(context):
    if "history" not in context.chat_data:
        context.chat_data["history"] = []

    yield context.chat_data["history"]

    context.chat_data["history"] = context.chat_data["history"][-10:]
