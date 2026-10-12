"""Rule checks on one generated test case against its coverage item. No LLM."""
from tpg.models import CoverageItem, TestCaseDraft

# ponytail: word gate, not semantics; a cross-model critic would be the upgrade
# D30 words a negative purpose two ways and both are behaviours a tester observes: an invalid instance is
# supplied and the system under test rejects it (REJECTION_WORDS), or the system under test never produces
# or holds one, so the observation is over every instance it makes (NEVER_WORDS, the majority wording since
# 83 per cent of objects are produced or internal). What the gate excludes is a case that observes nothing
# and merely asserts an absence of obligation -- "the nonce is not required, so the device need not emit
# one" -- which NOT_AN_OUTCOME removes from the text before an outcome is looked for, so that the negations
# such a sentence contains cannot stand in for one.
REJECTION_WORDS = ("reject", "error", "fail", "refuse", "ignore", "absent", "invalid", "discard", "abort",
                   "terminat", "does not", "is not", "are not", "not be", "silently", "drop", "nothing",
                   "no effect", "unchanged")
NEVER_WORDS = ("never", "always", "at no point", "in no case", "none of", "no malformed", "no invalid",
               "no ill-formed", "no such", "no instance", "no occurrence", "no violation", "not malformed",
               "not observed", "not emitted", "not produced", "not generated", "not stored")
NEGATIVE_WORDS = REJECTION_WORDS + NEVER_WORDS
NOT_AN_OUTCOME = ("no error", "without error", "not applicable", "fails to reject", "not require",
                  "not mandator", "not oblig", "does not have to", "need not", "no obligation",
                  "no requirement", "is optional", "are optional")


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
        for e in NOT_AN_OUTCOME:
            text = text.replace(e, " ")
        if not any(w in text for w in NEGATIVE_WORDS):
            msgs.append("a negative case must observe an outcome: the rejection of an invalid instance, an error, "
                        "the absence of the obligation's effect, or that the system under test never produces or "
                        "holds such an instance (expected_result or pass_criteria must say so, e.g. 'is rejected', "
                        "'returns an error', 'no malformed instance is ever observed'); that something is not "
                        "required is not an outcome")
    return msgs
