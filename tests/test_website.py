from pathlib import Path
from datetime import datetime, timezone
from io import BytesIO
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_server.accounts import LocalAccount
from agent_server.auth import issue_access_token
from agent_server.api.website import create_website_router
from agent_server.auth_sessions import AuthSessionService
from agent_server.docs import DOCS
from tests.test_auth_sessions import MemoryAuthRepository


class FakeAccounts:
    def __init__(self):
        self.account = LocalAccount(
            email="person@example.com",
            password_hash="hash",
            created_at=datetime.now(timezone.utc),
            display_name="Person",
        )

    async def sign_in(self, email, password):
        assert email == "person@example.com"
        assert password == "a-long-test-password"
        return "person@example.com"

    async def sign_up(self, email, password):
        return "person@example.com"

    async def get_profile(self, email):
        return self.account if email == self.account.email else None

    async def update_profile(self, email, display_name):
        self.account = self.account.__class__(
            email=self.account.email,
            password_hash=self.account.password_hash,
            created_at=self.account.created_at,
            display_name=display_name.strip() or None,
        )
        return self.account


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
    assert "Sign in" in response.text
    assert response.text.count('aria-label="Primary navigation"') == 1
    assert 'href="/docs/cli"' in response.text
    primary_nav = response.text.split('<nav class="ui-site-links"', 1)[1].split("</nav>", 1)[0]
    assert 'href="#how"' not in primary_nav
    assert "The CLI advantage" in response.text
    assert "Less context switching" in response.text
    assert 'href="/static/app.css"' in response.text


def test_documentation_is_repository_backed_and_navigable():
    app = FastAPI()
    app.include_router(create_website_router(Path("agent_server/templates")))

    response = TestClient(app).get("/docs/investigations/alertmanager")

    assert response.status_code == 200
    assert "Plain Deployment" in response.text
    assert "Helm" in response.text
    assert "Prometheus Operator" in response.text
    assert "Previous" in response.text
    assert "CLI" in response.text
    assert "Investigation" in response.text
    assert response.text.count('aria-label="Primary navigation"') == 1
    assert 'href="/docs/cli"' in response.text
    assert 'href="/"' in response.text


def test_cli_documentation_covers_tools_and_slash_commands():
    app = FastAPI()
    app.include_router(create_website_router(Path("agent_server/templates")))
    client = TestClient(app)

    overview = client.get("/docs/cli")
    slash_commands = client.get("/docs/cli/slash-commands")
    files_tool = client.get("/docs/cli/tools/files")

    assert overview.status_code == 200
    assert "Tools Available" in overview.text
    assert 'href="/docs/cli/tools/aws"' in overview.text
    assert "does not invoke a shell" in overview.text
    assert slash_commands.status_code == 200
    assert "/resume" in slash_commands.text
    assert "conversation-id" in slash_commands.text
    assert files_tool.status_code == 200
    assert "Linux" in files_tool.text
    assert "Windows" in files_tool.text
    for page in DOCS:
        assert client.get(f"/docs/{page['slug']}").status_code == 200


def test_alertmanager_docs_link_to_downloadable_safe_manifest_examples():
    app = FastAPI()
    app.include_router(create_website_router(Path("agent_server/templates")))
    client = TestClient(app)

    docs = client.get("/docs/investigations/alertmanager")
    kustomize = client.get("/docs/downloads/alertmanager/kustomize.zip")
    helm = client.get("/docs/downloads/alertmanager/helm.yaml")
    operator = client.get("/docs/downloads/alertmanager/operator.yaml")

    assert 'href="/docs/downloads/alertmanager/kustomize.zip"' in docs.text
    assert kustomize.headers["content-disposition"].startswith("attachment;")
    assert helm.headers["content-disposition"].startswith("attachment;")
    assert operator.headers["content-disposition"].startswith("attachment;")
    with ZipFile(BytesIO(kustomize.content)) as bundle:
        assert "kustomization.yaml" in bundle.namelist()
        assert b"REPLACE_WITH_WEBHOOK_TOKEN" in bundle.read("webhook-secret.yaml")
    assert "REPLACE_WITH_WEBHOOK_TOKEN" in helm.text
    assert "YOUR_AGENT_HOST" in helm.text
    assert "REPLACE_WITH_WEBHOOK_TOKEN" in operator.text
    assert "YOUR_AGENT_HOST" in operator.text


def test_runtime_image_includes_repository_documentation():
    dockerfiles = (
        Path("agent_server/api/Dockerfile").read_text(encoding="utf-8"),
        Path("agent_server/investigations/Dockerfile").read_text(encoding="utf-8"),
    )
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8")

    assert all("COPY agent_server agent_server" in dockerfile for dockerfile in dockerfiles)
    assert all("COPY docs/website docs/website" not in dockerfile for dockerfile in dockerfiles)
    assert "!docs/website/**" not in dockerignore
    assert "npm run css:build" in dockerfiles[0]


def test_tailwind_stylesheet_is_served_and_contains_shared_components():
    app = FastAPI()
    app.include_router(create_website_router(Path("agent_server/templates")))

    response = TestClient(app).get("/static/app.css")

    assert response.status_code == 200
    assert ".ui-button" in response.text
    assert ".ui-input" in response.text
    assert ".ui-site-header" in response.text


def test_authenticated_landing_page_shows_account_link_instead_of_sign_in():
    auth = AuthSessionService(
        repository=WebsiteAuthRepository(),
        approval_provider=object(),
        access_token_secret="test-secret",
    )
    app = FastAPI()
    app.include_router(create_website_router(Path("agent_server/templates"), auth_service=auth))
    client = TestClient(app, cookies={"devops_access_token": issue_access_token("test-secret", "person@example.com")})

    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/account"' in response.text
    assert "Account" in response.text
    assert ">Sign in<" not in response.text


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


def test_authenticated_user_is_redirected_from_login_and_can_edit_account():
    accounts = FakeAccounts()
    auth = AuthSessionService(
        repository=WebsiteAuthRepository(),
        approval_provider=object(),
        access_token_secret="test-secret",
    )
    app = FastAPI()
    app.include_router(create_website_router(Path("agent_server/templates"), accounts=accounts, auth_service=auth))
    client = TestClient(app, cookies={"devops_access_token": issue_access_token("test-secret", accounts.account.email)})

    login = client.get("/login", follow_redirects=False)
    assert login.status_code == 303
    assert login.headers["location"] == "/settings"

    page = client.get("/account")
    assert page.status_code == 200
    assert "person@example.com" in page.text
    assert "Person" in page.text

    saved = client.post("/account", data={"display_name": "Updated Person"})
    assert saved.status_code == 200
    assert "Account details updated." in saved.text
    assert "Updated Person" in saved.text


def test_account_page_redirects_unauthenticated_users_to_login():
    accounts = FakeAccounts()
    auth = AuthSessionService(
        repository=WebsiteAuthRepository(),
        approval_provider=object(),
        access_token_secret="test-secret",
    )
    app = FastAPI()
    app.include_router(create_website_router(Path("agent_server/templates"), accounts=accounts, auth_service=auth))

    response = TestClient(app).get("/account", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
