"""Typed state shared across the agent graph.

Everything the agent believes at any point in a run lives here, so each node
is a function State -> State and the whole reasoning trail can be serialized,
inspected and replayed. Every claim carries SourceRef citations — the
citation trail is the product.
"""

from typing import Literal

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    """A verifiable pointer into an uploaded document."""

    doc_id: str
    section: str = ""  # e.g. "Section 7.1(a)" or "Note 4"
    page: int | None = None
    quote: str = ""  # exact supporting text


class DocSection(BaseModel):
    section_id: str
    title: str
    page: int | None = None
    text: str


class ParsedDoc(BaseModel):
    doc_id: str
    filename: str
    kind: Literal["credit_agreement", "financial_report", "treasury_pack", "other"] = "other"
    sections: list[DocSection] = Field(default_factory=list)


class CovenantRule(BaseModel):
    rule_id: str
    name: str  # "Leverage Ratio"
    metric: str  # "total_debt / ltm_ebitda"
    operator: Literal["<=", ">=", "<", ">"]
    threshold: float
    unit: str = "x"  # "x" for ratios, "EUR" for absolute amounts
    frequency: str = "quarterly"
    definition_notes: str = ""  # e.g. "EBITDA measured on a trailing-twelve-months basis"
    sources: list[SourceRef] = Field(default_factory=list)


class FinancialFact(BaseModel):
    metric: str  # "ltm_ebitda"
    value: float
    unit: str = "EUR_m"
    period: str = ""  # "Q2-2026"
    basis: Literal["final", "preliminary", "ltm", "quarterly", "unspecified"] = "unspecified"
    sources: list[SourceRef] = Field(default_factory=list)


class TrendPoint(BaseModel):
    period: str
    value: float


class Finding(BaseModel):
    rule_id: str
    covenant: str
    required: str  # "<= 3.50x"
    actual: str  # "3.70x"
    actual_value: float | None = None
    status: Literal["breach", "at_risk", "ok", "data_missing", "conflict"]
    headroom: str = ""
    computed_by: str = ""  # the deterministic tool call that produced the number
    trend: list[TrendPoint] = Field(default_factory=list)
    projection_note: str = ""
    notes: str = ""
    sources: list[SourceRef] = Field(default_factory=list)


class CriticCheck(BaseModel):
    check: str  # "citation_valid" | "data_freshness" | "definition_basis" | "internal_consistency"
    passed: bool
    note: str = ""


class Verdict(BaseModel):
    rule_id: str
    original_status: str
    final_status: Literal["breach", "at_risk", "ok", "data_missing"]
    overturned: bool = False
    checks: list[CriticCheck] = Field(default_factory=list)
    confidence: float = 0.0  # deterministic — see tools/confidence.py
    rationale: str = ""
    sources: list[SourceRef] = Field(default_factory=list)


class CauseMatch(BaseModel):
    """Explains WHY a metric moved (e.g. which transactions drove a debt jump)."""

    rule_id: str
    description: str
    amount: float | None = None
    matched: bool = False  # matched to a clearly documented cause?
    sources: list[SourceRef] = Field(default_factory=list)


class RetrievalRequest(BaseModel):
    reason: str  # "facts:<rule_id>" | "cause:<rule_id>" | "clause:<rule_id>"
    query: str
    doc_kind: str | None = None


class EvidenceSnippet(BaseModel):
    """Raw retrieved passage kept for downstream reasoning (causes, clauses)."""

    doc_id: str
    section: str = ""
    page: int | None = None
    text: str
    tag: str = ""  # mirrors the RetrievalRequest reason that fetched it


class AuditState(BaseModel):
    run_id: str
    documents: list[ParsedDoc] = Field(default_factory=list)
    plan: list[str] = Field(default_factory=list)
    rules: list[CovenantRule] = Field(default_factory=list)
    facts: list[FinancialFact] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    causes: list[CauseMatch] = Field(default_factory=list)
    cause_coverage: dict[str, float] = Field(default_factory=dict)  # rule_id -> [0,1]
    snippets: list[EvidenceSnippet] = Field(default_factory=list)
    verdicts: list[Verdict] = Field(default_factory=list)
    pending_retrievals: list[RetrievalRequest] = Field(default_factory=list)
    retrieval_rounds: int = 0
    max_retrieval_rounds: int = 4
    memo_markdown: str | None = None
    overall_confidence: float | None = None
