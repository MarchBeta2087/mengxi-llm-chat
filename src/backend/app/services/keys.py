"""密钥服务：CRUD + 加密落库 + SSRF 校验 + 连通性测试。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Protocol
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequest, Forbidden, NotFound
from app.core.security import mask_key
from app.core.ssrf import SafeHttpClient, SsrfPolicy, validate_url
from app.models.api_key import ApiKey
from app.models.enums import KeyPool, KeyStatus
from app.models.recovery import AuditLog
from app.models.user import User
from app.repositories import ApiKeyRepository, AuditRepository
from app.schemas.keys import KeyCreate, KeyRead, KeyUpdate
from app.services.key_manager import KeyManager


@dataclass
class ProbeResult:
    ok: bool
    status_code: int
    latency_ms: int
    error: str | None = None


class UpstreamProbe(Protocol):
    async def __call__(
        self, base_url: str, api_key: str, *, timeout: float = 10.0
    ) -> ProbeResult: ...


class HttpUpstreamProbe:
    """默认探测器：经 SSRF 安全客户端访问上游 ``/models``。"""

    def __init__(self, policy: SsrfPolicy) -> None:
        self.policy = policy

    async def __call__(self, base_url: str, api_key: str, *, timeout: float = 10.0) -> ProbeResult:
        url = base_url.rstrip("/") + "/models"
        started = perf_counter()
        try:
            async with SafeHttpClient(self.policy, timeout=timeout) as client:
                resp = await client.request(
                    "GET", url, headers={"Authorization": f"Bearer {api_key}"}
                )
        except Exception as exc:  # noqa: BLE001 - 探测失败需回传给用户
            return ProbeResult(
                ok=False,
                status_code=0,
                latency_ms=int((perf_counter() - started) * 1000),
                error=str(exc),
            )
        latency = int((perf_counter() - started) * 1000)
        ok = 200 <= resp.status_code < 400
        return ProbeResult(
            ok=ok,
            status_code=resp.status_code,
            latency_ms=latency,
            error=None if ok else f"HTTP {resp.status_code}",
        )


def key_to_read(key: ApiKey) -> KeyRead:
    return KeyRead(
        id=key.id,
        provider_name=key.provider_name,
        base_url=key.base_url,
        models=list(key.models_json or []),
        masked_key=key.key_fingerprint,
        rate_limits=dict(key.rate_limits_json or {}),
        weight=key.weight,
        status=key.status,
        pool=key.priority_pool,
        created_at=key.created_at,
    )


class KeysService:
    def __init__(
        self,
        session: AsyncSession,
        key_manager: KeyManager,
        policy: SsrfPolicy,
        *,
        probe: UpstreamProbe | None = None,
    ) -> None:
        self.session = session
        self.km = key_manager
        self.policy = policy
        self.keys = ApiKeyRepository(session)
        self.audit = AuditRepository(session)
        self.probe: UpstreamProbe = probe or HttpUpstreamProbe(policy)

    @staticmethod
    def _aad(key_id: uuid.UUID) -> bytes:
        return f"api-key:{key_id}".encode()

    async def create(self, user: User, data: KeyCreate) -> ApiKey:
        # 新增即校验：阻止内网/回环/链路本地等目标（§4.1.4）
        await validate_url(data.base_url, self.policy)

        is_public = bool(data.is_public and user.is_admin)
        key_id = uuid.uuid4()
        encrypted = self.km.encrypt_secret(data.api_key, aad=self._aad(key_id))

        api_key = ApiKey(
            id=key_id,
            user_id=None if is_public else user.id,
            provider_name=data.provider_name,
            base_url=data.base_url.rstrip("/"),
            models_json=list(data.models),
            encrypted_key=encrypted,
            key_fingerprint=mask_key(data.api_key),
            rate_limits_json=data.rate_limits.model_dump(),
            weight=data.weight,
            status=KeyStatus.ACTIVE.value,
            priority_pool=(KeyPool.PUBLIC.value if is_public else KeyPool.PRIVATE.value),
        )
        await self.keys.add(api_key)
        await self.session.commit()
        return api_key

    async def list(self, user: User, *, pool: str | None = None) -> list[ApiKey]:
        if pool == KeyPool.PRIVATE.value:
            return await self.keys.list_private_for_user(user.id)
        if user.is_admin and pool != KeyPool.PRIVATE.value:
            return await self.keys.list_public()
        return await self.keys.list_private_for_user(user.id)

    async def get_manageable(self, user: User, key_id: uuid.UUID) -> ApiKey:
        key = await self.keys.get(key_id)
        if key is None:
            raise NotFound("Key 不存在")
        if key.user_id is None:
            if not user.is_admin:
                raise Forbidden("无权访问公有 Key")
        elif key.user_id != user.id:
            raise Forbidden("无权访问他人的私有 Key")
        return key

    async def update(self, user: User, key_id: uuid.UUID, data: KeyUpdate) -> ApiKey:
        key = await self.get_manageable(user, key_id)

        if data.base_url is not None:
            await validate_url(data.base_url, self.policy)
            key.base_url = data.base_url.rstrip("/")
        if data.api_key is not None:
            key.encrypted_key = self.km.encrypt_secret(data.api_key, aad=self._aad(key.id))
            key.key_fingerprint = mask_key(data.api_key)
        if data.provider_name is not None:
            key.provider_name = data.provider_name
        if data.models is not None:
            key.models_json = list(data.models)
        if data.rate_limits is not None:
            key.rate_limits_json = data.rate_limits.model_dump()
        if data.weight is not None:
            key.weight = data.weight
        if data.status is not None:
            key.status = data.status.value

        await self.session.commit()
        return key

    async def delete(self, user: User, key_id: uuid.UUID) -> None:
        key = await self.get_manageable(user, key_id)
        await self.keys.delete(key)
        await self.session.commit()

    async def test_connectivity(
        self, user: User, key_id: uuid.UUID, *, client_ip: str | None
    ) -> ProbeResult:
        key = await self.get_manageable(user, key_id)
        secret = self.km.decrypt_secret(key.encrypted_key, aad=self._aad(key.id))
        result = await self.probe(key.base_url, secret)

        now = datetime.now(UTC)
        key.last_used_at = now
        await self.audit.add(
            AuditLog(
                user_id=user.id,
                key_id=key.id,
                key_type=KeyPool.PUBLIC.value if key.is_public else KeyPool.PRIVATE.value,
                base_url_host=urlsplit(key.base_url).hostname,
                status=result.status_code,
                latency_ms=result.latency_ms,
                client_ip=client_ip,
            )
        )
        await self.session.commit()
        return result


def require_key_manager(key_manager: KeyManager | None) -> KeyManager:
    if key_manager is None:
        raise BadRequest("主密钥服务不可用")
    return key_manager
