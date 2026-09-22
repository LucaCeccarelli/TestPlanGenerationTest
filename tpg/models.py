"""All data types. Pydantic v2. Drafts are what the LLM returns; ids are assigned by code."""
from typing import Literal

from pydantic import BaseModel, Field

Modality = Literal["shall", "shall_not", "should", "should_not", "may"]
Kind = Literal["nominal", "negative", "boundary"]
Check = Literal["presence", "absence", "encoding_valid", "encoding_invalid", "value_valid", "value_invalid",
                "boundary_min", "boundary_max", "boundary_outside", "consistency", "condition_true", "condition_false",
                "nominal", "negative", "boundary"]
Stage = Literal["extract", "model", "generate"]


class Clause(BaseModel):
    id: str
    title: str
    text: str


class RequirementDraft(BaseModel):
    text: str
    modality: Modality
    conditions: list[str] = Field(default_factory=list)
    source_quote: str


class Requirement(RequirementDraft):
    id: str
    clause_id: str


class RequirementBatch(BaseModel):
    """LLM output schema for one clause chunk."""
    requirements: list[RequirementDraft]


class TestObjectDraft(BaseModel):
    name: str
    kind: Literal["field", "structure", "message", "parameter", "value", "behaviour"]
    direction: Literal["received", "produced", "internal"] = "internal"
    presence: Literal["mandatory", "optional", "conditional", "unspecified"] = "unspecified"
    condition: str | None = None
    type: str | None = None
    value_domain: str | None = None
    size: str | None = None
    relations: list[str] = Field(default_factory=list)
    source_quote: str


class TestObject(TestObjectDraft):
    id: str
    clause_id: str


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
