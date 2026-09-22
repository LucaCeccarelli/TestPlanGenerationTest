import json

import yaml

from tpg.emit import build_plan, write_plan
from tpg.models import CoverageItem, Gap, Requirement, Source, TestCase, TestObject

SRC = Source(path="s.md", sha256="0", generated_at="t", model="m")
R1 = Requirement(id="REQ-5.1-1", clause_id="5.1", text="a", modality="shall", conditions=[], source_quote="shall")
O1 = TestObject(id="OBJ-5.1-1", clause_id="5.1", name="n", kind="field", source_quote="q")
I1 = CoverageItem(id="CI-REQ-5.1-1-nominal", source_id="REQ-5.1-1", clause_id="5.1", check="nominal", kind="nominal", purpose="p")
I2 = CoverageItem(id="CI-OBJ-5.1-1-presence", source_id="OBJ-5.1-1", clause_id="5.1", check="presence", kind="nominal", purpose="p")
T1 = TestCase(id="TC-CI-REQ-5.1-1-nominal", source_id="REQ-5.1-1", coverage_item_id=I1.id, kind="nominal", objective="o",
              steps=["s"], expected_result="r", pass_criteria="p")


def test_build_plan_traceability_per_source_including_gapped_items():
    gap = Gap(source_id="OBJ-5.1-1", clause_id="5.1", stage="generate", reason="x", attempts=3)
    plan = build_plan(SRC, [R1], [O1], [I1, I2], [T1], [gap])
    assert [(t.source_id, t.coverage_item_ids, t.test_case_ids) for t in plan.traceability] == [
        ("REQ-5.1-1", [I1.id], [T1.id]), ("OBJ-5.1-1", [I2.id], [])]
    assert plan.gaps == [gap] and plan.objects == [O1] and plan.coverage_items == [I1, I2]


def test_write_plan_json_and_yaml(tmp_path):
    plan = build_plan(SRC, [R1], [], [I1], [T1], [])
    write_plan(plan, str(tmp_path / "p.json"), "json")
    write_plan(plan, str(tmp_path / "p.yaml"), "yaml")
    j = json.loads((tmp_path / "p.json").read_text())
    assert j == yaml.safe_load((tmp_path / "p.yaml").read_text())
    assert list(j) == ["source", "requirements", "objects", "coverage_items", "test_cases", "traceability", "gaps"]


def test_write_plan_is_utf8(tmp_path):
    text = "r\u00e9ponse \u2264 500 ms"
    plan = build_plan(SRC, [R1.model_copy(update={"text": text})], [], [], [], [])
    write_plan(plan, str(tmp_path / "p.json"), "json")
    assert text.encode("utf-8") in (tmp_path / "p.json").read_bytes()
