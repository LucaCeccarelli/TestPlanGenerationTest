import json
from tpg.models import (Clause, Requirement, TestCase, Gap, TraceLink, Source,
                        TestPlan, RequirementBatch, TestCaseBatch)


def test_testplan_round_trips_through_json():
    plan = TestPlan(
        source=Source(path="x.pdf", sha256="ab", generated_at="2026-09-21T00:00:00Z", model="m"),
        requirements=[Requirement(id="REQ-5.1-1", clause_id="5.1", text="The device shall respond.",
                                  modality="shall", conditions=[], source_quote="shall respond")],
        test_cases=[TestCase(id="TC-REQ-5.1-1-1", requirement_id="REQ-5.1-1", kind="nominal",
                             objective="o", preconditions=[], inputs=[], steps=["s"],
                             expected_result="r", pass_criteria="p", condition_assignment=None)],
        traceability=[TraceLink(requirement_id="REQ-5.1-1", test_case_ids=["TC-REQ-5.1-1-1"])],
        gaps=[Gap(requirement_id=None, clause_id="5.2", stage="extract", reason="bad", attempts=3)],
    )
    again = TestPlan.model_validate_json(plan.model_dump_json())
    assert again == plan


def test_batch_schemas_are_json_schema_objects():
    for batch in (RequirementBatch, TestCaseBatch):
        schema = batch.model_json_schema()
        assert schema["type"] == "object"
        assert "properties" in schema


def test_draft_defaults():
    from tpg.models import RequirementDraft, TestCaseDraft
    r = RequirementDraft(text="t", modality="may", source_quote="q")
    assert r.conditions == []
    t = TestCaseDraft(kind="nominal", objective="o", steps=["s"], expected_result="r", pass_criteria="p")
    assert t.preconditions == [] and t.inputs == [] and t.condition_assignment is None
