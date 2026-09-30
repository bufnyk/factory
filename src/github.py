import httpx

from config import Settings
from schemas import Github


def _client(settings: Settings) -> httpx.Client:
    return httpx.Client(
        base_url="https://api.github.com",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {settings.github_token.get_secret_value()}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
    )


def mark_problem_on_gh(payload: Github, settings: Settings, message: str) -> None:
    comment_on_issue(payload, settings, f"AI factory could not complete this issue.\n\n{message}")


def comment_on_issue(payload: Github, settings: Settings, message: str) -> None:
    url = f"/repos/{payload.repository.full_name}/issues/{payload.issue.number}/comments"
    with _client(settings) as client:
        response = client.post(url, json={"body": message})
        response.raise_for_status()


def create_pull_request(payload: Github, settings: Settings, branch: str, review: str) -> str:
    url = f"/repos/{payload.repository.full_name}/pulls"
    with _client(settings) as client:
        response = client.post(
            url,
            json={
                "title": f"Fix #{payload.issue.number}: {payload.issue.title}",
                "head": branch,
                "base": payload.repository.default_branch,
                "body": f"Closes #{payload.issue.number}\n\nCodex review and behavior tests:\n\n{review[:12000]}",
            },
        )
        response.raise_for_status()
        return response.json()["html_url"]
