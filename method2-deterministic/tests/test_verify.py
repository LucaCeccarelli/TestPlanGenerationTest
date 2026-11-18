from tpg.models import CoverageItem, TestCaseDraft
from tpg.verify import check_test_case, required_assignments


def item(check="presence", kind="nominal"):
    return CoverageItem(id="CI-x", source_id="OBJ-1", clause_id="1", check=check, kind=kind, group="valid_behaviour", purpose="p")


def draft(steps=("Send a request",), expected="Response within 500 ms", pc="pc"):
    return TestCaseDraft(objective="o", steps=list(steps), expected_result=expected, pass_criteria=pc)


def test_required_assignments():
    assert required_assignments([]) == []
    assert required_assignments(["A", "B"]) == [{"A": True, "B": True}, {"A": False, "B": True}, {"A": True, "B": False}]


def test_ok_nominal():
    assert check_test_case(item(), draft()) == []


def test_field_rules():
    assert any("steps" in m for m in check_test_case(item(), draft(steps=(" ",))))
    assert any("expected_result" in m for m in check_test_case(item(), draft(expected=" ")))
    assert any("expected_result" in m and "steps" in m for m in check_test_case(item(), draft(steps=("Same",), expected="Same")))
    assert any("pass_criteria" in m for m in check_test_case(item(), draft(pc=" ")))


def test_negative_items_need_a_rejection_style_expected_result():
    neg = item("absence", "negative")
    assert any("reject" in m for m in check_test_case(neg, draft(expected="The response is accepted")))
    assert check_test_case(neg, draft(expected="The request is rejected with an error")) == []
    assert check_test_case(neg, draft(expected="Nothing happens", pc="The obligation's effect is absent")) == []
    assert any("reject" in m for m in check_test_case(neg, draft(expected="The device returns the response and no error is raised")))
    assert check_test_case(neg, draft(expected="The device drops the request silently")) == []
    assert check_test_case(neg, draft(expected="Nothing is returned")) == []


def test_boundary_items_are_not_negative():
    assert check_test_case(item("boundary_max", "boundary"), draft(expected="Accepted at exactly 64 characters")) == []


def test_empty_objective_is_reported():
    d = TestCaseDraft.model_validate({"objective": None, "steps": ["s"], "expected_result": "r", "pass_criteria": "p"})
    assert any("objective" in m for m in check_test_case(item(), d))


# --- the two wordings D30 gives a negative purpose, each with a plausible generated case (task 17) ---

RECEIVED_PURPOSE = "Verify the reaction of the system under test when nonce is not a well-formed text string"
PRODUCED_PURPOSE = ("Verify that the system under test never produces or holds a case in which nonce is not a "
                    "well-formed text string")


def case(**kw):
    base = dict(objective="o", preconditions=["a session is open"], inputs=["i"], steps=["s"],
                expected_result="e", pass_criteria="p")
    return TestCaseDraft(**{**base, **kw})


def negative():
    return CoverageItem(id="CI-OBJ-1-encoding_invalid", source_id="OBJ-1", clause_id="1", check="encoding_invalid",
                        kind="negative", group="invalid_behaviour", purpose=PRODUCED_PURPOSE)


def test_a_negative_case_may_observe_a_rejection():
    """The received wording: an invalid instance is supplied and the system under test rejects it."""
    d = case(objective="Supply a malformed nonce and observe the reader's reaction",
             inputs=["a nonce encoded as an integer instead of a text string"],
             steps=["Send the request carrying the malformed nonce"],
             expected_result="The reader rejects the request and returns an error",
             pass_criteria="The case passes if the request is rejected and no response is returned")
    assert check_test_case(negative(), d) == []


def test_a_negative_case_may_observe_that_nothing_invalid_is_ever_produced():
    """The produced or internal wording, which 83 per cent of real objects carry: nothing is supplied and
    the observation is over every instance the system under test makes."""
    d = case(objective="Observe that every nonce the device emits is well-formed",
             steps=["Capture 50 consecutive responses", "Decode the nonce of each"],
             expected_result="Every nonce emitted is a well-formed text string; no malformed nonce is ever observed",
             pass_criteria="The case passes if no malformed nonce is observed in any captured response")
    assert check_test_case(negative(), d) == []


def test_a_negative_case_may_not_assert_an_absence_of_obligation():
    """The case that distinguishes the two accepted outcomes from what the gate excludes: nothing is
    observed at all, only that the specification asks for nothing."""
    d = case(expected_result="The nonce is not required by the specification, so the device need not emit one",
             pass_criteria="The case passes if the nonce is not mandatory for this profile")
    assert any("outcome" in m for m in check_test_case(negative(), d))
