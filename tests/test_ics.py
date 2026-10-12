import pytest

from tpg.ics import FEATURE_LIMIT, build_ics
from tpg.models import MODALITY_VALUES, PRESENCE_VALUES, Requirement, TestObject


def req(**kw):
    base = dict(id="REQ-5.1-1", clause_id="5.1", text="The device shall respond within 500 ms.", modality="shall",
                conditions=[], source_quote="shall respond within 500 ms")
    return Requirement(**{**base, **kw})


def obj(**kw):
    base = dict(id="OBJ-5.4-1", clause_id="5.4", name="nonce", kind="parameter", source_quote="Name: nonce")
    return TestObject(**{**base, **kw})


@pytest.mark.parametrize("modality,status", [("shall", "mandatory"), ("shall_not", "mandatory"), ("should", "optional"),
                                             ("should_not", "optional"), ("may", "optional")])
def test_requirement_modality_status_mapping(modality, status):
    assert [i.status for i in build_ics([req(modality=modality)], [])] == [status]


def test_every_modality_is_mapped():
    assert {i.status for i in build_ics([req(modality=m) for m in MODALITY_VALUES], [])} == {"mandatory", "optional"}
    assert len(build_ics([req(modality=m) for m in MODALITY_VALUES], [])) == len(MODALITY_VALUES)


@pytest.mark.parametrize("presence", PRESENCE_VALUES)
def test_object_presence_passes_straight_through_except_unspecified(presence):
    kw = {"condition": "the request asks for it"} if presence == "conditional" else {}
    items = build_ics([], [obj(presence=presence, **kw)])
    if presence == "unspecified":
        assert items == []
    else:
        assert [i.status for i in items] == [presence]


def test_ordering_objects_then_requirements_and_id_format():
    items = build_ics([req()], [obj(presence="mandatory")])
    assert [i.id for i in items] == ["ICS-OBJ-5.4-1", "ICS-REQ-5.1-1"]
    assert [i.source_id for i in items] == ["OBJ-5.4-1", "REQ-5.1-1"]
    assert [i.clause_id for i in items] == ["5.4", "5.1"]


def test_feature_is_the_object_name_or_the_truncated_requirement_text():
    long = "The device shall " + "a" * 400
    items = build_ics([req(text=long)], [obj(presence="optional")])
    assert items[0].feature == "nonce"
    assert items[1].feature == long[:FEATURE_LIMIT] and len(items[1].feature) == FEATURE_LIMIT


def test_empty_feature_is_skipped():
    assert build_ics([req(text="   ")], [obj(presence="mandatory", name="  ")]) == []


def test_condition_and_applies_when_are_carried_over():
    items = build_ics([req(applies_when=["the extended profile is in use"])],
                      [obj(presence="conditional", condition="the request asks for it",
                           applies_when=["the device is in secure mode"])])
    assert items[0].condition == "the request asks for it"
    assert items[0].applies_when == ["the device is in secure mode"]
    assert items[1].applies_when == ["the extended profile is in use"]
