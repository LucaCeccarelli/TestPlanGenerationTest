"""Assemble the TestPlan and write it. Traceability is known by construction."""
import json

import yaml

from tpg.models import Gap, Requirement, Source, TestCase, TestPlan, TraceLink


def build_plan(source: Source, requirements: list[Requirement], test_cases: list[TestCase], gaps: list[Gap]) -> TestPlan:
    links = [TraceLink(requirement_id=r.id, test_case_ids=[t.id for t in test_cases if t.requirement_id == r.id])
             for r in requirements]
    return TestPlan(source=source, requirements=requirements, test_cases=test_cases, traceability=links, gaps=gaps)


def write_plan(plan: TestPlan, path: str, fmt: str = "json") -> None:
    data = plan.model_dump(mode="json")
    with open(path, "w", encoding="utf-8") as f:
        if fmt == "yaml":
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
        else:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
