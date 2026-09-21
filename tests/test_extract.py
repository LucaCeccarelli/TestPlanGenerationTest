import pytest

from tpg.extract import (build_extract_prompt, check_requirements, extract, extract_clause,
                         find_candidates)
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


def test_check_requirements_empty_batch_is_a_failure():
    assert check_requirements(CLAUSE, []) == ["no requirements returned although candidates exist"]


def test_prompt_contains_clause_candidates_and_failures():
    p = build_extract_prompt(CLAUSE, ["c1", "c2"], ["prev failure"])
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


def test_extract_skips_clauses_without_candidates(fake_llm):
    info = Clause(id="1", title="Scope", text="This document describes things.")
    llm = fake_llm([GOOD])
    reqs, gaps = extract([info, CLAUSE], llm)
    assert len(llm.prompts) == 1 and len(reqs) == 2 and gaps == []
