"""One LLM call per coverage item, checked by verify.check_test_case, retried with feedback."""
import json

from tpg.extract import norm
from tpg.llm import LLMError
from tpg.models import Clause, CoverageItem, Gap, Requirement, TestCase, TestCaseDraft, TestObject
from tpg.verify import check_test_case

FIELDS = """Test case fields (ISO/IEC/IEEE 29119-3 test case specification):
- objective: one sentence, what this case demonstrates.
- preconditions: list of states that must hold before the steps.
- inputs: list of test data / stimuli.
- steps: ordered list of tester actions, concrete enough for a test engineer to execute.
- expected_result: what is observed if the specification is met. Must not repeat a step.
- pass_criteria: the measurable rule that decides pass/fail."""

KIND_RULES = {
    "nominal": "This is a nominal case: the stimulus is valid and the expected result is the behaviour the specification requires.",
    "negative": "This is a negative case: the stimulus violates the obligation or the condition does not hold; the expected result "
                "must describe the rejection, the error, or the absence of the obligation's effect.",
    "boundary": "This is a boundary case: use the exact limit value(s) stated (minimum or maximum), and state which one.",
}
WINDOW = 1500
WHOLE = 4000


def context_excerpt(clause: Clause, quote: str) -> str:
    text = clause.text
    if len(text) <= WHOLE:
        return text
    pos = norm(text).find(norm(quote)[:60])
    if pos < 0:
        return text[:WHOLE]
    # positions in the normalised text differ from the raw text; locate the raw quote start approximately
    raw_pos = text.lower().find(quote.strip()[:30].lower())
    if raw_pos < 0:
        raw_pos = min(pos, len(text))
    start = max(0, raw_pos - WINDOW)
    return text[start:raw_pos + WINDOW]


def _describe_source(src: Requirement | TestObject) -> str:
    if isinstance(src, Requirement):
        cond = f"\nconditions: {src.conditions}" if src.conditions else ""
        return f"Requirement {src.id} (modality {src.modality}): {src.text}{cond}\nquoted from the specification: \"{src.source_quote}\""
    attrs = {k: v for k, v in src.model_dump().items() if k not in ("id", "clause_id", "source_quote") and v not in (None, [], "unspecified")}
    return f"Object {src.id}: " + json.dumps(attrs, ensure_ascii=False) + f"\nquoted from the specification: \"{src.source_quote}\""


def build_generate_prompt(item: CoverageItem, source: Requirement | TestObject, clause: Clause, failures: list[str]) -> str:
    feedback = ""
    if failures:
        feedback = "\nYour previous answer was rejected for these reasons; fix them:\n" + "\n".join(f"- {f}" for f in failures) + "\n"
    assign = ""
    if item.condition_assignment is not None:
        assign = ("\n- Conditions for this case, state them in preconditions or inputs: "
                  + ", ".join(f"'{c}' {'holds' if v else 'does not hold'}" for c, v in item.condition_assignment.items()))
    return f"""You write ONE test case for one test purpose derived from a technical specification.

Test purpose {item.id} (check: {item.check}, kind: {item.kind}):
{item.purpose}

Source of the purpose:
{_describe_source(source)}

Context, clause {clause.id} "{clause.title}" (excerpt):
\"\"\"
{context_excerpt(clause, source.source_quote)}
\"\"\"

{FIELDS}

Rules:
- The case accomplishes exactly this test purpose and nothing else.
- {KIND_RULES[item.kind]}
- preconditions, inputs and steps are lists of plain strings; write data values as text.{assign}
{feedback}
Reply with JSON only: {{"objective": ..., "preconditions": [...], "inputs": [...], "steps": [...], "expected_result": ..., "pass_criteria": ...}}"""


def generate_item(item: CoverageItem, source: Requirement | TestObject, clause: Clause, llm, attempts: int = 3) -> tuple[TestCase | None, Gap | None]:
    failures: list[str] = []
    for _ in range(attempts):
        try:
            draft = llm.complete(build_generate_prompt(item, source, clause, failures), TestCaseDraft)
        except LLMError as e:
            failures = [str(e)]
            continue
        failures = check_test_case(item, draft)
        if not failures:
            return TestCase(id=f"TC-{item.id}", source_id=item.source_id, coverage_item_id=item.id, kind=item.kind,
                            condition_assignment=item.condition_assignment, **draft.model_dump()), None
    return None, Gap(source_id=item.source_id, clause_id=item.clause_id, stage="generate",
                     reason=f"{item.id}: " + "; ".join(failures), attempts=attempts)


def generate(items: list[CoverageItem], reqs: list[Requirement], objs: list[TestObject], clauses: list[Clause], llm,
             attempts: int = 3, log=lambda s: None) -> tuple[list[TestCase], list[Gap]]:
    sources: dict[str, Requirement | TestObject] = {r.id: r for r in reqs} | {o.id: o for o in objs}
    by_clause = {c.id: c for c in clauses}
    cases: list[TestCase] = []
    gaps: list[Gap] = []
    for item in items:
        tc, gap = generate_item(item, sources[item.source_id], by_clause[item.clause_id], llm, attempts)
        if tc:
            cases.append(tc)
        if gap:
            gaps.append(gap)
        log(f"{item.id}: " + ("ok" if tc else "GAP"))
    return cases, gaps
