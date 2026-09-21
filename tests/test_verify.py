from tpg.models import Requirement, TestCaseDraft
from tpg.verify import check_test_cases, required_assignments

REQ = Requirement(id="REQ-5.1-1", clause_id="5.1", text="The device shall respond within 500 ms.",
                  modality="shall", conditions=[], source_quote="shall respond within 500 ms")
COND_REQ = Requirement(id="REQ-5.2-1", clause_id="5.2",
                       text="If A or B, the device shall not process the request.", modality="shall_not",
                       conditions=["A", "B"], source_quote="shall not process the request")


def tc(kind="nominal", steps=("Send a request",), expected="Response within 500 ms", assignment=None, **kw):
    return TestCaseDraft(kind=kind, objective=kw.get("objective", "obj"), steps=list(steps),
                         expected_result=expected, pass_criteria=kw.get("pass_criteria", "pc"),
                         condition_assignment=assignment)


def test_required_assignments():
    assert required_assignments([]) == []
    assert required_assignments(["A", "B"]) == [{"A": True, "B": True}, {"A": False, "B": True}, {"A": True, "B": False}]


def test_ok_unconditional_shall():
    assert check_test_cases(REQ, [tc(), tc("negative", expected="Error"), tc("boundary", expected="Exactly 500 ms ok")]) == []


def test_exactly_one_nominal():
    assert any("nominal" in m for m in check_test_cases(REQ, [tc("negative", expected="e")]))
    assert any("nominal" in m for m in check_test_cases(REQ, [tc(), tc(), tc("negative", expected="e")]))


def test_shall_needs_negative():
    msgs = check_test_cases(REQ, [tc()])
    assert any("negative" in m for m in msgs)


def test_may_does_not_need_negative():
    may = REQ.model_copy(update={"modality": "may"})
    assert check_test_cases(may, [tc()]) == []


def test_empty_steps_and_results():
    msgs = check_test_cases(REQ, [tc(steps=()), tc("negative", expected="")])
    assert any("steps" in m for m in msgs) and any("expected_result" in m for m in msgs)


def test_expected_result_must_differ_from_steps():
    msgs = check_test_cases(REQ, [tc(steps=("Same",), expected="Same"), tc("negative", expected="e")])
    assert any("expected_result" in m and "steps" in m for m in msgs)


def test_empty_pass_criteria():
    msgs = check_test_cases(REQ, [tc(pass_criteria=" "), tc("negative", expected="e")])
    assert any("pass_criteria" in m for m in msgs)


def test_conditional_requires_exact_assignment_set():
    ok = [tc(assignment={"A": True, "B": True}),
          tc("negative", expected="rejected", assignment={"A": False, "B": True}),
          tc("negative", expected="rejected", assignment={"A": True, "B": False})]
    assert check_test_cases(COND_REQ, ok) == []
    missing = ok[:2]
    assert any("condition_assignment" in m for m in check_test_cases(COND_REQ, missing))
    wrong = ok[:2] + [tc("negative", expected="rejected", assignment={"A": False, "B": False})]
    assert any("condition_assignment" in m for m in check_test_cases(COND_REQ, wrong))


def test_unconditional_case_with_assignment_is_rejected():
    msgs = check_test_cases(REQ, [tc(assignment={"A": True}), tc("negative", expected="e")])
    assert any("condition_assignment" in m for m in msgs)
