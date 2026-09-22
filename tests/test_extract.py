import pytest

from tpg.extract import (build_extract_prompt, check_draft, check_requirements, chunks, extract,
                         extract_clause, find_candidates)
from tpg.llm import LLMError
from tpg.models import Clause, RequirementDraft

CLAUSE = Clause(id="5.2", title="Malformed requests",
                text="If the request is malformed or the session has expired, the device shall not "
                     "process the request and should return an error code. This clause is informative. "
                     "The device may log it.")

GOOD = {"requirements": [
    {"text": "If the request is malformed or the session has expired, the device shall not process the request.",
     "modality": "shall_not", "conditions": ["request is malformed", "session has expired"],
     "source_quote": "the device shall not process the request"},
    {"text": "The device may log the request.", "modality": "may", "conditions": [],
     "source_quote": "The device may log it."},
]}


def test_find_candidates_keeps_only_modal_sentences():
    cands = find_candidates(CLAUSE.text)
    assert len(cands) == 2
    assert cands[0].startswith("If the request is malformed")
    assert cands[1] == "The device may log it."


def test_find_candidates_none():
    assert find_candidates("Purely descriptive text. Nothing here.") == []


def test_check_requirements_ok():
    drafts = [RequirementDraft(**r) for r in GOOD["requirements"]]
    assert check_requirements(CLAUSE, drafts) == []


def test_check_requirements_quote_not_in_clause():
    d = RequirementDraft(text="x", modality="shall", source_quote="the device shall explode")
    msgs = check_requirements(CLAUSE, [d])
    assert len(msgs) == 1 and "source_quote" in msgs[0] and "explode" in msgs[0]


def test_check_requirements_quote_is_whitespace_and_case_insensitive():
    d = RequirementDraft(text="x", modality="shall_not",
                         source_quote="The Device  shall not\nprocess the request")
    assert check_requirements(CLAUSE, [d]) == []


def test_check_requirements_modality_must_appear_in_quote():
    d = RequirementDraft(text="x", modality="shall", source_quote="The device may log it.")
    msgs = check_requirements(CLAUSE, [d])
    assert len(msgs) == 1 and "modality" in msgs[0]


def test_check_requirements_empty_text():
    d = RequirementDraft(text="  ", modality="may", source_quote="The device may log it.")
    assert any("text" in m for m in check_requirements(CLAUSE, [d]))


def test_check_requirements_rejects_negated_modal_for_positive_modality():
    d = RequirementDraft(text="x", modality="shall", source_quote="the device shall not process the request")
    msgs = check_requirements(CLAUSE, [d])
    assert len(msgs) == 1 and "modality" in msgs[0]


def test_check_requirements_accepts_must_as_shall():
    c = Clause(id="1", title="t", text="The reader must respond. The reader must not crash.")
    ok = [RequirementDraft(text="a", modality="shall", source_quote="The reader must respond."),
          RequirementDraft(text="b", modality="shall_not", source_quote="The reader must not crash.")]
    assert check_requirements(c, ok) == []


def test_check_requirements_empty_batch_is_ok():
    assert check_requirements(CLAUSE, []) == []


def test_prompt_contains_clause_candidates_and_failures():
    p = build_extract_prompt(CLAUSE, CLAUSE.text, "1/1", ["c1", "c2"], ["prev failure"], [])
    assert "5.2" in p and "c1" in p and "c2" in p and "prev failure" in p


def test_extract_clause_success_assigns_ids(fake_llm):
    reqs, gap = extract_clause(CLAUSE, fake_llm([GOOD]))
    assert gap is None
    assert [r.id for r in reqs] == ["REQ-5.2-1", "REQ-5.2-2"]
    assert all(r.clause_id == "5.2" for r in reqs)


def test_extract_clause_retries_with_feedback_then_succeeds(fake_llm):
    bad = {"requirements": [{"text": "x", "modality": "shall", "source_quote": "not in clause"}]}
    llm = fake_llm([bad, LLMError("reply is not valid JSON"), GOOD])
    reqs, gap = extract_clause(CLAUSE, llm)
    assert gap is None and len(reqs) == 2
    assert len(llm.prompts) == 3
    assert "not in clause" in llm.prompts[1]
    assert "not valid JSON" in llm.prompts[2]


def test_extract_clause_gap_after_three_failures(fake_llm):
    bad = {"requirements": [{"text": "x", "modality": "shall", "source_quote": "nope"}]}
    reqs, gap = extract_clause(CLAUSE, fake_llm([bad, bad, bad]))
    assert reqs == []
    assert gap is not None and gap.stage == "extract" and gap.attempts == 3
    assert gap.clause_id == "5.2" and gap.requirement_id is None and "nope" in gap.reason


def test_extract_clause_ids_follow_source_order(fake_llm):
    reversed_good = {"requirements": list(reversed(GOOD["requirements"]))}
    reqs, gap = extract_clause(CLAUSE, fake_llm([reversed_good]))
    assert gap is None
    assert [r.modality for r in reqs] == ["shall_not", "may"]
    assert [r.id for r in reqs] == ["REQ-5.2-1", "REQ-5.2-2"]


def test_extract_clause_empty_batch_is_not_a_gap(fake_llm):
    reqs, gap = extract_clause(CLAUSE, fake_llm([{"requirements": []}]))
    assert reqs == [] and gap is None


def test_extract_skips_clauses_without_candidates(fake_llm):
    info = Clause(id="1", title="Scope", text="This document describes things.")
    llm = fake_llm([GOOD])
    reqs, gaps = extract([info, CLAUSE], llm)
    assert len(llm.prompts) == 1 and len(reqs) == 2 and gaps == []


def test_should_not_and_never_are_grounded():
    c = Clause(id="1", title="t", text="Other elements should not be present. A counter shall never be reused.")
    ok = [RequirementDraft(text="a", modality="should_not", source_quote="Other elements should not be present."),
          RequirementDraft(text="b", modality="shall_not", source_quote="A counter shall never be reused.")]
    assert check_requirements(c, ok) == []
    assert check_draft(c, 1, RequirementDraft(text="a", modality="should", source_quote="should not be present")) is not None


def test_chunks_split_at_line_boundaries_under_limit():
    text = "\n".join(f"line {i} " + "x" * 90 for i in range(100))
    parts = chunks(text, limit=1000)
    assert len(parts) >= 9 and all(len(p) <= 1000 for p in parts)
    assert "\n".join(parts) == text


def test_extract_clause_keeps_valid_drafts_and_retries_only_invalid(fake_llm):
    bad = {"text": "x", "modality": "shall", "source_quote": "not in clause"}
    good1 = GOOD["requirements"][0]
    fixed = GOOD["requirements"][1]
    llm = fake_llm([{"requirements": [good1, bad]}, {"requirements": [fixed]}])
    reqs, gap = extract_clause(CLAUSE, llm)
    assert gap is None and [r.modality for r in reqs] == ["shall_not", "may"]
    assert len(llm.prompts) == 2
    assert "not in clause" in llm.prompts[1] and good1["text"] in llm.prompts[1]


def test_extract_clause_gap_keeps_accepted_requirements(fake_llm):
    bad = {"text": "x", "modality": "shall", "source_quote": "nope"}
    good1 = GOOD["requirements"][0]
    llm = fake_llm([{"requirements": [good1, bad]}, {"requirements": [bad]}, {"requirements": [bad]}])
    reqs, gap = extract_clause(CLAUSE, llm)
    assert len(reqs) == 1 and reqs[0].id == "REQ-5.2-1"
    assert gap is not None and gap.attempts == 3 and "nope" in gap.reason


def test_extract_clause_chunks_long_clause(fake_llm):
    long = Clause(id="9", title="t", text="\n".join(f"Item {i}: the unit shall do thing {i}." for i in range(400)))
    llm = fake_llm([{"requirements": []}] * 10)
    reqs, gap = extract_clause(long, llm)
    assert gap is None and reqs == [] and 2 <= len(llm.prompts) <= 4
    assert "part 1/" in llm.prompts[0]
