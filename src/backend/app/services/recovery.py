"""恢复码服务（见设计说明书 §3.4）。

- 生成：每个恢复码的恢复密钥 Argon2id(code, salt) 加密 KEK 副本入库；
- 使用：解出 KEK → 重置主口令（重包裹 DEK）→ 作废全部旧码并生成新一批。
"""

from __future__ import annotations

import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.crypto.kek import Argon2Params, KekProvider, LocalKekProvider
from app.core.crypto.recovery import (
    RecoveryCodeRecord,
    code_hash,
    generate_recovery_codes,
    recover_kek,
)
from app.core.errors import BadRequest, WrongPassphrase
from app.models.recovery import RecoveryCode
from app.repositories import RecoveryCodeRepository, UserRepository
from app.services.conversation import ConversationKeyCache
from app.services.key_manager import CONV_DEK_AAD, KeyManager

_HMAC_INFO = b"mengxi-recovery-index"


class RecoveryService:
    def __init__(
        self,
        session: AsyncSession,
        provider: KekProvider,
        key_manager: KeyManager,
        settings: Settings,
        *,
        cache: ConversationKeyCache | None = None,
    ) -> None:
        self.session = session
        self.provider = provider
        self.key_manager = key_manager
        self.params = Argon2Params(
            time_cost=settings.argon2_time_cost,
            memory_cost=settings.argon2_memory_cost,
            parallelism=settings.argon2_parallelism,
            hash_len=settings.argon2_hash_len,
        )
        self.count = settings.recovery_code_count
        self.codes = RecoveryCodeRepository(session)
        self.users = UserRepository(session)
        self.cache = cache

    def _hmac_secret(self) -> bytes:
        kek = self.provider.kek
        return hashlib.sha256(_HMAC_INFO + kek).digest()

    async def remaining(self) -> int:
        return await self.codes.count_unused()

    async def generate(self) -> list[str]:
        """作废全部旧码并生成新一批，返回仅展示一次的明文码。"""
        kek = self.provider.kek
        generated = generate_recovery_codes(kek, self._hmac_secret(), self.params, count=self.count)
        await self.codes.delete_all()
        for record in generated.records:
            await self.codes.add(
                RecoveryCode(
                    code_hash=record.code_hash,
                    salt=record.salt,
                    kek_encrypted=record.kek_wrapped,
                )
            )
        await self.session.commit()
        return generated.plaintext

    async def use(self, code: str, *, new_passphrase: str | None = None) -> list[str]:
        """使用恢复码：校验 → 重置口令（档 A）→ 全量轮换恢复码。"""
        target = code_hash(self._hmac_secret(), code)
        row = await self.codes.get_by_hash(target)
        if row is None or row.used_at is not None:
            raise WrongPassphrase("恢复码无效或已使用")

        record = RecoveryCodeRecord(
            code_hash=row.code_hash, salt=row.salt, kek_wrapped=row.kek_encrypted
        )
        recovered_kek = recover_kek(code, record, self.params)  # 认证失败会抛 CipherError

        if isinstance(self.provider, LocalKekProvider):
            if not new_passphrase:
                raise BadRequest("档 A 重置必须提供新主口令")
            await self._rewrap_to_new_passphrase(recovered_kek, new_passphrase)
        else:
            # 档 B/C：口令由环境/KMS 托管，仅验证并解锁
            self.provider.install_kek(recovered_kek)

        return await self.generate()

    async def _rewrap_to_new_passphrase(self, old_kek: bytes, new_passphrase: str) -> None:
        """用旧 KEK 解出全部 DEK，改用新口令派生的 KEK 重新包裹。"""
        # 1) 以旧 KEK 解出 DEK_key 与各用户的 DEK_conv
        self.provider.install_kek(old_kek)
        self.key_manager.reset()
        self.key_manager.ensure_loaded()
        generation, api_dek = self.key_manager.api_dek()

        conversation_keys: dict = {}
        for user in await self.users.list(limit=100_000):
            if user.conversation_key_encrypted:
                conversation_keys[user.id] = self.provider.unwrap(
                    user.conversation_key_encrypted, aad=CONV_DEK_AAD
                )

        # 2) 用新口令重新派生 KEK
        await self.provider.reinitialize(new_passphrase)

        # 3) 以新 KEK 重包裹
        self.key_manager.store_api_dek(api_dek, generation)
        for user_id, dek in conversation_keys.items():
            user = await self.users.get_by_id(user_id)
            if user is not None:
                user.conversation_key_encrypted = self.provider.wrap(
                    dek, key_gen=0, aad=CONV_DEK_AAD
                )
        await self.session.commit()
        if self.cache is not None:
            self.cache.clear()
