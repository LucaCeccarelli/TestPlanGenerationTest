"""Implementation Conformance Statement proforma: one line per feature the standard declares, with the
status the clause gives it. ITU-T X.291 (ISO/IEC 9646-2) clause 10.4 requires one test purpose per
mandatory or optional ICS item, which is the coverage criterion the derive stage then applies.
Deterministic, no LLM.
"""
import textwrap

from tpg.models import ICSItem, Requirement, TestObject

FEATURE_LIMIT = 160
ELISION = "..."

# An obligation is a feature the implementation must support; a recommendation or a permission is one it
# may support. A negative obligation keeps the status of its positive twin: it is the same feature.
MODALITY_STATUS = {"shall": "mandatory", "shall_not": "mandatory",
                   "should": "optional", "should_not": "optional", "may": "optional"}


def _feature(text: str) -> str:
    """A requirement's text as one ICS line: cut on a word boundary and mark the elision. A first word
    longer than the limit leaves `shorten` nothing to keep, so that one is cut mid-word."""
    short = textwrap.shorten(text, width=FEATURE_LIMIT, placeholder=ELISION)
    return short if short != ELISION else text[:FEATURE_LIMIT - len(ELISION)] + ELISION


def build_ics(requirements: list[Requirement], objects: list[TestObject]) -> list[ICSItem]:
    """Objects first, then requirements. An object whose presence the text does not state is not a
    declared feature and is skipped, as is any source whose feature text is empty. A requirement
    carries no ICS condition: its `conditions` constrain the obligation, not the support of a feature.
    """
    items: list[ICSItem] = []
    for o in objects:
        if o.presence == "unspecified" or not o.name:
            continue
        items.append(ICSItem(id=f"ICS-{o.id}", source_id=o.id, clause_id=o.clause_id, feature=o.name,
                             status=o.presence, condition=o.condition, applies_when=list(o.applies_when)))
    for r in requirements:
        if not r.text:
            continue
        items.append(ICSItem(id=f"ICS-{r.id}", source_id=r.id, clause_id=r.clause_id, feature=_feature(r.text),
                             status=MODALITY_STATUS[r.modality], condition=None, applies_when=list(r.applies_when)))
    return items
