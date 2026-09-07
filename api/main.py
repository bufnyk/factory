from fastapi import FastAPI, Depends 
from taskiq import InMemoryBroker
from src.deps import check_claude, check_codex, verify_github
from schemas import Github
from contextlib import asynccontextmanager
from src.processing import start_agentic_pipline
from src.broker import broker

@asynccontextmanager
async def lifespan(app: FastAPI):
    await broker.startup()

    yield

    await broker.shutdown()

app = FastAPI(lifespan=lifespan)    

@app.post("/github", dependencies=[Depends(check_codex), Depends(check_claude), Depends(verify_github)])
async def start_agent(payload: Github):

    if payload.action != "labeled":
        return {"status": "skipped"}

    
    await start_agentic_pipline.kiq(payload)
    return {"status": "started agent"}

    