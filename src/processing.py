import asyncio
import io
import json
import logging
import tarfile
from uuid import uuid4

import docker
from pydantic import ValidationError

from config import Settings, get_settings
from schemas import CodexReview, Github, construct_claude_prompt, construct_codex_prompt
from src.broker import broker
from src.github import comment_on_issue, create_pull_request, mark_problem_on_gh

logger = logging.getLogger(__name__)
RUNTIME_IMAGE = "factory-runtime:local"
MAX_REPORT = 12000


class PipelineError(RuntimeError):
    pass


def _redact(message: str, settings: Settings) -> str:
    for secret in (settings.github_token, settings.claude_setup_token, settings.gh_secret):
        value = secret.get_secret_value()
        if value:
            message = message.replace(value, "[redacted]")
    return message[:MAX_REPORT]


def _decode(output: bytes | str | None) -> str:
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output or ""


def _helper(client, volume: str, command: str, settings: Settings, **variables: str) -> str:
    container = client.containers.run(
        RUNTIME_IMAGE,
        command=["sh", "-lc", command],
        volumes={volume: {"bind": "/workspace", "mode": "rw"}},
        environment={
            "GITHUB_TOKEN": settings.github_token.get_secret_value(),
            "GIT_ASKPASS": "/usr/local/bin/github-askpass",
            "GIT_TERMINAL_PROMPT": "0",
            **variables,
        },
        user="root",
        detach=True,
    )
    try:
        status = container.wait()["StatusCode"]
        output = _decode(container.logs())
        if status:
            raise PipelineError(f"Git step failed (exit {status}): {_redact(output, settings)}")
        return output
    finally:
        container.remove(force=True)


def _agent_result(raw: str, agent: str) -> str:
    if agent == "Claude":
        try:
            return json.loads(raw).get("result", raw)
        except json.JSONDecodeError:
            return raw
    if agent != "Codex":
        return raw
    final = ""
    completed = False
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") in {"turn.failed", "error"}:
            raise PipelineError("Codex reported a failed turn")
        if event.get("type") == "turn.completed":
            completed = True
        item = event.get("item", {})
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            final = item.get("text", final)
    if not completed or not final:
        raise PipelineError("Codex did not return a completed review")
    return final


def _exec_agent(container, agent: str, command: list[str], settings: Settings) -> str:
    environment = {"CLAUDE_CODE_OAUTH_TOKEN": settings.claude_setup_token.get_secret_value()} if agent == "Claude" else None
    result = container.exec_run(command, workdir="/workspace", environment=environment)
    output = _decode(result.output)
    if result.exit_code:
        raise PipelineError(f"{agent} failed (exit {result.exit_code}): {_redact(output, settings)}")
    return _agent_result(output, agent)


def _install_dependencies(container, settings: Settings) -> None:
    script = """set -eu
VENV_PYTHON=/home/node/.venv/bin/python
if [ -f requirements.txt ]; then "$VENV_PYTHON" -m pip install -r requirements.txt;
elif [ -f requirements.in ]; then "$VENV_PYTHON" -m pip install -r requirements.in;
elif [ -f pyproject.toml ]; then "$VENV_PYTHON" -m pip install -e .; fi
if [ -f package.json ]; then
  if [ -f package-lock.json ]; then npm ci; else npm install --no-package-lock; fi
fi
if [ -f go.mod ]; then go mod download; fi
if [ -f Cargo.toml ]; then cargo fetch; fi
"""
    result = container.exec_run(["sh", "-c", script], workdir="/workspace")
    if result.exit_code:
        raise PipelineError(f"Dependency installation failed (exit {result.exit_code}): {_redact(_decode(result.output), settings)}")


def _copy_codex_auth(container, settings: Settings) -> None:
    auth = settings.codex_auth_path.read_bytes()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        info = tarfile.TarInfo("auth.json")
        info.size = len(auth)
        info.mode = 0o600
        info.uid = info.gid = 1000
        tar.addfile(info, io.BytesIO(auth))
    if not container.put_archive("/home/node/.codex", archive.getvalue()):
        raise PipelineError("Could not copy Codex login into agent container")


def _remove_codex_auth(container) -> None:
    result = container.exec_run(["rm", "-f", "/home/node/.codex/auth.json"])
    if result.exit_code:
        raise PipelineError("Could not remove Codex login from agent container")


SNAPSHOT_SCRIPT = """import hashlib, json, os
skip = {'.git', 'node_modules', '.venv', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'target', 'dist', 'build', '.next', 'coverage', 'test-results'}
files = {}
for root, dirs, names in os.walk('/workspace'):
    dirs[:] = [name for name in dirs if name not in skip]
    for name in names:
        path = os.path.join(root, name)
        if name == '.coverage' or os.path.islink(path):
            continue
        try:
            with open(path, 'rb') as source:
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
            files[os.path.relpath(path, '/workspace')] = digest
        except OSError:
            pass
print(json.dumps(files))
"""


def _workspace_snapshot(container, settings: Settings) -> dict[str, str]:
    result = container.exec_run(["python3", "-c", SNAPSHOT_SCRIPT], workdir="/workspace")
    if result.exit_code:
        raise PipelineError(f"Could not inspect workspace: {_redact(_decode(result.output), settings)}")
    return json.loads(_decode(result.output))


def _is_test_file(path: str) -> bool:
    parts = path.lower().split("/")
    name = parts[-1]
    return (
        any(part in {"tests", "test", "__tests__", "spec"} for part in parts[:-1])
        or name.startswith("test_")
        or name.endswith(("_test.py", "_test.go"))
        or ".test." in name
        or ".spec." in name
    )


def _enforce_role(before: dict[str, str], after: dict[str, str], agent: str) -> set[str]:
    changed = {path for path in before.keys() | after.keys() if before.get(path) != after.get(path)}
    forbidden = sorted(path for path in changed if _is_test_file(path) == (agent == "Claude"))
    if forbidden:
        category = "test files" if agent == "Claude" else "production files"
        raise PipelineError(f"{agent} changed {category} outside its role: {', '.join(forbidden[:20])}")
    return changed


def _run_pipeline(payload: Github, settings: Settings) -> str:
    client = docker.from_env(timeout=3600)
    volume = client.volumes.create(name=f"factory_{payload.issue.id}_{uuid4().hex[:8]}")
    agent = None
    branch = f"factory/issue-{payload.issue.number}-{uuid4().hex[:8]}"
    try:
        _helper(
            client, volume.name,
            'git clone "$REPOSITORY_URL" /workspace && git -C /workspace switch -c "$BRANCH" && printf "\nnode_modules/\n__pycache__/\n.pytest_cache/\n.coverage\n.venv/\ntarget/\ndist/\nbuild/\n.next/\ncoverage/\ntest-results/\n" >> /workspace/.git/info/exclude && chown -R 1000:1000 /workspace',
            settings,
            REPOSITORY_URL=payload.repository.html_url,
            BRANCH=branch,
        )
        agent = client.containers.run(
            RUNTIME_IMAGE,
            command=["sleep", "infinity"],
            working_dir="/workspace",
            volumes={volume.name: {"bind": "/workspace", "mode": "rw"}},
            user="node",
            pids_limit=512,
            mem_limit="4g",
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            detach=True,
        )
        _install_dependencies(agent, settings)
        review_feedback = ""
        approved_review = None
        tests_written = False
        for _ in range(settings.loop_limit // 2):
            before_claude = _workspace_snapshot(agent, settings)
            _exec_agent(
                agent, "Claude",
                ["claude", "-p", construct_claude_prompt(payload, review_feedback), "--model", settings.claude_model, "--effort", settings.claude_effort, "--output-format", "json", "--dangerously-skip-permissions"],
                settings,
            )
            _enforce_role(before_claude, _workspace_snapshot(agent, settings), "Claude")
            before_codex = _workspace_snapshot(agent, settings)
            _copy_codex_auth(agent, settings)
            try:
                review_output = _exec_agent(
                    agent, "Codex",
                    ["codex", "exec", "--model", settings.codex_model, "--config", f"model_reasoning_effort={settings.codex_reasoning_effort}", "--json", "--dangerously-bypass-approvals-and-sandbox", "--output-schema", "/opt/factory/codex-review.schema.json", construct_codex_prompt(payload)],
                    settings,
                )
            finally:
                _remove_codex_auth(agent)
            changed_by_codex = _enforce_role(before_codex, _workspace_snapshot(agent, settings), "Codex")
            tests_written |= any(_is_test_file(path) for path in changed_by_codex)
            try:
                review = CodexReview.model_validate_json(review_output)
            except ValidationError as exc:
                raise PipelineError(f"Codex returned an invalid structured review: {_redact(str(exc), settings)}") from exc
            review_feedback = review.feedback()
            if review.verdict == "PASS" and review.tests_passed and review.test_commands:
                approved_review = review
                break
        else:
            raise PipelineError(f"Codex did not approve after {settings.loop_limit // 2} reviews. Last review:\n{_redact(review_feedback, settings)}")

        if not tests_written:
            raise PipelineError("Codex approved without creating or updating a behavior test")

        status = _exec_agent(agent, "Git", ["git", "status", "--porcelain"], settings)
        if not status.strip():
            raise PipelineError("Agents completed without changing any files")
        _helper(
            client, volume.name,
            'git config --global --add safe.directory /workspace && git -C /workspace config user.name "AI Factory" && git -C /workspace config user.email "ai-factory@users.noreply.github.com" && git -C /workspace add -A && git -C /workspace commit -m "Fix issue #$ISSUE_NUMBER" && git -C /workspace push origin "$BRANCH"',
            settings,
            ISSUE_NUMBER=str(payload.issue.number),
            BRANCH=branch,
        )
        return create_pull_request(payload, settings, branch, _redact(approved_review.feedback(), settings))
    finally:
        if agent is not None:
            agent.remove(force=True)
        volume.remove(force=True)


@broker.task
async def start_agentic_pipeline(payload_data: dict) -> None:
    payload = Github.model_validate(payload_data)
    settings = get_settings()
    try:
        pr_url = await asyncio.to_thread(_run_pipeline, payload, settings)
    except Exception as exc:
        message = _redact(str(exc), settings)
        logger.exception("Factory failed for issue %s", payload.issue.number)
        await asyncio.to_thread(mark_problem_on_gh, payload, settings, message)
        raise
    await asyncio.to_thread(comment_on_issue, payload, settings, f"AI factory completed the issue: {pr_url}")
