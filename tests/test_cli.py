import json
from pathlib import Path

import pytest

import tpg.cli as cli
from tpg.llm import LLMError
from tpg.models import Gap, Requirement, Source, TestPlan

FIX = Path(__file__).parent / "fixtures"
SRC = Source(path="s", sha256="0", generated_at="t", model="m")


class StubLLM:
    def __init__(self, *a, **k):
        pass

    def check(self):
        pass


def _stub_run(plan):
    return lambda path, llm, model, clause_ids=None, attempts=3, log=None: plan


def test_exit_0_and_writes_json(tmp_path, monkeypatch):
    out = tmp_path / "plan.json"
    plan = TestPlan(source=SRC, requirements=[], test_cases=[], traceability=[], gaps=[])
    monkeypatch.setattr(cli, "OllamaLLM", StubLLM)
    monkeypatch.setattr(cli, "run", _stub_run(plan))
    assert cli.main(["generate", str(FIX / "sample.md"), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["gaps"] == []


def test_exit_2_when_gaps(tmp_path, monkeypatch):
    gap = Gap(requirement_id=None, clause_id="5.1", stage="extract", reason="x", attempts=3)
    plan = TestPlan(source=SRC, requirements=[], test_cases=[], traceability=[], gaps=[gap])
    monkeypatch.setattr(cli, "OllamaLLM", StubLLM)
    monkeypatch.setattr(cli, "run", _stub_run(plan))
    assert cli.main(["generate", str(FIX / "sample.md"), "--out", str(tmp_path / "p.yaml"), "--format", "yaml"]) == 2
    assert (tmp_path / "p.yaml").exists()


def test_exit_1_when_ollama_unreachable(tmp_path, monkeypatch, capsys):
    class Down(StubLLM):
        def check(self):
            raise LLMError("cannot reach Ollama")

    monkeypatch.setattr(cli, "OllamaLLM", Down)
    assert cli.main(["generate", str(FIX / "sample.md"), "--out", str(tmp_path / "p.json")]) == 1
    assert "cannot reach Ollama" in capsys.readouterr().err


def test_exit_1_when_input_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "OllamaLLM", StubLLM)
    assert cli.main(["generate", str(tmp_path / "missing.pdf"), "--out", str(tmp_path / "p.json")]) == 1
    assert "missing.pdf" in capsys.readouterr().err


def test_clauses_flag_is_split_and_passed(tmp_path, monkeypatch):
    seen = {}

    def fake_run(path, llm, model, clause_ids=None, attempts=3, log=None):
        seen["clause_ids"] = clause_ids
        seen["model"] = model
        return TestPlan(source=SRC, requirements=[], test_cases=[], traceability=[], gaps=[])

    monkeypatch.setattr(cli, "OllamaLLM", StubLLM)
    monkeypatch.setattr(cli, "run", fake_run)
    cli.main(["generate", str(FIX / "sample.md"), "--out", str(tmp_path / "p.json"),
              "--clauses", "5.1,5.2", "--model", "other:7b"])
    assert seen == {"clause_ids": ["5.1", "5.2"], "model": "other:7b"}


def test_default_model():
    assert cli.DEFAULT_MODEL == "gemma4:31b"
