from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class Label(BaseModel):
    name: str


class Issue(BaseModel):
    title: str
    body: str | None = None
    number: int
    id: int
    labels: list[Label] = Field(default_factory=list)
    pull_request: dict | None = None


class Repository(BaseModel):
    html_url: str
    full_name: str
    default_branch: str

    @field_validator("html_url")
    @classmethod
    def github_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.username or parsed.password:
            raise ValueError("Repository URL must be a GitHub HTTPS URL")
        return value


class Github(BaseModel):
    action: str
    issue: Issue
    repository: Repository
    label: Label | None = None


def construct_claude_prompt(payload: Github, review: str = "") -> str:
    return f"""You are implementing GitHub issue #{payload.issue.number} in the current repository.
Title: {payload.issue.title}
Description: {payload.issue.body or '(no description)'}

Implement the requested behavior in production code. You MUST NOT create, edit, or delete any test files or write unit tests. Codex owns all tests and review. You may inspect existing tests to understand behavior. Run application checks that do not create tests when useful.
The workspace is an isolated Docker container. Install missing tools or dependencies inside it if needed (use user-level package managers for missing dependencies). Keep changes scoped to the issue.
Previous Codex review, if any:
{review or '(first implementation pass)'}
At the end, summarize the implementation and any checks you ran."""


def construct_codex_prompt(payload: Github) -> str:
    return f"""Review the implementation of GitHub issue #{payload.issue.number} in the current repository.
Title: {payload.issue.title}
Description: {payload.issue.body or '(no description)'}

You are the reviewer and test author. Do not change production code. Review the diff and create or adjust tests that verify the requested FUNCTIONS and observable behavior. Tests must exercise real behavior or meaningful integration boundaries; do not write tests that only inspect source text, mock the function under test, or assert implementation details. Run the new tests and relevant existing tests. You may install missing dependencies inside this isolated Docker container (use user-level package managers for missing dependencies).
If behavior is wrong, report concrete failures and reproduction steps for Claude. Return a JSON object matching the supplied output schema. Set verdict to PASS only when the requested behavior works, you ran meaningful behavior tests, and they passed. Otherwise use FAIL. Include the actual test commands and findings."""


class CodexReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["PASS", "FAIL"]
    summary: str
    findings: list[str]
    test_commands: list[str]
    tests_passed: StrictBool

    def feedback(self) -> str:
        findings = "\n".join(f"- {item}" for item in self.findings) or "- none"
        commands = ", ".join(self.test_commands) or "none"
        return f"{self.summary}\nFindings:\n{findings}\nTests: {commands} (passed: {self.tests_passed})"
