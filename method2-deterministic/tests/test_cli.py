import json
import os
from pathlib import Path

import pytest

import tpg.cli as cli
from tests.test_pipeline import OBJ_54_PROSE, REQ_51, REQ_52, REQ_54, TC, BatchLLM
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
    return lambda path, llm, model, **kw: plan


def test_exit_0_and_writes_json(tmp_path, monkeypatch):
    out = tmp_path / "plan.json"
    plan = TestPlan(source=SRC, requirements=[], test_cases=[], traceability=[], gaps=[])
    monkeypatch.setattr(cli, "OllamaLLM", StubLLM)
    monkeypatch.setattr(cli, "run", _stub_run(plan))
    assert cli.main(["generate", str(FIX / "sample.md"), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["gaps"] == []


def test_exit_2_when_gaps(tmp_path, monkeypatch):
    gap = Gap(source_id=None, clause_id="5.1", stage="extract", reason="x", attempts=3)
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

    def fake_run(path, llm, model, clause_ids=None, **kw):
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


def test_exit_1_when_input_unreadable(tmp_path, monkeypatch, capsys):
    calls = []

    class Counting(StubLLM):
        def check(self):
            calls.append(1)

    locked = tmp_path / "locked.md"
    locked.write_text("x")
    locked.chmod(0)
    if os.access(locked, os.R_OK):
        pytest.skip("running as root; cannot make a file unreadable")
    monkeypatch.setattr(cli, "OllamaLLM", Counting)
    try:
        assert cli.main(["generate", str(locked), "--out", str(tmp_path / "p.json")]) == 1
    finally:
        locked.chmod(0o600)
    assert "locked.md" in capsys.readouterr().err
    assert calls == []


def test_exit_1_when_attempts_below_one(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "OllamaLLM", StubLLM)
    assert cli.main(["generate", str(FIX / "sample.md"), "--out", str(tmp_path / "p.json"), "--attempts", "0"]) == 1
    assert "attempts" in capsys.readouterr().err


def _unwritable_dir(tmp_path):
    d = tmp_path / "ro"
    d.mkdir()
    d.chmod(0o500)
    return d


@pytest.mark.parametrize("kind", ["missing_dir", "unwritable_dir"])
def test_exit_1_before_any_model_call_when_output_unwritable(tmp_path, monkeypatch, capsys, kind):
    """The six-hour failure mode: the whole run discarded by `cannot write` at the very end. The path
    is probed before the model is even reached, so the same message arrives in the first second."""
    reached = []
    monkeypatch.setattr(cli, "OllamaLLM", type("Counting", (StubLLM,), {"check": lambda self: reached.append("check")}))
    monkeypatch.setattr(cli, "run", lambda *a, **kw: reached.append("run"))
    if kind == "missing_dir":
        out = tmp_path / "no_such_dir" / "p.json"
    else:
        d = _unwritable_dir(tmp_path)
        if os.access(d, os.W_OK):
            pytest.skip("running as root; cannot make a directory unwritable")
        out = d / "p.json"
    assert cli.main(["generate", str(FIX / "sample.md"), "--out", str(out)]) == 1
    err = capsys.readouterr().err
    assert "cannot write" in err and str(out) in err
    assert reached == []


def test_the_output_probe_leaves_no_empty_plan_behind(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "OllamaLLM", StubLLM)
    monkeypatch.setattr(cli, "run", lambda *a, **kw: (_ for _ in ()).throw(ValueError("unknown clause ids: 9.9")))
    out = tmp_path / "p.json"
    assert cli.main(["generate", str(FIX / "sample.md"), "--out", str(out), "--clauses", "9.9"]) == 1
    assert not out.exists() and list(tmp_path.iterdir()) == []


def test_no_model_flag_is_passed(tmp_path, monkeypatch):
    seen = {}

    def fake_run(path, llm, model, use_model=True, **kw):
        seen["use_model"] = use_model
        return TestPlan(source=SRC, requirements=[], test_cases=[], traceability=[], gaps=[])

    monkeypatch.setattr(cli, "OllamaLLM", StubLLM)
    monkeypatch.setattr(cli, "run", fake_run)
    cli.main(["generate", str(FIX / "sample.md"), "--out", str(tmp_path / "p.json"), "--no-model"])
    assert seen == {"use_model": False}


def test_no_grammar_and_no_deflate_flags_are_passed(tmp_path, monkeypatch):
    seen = {}

    def fake_run(path, llm, model, **kw):
        seen.update(kw)
        return TestPlan(source=SRC, requirements=[], test_cases=[], traceability=[], gaps=[])

    monkeypatch.setattr(cli, "OllamaLLM", StubLLM)
    monkeypatch.setattr(cli, "run", fake_run)
    cli.main(["generate", str(FIX / "sample.md"), "--out", str(tmp_path / "p.json"), "--no-grammar", "--no-deflate"])
    assert (seen["use_grammar"], seen["deflate"], seen["use_model"], seen["batch"]) == (False, False, True, True)


def test_no_batch_flag_is_passed(tmp_path, monkeypatch):
    seen = {}

    def fake_run(path, llm, model, **kw):
        seen.update(kw)
        return TestPlan(source=SRC, requirements=[], test_cases=[], traceability=[], gaps=[])

    monkeypatch.setattr(cli, "OllamaLLM", StubLLM)
    monkeypatch.setattr(cli, "run", fake_run)
    cli.main(["generate", str(FIX / "sample.md"), "--out", str(tmp_path / "p.json"), "--no-batch"])
    assert seen["batch"] is False


# the object is the prose-quoted variant, so deflation rule (b) has something to remove and
# --no-deflate is observable on this document
SCRIPT = [REQ_51, REQ_52, REQ_54, {"objects": []}, {"objects": []}, OBJ_54_PROSE] + [{"objects": []}] * 3


def _real_run(tmp_path, monkeypatch, *flags):
    """cli.main over the real pipeline with the scripted fake, so a flag that never reaches its stage
    shows up as an unchanged plan. Returns the plan's counts plus the number of model calls."""
    llm = BatchLLM(list(SCRIPT), fallback=TC)
    monkeypatch.setattr(cli, "OllamaLLM", lambda model: llm)
    monkeypatch.setattr(llm, "check", lambda: None, raising=False)
    out = tmp_path / "plan.json"
    cli.main(["generate", str(FIX / "sample.md"), "--out", str(out), *flags])
    plan = json.loads(out.read_text())
    return {k: len(plan[k]) for k in ("requirements", "objects", "ics", "coverage_items", "test_cases")} | {"calls": len(llm.prompts)}


# --no-batch leaves the plan identical by design (Task 5 proved the two paths agree), so its effect is
# the call count; the other three change the plan itself.
FLAG_EFFECT = {
    "--no-model": lambda base, got: got["objects"] < base["objects"],
    "--no-grammar": lambda base, got: got["objects"] < base["objects"],
    "--no-deflate": lambda base, got: got["coverage_items"] > base["coverage_items"],
    "--no-batch": lambda base, got: got["calls"] > base["calls"],
}


@pytest.mark.parametrize("flag", list(FLAG_EFFECT))
def test_each_flag_changes_the_run(tmp_path, monkeypatch, flag):
    base = _real_run(tmp_path, monkeypatch)
    got = _real_run(tmp_path, monkeypatch, flag)
    assert FLAG_EFFECT[flag](base, got), (flag, base, got)


def test_summary_line_reports_every_count(tmp_path, monkeypatch, capsys):
    base = _real_run(tmp_path, monkeypatch)
    err = capsys.readouterr().err.splitlines()[-1]
    for n, word in [(base["requirements"], "requirements"), (base["objects"], "objects"), (base["ics"], "ICS items"),
                    (base["coverage_items"], "coverage items"), (base["test_cases"], "test cases")]:
        assert f"{n} {word}" in err, (word, err)
    assert "gaps" in err and "ICS coverage 100.0%" in err


def test_a_successful_run_leaves_only_the_plan(tmp_path, monkeypatch):
    """The sidecars of an interrupted run are dropped once the plan itself is on disk, so a finished
    run looks exactly as it looks today."""
    _real_run(tmp_path, monkeypatch)
    assert [p.name for p in tmp_path.iterdir()] == ["plan.json"]


def test_the_sidecars_survive_a_plan_that_cannot_be_serialised(tmp_path, monkeypatch, capsys):
    """write_plan is the last thing that can fail; when it does, the work stays recoverable."""
    monkeypatch.setattr(cli, "write_plan", lambda *a, **kw: (_ for _ in ()).throw(OSError(28, "No space left on device")))
    llm = BatchLLM(list(SCRIPT), fallback=TC)
    monkeypatch.setattr(cli, "OllamaLLM", lambda model: llm)
    monkeypatch.setattr(llm, "check", lambda: None, raising=False)
    out = tmp_path / "plan.json"
    assert cli.main(["generate", str(FIX / "sample.md"), "--out", str(out)]) == 1
    assert "No space left on device" in capsys.readouterr().err
    assert {p.name for p in tmp_path.iterdir()} == {"plan.json.partial.json", "plan.json.cases.jsonl"}
