"""会话与消息路由（服务端透明加解密，见设计说明书 §9.3）。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_conversation_service, get_current_user
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationRead,
    ConversationUpdate,
    MessageRead,
)
from app.services.conversation import ConversationService

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _ok(data, message: str = "ok") -> dict:
    return {"code": 0, "data": data, "message": message}


@router.get("")
async def list_conversations(
    include_archived: bool = Query(default=False),
    user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> dict:
    items = await service.list(user, include_archived=include_archived)
    data = [ConversationRead.model_validate(c).model_dump(mode="json") for c in items]
    return _ok(data)


@router.post("", status_code=201)
async def create_conversation(
    body: ConversationCreate,
    user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> dict:
    conversation = await service.create(
        user, title=body.title, model=body.model, encrypted=body.encrypted
    )
    return _ok(ConversationRead.model_validate(conversation).model_dump(mode="json"))


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: uuid.UUID,
    body: ConversationUpdate,
    user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> dict:
    if body.title is not None:
        conversation = await service.rename(user, conversation_id, body.title)
    else:
        conversation = await service.get_owned(user, conversation_id)
    if body.archived is not None:
        conversation = await service.set_archived(user, conversation_id, body.archived)
    return _ok(ConversationRead.model_validate(conversation).model_dump(mode="json"))


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> dict:
    await service.delete(user, conversation_id)
    return _ok(None)


@router.get("/search")
async def search_conversations(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> dict:
    return _ok(await service.search(user, q, limit=limit))


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> dict:
    conversation = await service.get_owned(user, conversation_id)
    rows = await service.messages(user, conversation)
    data = [
        MessageRead(
            id=row.id,
            role=row.role,
            content=text,
            tokens_in=row.tokens_in,
            tokens_out=row.tokens_out,
            created_at=row.created_at,
        ).model_dump(mode="json")
        for row, text in rows
    ]
    return _ok(data)
