from src.broker import broker
from schemas import Github

@broker.task
async def start_agentic_pipline(payload: Github):
    pass
