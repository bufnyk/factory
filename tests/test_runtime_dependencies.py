import docker
import pytest
from pydantic import SecretStr

from config import Settings
from src.processing import RUNTIME_IMAGE, _install_dependencies


def test_python_requirements_install_in_runtime_venv(tmp_path):
    try:
        client = docker.from_env(timeout=10)
        client.ping()
        client.images.get(RUNTIME_IMAGE)
    except docker.errors.DockerException:
        pytest.skip("Docker runtime image is unavailable")

    container = client.containers.run(RUNTIME_IMAGE, command=["sleep", "infinity"], detach=True, user="node")
    try:
        created = container.exec_run(["sh", "-c", "printf 'pip\n' > requirements.txt"], workdir="/workspace", user="root")
        assert created.exit_code == 0
        settings = Settings(
            _env_file=None,
            gh_secret=SecretStr("hook"),
            github_token=SecretStr("github"),
            claude_setup_token=SecretStr("claude"),
            codex_auth_path=tmp_path / "auth.json",
        )
        _install_dependencies(container, settings)
        result = container.exec_run(
            ["sh", "-lc", "python -c 'import sys; assert sys.prefix != sys.base_prefix'"],
            workdir="/workspace",
        )
        assert result.exit_code == 0, result.output.decode(errors="replace")
    finally:
        container.remove(force=True)
