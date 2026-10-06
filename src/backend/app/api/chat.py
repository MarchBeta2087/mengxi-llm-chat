"""聊天路由：SSE 流式转发（见设计说明书 §7.2）。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_circuit_breaker,
    get_conversation_service,
    get_current_user,
    get_ip_rate_spec,
    get_key_manager,
    get_rate_limiter,
    get_scheduler,
    get_session,
    get_settings_dep,
    get_ssrf_policy,
    get_user_rate_spec,
)
from app.core.config import Settings
from app.core.errors import MengxiError
from app.core.ssrf import SsrfPolicy
from app.domain.ratelimit import RateLimitSpec
from app.models.user import User
from app.schemas.chat import ChatCompletionRequest
from app.services.chat import ChatEvent, ChatMessage, ChatService
from app.services.conversation import ConversationService
from app.services.key_manager import KeyManager
from app.services.ratelimit import CircuitBreaker, RateLimiter
from app.services.scheduler import SchedulerService

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _format_sse(event: ChatEvent) -> str:
    payload = json.dumps(event.data, ensure_ascii=False)
    return f"event: {event.event}\ndata: {payload}\n\n"


async def _event_stream(events: AsyncIterator[ChatEvent]) -> AsyncIterator[str]:
    try:
        async for event in events:
            yield _format_sse(event)
    except MengxiError as exc:
        data = {"code": exc.code, "message": exc.message, **exc.extra}
        yield f"event: error\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/completions")
async def completions(
    body: ChatCompletionRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    key_manager: KeyManager = Depends(get_key_manager),
    policy: SsrfPolicy = Depends(get_ssrf_policy),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    circuit_breaker: CircuitBreaker = Depends(get_circuit_breaker),
    scheduler: SchedulerService = Depends(get_scheduler),
    settings: Settings = Depends(get_settings_dep),
    user_rate_spec: RateLimitSpec = Depends(get_user_rate_spec),
    ip_rate_spec: RateLimitSpec = Depends(get_ip_rate_spec),
    conversations: ConversationService = Depends(get_conversation_service),
) -> StreamingResponse:
    if body.conversation_id is not None:
        conversation = await conversations.get_owned(user, body.conversation_id)
    else:
        conversation = await conversations.create(user, model=body.model)

    service = ChatService(
        session,
        user=user,
        key_manager=key_manager,
        rate_limiter=rate_limiter,
        circuit_breaker=circuit_breaker,
        scheduler=scheduler,
        policy=policy,
        fallback_to_public=settings.fallback_to_public,
        user_rate_spec=user_rate_spec,
        ip_rate_spec=ip_rate_spec,
        client_ip=request.client.host if request.client else None,
        conversations=conversations,
    )
    messages = [ChatMessage(role=m.role, content=m.content) for m in body.messages]
    events = service.stream(model=body.model, messages=messages, conversation=conversation)
    return StreamingResponse(
        _event_stream(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 反代关闭缓冲
        },
    )
