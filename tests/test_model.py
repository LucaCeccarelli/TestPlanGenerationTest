from tpg.llm import LLMError
from tpg.model import build_model_prompt, check_object, extract_objects, extract_objects_clause, has_rows, merge_objects
from tpg.models import Clause, TestObjectDraft

CLAUSE = Clause(id="5.4", title="Request parameters",
                text="The request contains the following parameters.\nName: nonce | Presence: mandatory | Type: text string of 16 to 64 characters\n"
                     "Name: locale | Presence: optional | Type: BCP 47 language tag\nThe reader shall reject a request whose nonce is missing.")
NONCE = {"name": "nonce", "kind": "parameter", "direction": "received", "presence": "mandatory",
         "type": "text string of 16 to 64 characters", "size": "16 to 64 characters",
         "source_quote": "Name: nonce | Presence: mandatory | Type: text string of 16 to 64 characters"}
LOCALE = {"name": "locale", "kind": "parameter", "direction": "received", "presence": "optional", "type": "BCP 47 language tag",
          "source_quote": "Name: locale | Presence: optional | Type: BCP 47 language tag"}


def test_has_rows():
    assert has_rows("Name: nonce | Presence: mandatory") and not has_rows("plain prose: with colon") and not has_rows("a | b")


def test_prompt_asks_for_applies_when():
    p = build_model_prompt(CLAUSE, CLAUSE.text, "1/1", [], [])
    assert p.count("applies_when") == 2          # one rule and the reply template
    rule = next(l for l in p.splitlines() if l.startswith('- "applies_when"'))
    assert "quote" in rule.lower() and "empty" in rule


def test_check_object_rules():
    assert check_object(CLAUSE, 1, TestObjectDraft(**NONCE)) is None
    assert "verbatim" in check_object(CLAUSE, 1, TestObjectDraft(**{**NONCE, "source_quote": "not there"}))
    assert "name" in check_object(CLAUSE, 1, TestObjectDraft(**{**NONCE, "name": " "}))
    assert "condition" in check_object(CLAUSE, 1, TestObjectDraft(**{**NONCE, "presence": "conditional"}))
    assert "condition" in check_object(CLAUSE, 1, TestObjectDraft(**{**NONCE, "condition": "when asked"}))


def test_merge_objects_fills_nulls_of_first_occurrence():
    a = TestObjectDraft(**{**NONCE, "type": None})
    b = TestObjectDraft(**{**NONCE, "name": "Nonce", "presence": "unspecified"})
    merged = merge_objects([a, b])
    assert len(merged) == 1 and merged[0].name == "nonce" and merged[0].type == NONCE["type"] and merged[0].presence == "mandatory"


def test_extract_objects_clause_assigns_ids_in_source_order(fake_llm):
    objs, gap = extract_objects_clause(CLAUSE, fake_llm([{"objects": [LOCALE, NONCE]}]))
    assert gap is None and [o.id for o in objs] == ["OBJ-5.4-1", "OBJ-5.4-2"] and objs[0].name == "nonce"


def test_extract_objects_clause_retries_invalid_and_keeps_valid(fake_llm):
    bad = {**LOCALE, "source_quote": "nope"}
    llm = fake_llm([{"objects": [NONCE, bad]}, LLMError("bad json"), {"objects": [bad]}])
    objs, gap = extract_objects_clause(CLAUSE, llm)
    assert [o.name for o in objs] == ["nonce"]
    assert gap is not None and gap.stage == "model" and gap.source_id is None and "nope" in gap.reason
    assert len(llm.prompts) == 3 and "bad json" in llm.prompts[2] and "nonce" in llm.prompts[1]


def test_extract_objects_clause_reemitted_object_does_not_resolve_failure(fake_llm):
    bad = {**LOCALE, "source_quote": "nope"}
    llm = fake_llm([{"objects": [NONCE, bad]}, {"objects": [NONCE]}, {"objects": [NONCE]}])
    objs, gap = extract_objects_clause(CLAUSE, llm)
    assert [o.name for o in objs] == ["nonce"] and gap is not None and "nope" in gap.reason and len(llm.prompts) == 3


def test_extract_objects_clause_empty_retry_keeps_failure_open(fake_llm):
    bad = {**LOCALE, "source_quote": "nope"}
    llm = fake_llm([{"objects": [bad]}, {"objects": []}, {"objects": []}])
    objs, gap = extract_objects_clause(CLAUSE, llm)
    assert objs == [] and gap is not None and gap.attempts == 3 and "nope" in gap.reason and len(llm.prompts) == 3


def test_extract_objects_skips_clauses_without_candidates_or_rows(fake_llm):
    prose = Clause(id="1", title="Scope", text="This document describes things.")
    rows_only = Clause(id="2", title="Codes", text="Code: 01 | Meaning: car\nCode: 03 | Meaning: truck")
    llm = fake_llm([{"objects": []}, {"objects": [NONCE]}])
    objs, gaps = extract_objects([prose, rows_only, CLAUSE], llm)
    assert len(llm.prompts) == 2 and [o.id for o in objs] == ["OBJ-5.4-1"] and gaps == []


def test_check_object_rejects_unrecognised_enum_values():
    assert "kind" in check_object(CLAUSE, 1, TestObjectDraft.model_validate({**NONCE, "kind": "gadget"}))
    assert "presence" in check_object(CLAUSE, 1, TestObjectDraft.model_validate({**NONCE, "presence": "sometimes"}))
    assert "direction" in check_object(CLAUSE, 1, TestObjectDraft.model_validate({**NONCE, "direction": "sideways"}))
    assert check_object(CLAUSE, 1, TestObjectDraft.model_validate({**NONCE, "presence": "M"})) is None


def test_extract_objects_clause_survives_one_unrecognised_enum(fake_llm):
    bad = {**LOCALE, "kind": "gadget"}
    llm = fake_llm([{"objects": [NONCE, bad]}, {"objects": []}, {"objects": []}])
    objs, gap = extract_objects_clause(CLAUSE, llm)
    assert [o.name for o in objs] == ["nonce"]
    assert gap is not None and "gadget" in gap.reason and len(llm.prompts) == 3


ROWS = [f"Name: p{i} | Presence: optional" for i in range(5)]
ROW_CLAUSE = Clause(id="9", title="Rows", text="\n".join(ROWS), row_count=5)


def _row_obj(i):
    return {"name": f"p{i}", "kind": "parameter", "direction": "received", "presence": "optional", "source_quote": ROWS[i]}


def test_extract_objects_clause_reprompts_for_missing_rows(fake_llm):
    llm = fake_llm([{"objects": [_row_obj(0), _row_obj(1)]}, {"objects": [_row_obj(2)]}], fallback={"objects": []})
    objs, gap = extract_objects_clause(ROW_CLAUSE, llm)
    assert len(objs) == 3 and gap is not None and gap.stage == "model" and "3/5 rows" in gap.reason
    assert ROWS[2] in llm.prompts[1] and ROWS[0] not in llm.prompts[1] and len(llm.prompts) == 4


def test_extract_objects_clause_missing_rows_gap_counts(fake_llm):
    llm = fake_llm([{"objects": [_row_obj(0), _row_obj(1)]}], fallback={"objects": []})
    objs, gap = extract_objects_clause(ROW_CLAUSE, llm)
    assert len(objs) == 2 and "2/5 rows" in gap.reason


def test_extract_objects_clause_no_gap_when_rows_recovered(fake_llm):
    llm = fake_llm([{"objects": [_row_obj(0)]}, {"objects": [_row_obj(i) for i in range(1, 5)]}])
    objs, gap = extract_objects_clause(ROW_CLAUSE, llm)
    assert len(objs) == 5 and gap is None and len(llm.prompts) == 2
