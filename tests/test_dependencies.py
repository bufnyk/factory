from src.deps import check_ai, verify_github
import pytest
import hmac
import hashlib
import random
from config import get_settings
from fastapi import HTTPException

settings = get_settings()

@pytest.mark.asyncio 
async def test_gitub(mocker):

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