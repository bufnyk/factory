import pytest

from schemas import Github


@pytest.fixture
def payload():
    return Github.model_validate({
        "action": "labeled",
        "label": {"name": "ai"},
        "issue": {"id": 42, "number": 7, "title": "Fix checkout", "body": None, "labels": [{"name": "ai"}]},
        "repository": {
            "html_url": "https://github.com/example/shop",
            "full_name": "example/shop",
            "default_branch": "main",
        },
    })
