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


def test_requirement_batch_keeps_every_draft_when_one_modality_is_unknown():
    """One out-of-vocabulary value must cost one draft, not the whole reply."""
    batch = RequirementBatch.model_validate({"requirements": [
        {"text": "a", "modality": "MUST NOT", "conditions": [], "source_quote": "q"},
        {"text": "b", "modality": "obligatory", "conditions": [], "source_quote": "q"},
    ]})
    assert [r.modality for r in batch.requirements] == ["shall_not", "obligatory"]


def test_object_batch_normalises_spelling_case_and_table_codes():
    batch = TestObjectBatch.model_validate({"objects": [
        {"name": "a", "kind": "Field", "direction": "Received", "presence": "M", "source_quote": "q"},
        {"name": "b", "kind": "behavior", "direction": "produces output", "presence": "mandatory (M)", "source_quote": "q"},
        {"name": "c", "kind": "parameters", "presence": "Ca", "condition": "x", "source_quote": "q"},
        {"name": "d", "kind": "value", "presence": "O", "source_quote": "q"},
        {"name": "e", "kind": "gadget", "presence": "sometimes", "source_quote": "q"},
    ]})
    assert [o.kind for o in batch.objects] == ["field", "behaviour", "parameter", "value", "gadget"]
    assert [o.presence for o in batch.objects] == ["mandatory", "mandatory", "conditional", "optional", "sometimes"]
    assert [o.direction for o in batch.objects][:2] == ["received", "produced"]


def test_scalar_and_single_string_coercion_for_llm_fields():
    from tpg.models import RequirementDraft, TestCaseDraft, TestObjectDraft
    o = TestObjectDraft.model_validate({"name": 25, "kind": "value", "source_quote": "q",
                                        "size": 150, "relations": "same value as x", "type": None, "value_domain": "  "})
    assert o.name == "25" and o.size == "150" and o.relations == ["same value as x"]
    assert o.type is None and o.value_domain is None
    r = RequirementDraft.model_validate({"text": "t", "modality": "shall", "source_quote": "q", "conditions": "A is set"})
    assert r.conditions == ["A is set"]
    t = TestCaseDraft.model_validate({"objective": "o", "preconditions": None, "inputs": ["a", 2],
                                      "steps": "send the request", "expected_result": "r", "pass_criteria": "p"})
    assert t.preconditions == [] and t.inputs == ["a", "2"] and t.steps == ["send the request"]


def test_persisted_types_normalise_but_stay_strict():
    import pytest
    from pydantic import ValidationError
    o = TestObject(id="OBJ-1-1", clause_id="1", name="n", kind="Field", presence="M", source_quote="q")
    assert o.kind == "field" and o.presence == "mandatory"
    with pytest.raises(ValidationError):
        TestObject(id="OBJ-1-2", clause_id="1", name="n", kind="gadget", source_quote="q")
    with pytest.raises(ValidationError):
        Requirement(id="REQ-1-1", clause_id="1", text="t", modality="obligatory", source_quote="q")


def test_draft_schemas_still_advertise_their_vocabulary():
    """Parsing is lenient, but a server that enforces the schema must still see the allowed values."""
    from tpg.models import MODALITY_VALUES, OBJECT_KIND_VALUES, PRESENCE_VALUES
    props = TestObjectBatch.model_json_schema()["$defs"]["TestObjectDraft"]["properties"]
    assert props["kind"]["enum"] == list(OBJECT_KIND_VALUES)
    assert props["presence"]["enum"] == list(PRESENCE_VALUES)
    modality = RequirementBatch.model_json_schema()["$defs"]["RequirementDraft"]["properties"]["modality"]
    assert modality["enum"] == list(MODALITY_VALUES)
