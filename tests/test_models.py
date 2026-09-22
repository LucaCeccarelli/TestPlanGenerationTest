from tpg.models import (CoverageItem, Gap, Requirement, RequirementBatch, Source, TestCase, TestObject,
                        TestObjectBatch, TestPlan, TraceLink)


def test_testplan_round_trips_through_json():
    plan = TestPlan(
        source=Source(path="x.pdf", sha256="ab", generated_at="2026-09-21T00:00:00Z", model="m"),
        requirements=[Requirement(id="REQ-5.1-1", clause_id="5.1", text="The device shall respond.",
                                  modality="shall", conditions=[], source_quote="shall respond")],
        objects=[TestObject(id="OBJ-5.1-1", clause_id="5.1", name="nonce", kind="parameter", direction="received",
                            presence="mandatory", type="text string", source_quote="Name: nonce | Presence: mandatory")],
        coverage_items=[CoverageItem(id="CI-OBJ-5.1-1-presence", source_id="OBJ-5.1-1", clause_id="5.1",
                                     check="presence", kind="nominal", purpose="Verify that nonce is present")],
        test_cases=[TestCase(id="TC-CI-OBJ-5.1-1-presence", source_id="OBJ-5.1-1", coverage_item_id="CI-OBJ-5.1-1-presence",
                             kind="nominal", objective="o", steps=["s"], expected_result="r", pass_criteria="p")],
        traceability=[TraceLink(source_id="OBJ-5.1-1", coverage_item_ids=["CI-OBJ-5.1-1-presence"],
                                test_case_ids=["TC-CI-OBJ-5.1-1-presence"])],
        gaps=[Gap(source_id=None, clause_id="5.2", stage="model", reason="bad", attempts=3)],
    )
    assert TestPlan.model_validate_json(plan.model_dump_json()) == plan
    assert list(plan.model_dump()) == ["source", "requirements", "objects", "coverage_items", "test_cases", "traceability", "gaps"]


def test_batch_schemas_are_json_schema_objects():
    for batch in (RequirementBatch, TestObjectBatch):
        assert batch.model_json_schema()["type"] == "object"


def test_object_draft_defaults():
    from tpg.models import TestObjectDraft
    o = TestObjectDraft(name="n", kind="field", source_quote="q")
    assert o.direction == "internal" and o.presence == "unspecified" and o.relations == [] and o.type is None
