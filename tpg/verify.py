"""Rule checks on generated test cases. No LLM. Returns human-readable failure messages fed back to the model."""
from tpg.models import Requirement, TestCaseDraft


def required_assignments(conditions: list[str]) -> list[dict[str, bool]]:
    """CiRA-style minimal set: all conditions true, then each one flipped to false in turn."""
    if not conditions:
        return []
    base = {c: True for c in conditions}
    return [dict(base)] + [{**base, c: False} for c in conditions]


def check_test_cases(req: Requirement, drafts: list[TestCaseDraft]) -> list[str]:
    msgs: list[str] = []
    nominal = sum(1 for d in drafts if d.kind == "nominal")
    if nominal != 1:
        msgs.append(f"expected exactly one nominal case, got {nominal}")
    if req.modality in ("shall", "shall_not") and not any(d.kind == "negative" for d in drafts):
        msgs.append("a shall/shall_not requirement needs at least one negative case")
    for n, d in enumerate(drafts, 1):
        if not [s for s in d.steps if s.strip()]:
            msgs.append(f"case {n}: steps are empty")
        if not d.expected_result.strip():
            msgs.append(f"case {n}: expected_result is empty")
        elif d.expected_result.strip() in {s.strip() for s in d.steps}:
            msgs.append(f"case {n}: expected_result must differ from the steps")
        if not d.pass_criteria.strip():
            msgs.append(f"case {n}: pass_criteria is empty")
    required = required_assignments(req.conditions)
    given = [d.condition_assignment for d in drafts if d.condition_assignment is not None]
    if not required and given:
        msgs.append("condition_assignment must be null for an unconditional requirement")
    if required:
        key = lambda a: tuple(sorted(a.items()))
        req_set, got_set = {key(a) for a in required}, {key(a) for a in given}
        if req_set != got_set:
            msgs.append(f"condition_assignment set must be exactly {required}, got {given}")
    return msgs
