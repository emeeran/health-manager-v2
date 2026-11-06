"""Consultation chat: conversations CRUD + SSE message streaming."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, get_household_id, get_scoped_member
from app.core.sse import sse_response
from app.schemas._datetime import UTCDateTime
from app.models import Conversation, Message, User
from app.services import chat_service
from app.services.ai import router as ai_router
from app.services.ai.verification import pick_verifiers

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    member_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=200)


class ConversationView(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID | None
    title: str | None
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


class MessageView(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    verification_id: uuid.UUID | None
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


async def _get_conversation_scoped(
    conversation_id: uuid.UUID, user: User, db: AsyncSession
) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.household_id != await get_household_id(user, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conversation


@router.post("", response_model=ConversationView, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    if body.member_id:
        await get_scoped_member(body.member_id, user, db)
    conversation = Conversation(
        household_id=await get_household_id(user, db),
        member_id=body.member_id,
        title=body.title,
    )
    db.add(conversation)
    await db.flush()
    await db.refresh(conversation)
    return conversation


@router.get("", response_model=list[ConversationView])
async def list_conversations(
    member_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Conversation]:
    conditions = [Conversation.household_id == await get_household_id(user, db)]
    if member_id:
        conditions.append(Conversation.member_id == member_id)
    rows = await db.scalars(
        select(Conversation).where(*conditions).order_by(Conversation.created_at.desc()).limit(200)
    )
    return list(rows)


@router.get("/{conversation_id}/messages", response_model=list[MessageView])
async def list_messages(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Message]:
    await _get_conversation_scoped(conversation_id, user, db)
    rows = await db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(rows)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    conversation = await _get_conversation_scoped(conversation_id, user, db)
    await db.delete(conversation)
    await db.flush()


@router.post("/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: uuid.UUID,
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation = await _get_conversation_scoped(conversation_id, user, db)
    member_id = conversation.member_id
    if member_id is not None:
        await get_scoped_member(member_id, user, db)

    plan = await ai_router.plan_for_household(
        db, await get_household_id(user, db), local_only=False
    )
    if member_id is not None:
        from app.models import FamilyMember

        member = await db.get(FamilyMember, member_id)
        if member is not None and not member.cloud_ai_consent:
            plan = ai_router.build_plan(local_only=True)
    providers = await ai_router.available_providers(plan)
    if not providers:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No AI provider available")
    verifier = (
        pick_verifiers(plan, str(getattr(providers[0], "name", "")))
        if get_settings().AI_VERIFICATION_ENABLED
        else None
    )

    source = chat_service.chat_stream(
        db,
        conversation.id,
        body.content,
        providers,
        verifier,
        member_id,
    )
    return sse_response(source)
