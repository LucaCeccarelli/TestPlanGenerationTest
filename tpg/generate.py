"""One LLM call per source carrying up to BATCH_LIMIT of its coverage items, each case checked by
verify.check_test_case and only the missing or rejected ids re-prompted (D26). `batch=False` keeps the
older path of one call per coverage item, for comparison."""
import json
import re

from tpg.llm import LLMError
from tpg.models import (Clause, CoverageItem, Gap, Requirement, TestCase, TestCaseBatch, TestCaseDraft,
                        TestObject)
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
BATCH_LIMIT = 8
NO_CASE = "no test case was returned for this coverage item"


def context_excerpt(clause: Clause, quote: str) -> str:
    """Window the clause around the quote. The quote may be wrapped across lines in the raw text, so it
    is matched word by word with any whitespace between words."""
    text = clause.text
    if len(text) <= WHOLE:
        return text
    words = quote.split()[:8]
    m = re.search(r"\s+".join(map(re.escape, words)), text, re.I) if words else None
    if m is None:
        return text[:WHOLE]
    start = max(0, m.start() - WINDOW)
    return text[start:m.start() + WINDOW]


def _describe_source(src: Requirement | TestObject) -> str:
    if isinstance(src, Requirement):
        cond = f"\nconditions: {src.conditions}" if src.conditions else ""
        return f"Requirement {src.id} (modality {src.modality}): {src.text}{cond}\nquoted from the specification: \"{src.source_quote}\""
    attrs = {k: v for k, v in src.model_dump().items() if k not in ("id", "clause_id", "source_quote") and v not in (None, [], "unspecified")}
    return f"Object {src.id}: " + json.dumps(attrs, ensure_ascii=False) + f"\nquoted from the specification: \"{src.source_quote}\""


CONDITION_LEAD = "Conditions for this case, state them in preconditions or inputs"


def _conditions(item: CoverageItem) -> str:
    if item.condition_assignment is None:
        return ""
    return ", ".join(f"'{c}' {'holds' if v else 'does not hold'}" for c, v in item.condition_assignment.items())


def build_generate_prompt(item: CoverageItem, source: Requirement | TestObject, clause: Clause, failures: list[str]) -> str:
    feedback = ""
    if failures:
        feedback = "\nYour previous answer was rejected for these reasons; fix them:\n" + "\n".join(f"- {f}" for f in failures) + "\n"
    cond = _conditions(item)
    assign = f"\n- {CONDITION_LEAD}: {cond}" if cond else ""
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


def _test_case(item: CoverageItem, d: TestCaseDraft) -> TestCase:
    """The one place a test case is minted, so its id is the same whichever path produced the draft."""
    return TestCase(id=f"TC-{item.id}", source_id=item.source_id, coverage_item_id=item.id, kind=item.kind,
                    condition_assignment=item.condition_assignment, **d.model_dump(exclude={"coverage_item_id"}))


def generate_item(item: CoverageItem, source: Requirement | TestObject, clause: Clause, llm, attempts: int = 3) -> tuple[TestCase | None, Gap | None]:
    failures: list[str] = []
    for _ in range(attempts):
        try:
            draft = llm.complete(build_generate_prompt(item, source, clause, failures), TestCaseDraft)
        except LLMError as e:
            failures = failures + [str(e)]
            continue
        failures = check_test_case(item, draft)
        if not failures:
            return _test_case(item, draft), None
    return None, Gap(source_id=item.source_id, clause_id=item.clause_id, stage="generate",
                     reason=f"{item.id}: " + "; ".join(failures), attempts=attempts)


def build_batch_prompt(source: Requirement | TestObject, clause: Clause, items: list[CoverageItem],
                       failures: list[str]) -> str:
    purposes = "\n".join(f"- {i.id} (check: {i.check}, kind: {i.kind}): {i.purpose}"
                         + (f"\n  {CONDITION_LEAD}: {c}" if (c := _conditions(i)) else "") for i in items)
    # KIND_RULES is worded for a single case ("This is a nominal case: ..."); here the kind labels the rule
    kinds = "\n".join(f"- A case of kind {k}: {KIND_RULES[k].split(': ', 1)[1]}"
                      for k in dict.fromkeys(i.kind for i in items))
    feedback = ""
    if failures:
        feedback = ("\nSome cases of your previous answer were rejected for these reasons; fix them:\n"
                    + "\n".join(f"- {f}" for f in failures) + "\n")
    return f"""You write ONE test case for each of several test purposes, all derived from the same part of a technical specification.

The {len(items)} test purposes, one test case for each:
{purposes}

Source of the purposes:
{_describe_source(source)}

Context, clause {clause.id} "{clause.title}" (excerpt):
\"\"\"
{context_excerpt(clause, source.source_quote)}
\"\"\"

{FIELDS}

Rules:
- Return exactly one case per test purpose id listed above, in that order, and no case for any other id.
- "coverage_item_id" repeats the id of the test purpose the case answers, exactly as written above.
- Each case accomplishes exactly its own test purpose and nothing else.
{kinds}
- preconditions, inputs and steps are lists of plain strings; write data values as text.
- Where the specification makes them the same, cases of this source state a shared precondition in the same words.
{feedback}
Reply with JSON only: {{"cases": [{{"coverage_item_id": ..., "objective": ..., "preconditions": [...], "inputs": [...],
"steps": [...], "expected_result": ..., "pass_criteria": ...}}]}}"""


def generate_source(source: Requirement | TestObject, clause: Clause, items: list[CoverageItem], llm,
                    attempts: int = 3) -> tuple[list[TestCase], list[Gap]]:
    """One call for the coverage items of one source. A case is accepted when its id was asked for, is
    answered once and passes the checks of its own item; every other id is re-prompted."""
    by_id = {i.id: i for i in items}
    cases: dict[str, TestCase] = {}
    reasons: dict[str, list[str]] = {}
    failures: list[str] = []
    for _ in range(attempts):
        pending = [i for i in items if i.id not in cases]
        if not pending:
            break
        try:
            batch = llm.complete(build_batch_prompt(source, clause, pending, failures), TestCaseBatch)
        except LLMError as e:
            failures = [str(e)]
            continue
        failures, seen = [], set()
        for entry in batch.cases:
            iid = entry.coverage_item_id
            if iid not in by_id:
                failures.append(f"coverage_item_id {iid!r} is not one of the ids listed; return a case only for those ids")
                continue
            if iid in seen or iid in cases:
                failures.append(f"coverage_item_id {iid!r} is answered more than once; return exactly one case per id")
                continue
            seen.add(iid)
            msgs = check_test_case(by_id[iid], entry)
            if msgs:
                failures.append(f"{iid}: " + "; ".join(msgs))
                reasons[iid] = msgs
            else:
                cases[iid] = _test_case(by_id[iid], entry)
                reasons.pop(iid, None)
    gaps = [Gap(source_id=i.source_id, clause_id=i.clause_id, stage="generate",
                reason=f"{i.id}: " + "; ".join(reasons.get(i.id) or [NO_CASE]), attempts=attempts)
            for i in items if i.id not in cases]
    return [cases[i.id] for i in items if i.id in cases], gaps


def generate(items: list[CoverageItem], reqs: list[Requirement], objs: list[TestObject], clauses: list[Clause], llm,
             attempts: int = 3, log=lambda s: None, batch: bool = True) -> tuple[list[TestCase], list[Gap]]:
    sources: dict[str, Requirement | TestObject] = {r.id: r for r in reqs} | {o.id: o for o in objs}
    by_clause = {c.id: c for c in clauses}
    cases: list[TestCase] = []
    gaps: list[Gap] = []
    if not batch:
        for item in items:
            tc, gap = generate_item(item, sources[item.source_id], by_clause[item.clause_id], llm, attempts)
            if tc:
                cases.append(tc)
            if gap:
                gaps.append(gap)
            log(f"{item.id}: " + ("ok" if tc else "GAP"))
        return cases, gaps
    groups: dict[str, list[CoverageItem]] = {}
    for item in items:
        groups.setdefault(item.source_id, []).append(item)
    for source_id, group in groups.items():
        for start in range(0, len(group), BATCH_LIMIT):
            part = group[start:start + BATCH_LIMIT]
            got, part_gaps = generate_source(sources[source_id], by_clause[part[0].clause_id], part, llm, attempts)
            cases.extend(got)
            gaps.extend(part_gaps)
            log(f"{source_id}: {len(got)}/{len(part)} cases" + (" (GAP)" if part_gaps else ""))
    return cases, gaps
