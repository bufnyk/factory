from src.deps import verify_github, check_claude, check_codex
from api.main import start_agent
import pytest
import hmac
import hashlib
import random
from config import get_settings
from fastapi import HTTPException
from schemas import Github
from pydantic import ValidationError
import json

settings = get_settings()

@pytest.mark.asyncio 
async def test_gitub_validator(mocker):

    fake_body = random.randbytes(64)

    fake_request = mocker.AsyncMock()
    fake_request.body.return_value = fake_body

    fake_x_hub_signature = (
        "sha256="
        + hmac.new(
            settings.gh_secret.encode("utf-8"),
            await fake_request.body(),
            hashlib.sha256
        ).hexdigest()
    )

    assert await verify_github(fake_request, fake_x_hub_signature)
    with pytest.raises(HTTPException, match="Invalid or missing signature"):
        await verify_github(fake_request)
    with pytest.raises(HTTPException, match="Invalid signature"):
        await verify_github(fake_request, "sha256=ksnfksn")

@pytest.mark.asyncio
async def test_github_full_payload():

    payload = {
        "action": "labeled",
        "issue": {
            "id": 5346324344,
            "number": 2,
            "title": "check for ai",
            "body": "testing testing",
            "repository_url": "https://api.github.com/repos/bufnyk/feedback_processor",
            "labels": [{"name": "bug"}, {"name": "ai"}],
        },
    }

    error_payload = {
        "action": "labeled"
    }
    
    assert await start_agent(Github.model_validate(payload)) == {"status": "started agent"}

    with pytest.raises(ValidationError):
        Github.model_validate(error_payload)

@pytest.mark.asyncio
async def test_check_claude_success(mocker):
    mock_config = mocker.patch("src.deps.CLAUDE_CONFIG")
    mock_config.is_file.return_value = True
    mock_config.read_text.return_value = json.dumps(
        {"oauthAccount": {"accountUuid": "usr_99a8b7c6", "emailAddress": "dev@test.com"}}
    )

    assert await check_claude() is True

@pytest.mark.asyncio
async def test_check_codex_success_via_tokens(mocker):
    mock_auth = mocker.patch("src.deps.CODEX_AUTH_PATH")
    mock_auth.is_file.return_value = True
    mock_auth.read_text.return_value = json.dumps(
        {"OPENAI_API_KEY": None, "tokens": {"access_token": "secret_token_123"}}
    )

    assert await check_codex() is True

@pytest.mark.asyncio
async def test_smoke_test_claude():
    assert await check_claude()

@pytest.mark.asyncio
async def test_smoke_test_codex():
    assert await check_codex()


