"""All data types. Pydantic v2. Drafts are what the LLM returns; ids are assigned by code."""
from typing import Literal

from pydantic import BaseModel, Field

Modality = Literal["shall", "shall_not", "should", "may"]
Kind = Literal["nominal", "negative", "boundary"]


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
    """LLM output schema for one clause."""
    requirements: list[RequirementDraft]


class TestCaseDraft(BaseModel):
    kind: Kind
    objective: str
    preconditions: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    steps: list[str]
    expected_result: str
    pass_criteria: str
    condition_assignment: dict[str, bool] | None = None


class TestCase(TestCaseDraft):
    id: str
    requirement_id: str


class TestCaseBatch(BaseModel):
    """LLM output schema for one requirement."""
    test_cases: list[TestCaseDraft]


class Gap(BaseModel):
    requirement_id: str | None
    clause_id: str
    stage: Literal["extract", "generate"]
    reason: str
    attempts: int


class TraceLink(BaseModel):
    requirement_id: str
    test_case_ids: list[str]


class Source(BaseModel):
    path: str
    sha256: str
    generated_at: str
    model: str


class TestPlan(BaseModel):
    source: Source
    requirements: list[Requirement]
    test_cases: list[TestCase]
    traceability: list[TraceLink]
    gaps: list[Gap]
