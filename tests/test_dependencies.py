import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from api.main import start_agent
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

    assert await start_agent(payload) == {"status": "started agent"}
    queue.assert_awaited_once_with(payload.model_dump(mode="json"))

    queue.reset_mock()
    assert await start_agent(payload.model_copy(update={"label": None})) == {"status": "skipped"}
    assert await start_agent(payload.model_copy(update={"label": payload.label.model_copy(update={"name": "bug"})})) == {"status": "skipped"}
    assert await start_agent(payload.model_copy(update={"action": "edited"})) == {"status": "skipped"}
    assert await start_agent(payload.model_copy(update={"issue": payload.issue.model_copy(update={"pull_request": {"url": "x"}})})) == {"status": "skipped"}
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
