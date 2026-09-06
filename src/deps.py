from fastapi import status, HTTPException, Request, Header
from config import get_settings
import hashlib
import hmac
from typing import Annotated
import json
from pathlib import Path

settings = get_settings()
CLAUDE_CONFIG = Path.home() / ".claude.json"
CODEX_AUTH_PATH = Path.home() / ".codex" / "auth.json"

def is_claude_authenticated() -> bool:
    if not CLAUDE_CONFIG.is_file():
        return False
    try:
        data = json.loads(CLAUDE_CONFIG.read_text(encoding="utf-8"))
        oauth = data.get("oauthAccount")
        return bool(oauth and oauth.get("accountUuid"))
    except (json.JSONDecodeError, OSError):
        return False


async def check_claude() -> bool:
    if not is_claude_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Claude session expired or unauthenticated",
        )
    return True

def is_codex_authenticated() -> bool:
    if not CODEX_AUTH_PATH.is_file():
        return False

    try:
        data = json.loads(CODEX_AUTH_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False

    if data.get("OPENAI_API_KEY"):
        return True

    tokens = data.get("tokens")
    if isinstance(tokens, dict) and len(tokens) > 0:
        return True

    return False


async def check_codex() -> bool:
    if not is_codex_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Codex session expired or missing tokens in ~/.codex/auth.json",
        )
    return True

async def verify_github(request: Request, x_hub_signature_256: Annotated[str | None, Header()] = None) -> bool:

    if not x_hub_signature_256 or not x_hub_signature_256.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing signature"
        )

    expected_signature = (
        "sha256="
        + hmac.new(
            settings.gh_secret.encode("utf-8"),
            await request.body(),
            hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(expected_signature, x_hub_signature_256):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature"
        )
    
    return True
    