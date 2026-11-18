from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_server.api.website import create_website_router


def test_landing_page_is_public_and_contains_product_message():
    app = FastAPI()
    app.include_router(create_website_router(Path("agent_server/templates")))

    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "Turn alerts into evidence-backed decisions" in response.text
    assert "/login" in response.text


def test_login_page_starts_browser_device_flow():
    app = FastAPI()
    app.include_router(create_website_router(Path("agent_server/templates")))

    response = TestClient(app).get("/login")

    assert response.status_code == 200
    assert "Create an account" in response.text
    assert "/v1/auth/device" in response.text
