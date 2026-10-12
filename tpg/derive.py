"""Coverage items from the ICS proforma, the requirements and the objects. Deterministic, no LLM
(ISO/IEC/IEEE 29119-4 test coverage items; test groups from ITU-T X.291 clause 10.2.2)."""
import re
from collections import Counter

from tpg.extract import norm
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

# Deflation rule (b) of D25 as amended by D31: the object checks a requirement-derived check duplicates,
# considered only when the two were read off the same prose. A requirement and an object that describe the
# same obligation yield the same test twice; the object-derived item is the specific one, so it is kept.
OVERLAP: dict[str, tuple[Check, ...]] = {
    "nominal": ("presence", "encoding_valid", "value_valid"),
    "negative": ("absence", "encoding_invalid", "value_invalid"),
    "boundary": ("boundary_min", "boundary_max"),
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
          assignment: dict[str, bool] | None = None, applies_when: list[str] | None = None,
          generic_group: str | None = None) -> CoverageItem:
    cid = f"CI-{source_id}-{check}" + (f"-{n}" if n is not None else "")
    return CoverageItem(id=cid, source_id=source_id, clause_id=clause_id, check=check, kind=kind,
                        group=group_for(check, kind), purpose=purpose, condition_assignment=assignment,
                        applies_when=list(applies_when or []), generic_group=generic_group)


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

    def add_invalid(check, violation):
        """D30: `direction` selects the wording of a negative item, never its existence. A received object
        must reject an invalid instance supplied to it; a produced or internal one must never make one
        (ISO/IEC/IEEE 29119-4 clause 5.2.4 syntax testing holds for a decoder and an encoder alike)."""
        add(check, "negative", f"Verify the reaction of the system under test when {violation}" if received
            else f"Verify that the system under test never produces or holds a case in which {violation}")

    if obj.presence == "mandatory":
        add("presence", "nominal", f"Verify that {obj.name} is present {d}")
        add_invalid("absence", f"{obj.name} is absent")
    elif obj.presence == "optional":
        add("presence", "nominal", f"Verify that {obj.name} is accepted when present {d}")
        add("absence", "nominal", f"Verify that {obj.name} may be absent {d}")
    elif obj.presence == "conditional":
        add("condition_true", "nominal", f"Verify that {obj.name} is present {d} when: {obj.condition}")
        add("condition_false", "negative", f"Verify the handling of {obj.name} when the condition does not hold: {obj.condition}")
    if obj.type:
        add("encoding_valid", "nominal", f"Verify that {obj.name} is a well-formed {obj.type} {d}")
        add_invalid("encoding_invalid", f"{obj.name} is not a well-formed {obj.type}")
    if obj.value_domain:
        add("value_valid", "nominal", f"Verify that the value of {obj.name} satisfies: {obj.value_domain}")
        add_invalid("value_invalid", f"the value of {obj.name} violates: {obj.value_domain}")
    if obj.size and any(c.isdigit() for c in obj.size):      # an occurrence marker such as "*" states no limit
        add("boundary_min", "boundary", f"Verify {obj.name} at the minimum of: {obj.size}")
        add("boundary_max", "boundary", f"Verify {obj.name} at the maximum of: {obj.size}")
        add_invalid("boundary_outside", f"{obj.name} is outside: {obj.size}")
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


def group_key(obj: TestObject) -> tuple:
    """D31: a generic group is a shared specification, not a shared name. The key is the normalised name
    together with every attribute the ladder of `derive_object` and `derive_inopportune` reads, so two
    occurrences of one group state the same test purposes and a `reference` item at either site asserts
    that site's own obligations. Each text attribute is normalised the way the name is, so that a spelling
    or spacing difference does not split a genuine group; `kind`, `presence` and `direction` are already
    controlled vocabularies."""
    return (norm(obj.name), obj.kind, obj.presence, obj.direction, norm(obj.type or ""),
            norm(obj.value_domain or ""), norm(obj.size or ""), norm(obj.condition or ""),
            tuple(norm(r) for r in obj.relations), tuple(norm(a) for a in obj.applies_when))


def same_prose(quote: str, text: str) -> bool:
    """Were an object and a requirement read off the same prose? Both sides normalised, and containment
    counts in either direction, because an extractor may store the obligation clause of a longer sentence
    as the quote or quote the whole sentence a shorter requirement text states. An empty side never
    matches: it would otherwise be contained in everything."""
    return bool(quote) and bool(text) and (quote in text or text in quote)


def group_generics(items: list[CoverageItem], objs: list[TestObject]) -> list[CoverageItem]:
    """Rule (a) of D25 as amended by D31: a specification declared in several clauses is a generic test
    suite (X.291 clause 11 and Annex D). Occurrences are grouped by `group_key`, not by the bare name, so
    an occurrence that differs on any attribute determining its test purposes is a distinct declaration and
    keeps its own ladder. The richest occurrence of a group owns the ladder, ties going to document order;
    every occurrence in another clause keeps one `reference` item pointing at it, as the official suites do
    with "perform all Common_X test cases". Keys on the text the document itself writes, so nothing here
    knows any particular standard."""
    by_key: dict[tuple, list[TestObject]] = {}
    for o in objs:
        if norm(o.name):
            by_key.setdefault(group_key(o), []).append(o)
    counts = Counter(i.source_id for i in items)
    referring: dict[str, tuple[str, str, TestObject]] = {}
    for key, group in by_key.items():
        if len({o.clause_id for o in group}) < 2:
            continue
        # max() keeps the first of equal counts and `objs` is in document order, so a tie goes to the first
        # occurrence. Under the D31 key the ladders of one group are identical, so a tie is the normal case.
        owner = max(group, key=lambda o: counts[o.id])
        # An occurrence of the owner's own clause keeps its ladder: a pointer naming its own clause tells a
        # reader nothing, and D25 groups what recurs across clauses.
        referring.update({o.id: (key[0], owner.clause_id, o) for o in group if o.clause_id != owner.clause_id})
    out: list[CoverageItem] = []
    done: set[str] = set()
    for i in items:
        ref = referring.get(i.source_id)
        if ref is None:
            out.append(i)
            continue
        name, owner_clause, o = ref
        if i.source_id in done:
            continue
        # One pointer per occurrence, not per clause: an ICS entry is joined to its coverage by the
        # occurrence's own id, so a second occurrence of the same clause needs its own item (D21).
        done.add(i.source_id)
        out.append(_item(o.id, o.clause_id, "reference", "nominal",
                         f"Perform the test purposes of {o.name} specified for clause {owner_clause}",
                         applies_when=o.applies_when, generic_group=name))
    return out


def drop_overlaps(items: list[CoverageItem], reqs: list[Requirement], objs: list[TestObject]) -> list[CoverageItem]:
    """Rule (b) of D25 as amended by D31: drop a requirement-derived item when an object of the same clause
    was derived from the same prose and carries a check of the same family. Provenance is the test, not the
    occurrence of the object's name in the requirement's text: a name is a word of ordinary English as often
    as it is a reference, and a limit declared on an object is not the limit a sentence states. The check
    family is still consulted, so an item is dropped only where the object really has a counterpart.
    Compared against the items that survived rule (a)."""
    quotes = {o.id: norm(o.source_quote) for o in objs}
    covered: dict[tuple[str, str], set[str]] = {}
    for i in items:
        quote = quotes.get(i.source_id)
        if quote:
            covered.setdefault((i.clause_id, quote), set()).add(i.check)
    texts = {r.id: norm(r.text) for r in reqs}

    def duplicated(i: CoverageItem) -> bool:
        text = texts.get(i.source_id)
        if text is None or i.check not in OVERLAP:
            return False
        return any(checks.intersection(OVERLAP[i.check]) and same_prose(quote, text)
                   for (clause, quote), checks in covered.items() if clause == i.clause_id)

    return [i for i in items if not duplicated(i)]


def derive(reqs: list[Requirement], objs: list[TestObject], ics: list[ICSItem],
           deflate: bool = True) -> list[CoverageItem]:
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
    if deflate:
        items = group_generics(items, objs)      # first, so a reference site no longer looks like a ladder
        items = drop_overlaps(items, reqs, objs)  # then, against what rule (a) left standing
    return items
