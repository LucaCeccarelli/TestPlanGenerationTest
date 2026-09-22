import hashlib
from pathlib import Path

import pytest

from tpg.pipeline import run

FIX = Path(__file__).parent / "fixtures"

REQ_51 = {"requirements": [
    {"text": "The device shall respond to any request within 500 ms.", "modality": "shall", "conditions": [],
     "source_quote": "The device shall respond to any request within 500 ms."},
    {"text": "The device may log the request.", "modality": "may", "conditions": [], "source_quote": "The device may log the request."}]}
REQ_52 = {"requirements": [
    {"text": "If the request is malformed or the session has expired, the device shall not process the request.",
     "modality": "shall_not", "conditions": ["request is malformed", "session has expired"],
     "source_quote": "the device shall not process the request"}]}
REQ_54 = {"requirements": [{"text": "The reader shall reject a request whose nonce is missing.", "modality": "shall", "conditions": [],
                            "source_quote": "The reader shall reject a request whose nonce is missing."}]}
OBJ_54 = {"objects": [{"name": "nonce", "kind": "parameter", "direction": "received", "presence": "mandatory",
                       "type": "text string of 16 to 64 characters", "size": "16 to 64 characters",
                       "source_quote": "Name: nonce | Presence: mandatory | Type: text string of 16 to 64 characters"}]}
TC = {"objective": "o", "preconditions": [], "inputs": [], "steps": ["s"], "expected_result": "the request is rejected with an error",
      "pass_criteria": "error observed"}


def test_run_end_to_end_with_fake(fake_llm):
    # sample.md: clauses 1, 3, 5, 5.1, 5.2, 5.3, 5.4; candidates in 5.1, 5.2, 5.4; rows only in 5.4.
    llm = fake_llm([REQ_51, REQ_52, REQ_54, {"objects": []}, {"objects": []}, OBJ_54], fallback=TC)
    lines = []
    plan = run(str(FIX / "sample.md"), llm, model="fake", log=lines.append)
    assert [r.id for r in plan.requirements] == ["REQ-5.1-1", "REQ-5.1-2", "REQ-5.2-1", "REQ-5.4-1"]
    assert [o.id for o in plan.objects] == ["OBJ-5.4-1"]
    checks = [i.check for i in plan.coverage_items if i.source_id == "OBJ-5.4-1"]
    assert checks == ["presence", "absence", "encoding_valid", "encoding_invalid", "boundary_min", "boundary_max", "boundary_outside"]
    assert len(plan.test_cases) == len(plan.coverage_items) and plan.gaps == []
    assert {t.coverage_item_id for t in plan.test_cases} == {i.id for i in plan.coverage_items}
    assert plan.source.sha256 == hashlib.sha256((FIX / "sample.md").read_bytes()).hexdigest()
    assert any("coverage items" in l for l in lines)


def test_run_without_model_stage(fake_llm):
    llm = fake_llm([REQ_51, REQ_52, REQ_54], fallback=TC)
    plan = run(str(FIX / "sample.md"), llm, model="fake", use_model=False)
    assert plan.objects == [] and all(i.source_id.startswith("REQ-") for i in plan.coverage_items)


def test_run_clause_filter(fake_llm):
    llm = fake_llm([REQ_52, {"objects": []}], fallback=TC)
    plan = run(str(FIX / "sample.md"), llm, model="fake", clause_ids=["5.2"])
    assert {r.clause_id for r in plan.requirements} == {"5.2"}
    assert len(plan.coverage_items) == 3 and len(llm.prompts) == 2 + 3


def test_run_unknown_clause_filter_raises(fake_llm):
    with pytest.raises(ValueError, match="9.9"):
        run(str(FIX / "sample.md"), fake_llm([]), model="fake", clause_ids=["9.9"])
