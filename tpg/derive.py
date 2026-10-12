"""Coverage items from the ICS proforma, the requirements and the objects. Deterministic, no LLM
(ISO/IEC/IEEE 29119-4 test coverage items; test groups from ITU-T X.291 clause 10.2.2)."""
import re

from tpg.models import Check, CoverageItem, Group, ICSItem, Kind, Requirement, TestObject
from tpg.verify import required_assignments

BOUNDARY_RE = re.compile(r"\d+\s*(ms|s\b|sec|seconds?|minutes?|hours?|days?|bytes?|octets?|bits?|characters?|chars?|digits?|items?|"
                         r"elements?|entries|%|mm|cm|km|m\b|kb|mb|gb)|\b(at most|at least|maximum|minimum|between|exceed|"
                         r"no more than|no less than|not exceed|up to|greater than|less than)\b", re.I)

# The test group of each check (ITU-T X.291 clause 10.2.2). A check maps to one group; a missing key is a
# bug, not a default. `absence` is the exception: it is emitted both ways, so `group_for` reads its kind.
GROUP: dict[str, Group] = {
    "presence": "valid_behaviour", "encoding_valid": "valid_behaviour", "value_valid": "valid_behaviour",
    "consistency": "valid_behaviour", "condition_true": "valid_behaviour", "nominal": "valid_behaviour",
    "boundary_min": "valid_behaviour", "boundary_max": "valid_behaviour", "boundary": "valid_behaviour",
    "reference": "valid_behaviour",
    "absence": "invalid_behaviour", "encoding_invalid": "invalid_behaviour", "value_invalid": "invalid_behaviour",
    "boundary_outside": "invalid_behaviour", "negative": "invalid_behaviour", "condition_false": "invalid_behaviour",
    "capability": "capability",
    "inopportune": "inopportune_behaviour",
}

DIRECTION = {"received": "when received by the system under test", "produced": "in what the system under test produces",
             "internal": "in the system under test"}


def group_for(check: Check, kind: Kind) -> Group:
    """An element that may legitimately be absent is valid behaviour; a missing mandatory one is invalid
    behaviour. Every other check's group is fixed by the check alone."""
    if check == "absence" and kind == "nominal":
        return "valid_behaviour"
    return GROUP[check]


def _item(source_id: str, clause_id: str, check: Check, kind: Kind, purpose: str, n: int | None = None,
          assignment: dict[str, bool] | None = None, applies_when: list[str] | None = None) -> CoverageItem:
    cid = f"CI-{source_id}-{check}" + (f"-{n}" if n is not None else "")
    return CoverageItem(id=cid, source_id=source_id, clause_id=clause_id, check=check, kind=kind,
                        group=group_for(check, kind), purpose=purpose, condition_assignment=assignment,
                        applies_when=list(applies_when or []))


def derive_requirement(req: Requirement) -> list[CoverageItem]:
    items: list[CoverageItem] = []

    def add(check, kind, purpose, n=None, assignment=None):
        # an item is applicable exactly where its source is
        items.append(_item(req.id, req.clause_id, check, kind, purpose, n, assignment, req.applies_when))

    if req.conditions:
        assigns = required_assignments(req.conditions)
        add("condition_true", "nominal", f"Verify: {req.text} (all conditions hold)", assignment=assigns[0])
        for n, (cond, a) in enumerate(zip(req.conditions, assigns[1:]), 1):
            add("condition_false", "negative", f"Verify the behaviour when '{cond}' does not hold: {req.text}", n=n, assignment=a)
    else:
        add("nominal", "nominal", f"Verify that the system under test satisfies: {req.text}")
        if req.modality in ("shall", "shall_not", "should_not"):
            add("negative", "negative",
                f"Verify the reaction of the system under test when the obligation is violated: {req.text}")
    if BOUNDARY_RE.search(req.text):
        add("boundary", "boundary", f"Verify the limit value stated in: {req.text}")
    return items


def derive_object(obj: TestObject) -> list[CoverageItem]:
    items: list[CoverageItem] = []
    d = DIRECTION[obj.direction]
    received = obj.direction == "received"

    def add(check, kind, purpose, n=None):
        items.append(_item(obj.id, obj.clause_id, check, kind, purpose, n, applies_when=obj.applies_when))

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
    if obj.size and any(c.isdigit() for c in obj.size):      # an occurrence marker such as "*" states no limit
        add("boundary_min", "boundary", f"Verify {obj.name} at the minimum of: {obj.size}")
        add("boundary_max", "boundary", f"Verify {obj.name} at the maximum of: {obj.size}")
        if received:
            add("boundary_outside", "negative", f"Verify the reaction of the system under test when {obj.name} is outside: {obj.size}")
    for n, rel in enumerate(obj.relations, 1):
        add("consistency", "nominal", f"Verify that {obj.name} satisfies: {rel}", n)
    return items


def derive_capability(ics_item: ICSItem, prohibition: bool = False) -> list[CoverageItem]:
    """One capability item per ICS item the implementation must or may support (X.291 clause 10.4). A
    prohibition is a feature the implementation enforces rather than one it supports."""
    if ics_item.status not in ("mandatory", "optional"):
        return []
    purpose = (f"Verify that the implementation enforces: {ics_item.feature}" if prohibition
               else f"Verify that the implementation supports {ics_item.feature}")
    return [_item(ics_item.source_id, ics_item.clause_id, "capability", "nominal", purpose,
                  applies_when=ics_item.applies_when)]


def derive_inopportune(obj: TestObject) -> list[CoverageItem]:
    """A valid message or structure supplied although its stated precondition does not hold: the one
    X.291 group the valid and invalid ladders have no analogue for. The precondition is the object's
    applicability text when it has one, else its presence condition. This overlaps the `condition_false`
    item of a conditional object on the precondition but not on the stimulus: there the element is
    withheld, here it is sent anyway, so the purposes say which."""
    if obj.direction != "received" or obj.kind not in ("message", "structure"):
        return []
    precondition = "; ".join(obj.applies_when) or (obj.condition or "").strip()
    if not precondition:
        return []
    return [_item(obj.id, obj.clause_id, "inopportune", "negative",
                  f"Verify the handling of {obj.name} supplied although its precondition does not hold: {precondition}",
                  applies_when=obj.applies_when)]


def derive(reqs: list[Requirement], objs: list[TestObject], ics: list[ICSItem]) -> list[CoverageItem]:
    items: list[CoverageItem] = []
    prohibitions = {r.id for r in reqs if r.modality in ("shall_not", "should_not")}
    for i in ics:
        items.extend(derive_capability(i, i.source_id in prohibitions))
    for r in reqs:
        items.extend(derive_requirement(r))
    for o in objs:
        items.extend(derive_object(o))
    for o in objs:
        items.extend(derive_inopportune(o))
    return items
