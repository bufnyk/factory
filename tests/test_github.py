import json

import httpx
from pydantic import SecretStr

from config import Settings
from src import github


def test_comment_targets_original_issue(monkeypatch, payload, tmp_path):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(201, json={"id": 99})

    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(github, "_client", lambda settings: httpx.Client(base_url="https://api.github.com", transport=transport))
    settings = Settings(gh_secret=SecretStr("hook"), github_token=SecretStr("gh-token"), claude_setup_token=SecretStr("claude"), codex_auth_path=tmp_path / "auth.json")

    github.mark_problem_on_gh(payload, settings, "Review failed: checkout returned 500")

    assert calls[0].url.path == "/repos/example/shop/issues/7/comments"
    assert "checkout returned 500" in calls[0].content.decode()


def test_unapproved_review_creates_draft_pull_request(monkeypatch, payload, tmp_path):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(201, json={"html_url": "https://github.com/example/shop/pull/3"})

    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(github, "_client", lambda settings: httpx.Client(base_url="https://api.github.com", transport=transport))
    settings = Settings(gh_secret=SecretStr("hook"), github_token=SecretStr("gh-token"), claude_setup_token=SecretStr("claude"), codex_auth_path=tmp_path / "auth.json")

    url = github.create_pull_request(payload, settings, "factory/issue-7", "Codex did not approve", draft=True)

    assert url.endswith("/pull/3")
    assert requests[0].url.path == "/repos/example/shop/pulls"
    assert json.loads(requests[0].content)["draft"] is True
