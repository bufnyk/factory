from src.broker import broker
from schemas import Github
from src.broker import docker_client
from config import get_settings, Settings

@broker.task
async def start_agentic_pipline(payload: Github):
    settings = get_settings()

    worksapce = create_workspace(payload, settings)

def mark_problem_on_gh(payload: Github, settings: Settings, message: str):
    pass

def create_workspace(payload: Github, settings: Settings):

    name = f"job_{payload.issue.number}"
    volume = docker_client.volumes.create(
        name=name
    )

    container = None

    try:
        container = docker_client.containers.run(
            image="alpine/git",
            command=[
                "git",
                "clone",
                payload.repository.html_url,
                "/workspace",
            ],
            volumes={
                name: {
                    "bind": "/workspace",
                    "mode": "rw",
                }
            },
            environment={"GITHUB_TOKEN": settings.gh_secret.get_secret_value()},
            detach=True,
        )

        if container.wait()["StatusCode"] != 0:
            volume.remove()
            mark_problem_on_gh(payload, settings, "There was a problem while cloning git repo")
            raise Exception
         

        return volume.name

    finally:
        if container is not None:
            container.remove()  

def run_claude()

