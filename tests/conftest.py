from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"


class FakeLLM:
    """Scripted stand-in for OllamaLLM. Each response is a dict validated against the requested schema,
    or an Exception to raise. When the script is exhausted, `fallback` (a dict) is used if given.
    Records prompts so tests can assert on retry feedback."""

    def __init__(self, responses, fallback=None):
        self.responses = list(responses)
        self.fallback = fallback
        self.prompts: list[str] = []

    def complete(self, prompt, schema):
        self.prompts.append(prompt)
        if not self.responses:
            if self.fallback is None:
                raise AssertionError("FakeLLM ran out of responses")
            return schema.model_validate(self.fallback)
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
