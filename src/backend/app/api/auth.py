"""认证路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserRead
from app.services.auth import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _payload(user: User) -> dict:
    data = UserRead.model_validate(user).model_dump(mode="json")
    return {"code": 0, "data": data, "message": "ok"}


@router.post("/register")
async def register(
    body: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    user = await AuthService(session).register(body.username, body.password)
    request.session["uid"] = str(user.id)
    return _payload(user)


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    user = await AuthService(session).authenticate(body.username, body.password)
    request.session["uid"] = str(user.id)
    return _payload(user)


@router.post("/logout")
async def logout(request: Request) -> dict:
    request.session.clear()
    return {"code": 0, "data": None, "message": "ok"}


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return _payload(user)
