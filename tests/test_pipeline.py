import hashlib
from pathlib import Path

from tpg.pipeline import run

FIX = Path(__file__).parent / "fixtures"

REQ_51 = {"requirements": [
    {"text": "The device shall respond to any request within 500 ms.", "modality": "shall", "conditions": [],
     "source_quote": "The device shall respond to any request within 500 ms."},
    {"text": "The device may log the request.", "modality": "may", "conditions": [],
     "source_quote": "The device may log the request."},
]}
REQ_52 = {"requirements": [
    {"text": "If the request is malformed or the session has expired, the device shall not process the request.",
     "modality": "shall_not", "conditions": ["request is malformed", "session has expired"],
     "source_quote": "the device shall not process the request"},
    {"text": "If the request is malformed or the session has expired, the device should return an error code.",
     "modality": "should", "conditions": ["request is malformed", "session has expired"],
     "source_quote": "should return an error code"},
]}
NOM = {"kind": "nominal", "objective": "o", "steps": ["s"], "expected_result": "r", "pass_criteria": "p"}
NEG = {**NOM, "kind": "negative"}
COND = ["request is malformed", "session has expired"]
TC_PLAIN_SHALL = {"test_cases": [NOM, NEG]}
TC_PLAIN_MAY = {"test_cases": [NOM]}
TC_COND = {"test_cases": [
    {**NOM, "condition_assignment": {COND[0]: True, COND[1]: True}},
    {**NEG, "condition_assignment": {COND[0]: False, COND[1]: True}},
    {**NEG, "condition_assignment": {COND[0]: True, COND[1]: False}},
]}


def test_run_end_to_end_with_fake(fake_llm):
    llm = fake_llm([REQ_51, REQ_52, TC_PLAIN_SHALL, TC_PLAIN_MAY, TC_COND, TC_COND])
    lines = []
    plan = run(str(FIX / "sample.md"), llm, model="fake", log=lines.append)
    assert [r.id for r in plan.requirements] == ["REQ-5.1-1", "REQ-5.1-2", "REQ-5.2-1", "REQ-5.2-2"]
    assert len(plan.test_cases) == 2 + 1 + 3 + 3
    assert plan.gaps == []
    assert plan.source.model == "fake"
    assert plan.source.sha256 == hashlib.sha256((FIX / "sample.md").read_bytes()).hexdigest()
    assert plan.source.generated_at.endswith("Z")
    assert any("5.1" in l for l in lines)


def test_run_clause_filter(fake_llm):
    llm = fake_llm([REQ_52, TC_COND, TC_COND])
    plan = run(str(FIX / "sample.md"), llm, model="fake", clause_ids=["5.2"])
    assert {r.clause_id for r in plan.requirements} == {"5.2"}
    assert len(llm.prompts) == 3


def test_run_unknown_clause_filter_raises(fake_llm):
    import pytest
    with pytest.raises(ValueError, match="9.9"):
        run(str(FIX / "sample.md"), fake_llm([]), model="fake", clause_ids=["9.9"])
