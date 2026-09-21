import json

import yaml

from tpg.emit import build_plan, write_plan
from tpg.models import Gap, Requirement, Source, TestCase

SRC = Source(path="s.md", sha256="0", generated_at="t", model="m")
R1 = Requirement(id="REQ-5.1-1", clause_id="5.1", text="a", modality="shall", conditions=[], source_quote="shall")
R2 = Requirement(id="REQ-5.2-1", clause_id="5.2", text="b", modality="may", conditions=[], source_quote="may")
T1 = TestCase(id="TC-REQ-5.1-1-1", requirement_id="REQ-5.1-1", kind="nominal", objective="o", steps=["s"],
              expected_result="r", pass_criteria="p")
T2 = TestCase(id="TC-REQ-5.1-1-2", requirement_id="REQ-5.1-1", kind="negative", objective="o", steps=["s"],
              expected_result="r", pass_criteria="p")


def test_build_plan_traceability_includes_empty_links_for_gapped_requirements():
    gap = Gap(requirement_id="REQ-5.2-1", clause_id="5.2", stage="generate", reason="x", attempts=3)
    plan = build_plan(SRC, [R1, R2], [T1, T2], [gap])
    assert [(t.requirement_id, t.test_case_ids) for t in plan.traceability] == [
        ("REQ-5.1-1", ["TC-REQ-5.1-1-1", "TC-REQ-5.1-1-2"]),
        ("REQ-5.2-1", []),
    ]
    assert plan.gaps == [gap]


def test_write_plan_json_and_yaml(tmp_path):
    plan = build_plan(SRC, [R1], [T1], [])
    write_plan(plan, str(tmp_path / "p.json"), "json")
    write_plan(plan, str(tmp_path / "p.yaml"), "yaml")
    j = json.loads((tmp_path / "p.json").read_text())
    y = yaml.safe_load((tmp_path / "p.yaml").read_text())
    assert j == y
    assert j["requirements"][0]["id"] == "REQ-5.1-1"
    assert list(j.keys()) == ["source", "requirements", "test_cases", "traceability", "gaps"]


def test_write_plan_is_utf8(tmp_path):
    text = "r\u00e9ponse \u2264 500 ms"
    plan = build_plan(SRC, [R1.model_copy(update={"text": text})], [], [])
    write_plan(plan, str(tmp_path / "p.json"), "json")
    raw = (tmp_path / "p.json").read_bytes()
    assert text.encode("utf-8") in raw
