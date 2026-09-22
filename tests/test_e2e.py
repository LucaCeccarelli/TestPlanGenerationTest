"""Slow tests: real model, real documents. Run with: TPG_E2E=1 OLLAMA_HOST=https://ollama.com uv run pytest -m slow -v"""
import os
from pathlib import Path

import pytest

from tpg.extract import norm
from tpg.ingest import ingest
from tpg.llm import OllamaLLM, load_dotenv
from tpg.pipeline import run

FIX = Path(__file__).parent / "fixtures"
MODEL = os.environ.get("TPG_MODEL", "gemma4:31b")

pytestmark = pytest.mark.slow
if not os.environ.get("TPG_E2E"):
    pytest.skip("set TPG_E2E=1 to run against a real Ollama server", allow_module_level=True)


@pytest.fixture(scope="module")
def llm():
    load_dotenv()
    client = OllamaLLM(model=MODEL)
    client.check()
    return client


def _assert_plan_is_sound(plan, path):
    clauses = {c.id: c for c in ingest(str(path))}
    assert plan.gaps == [], [g.model_dump() for g in plan.gaps]
    assert plan.requirements, "no requirements extracted"
    gapped = {g.source_id for g in plan.gaps}
    for r in plan.requirements:
        assert norm(r.source_quote) in norm(clauses[r.clause_id].text), r.id
    for o in plan.objects:
        assert norm(o.source_quote) in norm(clauses[o.clause_id].text), o.id
    covered = {t.coverage_item_id for t in plan.test_cases}
    for i in plan.coverage_items:
        assert i.id in covered or i.source_id in gapped, i.id
    # every requirement, and every object the text states an attribute for, is traced to coverage
    # items and to one test case each; an object with no stated attribute yields nothing by design
    for r in plan.requirements:
        link = next(t for t in plan.traceability if t.source_id == r.id)
        assert link.coverage_item_ids, r.id
        assert len(link.test_case_ids) == len(link.coverage_item_ids) or r.id in gapped, r.id
    for o in plan.objects:
        link = next(t for t in plan.traceability if t.source_id == o.id)
        stated = o.presence != "unspecified" or o.type or o.value_domain or o.size or o.relations
        assert link.coverage_item_ids or not stated, o.id
        assert len(link.test_case_ids) == len(link.coverage_item_ids) or o.id in gapped, o.id


def test_sample_markdown(llm):
    plan = run(str(FIX / "sample.md"), llm, MODEL, log=print)
    _assert_plan_is_sound(plan, FIX / "sample.md")
    assert {r.clause_id for r in plan.requirements} == {"5.1", "5.2", "5.4"}
    cond = [r for r in plan.requirements if r.clause_id == "5.2" and r.modality == "shall_not"]
    assert cond and len(cond[0].conditions) == 2
    assert any(o.name == "nonce" for o in plan.objects)
    assert any(i.check == "boundary_max" for i in plan.coverage_items)


def test_openid_clause_5_1(llm):
    plan = run(str(FIX / "OpenID4VP1-0.pdf"), llm, MODEL, clause_ids=["5.1"], log=print)
    _assert_plan_is_sound(plan, FIX / "OpenID4VP1-0.pdf")


def test_rfc_one_page(llm):
    # p12 has zero modal-sentence candidates; p3 is the first page with 3+ (see tpg.extract.find_candidates).
    plan = run(str(FIX / "RFC8949.pdf"), llm, MODEL, clause_ids=["p3"], log=print)
    _assert_plan_is_sound(plan, FIX / "RFC8949.pdf")


@pytest.mark.skipif(not (FIX / "iso_18013_5.pdf").exists(), reason="ISO fixture not distributed")
def test_iso_clause_7_3_2(llm):
    # 6.1 ("Introduction") has zero modal-sentence candidates in this fixture, same as RFC p12;
    # "2" (Normative references) has regex-matching candidates but they are bibliography titles, not
    # real obligations. 7.3.2 (DocType) is the first substantive clause with 3+ genuine candidates.
    plan = run(str(FIX / "iso_18013_5.pdf"), llm, MODEL, clause_ids=["7.3.2"], log=print)
    _assert_plan_is_sound(plan, FIX / "iso_18013_5.pdf")
