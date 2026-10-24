"""Generate concise titles for conversations from their first user message."""

from __future__ import annotations

from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage


MAX_CONVERSATION_TITLE_WORDS = 10
MAX_CONVERSATION_TITLE_LENGTH = 200


class ConversationTitleGenerator(Protocol):
    async def generate_title(self, first_message: str) -> str: ...


class ModelConversationTitleGenerator:
    """Use the configured chat model to name a conversation in at most ten words."""

    def __init__(self, model: Any) -> None:
        self.model = model

    async def generate_title(self, first_message: str) -> str:
        response = await self.model.ainvoke(
            [
                SystemMessage(
                    content=(
                        "Create a short title for a chat based on the user's first message. "
                        "Return only the title, with no quotes or explanation, and use no "
                        "more than 10 words."
                    )
                ),
                HumanMessage(content=first_message),
            ]
        )
        title = _response_text(response)
        title = " ".join(title.strip().strip("\"'` ").split())
        title = " ".join(title.split()[:MAX_CONVERSATION_TITLE_WORDS])
        if len(title) > MAX_CONVERSATION_TITLE_LENGTH:
            title = title[:MAX_CONVERSATION_TITLE_LENGTH].rstrip()
            if " " in title:
                title = title.rsplit(" ", 1)[0]
        if not title:
            raise ValueError("title model returned an empty title")
        return title


def _response_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            item["text"] for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
    raise ValueError("title model returned unsupported content")


__all__ = [
    "ConversationTitleGenerator",
    "MAX_CONVERSATION_TITLE_LENGTH",
    "MAX_CONVERSATION_TITLE_WORDS",
    "ModelConversationTitleGenerator",
]
