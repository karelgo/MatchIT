"""Browser end-to-end test for the admin portal.

The portal is vanilla JS served by the API itself; nothing else in the suite
executes that JavaScript, so this drives real Chromium against a real uvicorn
server: login → metrics render → suspend a user → the action shows up in audit.

Skips (rather than fails) where no Playwright browser is installed, so the
default backend CI job stays browser-free; the dedicated portal-e2e job runs it.
"""

import asyncio
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.ai.embeddings import FakeEmbeddingModel
from app.ai.llm import FakeChatModel
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models import User, UserRole
from app.services.notifications import FakePushSender
from app.services.payments import FakePaymentProvider
from app.services.pubsub import InMemoryPubSub
from app.services.ratelimit import InMemoryRateLimiter
from app.services.usage import InMemoryUsageCounter
from app.services.vector import InMemoryVectorIndex
from tests.conftest import FakeAppleVerifier, Settings

playwright_api = pytest.importorskip("playwright.sync_api")


def _launch_chromium(playwright):
    """Launch the revision playwright installed, or a pre-provisioned Chromium.

    Containers often ship a browser at a pinned path rather than the exact
    revision this playwright version would download; only skip when neither
    exists.
    """
    try:
        return playwright.chromium.launch(args=["--no-sandbox"])
    except Exception:  # noqa: BLE001 - fall through to the pinned executable
        pass
    for executable in ("/opt/pw-browsers/chromium", "/usr/bin/chromium"):
        try:
            return playwright.chromium.launch(
                executable_path=executable, args=["--no-sandbox"]
            )
        except Exception:  # noqa: BLE001
            continue
    pytest.skip("No Chromium available; the portal-e2e CI job covers this")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def live_server(tmp_path):
    """A real uvicorn server over the app with fakes and a file-backed SQLite."""
    database_url = f"sqlite+aiosqlite:///{tmp_path}/portal.db"
    engine = create_async_engine(database_url, poolclass=NullPool)

    async def create_schema():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    settings = Settings(
        jwt_secret="test-secret-0123456789abcdef0123456789abcdef",
        llm_provider="fake",
        embedding_provider="fake",
        vector_backend="memory",
        pubsub_backend="memory",
        rate_limit_backend="memory",
        usage_counter_backend="memory",
        payment_provider="fake",
        push_backend="fake",
        login_rate_limit=200,
    )
    app = create_app(
        settings,
        chat_model=FakeChatModel(),
        embedding_model=FakeEmbeddingModel(),
        vector_index=InMemoryVectorIndex(),
        apple_verifier=FakeAppleVerifier(),
        pubsub=InMemoryPubSub(),
        rate_limiter=InMemoryRateLimiter(),
        usage_counter=InMemoryUsageCounter(),
        payment_provider=FakePaymentProvider(),
        push_sender=FakePushSender(),
        sessionmaker=sessionmaker,
    )

    async def override_get_db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base_url}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:
        pytest.fail("uvicorn did not come up")

    yield base_url, database_url

    server.should_exit = True
    thread.join(timeout=10)


def _seed(base_url: str, database_url: str) -> None:
    """An admin account (promoted directly — admins cannot self-register) and
    one specialist to act on."""
    for email, role in (("portal-admin@example.com", "hiring_manager"),
                        ("portal-spec@example.com", "freelancer")):
        response = httpx.post(
            f"{base_url}/api/v1/auth/register",
            json={
                "email": email,
                "password": "s3cure-password",
                "full_name": "Portal " + role,
                "role": role,
            },
            timeout=5,
        )
        assert response.status_code == 201, response.text

    async def promote():
        engine = create_async_engine(database_url, poolclass=NullPool)
        async with async_sessionmaker(engine)() as db:
            user = await db.scalar(
                select(User).where(User.email == "portal-admin@example.com")
            )
            user.role = UserRole.ADMIN
            await db.commit()
        await engine.dispose()

    asyncio.run(promote())


def test_portal_is_served(live_server):
    base_url, _ = live_server
    response = httpx.get(f"{base_url}/admin-portal", timeout=5)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "MatchIT Admin" in response.text


def test_portal_login_metrics_suspend_and_audit(live_server):
    base_url, database_url = live_server
    _seed(base_url, database_url)

    with playwright_api.sync_playwright() as playwright:
        browser = _launch_chromium(playwright)
        page = browser.new_page()
        page.on("dialog", lambda dialog: dialog.accept())

        # login
        page.goto(f"{base_url}/admin-portal")
        page.fill("#email", "portal-admin@example.com")
        page.fill("#password", "s3cure-password")
        page.click("#login-button")

        # metrics rendered from the live API
        page.wait_for_selector("#funnel .bar-row")
        assert "Specialists" in page.inner_text("#funnel")
        assert "freelancer: 1" in page.inner_text("#roles")

        # suspend the specialist from the users table
        page.click("#nav-users")
        row = page.locator("tr", has_text="portal-spec@example.com")
        row.wait_for()
        assert "active" in row.inner_text()
        row.get_by_role("button", name="Suspend").click()
        page.locator("tr", has_text="portal-spec@example.com").get_by_text(
            "suspended", exact=True
        ).wait_for()

        # the suspension is in the audit trail (scope to the table body — the
        # filter dropdown also contains the literal text "user_suspended")
        page.click("#nav-audit")
        page.select_option("#audit-action-filter", "user_suspended")
        page.locator("#audit-body .chip", has_text="user_suspended").first.wait_for()

        browser.close()

    # and the suspension is real: the specialist can no longer sign in
    login = httpx.post(
        f"{base_url}/api/v1/auth/login",
        json={"email": "portal-spec@example.com", "password": "s3cure-password"},
        timeout=5,
    )
    assert login.status_code == 401
