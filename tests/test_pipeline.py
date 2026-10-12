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


GRAMMAR_55 = ["label", "count", "mode", "token", "prefix", "suffix", "key", "flag", "name", "state", "note"]


def test_run_end_to_end_with_fake(fake_llm):
    # sample.md: clauses 1, 3, 5, 5.1, 5.2, 5.3, 5.4, 5.5; candidates in 5.1, 5.2, 5.4; rows only in 5.4;
    # formal declarations only in 5.5, which therefore costs no model-stage call.
    llm = fake_llm([REQ_51, REQ_52, REQ_54, {"objects": []}, {"objects": []}, OBJ_54] + [{"objects": []}] * 3, fallback=TC)
    lines = []
    plan = run(str(FIX / "sample.md"), llm, model="fake", log=lines.append)
    assert [r.id for r in plan.requirements] == ["REQ-5.1-1", "REQ-5.1-2", "REQ-5.2-1", "REQ-5.4-1"]
    assert [o.id for o in plan.objects] == ["OBJ-5.4-1"] + [f"OBJ-5.5-{n}" for n in range(1, 12)]
    assert [o.name for o in plan.objects if o.clause_id == "5.5"] == GRAMMAR_55
    assert {(o.clause_id, o.origin) for o in plan.objects} == {("5.4", "prose"), ("5.5", "grammar")}
    checks = [i.check for i in plan.coverage_items if i.source_id == "OBJ-5.4-1"]
    assert checks == ["capability", "presence", "absence", "encoding_valid", "encoding_invalid", "boundary_min", "boundary_max",
                      "boundary_outside"]
    # OBJ-5.5-4 is the ABNF rule no other rule references: its presence is unspecified, so it is no ICS feature
    assert [i.id for i in plan.ics] == (["ICS-OBJ-5.4-1"] + [f"ICS-OBJ-5.5-{n}" for n in range(1, 12) if n != 4]
                                        + ["ICS-REQ-5.1-1", "ICS-REQ-5.1-2", "ICS-REQ-5.2-1", "ICS-REQ-5.4-1"])
    assert len(plan.test_cases) == len(plan.coverage_items)
    # the sample table has two rows; the scripted model only returns the first, so the second is reported
    assert [(g.stage, g.clause_id) for g in plan.gaps] == [("model", "5.4")] and "1/2 rows" in plan.gaps[0].reason
    assert {t.coverage_item_id for t in plan.test_cases} == {i.id for i in plan.coverage_items}
    assert plan.source.sha256 == hashlib.sha256((FIX / "sample.md").read_bytes()).hexdigest()
    assert any("coverage items" in l for l in lines)


def test_run_without_model_or_grammar_stage(fake_llm):
    llm = fake_llm([REQ_51, REQ_52, REQ_54], fallback=TC)
    plan = run(str(FIX / "sample.md"), llm, model="fake", use_model=False, use_grammar=False)
    assert plan.objects == [] and all(i.source_id.startswith("REQ-") for i in plan.coverage_items)


def test_run_with_grammar_but_no_model_stage(fake_llm):
    """The grammar stage is deterministic: without the model stage it still yields its objects."""
    llm = fake_llm([REQ_51, REQ_52, REQ_54], fallback=TC)
    plan = run(str(FIX / "sample.md"), llm, model="fake", use_model=False)
    assert [o.name for o in plan.objects] == GRAMMAR_55
    assert {o.origin for o in plan.objects} == {"grammar"} and plan.gaps == []


def test_run_without_grammar_stage_keeps_the_model_objects(fake_llm):
    llm = fake_llm([REQ_51, REQ_52, REQ_54, {"objects": []}, {"objects": []}, OBJ_54] + [{"objects": []}] * 3, fallback=TC)
    plan = run(str(FIX / "sample.md"), llm, model="fake", use_grammar=False)
    assert [o.id for o in plan.objects] == ["OBJ-5.4-1"] and plan.objects[0].origin == "prose"


def test_run_clause_filter(fake_llm):
    llm = fake_llm([REQ_52, {"objects": []}], fallback=TC)
    plan = run(str(FIX / "sample.md"), llm, model="fake", clause_ids=["5.2"])
    assert {r.clause_id for r in plan.requirements} == {"5.2"}
    assert len(plan.coverage_items) == 4 and len(llm.prompts) == 2 + 4


def test_run_unknown_clause_filter_raises(fake_llm):
    with pytest.raises(ValueError, match="9.9"):
        run(str(FIX / "sample.md"), fake_llm([]), model="fake", clause_ids=["9.9"])


def test_run_deflation_drops_the_requirement_items_the_object_already_covers(fake_llm):
    script = [REQ_51, REQ_52, REQ_54, {"objects": []}, {"objects": []}, OBJ_54] + [{"objects": []}] * 3
    plan = run(str(FIX / "sample.md"), fake_llm(list(script), fallback=TC), model="fake")
    kept = run(str(FIX / "sample.md"), fake_llm(list(script), fallback=TC), model="fake", deflate=False)
    # REQ-5.4-1 names the nonce object of its own clause, which covers both its nominal and its negative check
    assert [i.check for i in plan.coverage_items if i.source_id == "REQ-5.4-1"] == ["capability"]
    assert [i.check for i in kept.coverage_items if i.source_id == "REQ-5.4-1"] == ["capability", "nominal", "negative"]
    assert len(plan.coverage_items) == len(kept.coverage_items) - 2
