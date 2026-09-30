from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

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
async def start_agent(payload: Github):
    if (
        payload.action != "labeled"
        or payload.label is None
        or payload.label.name != "ai"
        or payload.issue.pull_request is not None
    ):
        return {"status": "skipped"}

    await start_agentic_pipeline.kiq(payload.model_dump(mode="json"))
    return {"status": "started agent"}
