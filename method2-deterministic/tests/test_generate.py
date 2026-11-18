import json
import re

from tpg.generate import (BATCH_LIMIT, KIND_RULES, build_batch_prompt, build_generate_prompt, context_excerpt, generate,
                          generate_item, generate_source)
from tpg.llm import LLMError, OllamaLLM
from tpg.models import Clause, CoverageItem, Requirement, TestCaseBatch, TestObject

CLAUSE = Clause(id="5.4", title="Params", text="Intro.\nName: nonce | Presence: mandatory | Type: text string\nThe reader shall reject a request whose nonce is missing.")
OBJ = TestObject(id="OBJ-5.4-1", clause_id="5.4", name="nonce", kind="parameter", direction="received", presence="mandatory",
                 type="text string", source_quote="Name: nonce | Presence: mandatory | Type: text string")
REQ = Requirement(id="REQ-5.4-1", clause_id="5.4", text="The reader shall reject a request whose nonce is missing.", modality="shall",
                  conditions=[], source_quote="shall reject a request whose nonce is missing")
ITEM = CoverageItem(id="CI-OBJ-5.4-1-absence", source_id="OBJ-5.4-1", clause_id="5.4", check="absence", kind="negative", group="invalid_behaviour",
                    purpose="Verify the reaction of the system under test when nonce is absent")
DRAFT = {"objective": "o", "preconditions": [], "inputs": ["request without nonce"], "steps": ["send request"],
         "expected_result": "the request is rejected with an error", "pass_criteria": "error returned"}


def test_context_excerpt_windows_around_quote():
    long = Clause(id="1", title="t", text="a" * 3000 + "\nName: nonce | X: y\n" + "b" * 3000)
    ex = context_excerpt(long, "Name: nonce | X: y")
    assert "Name: nonce" in ex and len(ex) <= 3200
    assert context_excerpt(CLAUSE, "missing quote") == CLAUSE.text


def test_context_excerpt_finds_quote_wrapped_across_lines():
    # the blank run collapses to one space when normalised, so a normalised index used as a raw
    # offset lands the window ~2000 characters before the quote
    body = "x" * 3000 + "\n" * 2000 + "The reader shall\nreject a request whose nonce\nis missing.\n" + "y" * 5000
    ex = context_excerpt(Clause(id="1", title="t", text=body), "The reader shall reject a request whose nonce is missing.")
    assert "reject a request whose nonce" in ex and len(ex) <= 2 * 1500 + 100


def test_prompt_carries_purpose_source_and_kind_rule():
    p = build_generate_prompt(ITEM, OBJ, CLAUSE, ["old failure"])
    assert ITEM.purpose in p and "nonce" in p and "mandatory" in p and "negative" in p and "old failure" in p
    p2 = build_generate_prompt(CoverageItem(id="CI-REQ-5.4-1-nominal", source_id="REQ-5.4-1", clause_id="5.4", check="nominal", group="valid_behaviour",
                                            kind="nominal", purpose="x"), REQ, CLAUSE, [])
    assert REQ.text in p2 and "holds" not in p2


def test_generate_item_sets_ids_kind_and_assignment(fake_llm):
    tc, gap = generate_item(ITEM, OBJ, CLAUSE, fake_llm([DRAFT]))
    assert gap is None and tc.id == "TC-CI-OBJ-5.4-1-absence" and tc.source_id == "OBJ-5.4-1"
    assert tc.coverage_item_id == ITEM.id and tc.kind == "negative" and tc.condition_assignment is None


def test_generate_item_retries_then_gap(fake_llm):
    weak = {**DRAFT, "expected_result": "the request is processed", "pass_criteria": "ok"}
    llm = fake_llm([weak, LLMError("bad json"), weak])
    tc, gap = generate_item(ITEM, OBJ, CLAUSE, llm)
    assert tc is None and gap is not None and gap.stage == "generate" and gap.source_id == "OBJ-5.4-1"
    assert ITEM.id in gap.reason and "reject" in llm.prompts[1] and "bad json" in llm.prompts[2] and "reject" in llm.prompts[2]


def test_generate_collects_across_items(fake_llm):
    items = [ITEM, CoverageItem(id="CI-REQ-5.4-1-nominal", source_id="REQ-5.4-1", clause_id="5.4", check="nominal", kind="nominal", group="valid_behaviour", purpose="x")]
    cases, gaps = generate(items, [REQ], [OBJ], [CLAUSE], fake_llm([], fallback=DRAFT), batch=False)
    assert [c.id for c in cases] == ["TC-CI-OBJ-5.4-1-absence", "TC-CI-REQ-5.4-1-nominal"] and gaps == []


# --- batched generation (D26) ---

ITEM_PRESENCE = CoverageItem(id="CI-OBJ-5.4-1-presence", source_id="OBJ-5.4-1", clause_id="5.4", check="presence",
                             kind="nominal", group="valid_behaviour", purpose="Verify that nonce is present")
ITEM_ENCODING = CoverageItem(id="CI-OBJ-5.4-1-encoding_valid", source_id="OBJ-5.4-1", clause_id="5.4",
                             check="encoding_valid", kind="nominal", group="valid_behaviour",
                             purpose="Verify that a valid nonce encoding is accepted")
THREE = [ITEM_PRESENCE, ITEM, ITEM_ENCODING]
WEAK = {**DRAFT, "expected_result": "the request is processed", "pass_criteria": "ok"}


def entry(item_id, draft=None):
    return {**(draft or DRAFT), "coverage_item_id": item_id}


def reply(items, draft=None):
    return {"cases": [entry(i.id, draft) for i in items]}


class EchoLLM:
    """Fake LLM that answers every coverage item id the prompt lists, under either schema. Lets the
    batched and the per-item path be driven by the same stand-in and compared."""

    def __init__(self, items, draft=None):
        self.items = list(items)
        self.draft = draft or DRAFT
        self.prompts: list[str] = []

    def complete(self, prompt, schema):
        self.prompts.append(prompt)
        asked = [i.id for i in self.items if re.search(re.escape(i.id) + r"\b", prompt)]
        if schema is TestCaseBatch:
            return schema.model_validate({"cases": [entry(i, self.draft) for i in asked]})
        return schema.model_validate(self.draft)


def test_batch_limit_is_eight():
    assert BATCH_LIMIT == 8


def test_batch_prompt_lists_every_item_once_and_asks_for_one_case_each():
    p = build_batch_prompt(OBJ, CLAUSE, THREE, [])
    assert all(i.id in p and i.purpose in p for i in THREE)
    assert "coverage_item_id" in p and "nonce" in p and "negative" in p and "nominal" in p


def test_generate_source_one_reply_yields_every_case(fake_llm):
    llm = fake_llm([reply(THREE)])
    cases, gaps = generate_source(OBJ, CLAUSE, THREE, llm)
    assert len(llm.prompts) == 1 and gaps == []
    assert [c.id for c in cases] == [f"TC-{i.id}" for i in THREE]
    assert [c.kind for c in cases] == ["nominal", "negative", "nominal"]
    assert [c.coverage_item_id for c in cases] == [i.id for i in THREE]
    assert {c.source_id for c in cases} == {"OBJ-5.4-1"}


def test_generate_source_reprompts_only_the_missing_id(fake_llm):
    llm = fake_llm([reply(THREE[:2]), reply(THREE[2:])])
    cases, gaps = generate_source(OBJ, CLAUSE, THREE, llm)
    assert gaps == [] and [c.coverage_item_id for c in cases] == [i.id for i in THREE]
    assert len(llm.prompts) == 2
    assert ITEM_ENCODING.id in llm.prompts[1]
    assert ITEM_PRESENCE.id not in llm.prompts[1] and ITEM.id not in llm.prompts[1]


def test_generate_source_reports_an_unknown_id_and_creates_no_case(fake_llm):
    bogus = {"cases": [entry("CI-OBJ-9.9-1-presence")]}
    llm = fake_llm([bogus, bogus, bogus])
    cases, gaps = generate_source(OBJ, CLAUSE, [ITEM_PRESENCE], llm)
    assert cases == [] and len(gaps) == 1
    assert "CI-OBJ-9.9-1-presence" in llm.prompts[1]
    assert gaps[0].stage == "generate" and gaps[0].source_id == "OBJ-5.4-1" and ITEM_PRESENCE.id in gaps[0].reason


def test_generate_source_takes_a_duplicate_id_once(fake_llm):
    duped = {"cases": [entry(ITEM_PRESENCE.id), entry(ITEM_PRESENCE.id, {**DRAFT, "objective": "second"})]}
    llm = fake_llm([duped])
    cases, gaps = generate_source(OBJ, CLAUSE, [ITEM_PRESENCE], llm)
    assert gaps == [] and len(llm.prompts) == 1 and [c.objective for c in cases] == ["o"]


def test_generate_source_reprompts_only_the_case_failing_its_kind_rule(fake_llm):
    first = {"cases": [entry(ITEM_PRESENCE.id), entry(ITEM.id, WEAK)]}
    llm = fake_llm([first, reply([ITEM])])
    cases, gaps = generate_source(OBJ, CLAUSE, [ITEM_PRESENCE, ITEM], llm)
    assert gaps == [] and [c.coverage_item_id for c in cases] == [ITEM_PRESENCE.id, ITEM.id]
    assert ITEM.id in llm.prompts[1] and ITEM_PRESENCE.id not in llm.prompts[1]
    assert "must observe an outcome" in llm.prompts[1]


def test_generate_source_gaps_the_items_still_unproduced(fake_llm):
    llm = fake_llm([{"cases": [entry(ITEM.id, WEAK)]}] * 3)
    cases, gaps = generate_source(OBJ, CLAUSE, [ITEM], llm)
    assert cases == [] and len(gaps) == 1 and gaps[0].attempts == 3
    assert ITEM.id in gaps[0].reason and "rejection" in gaps[0].reason


def test_generate_source_retries_an_llm_error(fake_llm):
    llm = fake_llm([LLMError("bad json"), reply([ITEM_PRESENCE])])
    cases, gaps = generate_source(OBJ, CLAUSE, [ITEM_PRESENCE], llm)
    assert gaps == [] and len(cases) == 1 and "bad json" in llm.prompts[1]


def test_generate_splits_a_group_larger_than_the_batch_limit():
    items = [CoverageItem(id=f"CI-OBJ-5.4-1-{n}", source_id="OBJ-5.4-1", clause_id="5.4", check="presence",
                          kind="nominal", group="valid_behaviour", purpose=f"p{n}") for n in range(1, 10)]
    llm = EchoLLM(items)
    cases, gaps = generate(items, [], [OBJ], [CLAUSE], llm)
    assert gaps == [] and len(cases) == 9
    assert len(llm.prompts) == 2
    assert sum(i.id in llm.prompts[0] for i in items) == BATCH_LIMIT


def test_batching_makes_one_call_per_source_and_no_batch_one_per_item():
    items = THREE + [CoverageItem(id="CI-REQ-5.4-1-nominal", source_id="REQ-5.4-1", clause_id="5.4", check="nominal",
                                  kind="nominal", group="valid_behaviour", purpose="x")]
    batched, per_item = EchoLLM(items), EchoLLM(items)
    generate(items, [REQ], [OBJ], [CLAUSE], batched)
    generate(items, [REQ], [OBJ], [CLAUSE], per_item, batch=False)
    assert len(batched.prompts) == 2 and len(per_item.prompts) == len(items) == 4


def test_the_two_paths_produce_identical_test_cases():
    items = THREE + [CoverageItem(id="CI-REQ-5.4-1-nominal", source_id="REQ-5.4-1", clause_id="5.4", check="nominal",
                                  kind="nominal", group="valid_behaviour", purpose="x")]
    batched, _ = generate(items, [REQ], [OBJ], [CLAUSE], EchoLLM(items))
    per_item, _ = generate(items, [REQ], [OBJ], [CLAUSE], EchoLLM(items), batch=False)
    assert [c.model_dump() for c in batched] == [c.model_dump() for c in per_item]


def test_a_truncated_batch_reply_keeps_its_complete_cases(monkeypatch):
    """`llm.complete` salvages the closed elements of the one list field of the schema, so a reply cut
    off by the context limit still delivers the cases it finished."""
    raw = json.dumps(reply(THREE))
    llm = OllamaLLM(model="m")
    monkeypatch.setattr(llm, "_chat", lambda prompt, schema: raw[: raw.rindex("}, {") + 1])
    got = llm.complete("p", TestCaseBatch)
    assert [c.coverage_item_id for c in got.cases] == [ITEM_PRESENCE.id, ITEM.id]


def test_a_bad_entry_does_not_reject_the_rest_of_the_batch(fake_llm):
    bad = {"coverage_item_id": ITEM_PRESENCE.id, "objective": 7, "preconditions": "one string", "inputs": None,
           "steps": [], "expected_result": {"a": 1}}
    llm = fake_llm([{"cases": [bad, entry(ITEM.id)]}, reply([ITEM_PRESENCE])])
    cases, gaps = generate_source(OBJ, CLAUSE, [ITEM_PRESENCE, ITEM], llm)
    assert gaps == [] and [c.coverage_item_id for c in cases] == [ITEM_PRESENCE.id, ITEM.id]
    assert "steps are empty" in llm.prompts[1] and "pass_criteria is empty" in llm.prompts[1]
    assert ITEM.id not in llm.prompts[1]


# --- D30 wording of the negative rule, D22 applicability in the case (task 17) ---

ITEM_APPLIES = CoverageItem(id="CI-OBJ-5.4-1-value_valid", source_id="OBJ-5.4-1", clause_id="5.4", check="value_valid",
                            kind="nominal", group="valid_behaviour", purpose="Verify that the value of nonce is fresh",
                            applies_when=["the extended profile is in use"])


def test_the_negative_rule_covers_both_d30_wordings():
    rule = KIND_RULES["negative"]
    assert "reject" in rule and "never" in rule


def test_both_prompts_state_the_applicability_of_the_purpose():
    p = build_generate_prompt(ITEM_APPLIES, OBJ, CLAUSE, [])
    b = build_batch_prompt(OBJ, CLAUSE, [ITEM_PRESENCE, ITEM_APPLIES], [])
    assert "the extended profile is in use" in p and "the extended profile is in use" in b
    assert "precondition" in p.lower() and "precondition" in b.lower()


def test_the_case_states_the_applicability_as_a_precondition(fake_llm):
    cases, gaps = generate_source(OBJ, CLAUSE, [ITEM_APPLIES], fake_llm([reply([ITEM_APPLIES])]))
    assert gaps == [] and cases[0].preconditions == ["the extended profile is in use"]
    tc, gap = generate_item(ITEM_APPLIES, OBJ, CLAUSE, fake_llm([DRAFT]))
    assert gap is None and tc.preconditions == ["the extended profile is in use"]


def test_the_case_does_not_repeat_an_applicability_the_model_already_stated(fake_llm):
    stated = {**DRAFT, "preconditions": ["The extended profile is in use", "a session is open"]}
    cases, _ = generate_source(OBJ, CLAUSE, [ITEM_APPLIES], fake_llm([reply([ITEM_APPLIES], stated)]))
    assert cases[0].preconditions == ["The extended profile is in use", "a session is open"]
