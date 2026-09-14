from src.broker import broker
from schemas import Github, construct_claude_prompt, construct_codex_prompt
from src.broker import docker_client
from config import get_settings, Settings

@broker.task
async def start_agentic_pipline(payload: Github):
    settings = get_settings()

    worksapce = create_workspace(payload, settings)

def mark_problem_on_gh(payload: Github, settings: Settings, message: str):
    pass

def create_workspace(payload: Github, settings: Settings):

    name = f"job_{payload.issue.id}"
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
            logs = container.logs().decode()
            mark_problem_on_gh(payload, settings, f"logs: {str(logs)}")
            raise Exception
        
    finally:
        if container is not None:
            container.remove()  

    container = docker_client.containers.run(
        image="agent-runtime:latest",
        command=["sleep", "infinity"],
        working_dir="/workspace",
        volumes={
            volume.name: {
                "bind": "/workspace",
                "mode": "rw",
            }
        },
        environment={
            "CLAUDE_CODE_OAUTH_TOKEN": settings.claude_setup_token.get_secret_value(),
        },
        detach=True,
    )
    return container

def run_agentic_loop(payload: Github, container, settings: Settings):

    prompt_claude = construct_claude_prompt(payload)
    prompt_codex = construct_codex_prompt(payload)

    for i in range(4):
        if i % 2 == 0:
            run_claude(payload, container, settings, prompt_claude)
        else:
            run_codex(payload, container, settings, prompt_codex)


def run_claude(payload: Github, container, settings: Settings, prompt: str):
    result = container.exec_run(
            cmd=[
                "claude",
                "-p",
                prompt,
                "--model opus-5",
                "--output-format",
                "json",
            ],
            working_dir="/workspace",
        )
    
    if result.exit_code != 0:
        logs = container.logs().decode()
        container.remove()
        mark_problem_on_gh(payload, settings, f"logs: {str(logs)}")
        raise Exception

    return result.output

def run_codex(payload: Github, container, settings: Settings, prompt: str):
    result = container.exec_run(
                cmd=[
                    "claude",
                    "-p",
                    prompt,
                    "--model opus-5",
                    "--output-format",
                    "json",
                ],
                working_dir="/workspace",
            )
        
    if result.exit_code != 0:
        logs = container.logs().decode()
        container.remove()
        mark_problem_on_gh(payload, settings, f"logs: {str(logs)}")
        raise Exception
    
    return result.output




