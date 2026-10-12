from typing import get_args

import pytest

from tpg.derive import GROUP, derive, derive_object, derive_requirement, group_for
from tpg.ics import build_ics
from tpg.models import Check, Direction, Kind, Requirement, TestObject


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
    assert checks(derive_object(obj(presence="mandatory", direction="produced"))) == [("presence", "nominal"), ("absence", "negative")]
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


def test_boundary_items_need_a_number_in_the_size():
    """An occurrence marker such as "*" reaches `size` from a grammar declaration and states no limit."""
    numeric = checks(derive_object(obj(presence="mandatory", direction="received", size="16 to 64 characters")))
    assert [c for c, _ in numeric if c.startswith("boundary")] == ["boundary_min", "boundary_max", "boundary_outside"]
    for size in ("*", "+", "one or more"):
        got = checks(derive_object(obj(presence="mandatory", direction="received", size=size)))
        assert [c for c, _ in got if c.startswith("boundary")] == [], size


def test_capability_purpose_of_a_prohibition_is_not_phrased_as_support():
    reqs = [req(text="The device shall not process the request.", modality="shall_not"),
            req(id="REQ-5.1-2", text="The device shall respond.", modality="shall")]
    caps = {i.source_id: i.purpose for i in derive(reqs, [], build_ics(reqs, [])) if i.check == "capability"}
    assert caps["REQ-5.1-1"] == "Verify that the implementation enforces: The device shall not process the request."
    assert caps["REQ-5.1-2"] == "Verify that the implementation supports The device shall respond."


# --- D30 invalid-side items for every direction ---

def rich(direction):
    return obj(presence="mandatory", direction=direction, type="text string", value_domain="one of a, b",
               size="16 to 64 characters")


INVALID = [("absence", "negative"), ("encoding_invalid", "negative"), ("value_invalid", "negative"),
           ("boundary_outside", "negative")]


@pytest.mark.parametrize("direction", get_args(Direction))
def test_invalid_side_items_are_emitted_whatever_the_direction(direction):
    """D30: direction selects the wording of a negative item, never its existence. A grammar-derived object
    has no stated direction, so a gate on `received` would drop the whole invalid half of its ladder."""
    items = derive_object(rich(direction))
    assert [c for c in checks(items) if c in INVALID] == INVALID
    assert all(i.group == "invalid_behaviour" for i in items if (i.check, i.kind) in INVALID)


def test_direction_changes_only_the_purpose_of_an_invalid_item():
    by_direction = {d: derive_object(rich(d)) for d in get_args(Direction)}
    skeleton = {d: [(i.id, i.check, i.kind, i.group) for i in items] for d, items in by_direction.items()}
    assert skeleton["received"] == skeleton["produced"] == skeleton["internal"]
    negatives = {d: [i.purpose for i in items if i.kind == "negative"] for d, items in by_direction.items()}
    assert negatives["produced"] == negatives["internal"]
    assert negatives["received"] != negatives["produced"]


def test_received_invalid_purposes_ask_for_the_instance_to_be_supplied_and_rejected():
    purposes = {i.check: i.purpose for i in derive_object(rich("received")) if i.kind == "negative"}
    assert purposes == {
        "absence": "Verify the reaction of the system under test when nonce is absent",
        "encoding_invalid": "Verify the reaction of the system under test when nonce is not a well-formed text string",
        "value_invalid": "Verify the reaction of the system under test when the value of nonce violates: one of a, b",
        "boundary_outside": "Verify the reaction of the system under test when nonce is outside: 16 to 64 characters"}


def test_produced_and_internal_invalid_purposes_ask_that_no_such_instance_is_ever_made():
    for direction in ("produced", "internal"):
        purposes = {i.check: i.purpose for i in derive_object(rich(direction)) if i.kind == "negative"}
        assert purposes == {
            "absence": "Verify that the system under test never produces or holds a case in which nonce is absent",
            "encoding_invalid": "Verify that the system under test never produces or holds a case in which nonce is not a well-formed text string",
            "value_invalid": "Verify that the system under test never produces or holds a case in which the value of nonce violates: one of a, b",
            "boundary_outside": "Verify that the system under test never produces or holds a case in which nonce is outside: 16 to 64 characters"}, direction


def test_an_unstated_presence_still_suppresses_both_absence_items():
    """D30 emits `absence` of a mandatory element. With no stated presence there is no obligation to
    violate and no permission to exercise, so neither the negative nor the nominal item is derived."""
    assert [c for c, _ in checks(derive_object(obj(presence="unspecified", type="text string")))] == [
        "encoding_valid", "encoding_invalid"]


def test_derive_orders_capability_then_requirements_then_objects():
    reqs, objs = [req()], [obj(presence="mandatory")]
    items = derive(reqs, objs, build_ics(reqs, objs))
    assert [i.source_id for i in items] == ["OBJ-5.4-1", "REQ-5.1-1"] + ["REQ-5.1-1"] * 3 + ["OBJ-5.4-1"] * 2
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


def expected_group(check, kind):
    """`absence` is the one check whose group depends on the item: an element that may legitimately be
    absent is valid behaviour, a missing mandatory one is invalid behaviour (X.291 clause 10.2.2)."""
    if check == "absence" and kind == "nominal":
        return "valid_behaviour"
    return EXPECTED_GROUPS[check]


@pytest.mark.parametrize("kind", get_args(Kind))
@pytest.mark.parametrize("check", get_args(Check))
def test_group_for_every_check_and_kind(check, kind):
    assert group_for(check, kind) == expected_group(check, kind)


def test_group_map_has_no_fall_through_and_no_extra_keys():
    assert set(GROUP) == set(get_args(Check))
    with pytest.raises(KeyError):
        group_for("not_a_check", "nominal")


def test_absence_group_follows_the_kind_of_the_emitted_item():
    optional = [i for i in derive_object(obj(presence="optional")) if i.check == "absence"]
    assert [(i.kind, i.group) for i in optional] == [("nominal", "valid_behaviour")]
    mandatory = [i for i in derive_object(obj(presence="mandatory", direction="received")) if i.check == "absence"]
    assert [(i.kind, i.group) for i in mandatory] == [("negative", "invalid_behaviour")]


def test_every_derived_item_carries_its_group():
    reqs = [req(), req(id="REQ-5.2-1", clause_id="5.2", text="If A the device shall stop.", conditions=["A"])]
    objs = [obj(presence="conditional", condition="the request asks for it", kind="message", direction="received",
                type="text string", value_domain="one of a, b", size="1 to 2 characters", relations=["unique per session"])]
    items = derive(reqs, objs, build_ics(reqs, objs))
    assert all(i.group == expected_group(i.check, i.kind) for i in items)
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

def test_inopportune_item_for_a_received_message_whose_precondition_is_an_applicability_text():
    objs = [obj(kind="message", direction="received", presence="mandatory",
                applies_when=["the session has been established"])]
    items = derive([], objs, build_ics([], objs))
    inopp = [i for i in items if i.check == "inopportune"]
    assert [(i.kind, i.group) for i in inopp] == [("negative", "inopportune_behaviour")]
    assert inopp[0].purpose.endswith(": the session has been established")


def test_inopportune_and_condition_false_of_one_conditional_object_are_distinguishable():
    """Both probe the same precondition, so the purposes must tell a reader which stimulus to send."""
    objs = [obj(kind="message", direction="received", presence="conditional", condition="the session is open")]
    items = derive([], objs, build_ics([], objs))
    purposes = {i.check: i.purpose for i in items}
    assert purposes["condition_false"] != purposes["inopportune"]
    assert "supplied" in purposes["inopportune"] and "supplied" not in purposes["condition_false"]
    assert purposes["inopportune"].endswith(": the session is open")


def test_inopportune_item_for_a_received_message_with_a_condition():
    objs = [obj(kind="message", direction="received", condition="the session is open", presence="conditional")]
    items = derive([], objs, build_ics([], objs))
    inopp = [i for i in items if i.check == "inopportune"]
    assert [(i.id, i.kind, i.group) for i in inopp] == [
        ("CI-OBJ-5.4-1-inopportune", "negative", "inopportune_behaviour")]
    assert inopp[0].purpose == "Verify the handling of nonce supplied although its precondition does not hold: the session is open"


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


# --- D25 deflation ---

def test_recurring_object_name_keeps_one_ladder_and_references_it_elsewhere():
    rich = obj(id="OBJ-5.4-1", clause_id="5.4", name="Device Engagement", kind="structure", direction="received",
               presence="mandatory", type="map", value_domain="one of a, b")
    lean = obj(id="OBJ-7.1-1", clause_id="7.1", name="device  engagement", kind="structure", direction="received",
               presence="optional")
    objs = [rich, lean]
    items = derive([], objs, build_ics([], objs))
    assert [i.id for i in items if i.source_id == "OBJ-5.4-1"] == [i.id for i in derive([], objs, build_ics([], objs), deflate=False)
                                                                   if i.source_id == "OBJ-5.4-1"]
    ref = [i for i in items if i.source_id == "OBJ-7.1-1"]
    assert len(ref) == 1
    assert (ref[0].id, ref[0].check, ref[0].kind, ref[0].group) == ("CI-OBJ-7.1-1-reference", "reference", "nominal", "valid_behaviour")
    assert ref[0].clause_id == "7.1" and ref[0].generic_group == "device engagement"
    assert ref[0].purpose == "Perform the test purposes of device  engagement specified for clause 5.4"


def test_the_richest_occurrence_owns_the_group_not_the_first():
    lean = obj(id="OBJ-5.4-1", clause_id="5.4", name="nonce", presence="optional", direction="received")
    rich = obj(id="OBJ-7.1-1", clause_id="7.1", name="nonce", presence="mandatory", direction="received",
               type="text string", value_domain="one of a, b")
    objs = [lean, rich]
    items = derive([], objs, build_ics([], objs))
    assert [i.check for i in items if i.source_id == "OBJ-5.4-1"] == ["reference"]
    assert len([i for i in items if i.source_id == "OBJ-7.1-1"]) > 1


def test_a_name_in_one_clause_only_is_not_grouped():
    objs = [obj(presence="mandatory", direction="received"), obj(id="OBJ-5.4-2", name="counter", presence="mandatory")]
    items = derive([], objs, build_ics([], objs))
    assert [i for i in items if i.check == "reference"] == []


def test_requirement_item_is_dropped_only_for_the_checks_the_object_covers():
    o = obj(presence="mandatory", direction="received", type="text string")
    r = req(id="REQ-5.4-1", clause_id="5.4", modality="shall",
            text="The reader shall reject a request whose nonce is absent for more than 2 seconds.")
    items = derive([r], [o], build_ics([r], [o]))
    assert [i.check for i in items if i.source_id == "REQ-5.4-1"] == ["capability", "boundary"]
    assert [i.check for i in items if i.source_id == "OBJ-5.4-1"] == ["capability", "presence", "absence",
                                                                      "encoding_valid", "encoding_invalid"]


def test_requirement_naming_no_object_keeps_every_item():
    o = obj(presence="mandatory", direction="received", type="text string")
    r = req(id="REQ-5.4-1", clause_id="5.4", text="The reader shall respond within 500 ms.")
    items = derive([r], [o], build_ics([r], [o]))
    assert [i.check for i in items if i.source_id == "REQ-5.4-1"] == ["capability", "nominal", "negative", "boundary"]


def test_an_object_in_another_clause_does_not_drop_the_requirement_item():
    o = obj(id="OBJ-9.9-1", clause_id="9.9", presence="mandatory", direction="received")
    r = req(id="REQ-5.4-1", clause_id="5.4", text="The reader shall reject a request whose nonce is missing.")
    items = derive([r], [o], build_ics([r], [o]))
    assert [i.check for i in items if i.source_id == "REQ-5.4-1"] == ["capability", "nominal", "negative"]


def test_object_names_shorter_than_three_characters_are_not_matched():
    short = obj(id="OBJ-5.4-2", name="id", presence="mandatory", direction="received")
    long = obj(id="OBJ-5.4-3", name="uid", presence="mandatory", direction="received")
    r = req(id="REQ-5.4-1", clause_id="5.4", text="The reader shall echo the id.")
    assert [i.check for i in derive([r], [short], build_ics([r], [short])) if i.source_id == "REQ-5.4-1"] == [
        "capability", "nominal", "negative"]
    r2 = req(id="REQ-5.4-1", clause_id="5.4", text="The reader shall echo the uid.")
    assert [i.check for i in derive([r2], [long], build_ics([r2], [long])) if i.source_id == "REQ-5.4-1"] == ["capability"]


def test_object_name_matches_only_on_a_word_boundary():
    o = obj(presence="mandatory", direction="received")
    r = req(id="REQ-5.4-1", clause_id="5.4", text="The reader shall validate the nonces of the session.")
    assert [i.check for i in derive([r], [o], build_ics([r], [o])) if i.source_id == "REQ-5.4-1"] == [
        "capability", "nominal", "negative"]


def test_generic_grouping_runs_before_the_overlap_rule():
    """At a reference site the object ladder is gone, so the requirement that names it keeps its items."""
    rich = obj(id="OBJ-5.4-1", clause_id="5.4", presence="mandatory", direction="received", type="text string")
    lean = obj(id="OBJ-7.1-1", clause_id="7.1", presence="optional", direction="received")
    r = req(id="REQ-7.1-1", clause_id="7.1", text="The reader shall reject a request whose nonce is missing.")
    items = derive([r], [rich, lean], build_ics([r], [rich, lean]))
    assert [i.check for i in items if i.source_id == "REQ-7.1-1"] == ["capability", "nominal", "negative"]
    assert [i.check for i in items if i.source_id == "OBJ-7.1-1"] == ["reference"]


def test_deflate_false_leaves_every_item_in_place():
    objs = [obj(presence="mandatory", direction="received", type="text string"),
            obj(id="OBJ-7.1-1", clause_id="7.1", presence="optional", direction="received")]
    reqs = [req(id="REQ-5.4-1", clause_id="5.4", text="The reader shall reject a request whose nonce is missing.")]
    ics = build_ics(reqs, objs)
    assert len(derive(reqs, objs, ics, deflate=False)) == 11
    assert len(derive(reqs, objs, ics)) == 7


def test_deflation_never_changes_the_id_of_a_surviving_item():
    objs = [obj(presence="mandatory", direction="received", type="text string"),
            obj(id="OBJ-7.1-1", clause_id="7.1", presence="optional", direction="received")]
    reqs = [req(id="REQ-5.4-1", clause_id="5.4", text="The reader shall reject a request whose nonce is missing."),
            req(id="REQ-7.1-1", clause_id="7.1", text="The reader shall respond within 500 ms.")]
    ics = build_ics(reqs, objs)
    before = {i.id: i for i in derive(reqs, objs, ics, deflate=False)}
    for i in derive(reqs, objs, ics):
        if i.check == "reference":
            continue
        assert i.id in before and before[i.id] == i, i.id
