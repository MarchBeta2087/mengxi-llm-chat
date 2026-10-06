"""认证服务。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequest, Forbidden, Unauthorized
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories import UserRepository


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def register(self, username: str, password: str) -> User:
        if await self.users.get_by_username(username) is not None:
            raise BadRequest("用户名已存在")
        user = User(username=username, password_hash=hash_password(password))
        await self.users.add(user)
        await self.session.commit()
        return user

    async def authenticate(self, username: str, password: str) -> User:
        user = await self.users.get_by_username(username)
        # 统一错误信息，避免用户名枚举
        if user is None or not verify_password(password, user.password_hash):
            raise Unauthorized("用户名或密码错误")
        if not user.is_active:
            raise Forbidden("账号已被封禁")
        return user
