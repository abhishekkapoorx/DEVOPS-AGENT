from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_server.api.website import create_website_router
from agent_server.auth_sessions import AuthSessionService
from tests.test_auth_sessions import MemoryAuthRepository


class FakeAccounts:
    async def sign_in(self, email, password):
        assert email == "person@example.com"
        assert password == "a-long-test-password"
        return "person@example.com"

    async def sign_up(self, email, password):
        return "person@example.com"


class WebsiteAuthRepository(MemoryAuthRepository):
    async def create_session(self, session):
        self.sessions[session.session_id] = session


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
    assert "/website/login" in response.text
    assert "/login?mode=signup" in response.text


def test_website_login_issues_browser_cookies_without_device_route():
    auth = AuthSessionService(
        repository=WebsiteAuthRepository(),
        approval_provider=object(),
        access_token_secret="test-secret",
    )
    app = FastAPI()
    app.include_router(
        create_website_router(
            Path("agent_server/templates"),
            accounts=FakeAccounts(),
            auth_service=auth,
        )
    )

    response = TestClient(app).post(
        "/website/login",
        data={"email": "person@example.com", "password": "a-long-test-password"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "devops_access_token" in response.headers["set-cookie"]
    assert response.headers["location"] == "/settings"
