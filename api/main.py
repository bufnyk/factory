from fastapi import FastAPI, Depends

from src.deps import check_claude, check_codex, verify_github
from schemas import Github

app = FastAPI()

@app.post("/github", dependencies=[Depends(check_codex), Depends(check_claude), Depends(verify_github)])
async def start_agent(payload: Github):

    if payload.action != "labeled":
        return {"status": "skipped"}

    return {"status": "started agent"}

    