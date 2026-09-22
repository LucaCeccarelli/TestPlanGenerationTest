"""Coverage items from requirements and objects. Deterministic, no LLM (ISO/IEC/IEEE 29119-4 test coverage items)."""
import re

from tpg.models import Check, CoverageItem, Kind, Requirement, TestObject
from tpg.verify import required_assignments

BOUNDARY_RE = re.compile(r"\d+\s*(ms|s\b|sec|seconds?|minutes?|hours?|days?|bytes?|octets?|bits?|characters?|chars?|digits?|items?|"
                         r"elements?|entries|%|mm|cm|km|m\b|kb|mb|gb)|\b(at most|at least|maximum|minimum|between|exceed|"
                         r"no more than|no less than|not exceed|up to|greater than|less than)\b", re.I)

DIRECTION = {"received": "when received by the system under test", "produced": "in what the system under test produces",
             "internal": "in the system under test"}


def _item(source_id: str, clause_id: str, check: Check, kind: Kind, purpose: str, n: int | None = None,
          assignment: dict[str, bool] | None = None) -> CoverageItem:
    cid = f"CI-{source_id}-{check}" + (f"-{n}" if n is not None else "")
    return CoverageItem(id=cid, source_id=source_id, clause_id=clause_id, check=check, kind=kind, purpose=purpose,
                        condition_assignment=assignment)


def derive_requirement(req: Requirement) -> list[CoverageItem]:
    items: list[CoverageItem] = []
    if req.conditions:
        assigns = required_assignments(req.conditions)
        items.append(_item(req.id, req.clause_id, "condition_true", "nominal",
                           f"Verify: {req.text} (all conditions hold)", assignment=assigns[0]))
        for n, (cond, a) in enumerate(zip(req.conditions, assigns[1:]), 1):
            items.append(_item(req.id, req.clause_id, "condition_false", "negative",
                               f"Verify the behaviour when '{cond}' does not hold: {req.text}", n=n, assignment=a))
    else:
        items.append(_item(req.id, req.clause_id, "nominal", "nominal", f"Verify that the system under test satisfies: {req.text}"))
        if req.modality in ("shall", "shall_not", "should_not"):
            items.append(_item(req.id, req.clause_id, "negative", "negative",
                               f"Verify the reaction of the system under test when the obligation is violated: {req.text}"))
    if BOUNDARY_RE.search(req.text):
        items.append(_item(req.id, req.clause_id, "boundary", "boundary", f"Verify the limit value stated in: {req.text}"))
    return items


def derive_object(obj: TestObject) -> list[CoverageItem]:
    items: list[CoverageItem] = []
    d = DIRECTION[obj.direction]
    received = obj.direction == "received"

    def add(check, kind, purpose, n=None):
        items.append(_item(obj.id, obj.clause_id, check, kind, purpose, n))

    if obj.presence == "mandatory":
        add("presence", "nominal", f"Verify that {obj.name} is present {d}")
        if received:
            add("absence", "negative", f"Verify the reaction of the system under test when {obj.name} is absent")
    elif obj.presence == "optional":
        add("presence", "nominal", f"Verify that {obj.name} is accepted when present {d}")
        add("absence", "nominal", f"Verify that {obj.name} may be absent {d}")
    elif obj.presence == "conditional":
        add("condition_true", "nominal", f"Verify that {obj.name} is present {d} when: {obj.condition}")
        add("condition_false", "negative", f"Verify the handling of {obj.name} when the condition does not hold: {obj.condition}")
    if obj.type:
        add("encoding_valid", "nominal", f"Verify that {obj.name} is a well-formed {obj.type} {d}")
        if received:
            add("encoding_invalid", "negative", f"Verify the reaction of the system under test when {obj.name} is not a well-formed {obj.type}")
    if obj.value_domain:
        add("value_valid", "nominal", f"Verify that the value of {obj.name} satisfies: {obj.value_domain}")
        if received:
            add("value_invalid", "negative", f"Verify the reaction of the system under test when the value of {obj.name} violates: {obj.value_domain}")
    if obj.size:
        add("boundary_min", "boundary", f"Verify {obj.name} at the minimum of: {obj.size}")
        add("boundary_max", "boundary", f"Verify {obj.name} at the maximum of: {obj.size}")
        if received:
            add("boundary_outside", "negative", f"Verify the reaction of the system under test when {obj.name} is outside: {obj.size}")
    for n, rel in enumerate(obj.relations, 1):
        add("consistency", "nominal", f"Verify that {obj.name} satisfies: {rel}", n)
    return items


def derive(reqs: list[Requirement], objs: list[TestObject]) -> list[CoverageItem]:
    items: list[CoverageItem] = []
    for r in reqs:
        items.extend(derive_requirement(r))
    for o in objs:
        items.extend(derive_object(o))
    return items
