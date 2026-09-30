import json
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
        calls.append((role, command))
        return {"Claude": "implementation done", "Codex": json.dumps({"verdict": "PASS", "summary": "Tests passed", "findings": [], "test_commands": ["pytest -q"], "tests_passed": True}), "Git": " M app.py"}[role]

    monkeypatch.setattr(processing, "_exec_agent", run)
    snapshots = iter([{}, {"src/app.py": "code"}, {"src/app.py": "code"}, {"src/app.py": "code", "tests/test_app.py": "test"}])
    monkeypatch.setattr(processing, "_workspace_snapshot", lambda *args: next(snapshots))
    created = []
    monkeypatch.setattr(processing, "create_pull_request", lambda *args, **kwargs: created.append(kwargs) or "https://github.com/example/shop/pull/3")

    result = processing._run_pipeline(payload, settings)
    assert result.pr_url.endswith("/pull/3")
    assert result.approved
    assert created == [{"draft": False}]
    assert [role for role, _ in calls] == ["Claude", "Codex", "Git"]
    assert calls[0][1][calls[0][1].index("--model") + 1] == "claude-opus-5-5"
    assert calls[0][1][calls[0][1].index("--effort") + 1] == "high"
    assert calls[1][1][calls[1][1].index("--model") + 1] == "gpt-6-sol"
    assert calls[1][1][calls[1][1].index("--config") + 1] == "model_reasoning_effort=high"
    assert volume.removed and agent.removed


def test_failed_review_creates_draft_pr_and_keeps_codex_feedback(monkeypatch, pipeline, payload):
    settings, volume, agent = pipeline
    prompts = []
    created = []

    def run(container, role, command, settings):
        if role == "Claude":
            prompts.append(command[2])
            return "implementation done"
        if role == "Git":
            return " M app.py"
        return json.dumps({"verdict": "FAIL", "summary": "Checkout returns 500 for empty cart", "findings": ["Boundary case fails"], "test_commands": ["pytest -q"], "tests_passed": False})

    def create_pr(*args, **kwargs):
        created.append((args, kwargs))
        return "https://github.com/example/shop/pull/3"

    monkeypatch.setattr(processing, "_exec_agent", run)
    snapshots = iter([
        {}, {"src/app.py": "first"}, {"src/app.py": "first"}, {"src/app.py": "first", "tests/test_app.py": "test"},
        {"src/app.py": "first", "tests/test_app.py": "test"}, {"src/app.py": "second", "tests/test_app.py": "test"},
        {"src/app.py": "second", "tests/test_app.py": "test"}, {"src/app.py": "second", "tests/test_app.py": "test"},
    ])
    monkeypatch.setattr(processing, "_workspace_snapshot", lambda *args: next(snapshots))
    monkeypatch.setattr(processing, "create_pull_request", create_pr)

    result = processing._run_pipeline(payload, settings)
    assert result.pr_url.endswith("/pull/3")
    assert not result.approved
    assert "Checkout returns 500 for empty cart" in result.review
    assert "Checkout returns 500 for empty cart" in prompts[1]
    assert created[0][1]["draft"] is True
    assert "did not approve after 2 reviews" in created[0][0][3]
    assert volume.removed and agent.removed


def test_role_guard_rejects_test_changes_by_claude():
    with pytest.raises(processing.PipelineError, match="Claude changed test files"):
        processing._enforce_role({}, {"tests/test_checkout.py": "hash"}, "Claude")


def test_role_guard_rejects_production_changes_by_codex():
    with pytest.raises(processing.PipelineError, match="Codex changed production files"):
        processing._enforce_role({"src/checkout.py": "old"}, {"src/checkout.py": "new"}, "Codex")


def test_role_guard_accepts_codex_behavior_test_changes():
    processing._enforce_role({"src/checkout.py": "same"}, {"src/checkout.py": "same", "tests/test_checkout.py": "new"}, "Codex")


def test_missing_behavior_tests_produces_unapproved_draft(monkeypatch, pipeline, payload):
    settings, _, _ = pipeline
    created = []

    def run(container, role, command, settings):
        if role == "Git":
            return " M src/app.py"
        return json.dumps({"verdict": "PASS", "summary": "Tests passed", "findings": [], "test_commands": ["pytest -q"], "tests_passed": True})

    monkeypatch.setattr(processing, "_exec_agent", run)
    snapshots = iter([
        {}, {"src/app.py": "first"}, {"src/app.py": "first"}, {"src/app.py": "first"},
        {"src/app.py": "first"}, {"src/app.py": "second"}, {"src/app.py": "second"}, {"src/app.py": "second"},
    ])
    monkeypatch.setattr(processing, "_workspace_snapshot", lambda *args: next(snapshots))
    monkeypatch.setattr(processing, "create_pull_request", lambda *args, **kwargs: created.append(kwargs) or "https://github.com/example/shop/pull/4")

    result = processing._run_pipeline(payload, settings)
    assert not result.approved
    assert "No behavior test was created or updated" in result.review
    assert created == [{"draft": True}]


def test_invalid_codex_result_never_approves(monkeypatch, pipeline, payload):
    settings, _, _ = pipeline
    monkeypatch.setattr(processing, "_exec_agent", lambda container, role, command, settings: "VERDICT: PASS")
    monkeypatch.setattr(processing, "create_pull_request", lambda *args: pytest.fail("PR must not be created"))
    with pytest.raises(processing.PipelineError, match="invalid structured review"):
        processing._run_pipeline(payload, settings)


def test_codex_jsonl_requires_completed_turn():
    message = json.dumps({"verdict": "PASS", "summary": "ok", "findings": [], "test_commands": ["pytest"], "tests_passed": True})
    event = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": message}})
    assert processing._agent_result(event + "\n" + json.dumps({"type": "turn.completed"}), "Codex") == message
    with pytest.raises(processing.PipelineError, match="completed review"):
        processing._agent_result(event, "Codex")
    with pytest.raises(processing.PipelineError, match="failed turn"):
        processing._agent_result(event + "\n" + json.dumps({"type": "turn.failed"}), "Codex")


@pytest.mark.asyncio
async def test_unapproved_pr_is_reported_in_issue_comment(monkeypatch, pipeline, payload):
    settings, _, _ = pipeline
    comments = []
    monkeypatch.setattr(processing, "get_settings", lambda: settings)
    monkeypatch.setattr(processing, "_run_pipeline", lambda *args: processing.PipelineResult(
        pr_url="https://github.com/example/shop/pull/3",
        approved=False,
        review="Codex did not approve. Last review: checkout returns 500",
    ))
    monkeypatch.setattr(processing, "comment_on_issue", lambda payload, settings, message: comments.append(message))

    await processing.start_agentic_pipeline.original_func(payload.model_dump(mode="json"))

    assert len(comments) == 1
    assert "draft PR without Codex approval" in comments[0]
    assert "/pull/3" in comments[0]
    assert "checkout returns 500" in comments[0]
