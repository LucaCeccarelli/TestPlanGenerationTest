"""One LLM call per requirement, checked by verify.check_test_cases, retried with feedback."""
import json

from tpg.llm import LLMError
from tpg.models import Clause, Gap, Requirement, TestCase, TestCaseBatch
from tpg.verify import check_test_cases, required_assignments

FIELDS = """Test case fields (ISO/IEC/IEEE 29119-3 test case specification):
- kind: "nominal" (the requirement is met on the main path), "negative" (the obligation is violated or the condition is false and the system must react), or "boundary" (a limit value: exactly at, just below, just above).
- objective: one sentence, what this case demonstrates.
- preconditions: list of states that must hold before the steps.
- inputs: list of test data / stimuli.
- steps: ordered list of tester actions.
- expected_result: what is observed if the requirement holds. Must not repeat a step.
- pass_criteria: the measurable rule that decides pass/fail.
- condition_assignment: see below."""


def build_generate_prompt(req: Requirement, clause: Clause, failures: list[str]) -> str:
    required = required_assignments(req.conditions)
    if required:
        assign = ("This requirement is conditional. Produce exactly these condition_assignment values, one case each "
                  "(the all-true one is the nominal case, the others are negative cases):\n"
                  + "\n".join(f"- {json.dumps(a)}" for a in required))
    else:
        assign = "This requirement is unconditional: set condition_assignment to null in every case."
    feedback = ""
    if failures:
        feedback = "\nYour previous answer was rejected for these reasons; fix them:\n" + "\n".join(f"- {f}" for f in failures) + "\n"
    return f"""You write test cases for one requirement taken from a technical standard.

Requirement {req.id} (modality: {req.modality}):
{req.text}

Context, clause {clause.id} "{clause.title}":
\"\"\"
{clause.text}
\"\"\"

{FIELDS}

Rules:
- Produce exactly one nominal case.
- Produce at least one negative case when the modality is shall or shall_not.
- Produce one boundary case when the requirement mentions a numeric limit, range, size, or time.
- {assign}
{feedback}
Reply with JSON only: {{"test_cases": [{{"kind": ..., "objective": ..., "preconditions": [...], "inputs": [...], "steps": [...], "expected_result": ..., "pass_criteria": ..., "condition_assignment": ...}}]}}"""


def generate_requirement(req: Requirement, clause: Clause, llm, attempts: int = 3) -> tuple[list[TestCase], Gap | None]:
    failures: list[str] = []
    for _ in range(attempts):
        try:
            batch = llm.complete(build_generate_prompt(req, clause, failures), TestCaseBatch)
        except LLMError as e:
            failures = [str(e)]
            continue
        failures = check_test_cases(req, batch.test_cases)
        if not failures:
            return [TestCase(id=f"TC-{req.id}-{n}", requirement_id=req.id, **d.model_dump())
                    for n, d in enumerate(batch.test_cases, 1)], None
    return [], Gap(requirement_id=req.id, clause_id=req.clause_id, stage="generate",
                   reason="; ".join(failures), attempts=attempts)


def generate(reqs: list[Requirement], clauses: list[Clause], llm, attempts: int = 3, log=lambda s: None) -> tuple[list[TestCase], list[Gap]]:
    by_id = {c.id: c for c in clauses}
    cases: list[TestCase] = []
    gaps: list[Gap] = []
    for req in reqs:
        got, gap = generate_requirement(req, by_id[req.clause_id], llm, attempts)
        cases.extend(got)
        if gap:
            gaps.append(gap)
        log(f"{req.id}: {len(got)} test cases" + (" (GAP)" if gap else ""))
    return cases, gaps
