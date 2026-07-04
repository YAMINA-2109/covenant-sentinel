"""Flat models for LLM structured output.

Deliberately shallower than the domain models in state.py: flatter schemas
validate far more reliably across models. Node code maps these onto the
domain models and resolves proper SourceRefs from the retrieval hits.
"""

from typing import Literal

from pydantic import BaseModel, Field


class ExtractedRule(BaseModel):
    rule_id: str
    name: str
    metric: str  # e.g. "total_debt / ltm_ebitda" or "unrestricted_cash"
    operator: Literal["<=", ">=", "<", ">"]
    threshold: float  # ratios as decimals (3.5), money in EUR millions (5.0)
    unit: str = "x"  # "x" for ratios, "EUR_m" for amounts
    definition_notes: str = ""
    source_section: str = ""
    source_quote: str = ""


class PlannerOutput(BaseModel):
    plan: list[str] = Field(default_factory=list)
    rules: list[ExtractedRule] = Field(default_factory=list)


class ExtractedFact(BaseModel):
    metric: str
    value: float  # EUR millions for money, decimal for ratios
    unit: str = "EUR_m"
    period: str = ""  # "Q2-2026", "Q1-2026", ...
    basis: Literal["final", "preliminary", "ltm", "quarterly", "unspecified"] = "unspecified"
    source_section: str = ""
    source_quote: str = ""


class FactExtraction(BaseModel):
    facts: list[ExtractedFact] = Field(default_factory=list)


class TrendPair(BaseModel):
    period: str
    numerator_fact: int | None = None
    denominator_fact: int | None = None
    value_fact: int | None = None


class RuleAssessment(BaseModel):
    rule_id: str
    mode: Literal["ratio", "absolute"]
    numerator_fact: int | None = None
    denominator_fact: int | None = None
    value_fact: int | None = None
    conflict_facts: list[int] = Field(default_factory=list)
    trend: list[TrendPair] = Field(default_factory=list)  # oldest -> newest, include current
    missing_metrics: list[str] = Field(default_factory=list)
    followup_queries: list[str] = Field(default_factory=list)
    rationale: str = ""


class AnalyzerOutput(BaseModel):
    assessments: list[RuleAssessment] = Field(default_factory=list)


class CauseItem(BaseModel):
    description: str
    amount: float | None = None  # EUR millions
    matched: bool = False  # clearly documented, legitimate cause?
    source_section: str = ""
    source_quote: str = ""


class CauseAnalysis(BaseModel):
    items: list[CauseItem] = Field(default_factory=list)
    note: str = ""


class CriticCheckOut(BaseModel):
    check: Literal["citation_valid", "data_freshness", "definition_basis", "internal_consistency"]
    passed: bool
    note: str = ""


class CriticOutput(BaseModel):
    final_status: Literal["breach", "at_risk", "ok", "data_missing"]
    overturned: bool = False
    checks: list[CriticCheckOut] = Field(default_factory=list)
    rationale: str = ""
    key_source_section: str = ""
    key_source_quote: str = ""


class MemoOutput(BaseModel):
    memo_markdown: str
