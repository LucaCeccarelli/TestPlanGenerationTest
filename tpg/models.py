"""All data types. Pydantic v2.

Drafts are what the LLM returns. Their vocabulary fields are typed `str`, not a Literal, because
pydantic validates a whole reply in one go: a single out-of-vocabulary value would reject every draft
in the batch, which costs a clause instead of a draft. A before-validator maps the common spellings,
plurals, abbreviations and single-letter table codes onto the canonical value; anything it cannot map
is kept as written so the per-draft check can reject just that draft. Scalars and lone strings are
likewise coerced where a text or a list of text is wanted. The persisted types re-declare the strict
fields, so the emitted plan still carries canonical values only.
"""
import re
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, field_validator

Modality = Literal["shall", "shall_not", "should", "should_not", "may"]
ObjectKind = Literal["field", "structure", "message", "parameter", "value", "behaviour"]
Direction = Literal["received", "produced", "internal"]
Presence = Literal["mandatory", "optional", "conditional", "unspecified"]
Kind = Literal["nominal", "negative", "boundary"]
Check = Literal["presence", "absence", "encoding_valid", "encoding_invalid", "value_valid", "value_invalid",
                "boundary_min", "boundary_max", "boundary_outside", "consistency", "condition_true", "condition_false",
                "nominal", "negative", "boundary"]
Stage = Literal["extract", "model", "generate"]

MODALITY_VALUES = get_args(Modality)
OBJECT_KIND_VALUES = get_args(ObjectKind)
DIRECTION_VALUES = get_args(Direction)
PRESENCE_VALUES = get_args(Presence)

KIND_WORDS = {
    "field": "field", "attribute": "field", "element": "field", "datum": "field", "item": "field",
    "structure": "structure", "struct": "structure", "record": "structure", "container": "structure",
    "message": "message", "msg": "message", "packet": "message", "frame": "message",
    "parameter": "parameter", "param": "parameter", "argument": "parameter", "option": "parameter",
    "value": "value", "code": "value", "constant": "value",
    "behaviour": "behaviour", "behavior": "behaviour", "operation": "behaviour", "action": "behaviour",
    "procedure": "behaviour", "process": "behaviour", "function": "behaviour",
}
DIRECTION_WORDS = {
    "received": "received", "receive": "received", "receives": "received", "incoming": "received",
    "inbound": "received", "input": "received", "read": "received", "parsed": "received",
    "produced": "produced", "produce": "produced", "produces": "produced", "outgoing": "produced",
    "outbound": "produced", "output": "produced", "sent": "produced", "send": "produced", "written": "produced",
    "internal": "internal", "internally": "internal", "stored": "internal", "none": "internal",
}
PRESENCE_WORDS = {
    "mandatory": "mandatory", "required": "mandatory", "require": "mandatory", "must": "mandatory",
    "optional": "optional", "opt": "optional", "may": "optional",
    "conditional": "conditional", "cond": "conditional", "conditionally": "conditional",
    "unspecified": "unspecified", "unknown": "unspecified", "unstated": "unspecified",
}
# ponytail: tables code presence as a letter, sometimes with a footnote mark ("M", "O", "Ca", "C/M");
# the first letter of a short token decides. Drop this if a vocabulary ever collides on it.
PRESENCE_LETTERS = {"m": "mandatory", "o": "optional", "c": "conditional", "u": "unspecified"}


def _words(raw: Any) -> list[str]:
    return re.findall(r"[a-z]+", str(raw).lower())


def _match(words: list[str], table: dict[str, str]) -> str | None:
    for w in words:
        if w in table:
            return table[w]
        if w.endswith("s") and w[:-1] in table:
            return table[w[:-1]]
    return None


def normalise_modality(raw: Any) -> str | None:
    """Canonical modality, or None when the value states no recognisable obligation."""
    words = _words(raw)
    negated = "not" in words or "never" in words
    if "shall" in words or "must" in words:
        return "shall_not" if negated else "shall"
    if "should" in words:
        return "should_not" if negated else "should"
    if "may" in words and not negated:
        return "may"
    return None


def normalise_object_kind(raw: Any) -> str | None:
    return _match(_words(raw), KIND_WORDS)


def normalise_direction(raw: Any) -> str | None:
    return _match(_words(raw), DIRECTION_WORDS)


def normalise_presence(raw: Any) -> str | None:
    words = _words(raw)
    hit = _match(words, PRESENCE_WORDS)
    if hit:
        return hit
    for w in words:
        if len(w) <= 2 and w[0] in PRESENCE_LETTERS:
            return PRESENCE_LETTERS[w[0]]
    return None


def _canonical(raw: Any, normalise) -> str:
    """The canonical value, or the value as written so the per-draft check can name it."""
    return normalise(raw) or (raw if isinstance(raw, str) else str(raw))


def as_str(v: Any) -> str:
    """A required text field: a scalar becomes text, a missing value becomes empty for the check to report."""
    return "" if v is None else (v if isinstance(v, str) else str(v)).strip()


def as_text(v: Any) -> str | None:
    """An optional text field: blank becomes None."""
    return as_str(v) or None


def as_text_list(v: Any) -> list[str]:
    """A list of text: one string, a list of scalars, or null all become a list of non-empty strings."""
    if v is None:
        return []
    items = v if isinstance(v, (list, tuple)) else [v]
    return [t for t in (as_str(i) for i in items) if t]


class Clause(BaseModel):
    id: str
    title: str
    text: str


def _vocabulary(values: tuple[str, ...], default: Any = ...) -> Any:
    """A lenient `str` field that still advertises its vocabulary in the JSON schema, so a server
    that enforces the schema constrains generation while a server that ignores it gets normalised."""
    return Field(default, json_schema_extra={"enum": list(values)})


class RequirementDraft(BaseModel):
    text: str
    modality: str = _vocabulary(MODALITY_VALUES)
    conditions: list[str] = Field(default_factory=list)
    source_quote: str

    @field_validator("text", "source_quote", mode="before")
    @classmethod
    def _text_fields(cls, v: Any) -> str:
        return as_str(v)

    @field_validator("conditions", mode="before")
    @classmethod
    def _list_fields(cls, v: Any) -> list[str]:
        return as_text_list(v)

    @field_validator("modality", mode="before")
    @classmethod
    def _modality(cls, v: Any) -> str:
        return _canonical(v, normalise_modality)


class Requirement(RequirementDraft):
    id: str
    clause_id: str
    modality: Modality


class RequirementBatch(BaseModel):
    """LLM output schema for one clause chunk."""
    requirements: list[RequirementDraft]


class TestObjectDraft(BaseModel):
    name: str
    kind: str = _vocabulary(OBJECT_KIND_VALUES)
    direction: str = _vocabulary(DIRECTION_VALUES, "internal")
    presence: str = _vocabulary(PRESENCE_VALUES, "unspecified")
    condition: str | None = None
    type: str | None = None
    value_domain: str | None = None
    size: str | None = None
    relations: list[str] = Field(default_factory=list)
    source_quote: str

    @field_validator("name", "source_quote", mode="before")
    @classmethod
    def _text_fields(cls, v: Any) -> str:
        return as_str(v)

    @field_validator("condition", "type", "value_domain", "size", mode="before")
    @classmethod
    def _optional_text_fields(cls, v: Any) -> str | None:
        return as_text(v)

    @field_validator("relations", mode="before")
    @classmethod
    def _list_fields(cls, v: Any) -> list[str]:
        return as_text_list(v)

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, v: Any) -> str:
        return _canonical(v, normalise_object_kind)

    @field_validator("direction", mode="before")
    @classmethod
    def _direction(cls, v: Any) -> str:
        return _canonical(v, normalise_direction)

    @field_validator("presence", mode="before")
    @classmethod
    def _presence(cls, v: Any) -> str:
        return _canonical(v, normalise_presence)


class TestObject(TestObjectDraft):
    id: str
    clause_id: str
    kind: ObjectKind
    direction: Direction = "internal"
    presence: Presence = "unspecified"


class TestObjectBatch(BaseModel):
    """LLM output schema for one clause chunk."""
    objects: list[TestObjectDraft]


class CoverageItem(BaseModel):
    id: str
    source_id: str
    clause_id: str
    check: Check
    kind: Kind
    purpose: str
    condition_assignment: dict[str, bool] | None = None


class TestCaseDraft(BaseModel):
    """LLM output schema for one coverage item."""
    objective: str
    preconditions: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    steps: list[str]
    expected_result: str
    pass_criteria: str

    @field_validator("objective", "expected_result", "pass_criteria", mode="before")
    @classmethod
    def _text_fields(cls, v: Any) -> str:
        return as_str(v)

    @field_validator("preconditions", "inputs", "steps", mode="before")
    @classmethod
    def _list_fields(cls, v: Any) -> list[str]:
        return as_text_list(v)


class TestCase(TestCaseDraft):
    id: str
    source_id: str
    coverage_item_id: str
    kind: Kind
    condition_assignment: dict[str, bool] | None = None


class Gap(BaseModel):
    source_id: str | None
    clause_id: str
    stage: Stage
    reason: str
    attempts: int


class TraceLink(BaseModel):
    source_id: str
    coverage_item_ids: list[str]
    test_case_ids: list[str]


class Source(BaseModel):
    path: str
    sha256: str
    generated_at: str
    model: str


class TestPlan(BaseModel):
    source: Source
    requirements: list[Requirement]
    objects: list[TestObject] = Field(default_factory=list)
    coverage_items: list[CoverageItem] = Field(default_factory=list)
    test_cases: list[TestCase]
    traceability: list[TraceLink]
    gaps: list[Gap]
