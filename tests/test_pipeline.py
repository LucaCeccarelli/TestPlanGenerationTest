import hashlib
import re
from pathlib import Path

import pytest

from tests.conftest import FakeLLM
from tpg.models import CoverageItem, ICSItem, TestCaseBatch
from tpg.pipeline import ics_coverage, ics_coverage_line, run

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
# The same object read off the prose sentence of clause 5.4 instead of the table row: rule (b) of D25 as
# amended by D31 compares provenance, so only this one shares its source with REQ-5.4-1.
OBJ_54_PROSE = {"objects": [{**OBJ_54["objects"][0],
                             "source_quote": "The reader shall reject a request whose nonce is missing."}]}
TC = {"objective": "o", "preconditions": [], "inputs": [], "steps": ["s"], "expected_result": "the request is rejected with an error",
      "pass_criteria": "error observed"}


class BatchLLM(FakeLLM):
    """The scripted fake for every stage, plus a batched generation reply carrying one case per
    coverage item id the prompt lists, since those ids are only known once derive has run."""

    def complete(self, prompt, schema):
        if schema is TestCaseBatch:
            self.prompts.append(prompt)
            ids = re.findall(r"^- (CI-\S+) \(check", prompt, re.M)
            assert ids, "batched generation prompt listed no coverage item id"
            return schema.model_validate({"cases": [{**TC, "coverage_item_id": i} for i in ids]})
        return super().complete(prompt, schema)


GRAMMAR_55 = ["label", "count", "mode", "token", "prefix", "suffix", "key", "flag", "name", "state", "note"]


def test_run_end_to_end_with_fake():
    # sample.md: clauses 1, 3, 5, 5.1, 5.2, 5.3, 5.4, 5.5; candidates in 5.1, 5.2, 5.4; rows only in 5.4;
    # formal declarations only in 5.5, which therefore costs no model-stage call.
    llm = BatchLLM([REQ_51, REQ_52, REQ_54, {"objects": []}, {"objects": []}, OBJ_54] + [{"objects": []}] * 3, fallback=TC)
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


def test_run_without_model_or_grammar_stage():
    llm = BatchLLM([REQ_51, REQ_52, REQ_54], fallback=TC)
    plan = run(str(FIX / "sample.md"), llm, model="fake", use_model=False, use_grammar=False)
    assert plan.objects == [] and all(i.source_id.startswith("REQ-") for i in plan.coverage_items)


def test_run_with_grammar_but_no_model_stage():
    """The grammar stage is deterministic: without the model stage it still yields its objects."""
    llm = BatchLLM([REQ_51, REQ_52, REQ_54], fallback=TC)
    plan = run(str(FIX / "sample.md"), llm, model="fake", use_model=False)
    assert [o.name for o in plan.objects] == GRAMMAR_55
    assert {o.origin for o in plan.objects} == {"grammar"} and plan.gaps == []


def test_run_without_grammar_stage_keeps_the_model_objects():
    llm = BatchLLM([REQ_51, REQ_52, REQ_54, {"objects": []}, {"objects": []}, OBJ_54] + [{"objects": []}] * 3, fallback=TC)
    plan = run(str(FIX / "sample.md"), llm, model="fake", use_grammar=False)
    assert [o.id for o in plan.objects] == ["OBJ-5.4-1"] and plan.objects[0].origin == "prose"


def test_run_clause_filter():
    llm = BatchLLM([REQ_52, {"objects": []}], fallback=TC)
    plan = run(str(FIX / "sample.md"), llm, model="fake", clause_ids=["5.2"])
    assert {r.clause_id for r in plan.requirements} == {"5.2"}
    # the four items of REQ-5.2-1 are one batched call, where the per-item path made four
    assert len(plan.coverage_items) == 4 and len(llm.prompts) == 2 + 1


def test_run_without_batching_calls_once_per_coverage_item(fake_llm):
    llm = fake_llm([REQ_52, {"objects": []}], fallback=TC)
    plan = run(str(FIX / "sample.md"), llm, model="fake", clause_ids=["5.2"], batch=False)
    assert len(plan.coverage_items) == 4 and len(llm.prompts) == 2 + 4
    assert len(plan.test_cases) == 4 and plan.gaps == []


def test_run_unknown_clause_filter_raises(fake_llm):
    with pytest.raises(ValueError, match="9.9"):
        run(str(FIX / "sample.md"), fake_llm([]), model="fake", clause_ids=["9.9"])


def test_run_deflation_drops_the_requirement_items_the_object_already_covers():
    script = [REQ_51, REQ_52, REQ_54, {"objects": []}, {"objects": []}, OBJ_54_PROSE] + [{"objects": []}] * 3
    plan = run(str(FIX / "sample.md"), BatchLLM(list(script), fallback=TC), model="fake")
    kept = run(str(FIX / "sample.md"), BatchLLM(list(script), fallback=TC), model="fake", deflate=False)
    # OBJ-5.4-1 was read off the sentence REQ-5.4-1 states, so it covers both its nominal and its negative check
    assert [i.check for i in plan.coverage_items if i.source_id == "REQ-5.4-1"] == ["capability"]
    assert [i.check for i in kept.coverage_items if i.source_id == "REQ-5.4-1"] == ["capability", "nominal", "negative"]
    assert len(plan.coverage_items) == len(kept.coverage_items) - 2


def test_ics_coverage_counts_only_the_mandatory_and_optional_items():
    """X.291 clause 10.4 / D21: a conditional or unspecified feature is not part of the denominator."""
    ics = [ICSItem(id="ICS-A", source_id="A", clause_id="5", feature="a", status="mandatory"),
           ICSItem(id="ICS-B", source_id="B", clause_id="5", feature="b", status="optional"),
           ICSItem(id="ICS-C", source_id="C", clause_id="5", feature="c", status="conditional"),
           ICSItem(id="ICS-D", source_id="D", clause_id="5", feature="d", status="unspecified")]
    items = [CoverageItem(id="CI-1", source_id="A", clause_id="5", check="capability", kind="nominal",
                          group="capability", purpose="p")]
    assert ics_coverage(ics, items) == (1, 2)
    assert ics_coverage([], []) == (0, 0)
    assert ics_coverage_line(ics, items) == "ICS coverage 50.0% (1/2)"
    # a document from which no feature was read reports no figure rather than a vacuous 100 per cent
    assert ics_coverage_line([], []) == "ICS coverage n/a (no mandatory or optional ICS item)"


def test_run_logs_one_line_per_stage_with_its_counts():
    llm = BatchLLM([REQ_51, REQ_52, REQ_54, {"objects": []}, {"objects": []}, OBJ_54] + [{"objects": []}] * 3, fallback=TC)
    lines = []
    plan = run(str(FIX / "sample.md"), llm, model="fake", log=lines.append)
    cov, due = ics_coverage(plan.ics, plan.coverage_items)
    assert "8 clauses" in lines
    assert f"{len([o for o in plan.objects if o.origin == 'grammar'])} objects from formal declarations" in lines
    assert f"{len(plan.requirements)} requirements, 0 gaps" in lines
    assert f"{len(plan.objects)} objects in the test model" in lines
    assert f"{len(plan.ics)} ICS items" in lines
    assert f"{len(plan.coverage_items)} coverage items, ICS coverage 100.0% ({cov}/{due})" in lines
    assert f"{len(plan.test_cases)} test cases, 0 gaps" in lines
    assert any(l.startswith("plan: ") and "traceability" in l for l in lines)


def test_every_mandatory_or_optional_ics_item_reaches_a_coverage_item():
    """D21 through the whole pipeline: deflation drops the ladder of a non-owning occurrence, so the
    reference item it leaves behind is what keeps the ICS coverage at 100 per cent."""
    llm = BatchLLM([REQ_51, REQ_52, REQ_54, {"objects": []}, {"objects": []}, OBJ_54] + [{"objects": []}] * 3, fallback=TC)
    plan = run(str(FIX / "sample.md"), llm, model="fake")
    cov, due = ics_coverage(plan.ics, plan.coverage_items)
    assert due and cov == due, [i.id for i in plan.ics if i.source_id not in {c.source_id for c in plan.coverage_items}]
