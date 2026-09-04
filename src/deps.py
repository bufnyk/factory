from fastapi import status, HTTPException, Request, Header
from config import get_settings
import hashlib
import hmac
from typing import Annotated, Sequence
import asyncio

settings = get_settings()

async def check_ai(name: str = "LLM", phrases: Sequence[str] = ["Accessing workspace:", "Do you trust the contents of this directory?"]) -> bool:

    process = await asyncio.create_subprocess_exec(
        name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        stdin=asyncio.subprocess.DEVNULL,
    )

    try:

        async with asyncio.timeout(4.0):
            output_text = ""

            while True:
                line = await process.stdout.readline()
                if not line:
                    break

                text = line.decode("utf-8", errors="replace")
                output_text += text

                for phrase in phrases:
                    if phrase in output_text:
                        return True

                if (
                    "login" in output_text.lower()
                    or "unauthorized" in output_text.lower()
                ):
                    #TO DO 
                    #jakaś logika powiadomienia jesli brak sesji
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=f"{name} session expired"
                    )
    #Tutaj jakaś logika retry        
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"{name} did not respond in time"
        )

    finally:
        process.kill()
        await process.wait()
        
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"{name} session expired"
    )

async def check_codex():
    await check_ai("codex", ("You are in", "Do you trust the contents of this directory?"))

async def check_claude():
    await check_ai("claude", ("Accessing workspace:", "Quick safety check:"))

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
    