"""Assemble the TestPlan and write it. Traceability is known by construction."""
import json

import yaml

from tpg.models import CoverageItem, Gap, Requirement, Source, TestCase, TestObject, TestPlan, TraceLink


def build_plan(source: Source, requirements: list[Requirement], objects: list[TestObject], coverage_items: list[CoverageItem],
               test_cases: list[TestCase], gaps: list[Gap]) -> TestPlan:
    links = []
    for src_id in [r.id for r in requirements] + [o.id for o in objects]:
        links.append(TraceLink(source_id=src_id,
                               coverage_item_ids=[i.id for i in coverage_items if i.source_id == src_id],
                               test_case_ids=[t.id for t in test_cases if t.source_id == src_id]))
    return TestPlan(source=source, requirements=requirements, objects=objects, coverage_items=coverage_items,
                    test_cases=test_cases, traceability=links, gaps=gaps)


def write_plan(plan: TestPlan, path: str, fmt: str = "json") -> None:
    data = plan.model_dump(mode="json")
    with open(path, "w", encoding="utf-8") as f:
        if fmt == "yaml":
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
        else:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
