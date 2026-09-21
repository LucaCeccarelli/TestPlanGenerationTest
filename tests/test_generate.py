from tpg.generate import build_generate_prompt, generate, generate_requirement
from tpg.llm import LLMError
from tpg.models import Clause, Requirement

CLAUSE = Clause(id="5.1", title="Response time", text="The device shall respond within 500 ms.")
REQ = Requirement(id="REQ-5.1-1", clause_id="5.1", text="The device shall respond within 500 ms.",
                  modality="shall", conditions=[], source_quote="shall respond within 500 ms")
COND = Requirement(id="REQ-5.2-1", clause_id="5.2", text="If A or B the device shall not process.",
                   modality="shall_not", conditions=["A", "B"], source_quote="shall not process")

NOM = {"kind": "nominal", "objective": "o", "preconditions": [], "inputs": ["valid request"],
       "steps": ["send request", "measure time"], "expected_result": "reply within 500 ms", "pass_criteria": "t <= 500 ms"}
NEG = {**NOM, "kind": "negative", "expected_result": "error", "pass_criteria": "error returned"}
BND = {**NOM, "kind": "boundary", "expected_result": "reply at exactly 500 ms accepted"}
GOOD = {"test_cases": [NOM, NEG, BND]}


def test_prompt_mentions_requirement_clause_rules_and_assignments():
    p = build_generate_prompt(COND, CLAUSE, ["old failure"])
    assert COND.text in p and CLAUSE.text in p and "old failure" in p
    assert '{"A": true, "B": true}' in p and '{"A": false, "B": true}' in p
    assert "exactly one nominal" in p and "boundary" in p


def test_prompt_unconditional_says_null():
    p = build_generate_prompt(REQ, CLAUSE, [])
    assert "condition_assignment" in p and "null" in p


def test_generate_requirement_assigns_ids(fake_llm):
    cases, gap = generate_requirement(REQ, CLAUSE, fake_llm([GOOD]))
    assert gap is None
    assert [c.id for c in cases] == ["TC-REQ-5.1-1-1", "TC-REQ-5.1-1-2", "TC-REQ-5.1-1-3"]
    assert all(c.requirement_id == "REQ-5.1-1" for c in cases)


def test_generate_requirement_retries_then_gap(fake_llm):
    only_nominal = {"test_cases": [NOM]}
    llm = fake_llm([only_nominal, LLMError("bad json"), only_nominal])
    cases, gap = generate_requirement(REQ, CLAUSE, llm)
    assert cases == [] and gap is not None
    assert gap.stage == "generate" and gap.requirement_id == "REQ-5.1-1" and gap.clause_id == "5.1"
    assert gap.attempts == 3 and "negative" in gap.reason
    assert "negative" in llm.prompts[1] and "bad json" in llm.prompts[2]


def test_generate_collects_across_requirements(fake_llm):
    cond_good = {"test_cases": [
        {**NOM, "condition_assignment": {"A": True, "B": True}},
        {**NEG, "condition_assignment": {"A": False, "B": True}},
        {**NEG, "condition_assignment": {"A": True, "B": False}},
    ]}
    c52 = Clause(id="5.2", title="x", text="If A or B the device shall not process.")
    cases, gaps = generate([REQ, COND], [CLAUSE, c52], fake_llm([GOOD, cond_good]))
    assert len(cases) == 6 and gaps == []
    assert cases[3].id == "TC-REQ-5.2-1-1"
