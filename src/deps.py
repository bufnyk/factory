import hashlib
import hmac
import json

from fastapi import Header, HTTPException, Request, status
from typing import Annotated

from config import get_settings


def is_claude_authenticated() -> bool:
    return bool(get_settings().claude_setup_token.get_secret_value())


async def check_claude() -> bool:
    if not is_claude_authenticated():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Claude OAuth token is missing")
    return True


def is_codex_authenticated() -> bool:
    path = get_settings().codex_auth_path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(isinstance(data.get("tokens"), dict) and data["tokens"])


async def check_codex() -> bool:
    if not is_codex_authenticated():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Codex CLI login is missing")
    return True


async def verify_github(request: Request, x_hub_signature_256: Annotated[str | None, Header()] = None) -> bool:
    if not x_hub_signature_256 or not x_hub_signature_256.startswith("sha256="):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing signature")

    secret = get_settings().gh_secret.get_secret_value().encode("utf-8")
    expected = "sha256=" + hmac.new(secret, await request.body(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_hub_signature_256):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
    return True
