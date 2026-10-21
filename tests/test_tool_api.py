from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from agent_core.tools import ToolDefinition
from agent_server.tool_api import ToolPrincipal, create_tool_router
from agent_server.tool_service import ToolRegistry, ToolService


class Args(BaseModel):
    value: str


class Result(BaseModel):
    value: str


class Echo:
    async def execute(self, arguments, context):
        return Result(value=arguments.value)


def test_tool_service_http_contract_authenticates_and_returns_typed_results():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            version="1.0.0",
            description="echo",
            input_model=Args,
            output_model=Result,
            required_scopes=frozenset({"tools:echo"}),
        ),
        lambda _: Echo(),
    )
    calls = []

    def resolve_principal(authorization):
        calls.append(authorization)
        if authorization != "Bearer trusted":
            from fastapi import HTTPException
            raise HTTPException(status_code=401)
        return ToolPrincipal(user_id="user-1", scopes=frozenset({"tools:echo"}))

    app = FastAPI()
    app.include_router(create_tool_router(ToolService(registry), resolve_principal))
    client = TestClient(app)

    catalog = client.get("/v1/tools", headers={"Authorization": "Bearer trusted"})
    response = client.post(
        "/v1/tool-calls",
        headers={
            "Authorization": "Bearer trusted",
            "Idempotency-Key": "call-key-1",
            "X-Correlation-ID": "correlation-1",
            "traceparent": "00-abc-def-01",
        },
        json={
            "run_id": "run-1",
            "call_id": "call-1",
            "name": "echo",
            "version": "1.0.0",
            "arguments": {"value": "hello"},
        },
    )

    assert [item["name"] for item in catalog.json()] == ["echo"]
    assert response.status_code == 200
    assert response.json()["output"] == {"value": "hello"}
    assert calls == ["Bearer trusted", "Bearer trusted"]


def test_tool_service_http_contract_rejects_missing_auth_and_idempotency_key():
    def resolve(authorization):
        from fastapi import HTTPException
        if authorization != "Bearer trusted":
            raise HTTPException(status_code=401)
        return ToolPrincipal(user_id="u")

    app = FastAPI()
    app.include_router(create_tool_router(ToolService(ToolRegistry()), resolve))
    client = TestClient(app)

    unauthenticated = client.get("/v1/tools")
    missing_key = client.post(
        "/v1/tool-calls",
        headers={"Authorization": "Bearer trusted"},
        json={"run_id": "r", "call_id": "c", "name": "echo", "version": "1", "arguments": {}},
    )

    assert unauthenticated.status_code == 401
    assert missing_key.status_code == 422


def test_tool_service_http_contract_rejects_unbounded_arguments():
    app = FastAPI()
    app.include_router(
        create_tool_router(
            ToolService(ToolRegistry()),
            lambda _: ToolPrincipal(user_id="u"),
        )
    )
    response = TestClient(app).post(
        "/v1/tool-calls",
        headers={"Authorization": "Bearer trusted", "Idempotency-Key": "large"},
        json={
            "run_id": "r",
            "call_id": "c",
            "name": "echo",
            "version": "1",
            "arguments": {"payload": "x" * 70_000},
        },
    )
    assert response.status_code == 422
