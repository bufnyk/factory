import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from api.main import app, start_agent
from src import deps


@pytest.mark.asyncio
async def test_webhook_signature_uses_webhook_secret(monkeypatch):
    monkeypatch.setattr(deps, "get_settings", lambda: SimpleNamespace(gh_secret=SecretStr("webhook-secret")))
    request = SimpleNamespace(body=AsyncMock(return_value=b'{"action":"labeled"}'))
    signature = "sha256=" + hmac.new(b"webhook-secret", await request.body(), hashlib.sha256).hexdigest()

    assert await deps.verify_github(request, signature)
    with pytest.raises(HTTPException) as wrong:
        await deps.verify_github(request, "sha256=wrong")
    assert wrong.value.status_code == 401


@pytest.mark.asyncio
async def test_only_ai_label_queues_an_issue(monkeypatch, payload):
    queue = AsyncMock()
    monkeypatch.setattr("api.main.start_agentic_pipeline", SimpleNamespace(kiq=queue))

    assert await start_agent(payload.model_dump(mode="json"), "issues") == {"status": "started agent"}
    queue.assert_awaited_once_with(payload.model_dump(mode="json"))

    queue.reset_mock()
    assert await start_agent(payload.model_copy(update={"label": None}).model_dump(mode="json"), "issues") == {"status": "skipped"}
    assert await start_agent(payload.model_copy(update={"label": payload.label.model_copy(update={"name": "bug"})}).model_dump(mode="json"), "issues") == {"status": "skipped"}
    assert await start_agent(payload.model_copy(update={"action": "edited"}).model_dump(mode="json"), "issues") == {"status": "skipped"}
    assert await start_agent(payload.model_copy(update={"issue": payload.issue.model_copy(update={"pull_request": {"url": "x"}})}).model_dump(mode="json"), "issues") == {"status": "skipped"}
    queue.assert_not_awaited()


@pytest.mark.asyncio
async def test_codex_login_requires_cli_session(monkeypatch, tmp_path):
    path = tmp_path / "auth.json"
    monkeypatch.setattr(deps, "get_settings", lambda: SimpleNamespace(codex_auth_path=path))
    assert not deps.is_codex_authenticated()
    path.write_text(json.dumps({"OPENAI_API_KEY": "key"}))
    assert not deps.is_codex_authenticated()
    path.write_text(json.dumps({"tokens": {"access_token": "token"}}))
    assert await deps.check_codex()


@pytest.mark.asyncio
async def test_github_ping_is_acknowledged_without_issue(monkeypatch):
    queue = AsyncMock()
    monkeypatch.setattr("api.main.start_agentic_pipeline", SimpleNamespace(kiq=queue))
    assert await start_agent({"zen": "Keep it simple"}, "ping") == {"status": "pong"}
    queue.assert_not_awaited()


@pytest.mark.asyncio
async def test_signed_ping_reaches_public_route(monkeypatch):
    monkeypatch.setattr(deps, "get_settings", lambda: SimpleNamespace(gh_secret=SecretStr("webhook-secret")))
    app.dependency_overrides[deps.check_codex] = lambda: True
    app.dependency_overrides[deps.check_claude] = lambda: True
    body = b'{"zen":"Keep it simple"}'
    signature = "sha256=" + hmac.new(b"webhook-secret", body, hashlib.sha256).hexdigest()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "ping",
                    "X-Hub-Signature-256": signature,
                },
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {"status": "pong"}


@pytest.mark.asyncio
async def test_invalid_issue_payload_returns_422():
    with pytest.raises(HTTPException) as error:
        await start_agent({"action": "labeled"}, "issues")
    assert error.value.status_code == 422
