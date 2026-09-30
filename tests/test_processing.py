from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from config import Settings
from src import processing


class FakeVolume:
    name = "job-volume"

    def __init__(self):
        self.removed = False

    def remove(self, force=False):
        self.removed = True


class FakeAgent:
    def __init__(self):
        self.removed = False

    def remove(self, force=False):
        self.removed = True


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    volume = FakeVolume()
    agent = FakeAgent()
    client = SimpleNamespace(
        volumes=SimpleNamespace(create=lambda **kwargs: volume),
        containers=SimpleNamespace(run=lambda *args, **kwargs: agent),
    )
    monkeypatch.setattr(processing.docker, "from_env", lambda **kwargs: client)
    monkeypatch.setattr(processing, "_helper", lambda *args, **kwargs: "")
    monkeypatch.setattr(processing, "_install_dependencies", lambda *args: None)
    monkeypatch.setattr(processing, "_copy_codex_auth", lambda *args: None)
    monkeypatch.setattr(processing, "_remove_codex_auth", lambda *args: None)
    monkeypatch.setattr(processing, "_workspace_snapshot", lambda *args: {})
    settings = Settings(gh_secret=SecretStr("hook"), github_token=SecretStr("gh-token"), claude_setup_token=SecretStr("claude"), codex_auth_path=tmp_path / "auth.json")
    return settings, volume, agent


def test_passed_review_creates_pr_and_cleans_up(monkeypatch, pipeline, payload):
    settings, volume, agent = pipeline
    calls = []

    def run(container, role, command, settings):
        calls.append(role)
        return {"Claude": "implementation done", "Codex": "Tests passed\nVERDICT: PASS", "Git": " M app.py"}[role]

    monkeypatch.setattr(processing, "_exec_agent", run)
    snapshots = iter([{}, {"src/app.py": "code"}, {"src/app.py": "code"}, {"src/app.py": "code", "tests/test_app.py": "test"}])
    monkeypatch.setattr(processing, "_workspace_snapshot", lambda *args: next(snapshots))
    monkeypatch.setattr(processing, "create_pull_request", lambda *args: "https://github.com/example/shop/pull/3")

    assert processing._run_pipeline(payload, settings).endswith("/pull/3")
    assert calls == ["Claude", "Codex", "Git"]
    assert volume.removed and agent.removed


def test_failed_review_returns_feedback_to_claude_and_does_not_publish(monkeypatch, pipeline, payload):
    settings, volume, agent = pipeline
    prompts = []

    def run(container, role, command, settings):
        if role == "Claude":
            prompts.append(command[2])
            return "implementation done"
        return "Checkout returns 500 for empty cart\nVERDICT: FAIL"

    monkeypatch.setattr(processing, "_exec_agent", run)
    monkeypatch.setattr(processing, "create_pull_request", lambda *args: pytest.fail("PR must not be created"))

    with pytest.raises(processing.PipelineError, match="did not approve"):
        processing._run_pipeline(payload, settings)
    assert len(prompts) == 2
    assert "Checkout returns 500 for empty cart" in prompts[1]
    assert volume.removed and agent.removed


def test_role_guard_rejects_test_changes_by_claude():
    with pytest.raises(processing.PipelineError, match="Claude changed test files"):
        processing._enforce_role({}, {"tests/test_checkout.py": "hash"}, "Claude")


def test_role_guard_rejects_production_changes_by_codex():
    with pytest.raises(processing.PipelineError, match="Codex changed production files"):
        processing._enforce_role({"src/checkout.py": "old"}, {"src/checkout.py": "new"}, "Codex")


def test_role_guard_accepts_codex_behavior_test_changes():
    processing._enforce_role({"src/checkout.py": "same"}, {"src/checkout.py": "same", "tests/test_checkout.py": "new"}, "Codex")


def test_review_cannot_pass_without_writing_behavior_tests(monkeypatch, pipeline, payload):
    settings, _, _ = pipeline
    monkeypatch.setattr(processing, "_exec_agent", lambda *args: "VERDICT: PASS")
    monkeypatch.setattr(processing, "create_pull_request", lambda *args: pytest.fail("PR must not be created"))
    with pytest.raises(processing.PipelineError, match="without creating or updating a behavior test"):
        processing._run_pipeline(payload, settings)
