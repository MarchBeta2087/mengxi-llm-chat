"""审计日志查询（普通用户仅本人）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.repositories import AuditRepository
from app.schemas.admin import AuditRead

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
async def my_audit(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    logs = await AuditRepository(session).list_for_user(user.id, limit=limit, offset=offset)
    data = [AuditRead.model_validate(log).model_dump(mode="json") for log in logs]
    return {"code": 0, "data": data, "message": "ok"}
