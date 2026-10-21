from __future__ import annotations

import ast
from pathlib import Path

from agent_server.persistence.auth import AuthSessionRow, AuthBase, DeviceAuthorizationRow
from agent_server.persistence.postgres import Base


def test_auth_tables_register_on_shared_postgres_metadata_without_plaintext_tokens():
    assert AuthBase is Base
    assert AuthSessionRow.__table__.metadata is Base.metadata
    assert DeviceAuthorizationRow.__table__.metadata is Base.metadata
    assert "refresh_hash" in AuthSessionRow.__table__.columns
    assert "refresh_token" not in AuthSessionRow.__table__.columns
    assert "device_code_hash" in DeviceAuthorizationRow.__table__.columns
    assert "device_code" not in DeviceAuthorizationRow.__table__.columns


def test_auth_migration_follows_conversation_migration():
    path = Path(__file__).parents[1] / "migrations" / "versions" / "0002_auth_sessions.py"
    module = ast.parse(path.read_text(encoding="utf-8"))
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"revision", "down_revision"}
    }
    assert constants == {
        "revision": "0002_auth_sessions",
        "down_revision": "0001_conversations",
    }
