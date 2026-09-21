from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"


class FakeLLM:
    """Scripted stand-in for OllamaLLM. Each response is a dict validated against the requested schema,
    or an Exception to raise. Records prompts so tests can assert on retry feedback."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts: list[str] = []

    def complete(self, prompt, schema):
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError("FakeLLM ran out of responses")
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return schema.model_validate(r)


@pytest.fixture(autouse=True)
def _clear_ollama_env(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)


@pytest.fixture
def fake_llm():
    return FakeLLM
