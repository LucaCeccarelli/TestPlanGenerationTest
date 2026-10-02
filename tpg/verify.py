"""Rule checks on one generated test case against its coverage item. No LLM."""
from tpg.models import CoverageItem, TestCaseDraft

# ponytail: word gate, not semantics; a cross-model critic would be the upgrade
NEGATIVE_WORDS = ("reject", "error", "fail", "refuse", "ignore", "absent", "invalid", "discard", "abort", "terminat",
                  "does not", "is not", "are not", "not be", "silently", "drop", "nothing", "no effect", "unchanged")
NEGATIVE_EXCEPTIONS = ("no error", "without error", "not applicable", "fails to reject")


def required_assignments(conditions: list[str]) -> list[dict[str, bool]]:
    """CiRA-style minimal set: all conditions true, then each one flipped to false in turn."""
    if not conditions:
        return []
    base = {c: True for c in conditions}
    return [dict(base)] + [{**base, c: False} for c in conditions]


def check_test_case(item: CoverageItem, d: TestCaseDraft) -> list[str]:
    msgs: list[str] = []
    if not d.objective.strip():
        msgs.append("objective is empty")
    if not [s for s in d.steps if s.strip()]:
        msgs.append("steps are empty")
    if not d.expected_result.strip():
        msgs.append("expected_result is empty")
    elif d.expected_result.strip() in {s.strip() for s in d.steps}:
        msgs.append("expected_result must differ from the steps")
    if not d.pass_criteria.strip():
        msgs.append("pass_criteria is empty")
    if item.kind == "negative":
        text = (d.expected_result + " " + d.pass_criteria).lower()
        for e in NEGATIVE_EXCEPTIONS:
            text = text.replace(e, " ")
        if not any(w in text for w in NEGATIVE_WORDS):
            msgs.append("a negative case must expect a rejection, an error, or the absence of the obligation's effect "
                        "(expected_result or pass_criteria must say so, e.g. 'is rejected', 'returns an error', 'is not ...')")
    return msgs
