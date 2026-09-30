from schemas import construct_claude_prompt, construct_codex_prompt


def test_claude_prompt_assigns_implementation_without_tests(payload):
    prompt = construct_claude_prompt(payload, "Checkout still fails for empty cart")
    assert "Fix checkout" in prompt
    assert "MUST NOT create, edit, or delete any test files" in prompt
    assert "Checkout still fails for empty cart" in prompt
    assert "missing tools" in prompt


def test_codex_prompt_requires_behavior_tests_and_explicit_verdict(payload):
    prompt = construct_codex_prompt(payload)
    assert "Do not change production code" in prompt
    assert "observable behavior" in prompt
    assert "do not write tests that only inspect source text" in prompt
    assert "JSON object matching the supplied output schema" in prompt
    assert "actual test commands" in prompt
