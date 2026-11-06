"""Records-grounded consultation chat.

Context: a compact summary of the member's active meds, recent labs/vitals,
and conditions is injected into the system prompt — the model answers from
the household's own records. Streaming via provider.stream() when
available; verification runs on the full reply with a second provider.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ConditionEpisode,
    FamilyMember,
    LabResult,
    Medication,
    VitalMeasurement,
)

CHAT_SYSTEM = (
    "You are a careful family-health assistant. Answer using the member "
    "context below and general medical knowledge. Be concise and concrete "
    "with a professional tone — no filler or restating the question. "
    "Recommend professional care for red-flag symptoms; never invent "
    "readings that are not in the context."
)

RECENT_DAYS = 90


async def build_member_context(db: AsyncSession, member_id: uuid.UUID) -> str:
    member = await db.get(FamilyMember, member_id)
    if member is None:
        return "(no member context)"
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=RECENT_DAYS)

    meds = (
        await db.scalars(
            select(Medication).where(
                Medication.member_id == member_id, Medication.status == "active"
            )
        )
    ).all()
    labs = (
        await db.scalars(
            select(LabResult)
            .where(LabResult.member_id == member_id)
            .order_by(LabResult.record_date.desc().nullslast())
            .limit(10)
        )
    ).all()
    vitals = (
        await db.scalars(
            select(VitalMeasurement)
            .where(
                VitalMeasurement.member_id == member_id,
                VitalMeasurement.measured_at >= since,
            )
            .order_by(VitalMeasurement.measured_at.desc())
            .limit(10)
        )
    ).all()
    conditions = (
        await db.scalars(
            select(ConditionEpisode).where(
                ConditionEpisode.member_id == member_id,
                ConditionEpisode.status != "resolved",
            )
        )
    ).all()

    lines = [f"Member: {member.name} ({member.relationship})"]
    if meds:
        lines.append(
            "Active medications: "
            + "; ".join(f"{m.medicine} {m.dosage or ''}".strip() for m in meds)
        )
    if conditions:
        lines.append("Conditions: " + "; ".join(f"{c.name} ({c.status})" for c in conditions))
    if labs:
        lines.append(
            "Recent labs: "
            + "; ".join(
                f"{lab.test_name}={lab.result or ''}{lab.units or ''} ({lab.record_date})"
                for lab in labs
                if lab.record_date is None or lab.record_date >= since.date()
            )
        )
    if vitals:
        lines.append(
            "Recent vitals: "
            + "; ".join(
                f"{v.vital_type}={v.value_num}"
                + (f"/{v.value_secondary}" if v.value_secondary else "")
                + f" ({v.measured_at.date()})"
                for v in vitals
            )
        )
    return "\n".join(lines)


async def chat_stream(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    user_content: str,
    providers: list,
    verifier,
    member_id: uuid.UUID | None,
) -> AsyncIterator[dict]:
    """SSE source: persists the user message, streams the reply, persists
    the assistant message, schedules verification. ``providers`` is the
    ordered failover list — a provider that dies before emitting anything
    (dead cloud key, dropped connection) is skipped in favour of the next."""

    from app.models import Message
    from app.services.ai.router import mark_unhealthy
    from app.services.ai.verification import schedule_audit

    context = await build_member_context(db, member_id) if member_id else "(general)"
    yield {"stage": "context", "message": "member records loaded"}

    # Optional RAG grounding from the household's local reference index.
    from app.services import rag

    rag_block, citations = rag.grounding_block(user_content)

    user_msg = Message(conversation_id=conversation_id, role="user", content=user_content)
    db.add(user_msg)
    await db.flush()

    prompt = f"Member context:\n{context}\n\n"
    if rag_block:
        prompt += f"{rag_block}\n\n"
    prompt += f"Question: {user_content}"
    collected: list[str] = []
    for provider in providers:
        try:
            stream_fn = getattr(provider, "stream", None)
            if stream_fn is not None:
                deltas = await stream_fn(prompt, system=CHAT_SYSTEM)
                async for delta in deltas:
                    collected.append(delta)
                    yield {"stage": "streaming", "delta": delta}
            else:  # non-streaming provider fallback
                text = await provider.complete(prompt, system=CHAT_SYSTEM)
                collected.append(text)
                yield {"stage": "streaming", "delta": text}
            break
        except Exception:
            if collected:
                # Partial output already streamed — retrying would duplicate
                # text the user has seen. Surface the failure instead.
                raise
            # Nothing emitted: this provider never stood up (dead key,
            # refused connection). Mark it and fail over to the next.
            mark_unhealthy(getattr(provider, "name", ""))
            continue
    else:
        yield {
            "stage": "error",
            "message": "No AI provider could generate a reply.",
        }
        return

    reply = "".join(collected)
    verification_id = None
    # verifications.member_id is NOT NULL — general (member-less) chats
    # skip verification rather than fabricate a member reference.
    if verifier and member_id is not None:
        yield {"stage": "verifying", "message": "auditing claims"}
        verification_id = await schedule_audit(
            db,
            member_id,
            "chat_message",
            reply,
            verifier,
            commit=False,
        )

    assistant_msg = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=reply,
        verification_id=verification_id,
    )
    db.add(assistant_msg)
    await db.commit()
    yield {
        "stage": "complete",
        "message": {
            "id": str(assistant_msg.id),
            "role": "assistant",
            "content": reply,
            "created_at": assistant_msg.created_at.isoformat(),
            "verification_id": str(verification_id) if verification_id else None,
        },
        "sources": citations,
    }
