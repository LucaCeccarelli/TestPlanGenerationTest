import os

import pytest
from pydantic import BaseModel

from tpg.llm import LLMError, OllamaLLM, clean_json, load_dotenv


class Out(BaseModel):
    a: int


def test_clean_json_strips_fences_and_prose():
    raw = 'Sure! Here you go:\n```json\n{"a": 1}\n```\nHope this helps.'
    assert clean_json(raw) == '{"a": 1}'


def test_clean_json_handles_arrays_and_nested_braces():
    assert clean_json('x [ {"a": {"b": 1}} ] y') == '[ {"a": {"b": 1}} ]'


def test_clean_json_ignores_braces_inside_strings():
    assert clean_json('{"a": "}", "b": 1}') == '{"a": "}", "b": 1}'


def test_clean_json_raises_when_nothing_found():
    with pytest.raises(LLMError):
        clean_json("no json here")


def test_load_dotenv_sets_but_does_not_override(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nOLLAMA_API_KEY=abc\nEXISTING=new\n\nQUOTED='q v'\n")
    monkeypatch.setenv("EXISTING", "old")
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    load_dotenv(str(env))
    assert os.environ["OLLAMA_API_KEY"] == "abc"
    assert os.environ["EXISTING"] == "old"
    assert os.environ["QUOTED"] == "q v"


def test_load_dotenv_missing_file_is_noop(tmp_path):
    load_dotenv(str(tmp_path / "nope"))


def test_complete_parses_valid_reply(monkeypatch):
    llm = OllamaLLM(model="m", host="http://x")
    monkeypatch.setattr(llm, "_chat", lambda prompt, schema: '```json\n{"a": 2}\n```')
    assert llm.complete("p", Out) == Out(a=2)


def test_complete_raises_llmerror_on_schema_violation(monkeypatch):
    llm = OllamaLLM(model="m", host="http://x")
    monkeypatch.setattr(llm, "_chat", lambda prompt, schema: '{"a": "not an int"}')
    with pytest.raises(LLMError):
        llm.complete("p", Out)


def test_complete_wraps_transport_errors(monkeypatch):
    llm = OllamaLLM(model="m", host="http://x")

    def boom(prompt, schema):
        raise ConnectionError("down")

    monkeypatch.setattr(llm, "_chat", boom)
    with pytest.raises(LLMError):
        llm.complete("p", Out)


def test_bearer_header_only_when_key_given():
    assert "Authorization" not in OllamaLLM(model="m", host="http://x").headers
    assert OllamaLLM(model="m", host="http://x", api_key="k").headers["Authorization"] == "Bearer k"
