"""Pydantic contracts shared by the history and audit agents.

The LLM-facing models (``AuditDraft``, ``WebVerdict``) are rendered into
prompts with ``insight_service.render_schema_block``; the stored models
(``AuditReport``, ``ClaimAudit``) are what the UI reads. Evidence is
referenced by stable ids from the history index — the model never invents
a value or a URL, and code expands ids into labelled rows afterwards.
"""

from typing import Literal

from pydantic import BaseModel, Field

ClaimCategory = Literal[
    "record_fact",
    "condition",
    "prognosis",
    "guideline",
    "drug_interaction",
    "recommendation",
]
ClaimVerdict = Literal[
    "supported",
    "contradicted",
    "not_in_records",
    "external_verified",
    "unverified",
]
Severity = Literal["info", "warning", "critical"]
AuditOverall = Literal["passed", "flagged", "failed"]


class DataGap(BaseModel):
    """A deterministic coverage gap in the member's record."""

    domain: str = Field(description="Record domain (labs, vitals, allergies, …)")
    status: Literal["missing", "stale"] = Field(description="missing or stale")
    detail: str = Field(description="Plain-language description of the gap")


class EvidenceRef(BaseModel):
    """One concrete record that supports (or contradicts) a claim."""

    domain: str = Field(description="Record domain")
    ref: str = Field(description="Stable evidence id, e.g. lab:<uuid>")
    label: str = Field(description="Human label, e.g. the test or medicine name")
    value: str | None = Field(default=None, description="Recorded value/status")
    date: str | None = Field(default=None, description="Recorded date (ISO)")


class WebSource(BaseModel):
    title: str
    url: str = Field(description="http(s) URL only")


class WebCheck(BaseModel):
    """Search evidence attached to a claim that was sent to the web."""

    query: str
    results: list[WebSource] = Field(default_factory=list)


class ClaimAudit(BaseModel):
    """One audited claim, stored and shown to the user."""

    claim: str = Field(description="Verbatim claim from the narrative")
    category: ClaimCategory
    verdict: ClaimVerdict
    severity: Severity = "info"
    evidence_ids: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    needs_web: bool = False
    web_query: str | None = None
    web: WebCheck | None = None
    note: str | None = Field(default=None, description="Why the verdict was reached")


class ClaimDraft(BaseModel):
    """LLM output for one extracted claim (no values, only evidence ids)."""

    claim: str = Field(description="Verbatim claim copied from the narrative")
    category: ClaimCategory
    verdict: ClaimVerdict = Field(
        description="supported | contradicted | not_in_records for the local pass"
    )
    severity: Severity = "info"
    evidence: list[str] = Field(
        default_factory=list,
        description="Evidence ids copied from the evidence index that support the claim",
    )
    needs_web: bool = Field(
        default=False,
        description="True only for condition/prognosis/guideline/drug_interaction claims "
        "that need external clinical knowledge",
    )
    web_query: str | None = Field(
        default=None,
        description="Generic clinical query with no names, dates, or identifiers",
    )
    note: str | None = Field(default=None, description="Short reason for the verdict")


class AuditDraft(BaseModel):
    """First audit pass: claims + additional gaps the auditor noticed."""

    claims: list[ClaimDraft] = Field(default_factory=list)
    gaps: list[DataGap] = Field(default_factory=list)
    summary: str = Field(default="", description="One or two sentences on the audit")


class WebVerdict(BaseModel):
    """Second audit pass: adjudicate one claim against search results."""

    claim_index: int = Field(description="Zero-based index into the claims array")
    verdict: Literal["external_verified", "contradicted", "unverified"]
    note: str = Field(description="What the sources say, briefly")
    source_indexes: list[int] = Field(
        default_factory=list,
        description="One-based indexes of the search results relied on",
    )


class WebAdjudication(BaseModel):
    findings: list[WebVerdict] = Field(default_factory=list)


class AuditReport(BaseModel):
    """Complete audit persisted on the verification row and rendered by the UI."""

    overall: AuditOverall
    summary: str
    claims: list[ClaimAudit] = Field(default_factory=list)
    gaps: list[DataGap] = Field(default_factory=list)
    interactions: list[dict] = Field(default_factory=list)
    web_used: bool = False
    sources: list[WebSource] = Field(default_factory=list)
