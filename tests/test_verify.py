from tpg.models import CoverageItem, TestCaseDraft
from tpg.verify import check_test_case, required_assignments


def item(check="presence", kind="nominal"):
    return CoverageItem(id="CI-x", source_id="OBJ-1", clause_id="1", check=check, kind=kind, purpose="p")


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
