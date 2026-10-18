import tempfile
from pathlib import Path

from agent_cli.local_state import JsonConversationSelectionStore


def test_selected_conversation_id_is_persisted_and_clearable():
    with tempfile.TemporaryDirectory(dir=".") as directory:
        store = JsonConversationSelectionStore(Path(directory) / "state" / "conversation.json")

        assert store.load() is None
        store.save("conversation-42")
        assert store.load() == "conversation-42"
        store.clear()
        assert store.load() is None
