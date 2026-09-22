from tpg.derive import derive, derive_object, derive_requirement
from tpg.models import Requirement, TestObject


def req(**kw):
    base = dict(id="REQ-5.1-1", clause_id="5.1", text="The device shall respond within 500 ms.", modality="shall",
                conditions=[], source_quote="shall respond within 500 ms")
    return Requirement(**{**base, **kw})


def obj(**kw):
    base = dict(id="OBJ-5.4-1", clause_id="5.4", name="nonce", kind="parameter", source_quote="Name: nonce")
    return TestObject(**{**base, **kw})


def checks(items):
    return [(i.check, i.kind) for i in items]


def test_requirement_nominal_negative_boundary():
    assert checks(derive_requirement(req())) == [("nominal", "nominal"), ("negative", "negative"), ("boundary", "boundary")]
    assert checks(derive_requirement(req(text="The device may log.", modality="may"))) == [("nominal", "nominal")]
    assert checks(derive_requirement(req(text="Other elements should not be present.", modality="should_not"))) == [("nominal", "nominal"), ("negative", "negative")]
    ids = [i.id for i in derive_requirement(req())]
    assert ids == ["CI-REQ-5.1-1-nominal", "CI-REQ-5.1-1-negative", "CI-REQ-5.1-1-boundary"]


def test_requirement_boundary_detection_words():
    assert ("boundary", "boundary") in checks(derive_requirement(req(text="The name shall be at most 150 characters.")))
    assert ("boundary", "boundary") not in checks(derive_requirement(req(text="The device shall log every request.")))


def test_conditional_requirement_items_carry_assignments():
    items = derive_requirement(req(text="If A or B the device shall not process.", modality="shall_not", conditions=["A", "B"]))
    assert checks(items) == [("condition_true", "nominal"), ("condition_false", "negative"), ("condition_false", "negative")]
    assert [i.condition_assignment for i in items] == [{"A": True, "B": True}, {"A": False, "B": True}, {"A": True, "B": False}]
    assert [i.id for i in items] == ["CI-REQ-5.1-1-condition_true", "CI-REQ-5.1-1-condition_false-1", "CI-REQ-5.1-1-condition_false-2"]


def test_object_presence_rules():
    assert checks(derive_object(obj(presence="mandatory", direction="received"))) == [("presence", "nominal"), ("absence", "negative")]
    assert checks(derive_object(obj(presence="mandatory", direction="produced"))) == [("presence", "nominal")]
    assert checks(derive_object(obj(presence="optional"))) == [("presence", "nominal"), ("absence", "nominal")]
    assert checks(derive_object(obj(presence="conditional", condition="the request asks for it"))) == [("condition_true", "nominal"), ("condition_false", "negative")]
    assert checks(derive_object(obj())) == []


def test_object_type_value_size_relations():
    o = obj(presence="mandatory", direction="received", type="text string", value_domain="one of a, b", size="16 to 64 characters",
            relations=["same value as the request nonce", "unique per session"])
    got = checks(derive_object(o))
    assert got == [("presence", "nominal"), ("absence", "negative"), ("encoding_valid", "nominal"), ("encoding_invalid", "negative"),
                   ("value_valid", "nominal"), ("value_invalid", "negative"), ("boundary_min", "boundary"), ("boundary_max", "boundary"),
                   ("boundary_outside", "negative"), ("consistency", "nominal"), ("consistency", "nominal")]
    ids = [i.id for i in derive_object(o)]
    assert ids[-2:] == ["CI-OBJ-5.4-1-consistency-1", "CI-OBJ-5.4-1-consistency-2"]
    p = derive_object(o)[0].purpose
    assert "nonce" in p and "present" in p


def test_produced_objects_get_no_invalid_stimuli():
    o = obj(presence="mandatory", direction="produced", type="text", value_domain="x", size="1 to 2")
    assert all(k != "negative" for _, k in checks(derive_object(o)))


def test_derive_orders_requirements_then_objects():
    items = derive([req()], [obj(presence="mandatory")])
    assert [i.source_id for i in items] == ["REQ-5.1-1"] * 3 + ["OBJ-5.4-1"]
    assert all(i.clause_id in ("5.1", "5.4") for i in items)
