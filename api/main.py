from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException

from pydantic import ValidationError

from schemas import Github
from src.broker import broker
from src.deps import check_claude, check_codex, verify_github
from src.processing import start_agentic_pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    await broker.startup()
    yield
    await broker.shutdown()


app = FastAPI(lifespan=lifespan)


@app.post("/github", dependencies=[Depends(check_codex), Depends(check_claude), Depends(verify_github)])
async def start_agent(payload: dict, x_github_event: Annotated[str | None, Header()] = None):
    if x_github_event == "ping":
        return {"status": "pong"}
    if x_github_event != "issues":
        return {"status": "skipped"}

    try:
        issue_event = Github.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Invalid issues payload") from exc
    if (
        issue_event.action != "labeled"
        or issue_event.label is None
        or issue_event.label.name != "ai"
        or issue_event.issue.pull_request is not None
    ):
        return {"status": "skipped"}

    await start_agentic_pipeline.kiq(issue_event.model_dump(mode="json"))
    return {"status": "started agent"}
