from tpg.generate import build_generate_prompt, context_excerpt, generate, generate_item
from tpg.llm import LLMError
from tpg.models import Clause, CoverageItem, Requirement, TestObject

CLAUSE = Clause(id="5.4", title="Params", text="Intro.\nName: nonce | Presence: mandatory | Type: text string\nThe reader shall reject a request whose nonce is missing.")
OBJ = TestObject(id="OBJ-5.4-1", clause_id="5.4", name="nonce", kind="parameter", direction="received", presence="mandatory",
                 type="text string", source_quote="Name: nonce | Presence: mandatory | Type: text string")
REQ = Requirement(id="REQ-5.4-1", clause_id="5.4", text="The reader shall reject a request whose nonce is missing.", modality="shall",
                  conditions=[], source_quote="shall reject a request whose nonce is missing")
ITEM = CoverageItem(id="CI-OBJ-5.4-1-absence", source_id="OBJ-5.4-1", clause_id="5.4", check="absence", kind="negative",
                    purpose="Verify the reaction of the system under test when nonce is absent")
DRAFT = {"objective": "o", "preconditions": [], "inputs": ["request without nonce"], "steps": ["send request"],
         "expected_result": "the request is rejected with an error", "pass_criteria": "error returned"}


def test_context_excerpt_windows_around_quote():
    long = Clause(id="1", title="t", text="a" * 3000 + "\nName: nonce | X: y\n" + "b" * 3000)
    ex = context_excerpt(long, "Name: nonce | X: y")
    assert "Name: nonce" in ex and len(ex) <= 3200
    assert context_excerpt(CLAUSE, "missing quote") == CLAUSE.text


def test_prompt_carries_purpose_source_and_kind_rule():
    p = build_generate_prompt(ITEM, OBJ, CLAUSE, ["old failure"])
    assert ITEM.purpose in p and "nonce" in p and "mandatory" in p and "negative" in p and "old failure" in p
    p2 = build_generate_prompt(CoverageItem(id="CI-REQ-5.4-1-nominal", source_id="REQ-5.4-1", clause_id="5.4", check="nominal",
                                            kind="nominal", purpose="x"), REQ, CLAUSE, [])
    assert REQ.text in p2 and "condition_assignment" not in p2


def test_generate_item_sets_ids_kind_and_assignment(fake_llm):
    tc, gap = generate_item(ITEM, OBJ, CLAUSE, fake_llm([DRAFT]))
    assert gap is None and tc.id == "TC-CI-OBJ-5.4-1-absence" and tc.source_id == "OBJ-5.4-1"
    assert tc.coverage_item_id == ITEM.id and tc.kind == "negative" and tc.condition_assignment is None


def test_generate_item_retries_then_gap(fake_llm):
    weak = {**DRAFT, "expected_result": "the request is processed", "pass_criteria": "ok"}
    llm = fake_llm([weak, LLMError("bad json"), weak])
    tc, gap = generate_item(ITEM, OBJ, CLAUSE, llm)
    assert tc is None and gap is not None and gap.stage == "generate" and gap.source_id == "OBJ-5.4-1"
    assert ITEM.id in gap.reason and "reject" in llm.prompts[1] and "bad json" in llm.prompts[2]


def test_generate_collects_across_items(fake_llm):
    items = [ITEM, CoverageItem(id="CI-REQ-5.4-1-nominal", source_id="REQ-5.4-1", clause_id="5.4", check="nominal", kind="nominal", purpose="x")]
    cases, gaps = generate(items, [REQ], [OBJ], [CLAUSE], fake_llm([], fallback=DRAFT))
    assert [c.id for c in cases] == ["TC-CI-OBJ-5.4-1-absence", "TC-CI-REQ-5.4-1-nominal"] and gaps == []
