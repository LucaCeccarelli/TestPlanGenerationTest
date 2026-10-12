from typing import get_args

import pytest

from tpg.derive import GROUP, derive, derive_object, derive_requirement, group_for
from tpg.ics import build_ics
from tpg.models import Check, Requirement, TestObject


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


def test_derive_orders_capability_then_requirements_then_objects():
    reqs, objs = [req()], [obj(presence="mandatory")]
    items = derive(reqs, objs, build_ics(reqs, objs))
    assert [i.source_id for i in items] == ["OBJ-5.4-1", "REQ-5.1-1"] + ["REQ-5.1-1"] * 3 + ["OBJ-5.4-1"]
    assert [i.check for i in items][:2] == ["capability", "capability"]
    assert all(i.clause_id in ("5.1", "5.4") for i in items)


# --- D23 groups ---

EXPECTED_GROUPS = {
    "presence": "valid_behaviour", "encoding_valid": "valid_behaviour", "value_valid": "valid_behaviour",
    "consistency": "valid_behaviour", "condition_true": "valid_behaviour", "nominal": "valid_behaviour",
    "boundary_min": "valid_behaviour", "boundary_max": "valid_behaviour", "boundary": "valid_behaviour",
    "reference": "valid_behaviour",
    "absence": "invalid_behaviour", "encoding_invalid": "invalid_behaviour", "value_invalid": "invalid_behaviour",
    "boundary_outside": "invalid_behaviour", "negative": "invalid_behaviour", "condition_false": "invalid_behaviour",
    "capability": "capability",
    "inopportune": "inopportune_behaviour",
}


@pytest.mark.parametrize("check", get_args(Check))
def test_group_for_every_check(check):
    assert group_for(check) == EXPECTED_GROUPS[check]


def test_group_map_has_no_fall_through_and_no_extra_keys():
    assert set(GROUP) == set(get_args(Check))
    with pytest.raises(KeyError):
        group_for("not_a_check")


def test_every_derived_item_carries_its_group():
    reqs = [req(), req(id="REQ-5.2-1", clause_id="5.2", text="If A the device shall stop.", conditions=["A"])]
    objs = [obj(presence="conditional", condition="the request asks for it", kind="message", direction="received",
                type="text string", value_domain="one of a, b", size="1 to 2 characters", relations=["unique per session"])]
    items = derive(reqs, objs, build_ics(reqs, objs))
    assert all(i.group == EXPECTED_GROUPS[i.check] for i in items)
    assert {i.group for i in items} == {"capability", "valid_behaviour", "invalid_behaviour", "inopportune_behaviour"}


# --- D21 capability items ---

def test_capability_item_per_mandatory_or_optional_ics_item_and_none_for_unspecified():
    reqs = [req()]
    objs = [obj(presence="mandatory"), obj(id="OBJ-5.4-2", name="locale", presence="unspecified")]
    items = derive(reqs, objs, build_ics(reqs, objs))
    caps = [i for i in items if i.check == "capability"]
    assert [i.id for i in caps] == ["CI-OBJ-5.4-1-capability", "CI-REQ-5.1-1-capability"]
    assert [i.kind for i in caps] == ["nominal", "nominal"]
    assert caps[0].purpose == "Verify that the implementation supports nonce"


def test_no_capability_item_for_a_conditional_ics_item():
    objs = [obj(presence="conditional", condition="the request asks for it")]
    items = derive([], objs, build_ics([], objs))
    assert [i.check for i in items if i.check == "capability"] == []


def test_applies_when_propagates_from_the_source_and_the_ics_item():
    reqs = [req(applies_when=["the extended profile is in use"])]
    objs = [obj(presence="mandatory", applies_when=["the device is in secure mode"])]
    items = derive(reqs, objs, build_ics(reqs, objs))
    for i in items:
        want = ["the device is in secure mode"] if i.source_id.startswith("OBJ-") else ["the extended profile is in use"]
        assert i.applies_when == want, i.id


def test_items_default_to_no_applicability_condition_and_no_generic_group():
    items = derive_object(obj(presence="mandatory"))
    assert all(i.applies_when == [] and i.generic_group is None for i in items)


# --- D23 inopportune items ---

def test_inopportune_item_for_a_received_message_with_a_condition():
    objs = [obj(kind="message", direction="received", condition="the session is open", presence="conditional")]
    items = derive([], objs, build_ics([], objs))
    inopp = [i for i in items if i.check == "inopportune"]
    assert [(i.id, i.kind, i.group) for i in inopp] == [
        ("CI-OBJ-5.4-1-inopportune", "negative", "inopportune_behaviour")]
    assert inopp[0].purpose == "Verify the handling of nonce supplied when the session is open does not hold"


def test_no_inopportune_item_when_produced_or_not_a_message_or_structure_or_unconditioned():
    cases = [
        dict(kind="message", direction="produced", condition="the session is open", presence="conditional"),
        dict(kind="field", direction="received", condition="the session is open", presence="conditional"),
        dict(kind="message", direction="received", presence="mandatory"),
    ]
    for kw in cases:
        objs = [obj(**kw)]
        assert [i for i in derive([], objs, build_ics([], objs)) if i.check == "inopportune"] == [], kw


def test_inopportune_items_come_after_the_ladders():
    objs = [obj(kind="structure", direction="received", condition="the session is open", presence="conditional")]
    items = derive([], objs, build_ics([], objs))
    assert [i.check for i in items][-1] == "inopportune"
