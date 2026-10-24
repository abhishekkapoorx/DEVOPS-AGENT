from types import SimpleNamespace

import pytest

from agent_server.conversation_titles import ModelConversationTitleGenerator


class FakeModel:
    def __init__(self, response):
        self.response = response
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return SimpleNamespace(content=self.response)


@pytest.mark.asyncio
async def test_model_title_generator_normalizes_and_limits_title_to_ten_words():
    model = FakeModel('  "One two three four five six seven eight nine ten eleven"  ')

    title = await ModelConversationTitleGenerator(model).generate_title(
        "Summarize the first message"
    )

    assert title == "One two three four five six seven eight nine ten"
    assert len(title.split()) == 10
    assert model.messages[-1].content == "Summarize the first message"


@pytest.mark.asyncio
async def test_model_title_generator_rejects_an_empty_model_response():
    with pytest.raises(ValueError, match="empty title"):
        await ModelConversationTitleGenerator(FakeModel("  ")).generate_title("Hello")
