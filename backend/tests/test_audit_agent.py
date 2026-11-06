"""Audit agent: claim parsing, evidence assembly, consent gating, persistence."""

import json
import uuid
from datetime import date

import pytest

from app.core.config import get_settings
from app.models import FamilyMember, Household, LabResult, User, Verification
from app.services.ai import verification as verification_service
from app.services.ai import web_search
from app.services.ai.agents import auditor, history
from app.services.ai.agents.contracts import (
    AuditDraft,
    ClaimDraft,
    DataGap,
    EvidenceRef,
)


class FakeProvider:
    name = "fake"
    model = "fake-model"
    local = True
    timeout = 5

    def __init__(self, handler):
        self.handler = handler
        self.prompts: list[str] = []

    async def available(self) -> bool:
        return True

    async def complete(self, prompt: str, **kwargs) -> str:
        self.prompts.append(prompt)
        return self.handler(prompt)


async def _member(session, *, name: str = "John Smith") -> FamilyMember:
    user = User(username=f"u{uuid.uuid4().hex[:8]}", password_hash="x")
    session.add(user)
    await session.flush()
    household = Household(name="Home", primary_user_id=user.id)
    session.add(household)
    await session.flush()
    member = FamilyMember(household_id=household.id, name=name, relationship="self")
    session.add(member)
    await session.flush()
    return member


def _lab_row(lab_id: uuid.UUID) -> dict:
    return {
        "domain": "lab",
        "ref": f"lab:{lab_id}",
        "label": "HbA1c",
        "value": "8.4 % [high]",
        "date": "2026-05-01",
    }


def test_parse_draft_accepts_fenced_json_and_coerces_bad_enums():
    payload = {
        "claims": [
            {
                "claim": "HbA1c was 8.4 %",
                "category": "record_fact",
                "verdict": "supported",
                "evidence": ["lab:1"],
            },
            {
                "claim": "Vague statement",
                "category": "not-a-category",
                "verdict": "not-a-verdict",
                "severity": "extreme",
            },
        ],
        "gaps": [{"domain": "labs", "status": "stale", "detail": "Old labs."}],
        "summary": "Checked.",
    }
    draft = auditor.parse_draft("```json\n" + json.dumps(payload) + "\n```")

    assert draft is not None
    assert len(draft.claims) == 2
    assert draft.claims[1].category == "recommendation"
    assert draft.claims[1].verdict == "unverified"
    assert draft.claims[1].severity == "info"
    assert draft.gaps[0].domain == "labs"


def test_parse_draft_rejects_non_object_reply():
    assert auditor.parse_draft("I cannot audit this.") is None
    assert auditor.parse_draft("") is None


def test_assemble_expands_evidence_ids_and_flags_contradictions():
    lab_id = uuid.uuid4()
    context = {"evidence": [_lab_row(lab_id)], "gaps": []}
    draft = AuditDraft(
        claims=[
            ClaimDraft(
                claim="HbA1c was 8.4 %",
                category="record_fact",
                verdict="supported",
                evidence=[f"lab:{lab_id}"],
            )
        ],
        summary="Supported.",
    )

    report = auditor.assemble(draft, context)

    assert report.overall == "passed"
    assert report.claims[0].evidence[0].label == "HbA1c"
    assert report.claims[0].evidence[0].value == "8.4 % [high]"
    assert report.claims[0].evidence_ids == [f"lab:{lab_id}"]

    draft.claims[0].verdict = "contradicted"
    assert auditor.assemble(draft, context).overall == "flagged"


def test_recommendations_do_not_flag_a_report():
    context = {"evidence": [], "gaps": []}
    draft = AuditDraft(
        claims=[
            ClaimDraft(
                claim="Discuss the trend with your doctor.",
                category="recommendation",
                verdict="not_in_records",
            )
        ]
    )
    assert auditor.assemble(draft, context).overall == "passed"


def test_assemble_dedupes_deterministic_and_model_gaps():
    context = {
        "evidence": [],
        "gaps": [{"domain": "labs", "status": "stale", "detail": "Old labs."}],
    }
    draft = AuditDraft(
        gaps=[DataGap(domain="labs", status="stale", detail="Old labs.")]
    )
    report = auditor.assemble(draft, context)
    assert len(report.gaps) == 1


@pytest.mark.asyncio
async def test_extract_claims_uses_the_evidence_index():
    provider = FakeProvider(
        lambda prompt: json.dumps(
            {
                "claims": [
                    {
                        "claim": "HbA1c was 8.4 %",
                        "category": "record_fact",
                        "verdict": "supported",
                        "evidence": ["lab:abc"],
                    }
                ]
            }
        )
    )
    context = {
        "evidence": [
            {
                "domain": "lab",
                "ref": "lab:abc",
                "label": "HbA1c",
                "value": "8.4",
                "date": "2026-05-01",
            }
        ],
        "coverage": {},
        "gaps": [],
    }

    draft = await auditor.extract_claims("HbA1c was 8.4 %.", context, provider)

    assert draft.claims[0].evidence == ["lab:abc"]
    assert "lab:abc" in provider.prompts[0]
    assert "AUDIT DRAFT SCHEMA" in provider.prompts[0]


@pytest.mark.asyncio
async def test_extract_claims_rejects_unparseable_output():
    provider = FakeProvider(lambda prompt: "not json")
    with pytest.raises(ValueError):
        await auditor.extract_claims("narrative", {"evidence": []}, provider)


@pytest.mark.asyncio
async def test_web_checks_skip_record_facts_and_redact_queries(monkeypatch, session_factory):
    settings = get_settings()
    monkeypatch.setattr(settings, "WEB_FACTCHECK_ENABLED", True)
    monkeypatch.setattr(settings, "SEARXNG_URL", "http://searx.local")
    calls: list[str] = []

    async def fake_search(query, *, limit=None):
        calls.append(query)
        return [web_search.SearchResult(title="Guideline", url="https://example.org/g")]

    monkeypatch.setattr(web_search, "search", fake_search)

    draft = AuditDraft(
        claims=[
            ClaimDraft(
                claim="HbA1c was 8.4 %.",
                category="record_fact",
                verdict="supported",
                needs_web=True,
                web_query="HbA1c 8.4 % John Smith 2026-05-01",
            ),
            ClaimDraft(
                claim="An HbA1c of 8.4 % is above the usual target.",
                category="guideline",
                verdict="not_in_records",
                needs_web=True,
                web_query="HbA1c target John Smith 2026-05-01",
            ),
        ]
    )
    context = {
        "evidence": [
            {
                "domain": "lab",
                "ref": "lab:abc",
                "label": "HbA1c",
                "value": "8.4",
                "date": "2026-05-01",
            }
        ],
        "household_names": ["John Smith"],
        "member_id": str(uuid.uuid4()),
    }

    async with session_factory() as db:
        checks = await auditor.run_web_checks(
            draft, context=context, db=db, household_id=None
        )
        await db.commit()

    assert list(checks) == [1]
    assert len(calls) == 1
    for forbidden in ("John", "Smith", "2026-05-01"):
        assert forbidden not in calls[0]


@pytest.mark.asyncio
async def test_adjudicate_web_attaches_only_provided_sources():
    checks = {
        3: (
            "HbA1c target",
            [
                web_search.SearchResult(title="A", url="https://a.example/x", snippet="a"),
                web_search.SearchResult(title="B", url="https://b.example/x", snippet="b"),
            ],
        )
    }
    draft = AuditDraft(
        claims=[
            ClaimDraft(
                claim="HbA1c target is 7 %.",
                category="guideline",
                verdict="not_in_records",
                needs_web=True,
            )
        ]
    )
    provider = FakeProvider(
        lambda prompt: json.dumps(
            {
                "findings": [
                    {
                        "claim_index": 0,
                        "verdict": "external_verified",
                        "note": "Guideline agrees.",
                        "source_indexes": [2],
                    }
                ]
            }
        )
    )

    web_by_claim = await auditor.adjudicate_web(draft, {0: checks[3]}, provider)

    assert draft.claims[0].verdict == "external_verified"
    assert web_by_claim[0].results[0].url == "https://b.example/x"


@pytest.mark.asyncio
async def test_run_audit_persists_a_supported_claim(session_factory):
    async with session_factory() as db:
        member = await _member(db)
        lab = LabResult(
            member_id=member.id,
            test_name="HbA1c",
            result="8.4",
            units="%",
            flag="high",
            value_num=8.4,
            record_date=date(2026, 5, 1),
        )
        db.add(lab)
        await db.flush()
        verification = Verification(
            member_id=member.id,
            subject_type="report:health_insights",
            status="pending",
        )
        db.add(verification)
        await db.commit()
        verification_id = verification.id
        member_id = member.id
        lab_id = lab.id

    def handler(prompt: str) -> str:
        if "AUDIT DRAFT SCHEMA" in prompt:
            return json.dumps(
                {
                    "claims": [
                        {
                            "claim": "HbA1c was 8.4 % on 2026-05-01.",
                            "category": "record_fact",
                            "verdict": "supported",
                            "evidence": [f"lab:{lab_id}"],
                        }
                    ],
                    "summary": "One claim supported.",
                }
            )
        return "[]"

    await verification_service.run_audit(
        verification_id,
        member_id,
        "report:health_insights",
        "HbA1c was 8.4 % on 2026-05-01.",
        FakeProvider(handler),
        kind="health_insights",
    )

    async with session_factory() as db:
        row = await db.get(Verification, verification_id)
        assert row is not None
        assert row.status == "passed"
        assert row.notes == "One claim supported."
        assert row.audit_json is not None
        payload = json.loads(row.audit_json)
        assert payload["overall"] == "passed"
        assert payload["claims"][0]["evidence"][0]["label"] == "HbA1c"


@pytest.mark.asyncio
async def test_run_audit_never_searches_without_consent(monkeypatch, session_factory):
    settings = get_settings()
    monkeypatch.setattr(settings, "WEB_FACTCHECK_ENABLED", True)
    monkeypatch.setattr(settings, "SEARXNG_URL", "http://searx.local")
    calls: list[str] = []

    async def fake_search(query, *, limit=None):
        calls.append(query)
        return []

    monkeypatch.setattr(web_search, "search", fake_search)

    async with session_factory() as db:
        member = await _member(db)
        member.web_factcheck_consent = False
        verification = Verification(
            member_id=member.id,
            subject_type="report:health_insights",
            status="pending",
        )
        db.add(verification)
        await db.commit()
        verification_id = verification.id
        member_id = member.id

    def handler(prompt: str) -> str:
        if "AUDIT DRAFT SCHEMA" in prompt:
            return json.dumps(
                {
                    "claims": [
                        {
                            "claim": "An HbA1c of 8.4 % is above target.",
                            "category": "guideline",
                            "verdict": "not_in_records",
                            "needs_web": True,
                            "web_query": "HbA1c target",
                        }
                    ]
                }
            )
        return "[]"

    await verification_service.run_audit(
        verification_id,
        member_id,
        "report:health_insights",
        "An HbA1c of 8.4 % is above target.",
        FakeProvider(handler),
        kind="health_insights",
    )

    assert calls == []
    async with session_factory() as db:
        row = await db.get(Verification, verification_id)
        assert row is not None
        assert row.status == "flagged"


@pytest.mark.asyncio
async def test_history_context_includes_deterministic_gaps(session_factory):
    async with session_factory() as db:
        member = await _member(db)
        await db.commit()
        context = await history.build_audit_context(db, member.id)

    domains = {gap["domain"] for gap in context["gaps"]}
    assert {"history", "allergies", "labs", "vitals", "visits", "vaccinations"} <= domains
    assert "John Smith" in context["household_names"]
    assert context["evidence"][0]["ref"] == "member:profile"


def test_fallback_query_uses_record_labels_only():
    context = {
        "evidence": [
            {"domain": "condition", "label": "Type 2 Diabetes", "ref": "condition:1"}
        ]
    }
    claim = ClaimDraft(
        claim="Type 2 Diabetes control is stable.",
        category="prognosis",
        verdict="not_in_records",
        needs_web=True,
    )
    assert auditor.fallback_query(claim, context) == (
        "Type 2 Diabetes prognosis clinical guidelines"
    )


def test_evidence_ref_contract_roundtrips():
    ref = EvidenceRef(domain="lab", ref="lab:1", label="HbA1c", value="8.4", date=None)
    assert ref.model_dump()["label"] == "HbA1c"


async def test_member_web_consent_defaults_off_and_roundtrips(auth_client):
    created = await auth_client.post("/api/v1/members", json={"name": "Asha"})
    assert created.status_code == 201, created.text
    member = created.json()
    assert member["web_factcheck_consent"] is False

    updated = await auth_client.patch(
        f"/api/v1/members/{member['id']}",
        json={"web_factcheck_consent": True},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["web_factcheck_consent"] is True


async def test_verification_endpoint_returns_the_claim_audit(
    auth_client, session_factory
):
    created = await auth_client.post("/api/v1/members", json={"name": "Asha"})
    member_id = uuid.UUID(created.json()["id"])
    async with session_factory() as db:
        row = Verification(
            member_id=member_id,
            subject_type="report:health_insights",
            status="passed",
            notes="One claim verified.",
            audit_json=json.dumps(
                {
                    "overall": "passed",
                    "summary": "One claim verified.",
                    "claims": [
                        {
                            "claim": "HbA1c was 8.4 %.",
                            "category": "record_fact",
                            "verdict": "supported",
                            "severity": "info",
                            "evidence_ids": ["lab:1"],
                            "evidence": [
                                {
                                    "domain": "lab",
                                    "ref": "lab:1",
                                    "label": "HbA1c",
                                    "value": "8.4 %",
                                    "date": "2026-05-01",
                                }
                            ],
                            "needs_web": False,
                            "web_query": None,
                            "web": None,
                            "note": None,
                        }
                    ],
                    "gaps": [],
                    "interactions": [],
                    "web_used": False,
                    "sources": [],
                }
            ),
        )
        db.add(row)
        await db.commit()
        verification_id = row.id

    response = await auth_client.get(f"/api/v1/verifications/{verification_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["audit"]["overall"] == "passed"
    assert body["audit"]["claims"][0]["evidence"][0]["label"] == "HbA1c"
