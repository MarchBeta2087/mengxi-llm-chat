"""文档截图专用后端：SQLite + 内存 Redis + 确定性假上游。

该脚本**仅用于生成文档/README 截图**，与生产运行方式无关：

- 存储使用单文件 SQLite（``_shots.db``）与本地数据目录（``_shotsdata/``），
  无需 PostgreSQL / Redis；
- 上游 LLM 被替换为确定性假实现，回复内容固定，便于稳定复现截图；
- 自动播种演示数据（``newuser`` / ``admin``，口令均为 ``12345678``）；
- 可选挂载已构建的前端 ``dist/``，以同源方式提供 SPA（免去单独的前端服务）。

用法::

    # 1) 先构建前端（若尚未构建）
    cd src/frontend && pnpm build

    # 2) 启动截图后端（默认 127.0.0.1:8800）
    python src/backend/scripts/shots_backend.py --reset

通常无需手动调用：``pnpm screenshots`` 会自动完成构建、启动、截图与清理。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from sqlalchemy import delete  # noqa: E402

import app.services.chat as chat_module  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.crypto.kek import build_kek_provider  # noqa: E402
from app.core.security import hash_password, mask_key  # noqa: E402
from app.db.session import Database  # noqa: E402
from app.infra.redis_store import RedisStore  # noqa: E402
from app.infra.upstream import UpstreamChunk  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.api_key import ApiKey  # noqa: E402
from app.models.conversation import Conversation, Message, MessageKeyword  # noqa: E402
from app.models.enums import KeyPool, KeyStatus  # noqa: E402
from app.models.plugin import GroupPlugin, Plugin, UserPlugin  # noqa: E402
from app.models.recovery import AuditLog, RecoveryCode  # noqa: E402
from app.models.user import User, UserGroup  # noqa: E402
from app.services.conversation import ConversationKeyCache, ConversationService  # noqa: E402
from app.services.key_manager import KeyManager  # noqa: E402

REPO_ROOT = BACKEND_DIR.parents[1]
BUILTIN_PLUGINS_DIR = REPO_ROOT / "src" / "plugins"
DEFAULT_DIST = REPO_ROOT / "src" / "frontend" / "dist"

DEMO_USERNAME = "newuser"
DEMO_ADMIN = "admin"
DEMO_PASSWORD = "12345678"

# 档 B 主密钥固定为常量的 SHA-256，保证多次运行可解密同一份 SQLite 数据。
_MASTER_SEED = b"mengxi-llm-chat-screenshots-v1"


def demo_master_key() -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(_MASTER_SEED).digest()).decode()


# --------------------------------------------------------------------------- #
# 假上游：返回固定、体面的回复，避免调用真实 LLM
# --------------------------------------------------------------------------- #

_DEMO_REPLY = (
    "这是一个用于文档截图的演示回复。「梦溪畅谈」取自沈括《梦溪笔谈》，"
    "以加密存储承载对话隐私，以公私双轨调度汇聚多样的模型能力。"
    "你的消息在本机以 AES-256-GCM 加密落库，只有持有密钥的你才能解开。"
)


class DemoUpstream:
    """确定性流式上游：按固定文本分片产出，附带 usage。"""

    def __init__(self, policy, *, timeout: float = 120.0) -> None:  # noqa: ARG002
        self.policy = policy
        self.timeout = timeout

    async def stream_chat(self, *, base_url: str, api_key: str, payload: dict):  # noqa: ARG002
        text = _DEMO_REPLY
        for index in range(0, len(text), 4):
            await asyncio.sleep(0.02)
            yield UpstreamChunk(text=text[index : index + 4])
        await asyncio.sleep(0.05)
        yield UpstreamChunk(usage={"prompt_tokens": 42, "completion_tokens": 118})


# --------------------------------------------------------------------------- #
# 播种数据
# --------------------------------------------------------------------------- #


async def _seed(settings: Settings) -> None:
    provider = build_kek_provider(settings)
    key_manager = KeyManager(provider, settings.keys_dir)
    database = Database(settings.database_url)
    await database.create_all()

    async with database.session() as session:
        # 清空旧数据，保证每次运行可复现（SQLite 主键/外键顺序无关紧要）
        for model in (
            MessageKeyword,
            Message,
            Conversation,
            AuditLog,
            RecoveryCode,
            UserPlugin,
            GroupPlugin,
            Plugin,
            ApiKey,
            User,
            UserGroup,
        ):
            await session.execute(delete(model))
        await session.commit()

        group = UserGroup(
            id=uuid.uuid4(), name="研发组", daily_quota_tokens=1_000_000, settings_json={}
        )
        newuser = User(
            id=uuid.uuid4(),
            username=DEMO_USERNAME,
            password_hash=hash_password(DEMO_PASSWORD),
            role="user",
            status="active",
            daily_quota_tokens=0,
            group_id=group.id,
        )
        admin = User(
            id=uuid.uuid4(),
            username=DEMO_ADMIN,
            password_hash=hash_password(DEMO_PASSWORD),
            role="admin",
            status="active",
            daily_quota_tokens=0,
        )
        session.add_all([group, newuser, admin])
        await session.flush()

        # --- API Key：一条公有 + 两条私有 ---
        public_id = uuid.uuid4()
        public_secret = "sk-demo-public-0000abcd"
        private_id = uuid.uuid4()
        private_secret = "sk-demo-private-deepseek-0000"
        admin_private_id = uuid.uuid4()
        admin_private_secret = "sk-demo-private-admin-0000"
        zero_limits = {"rpm": 0, "rph": 0, "rpd": 0, "tpm": 0, "tph": 0, "tpd": 0}
        session.add_all(
            [
                ApiKey(
                    id=public_id,
                    user_id=None,
                    provider_name="官方主通道",
                    base_url="https://api.openai.com/v1",
                    models_json=["gpt-4o", "gpt-4o-mini"],
                    encrypted_key=key_manager.encrypt_secret(
                        public_secret, aad=f"api-key:{public_id}".encode()
                    ),
                    key_fingerprint=mask_key(public_secret),
                    rate_limits_json=dict(zero_limits),
                    priority_pool=KeyPool.PUBLIC.value,
                    status=KeyStatus.ACTIVE.value,
                ),
                ApiKey(
                    id=private_id,
                    user_id=newuser.id,
                    provider_name="我的 DeepSeek",
                    base_url="https://api.deepseek.com",
                    models_json=["deepseek-chat", "deepseek-reasoner"],
                    encrypted_key=key_manager.encrypt_secret(
                        private_secret, aad=f"api-key:{private_id}".encode()
                    ),
                    key_fingerprint=mask_key(private_secret),
                    rate_limits_json=dict(zero_limits),
                    priority_pool=KeyPool.PRIVATE.value,
                    status=KeyStatus.ACTIVE.value,
                ),
                ApiKey(
                    id=admin_private_id,
                    user_id=admin.id,
                    provider_name="管理员的通道",
                    base_url="https://api.moonshot.cn/v1",
                    models_json=["moonshot-v1-8k"],
                    encrypted_key=key_manager.encrypt_secret(
                        admin_private_secret, aad=f"api-key:{admin_private_id}".encode()
                    ),
                    key_fingerprint=mask_key(admin_private_secret),
                    rate_limits_json=dict(zero_limits),
                    priority_pool=KeyPool.PRIVATE.value,
                    status=KeyStatus.ACTIVE.value,
                ),
            ]
        )

        # --- 内置插件（市场可见）---
        session.add(
            Plugin(
                id=uuid.uuid4(),
                name="echo",
                version="1.0.0",
                description="回显输入文本，用于验证沙箱与协议",
                type="optional",
                default_state="disabled",
                status="active",
                manifest_json={
                    "name": "echo",
                    "version": "1.0.0",
                    "description": "回显输入文本，用于验证沙箱与协议",
                    "type": "optional",
                    "entry": "main.py",
                    "permissions": [],
                    "default_state": "disabled",
                    "runtime": {"timeout_ms": 5000, "memory_mb": 64, "cpu_seconds": 2},
                },
                permissions_json=[],
                runtime_json={"timeout_ms": 5000, "memory_mb": 64, "cpu_seconds": 2},
                package_dir=str(BUILTIN_PLUGINS_DIR / "echo"),
            )
        )

        # --- 审计日志 ---
        samples = [
            {
                "model": "gpt-4o",
                "host": "api.openai.com",
                "kind": "private",
                "tin": 120,
                "tout": 340,
                "latency": 820,
                "status": 200,
                "fallback": False,
                "ip": "203.0.113.10",
            },
            {
                "model": "deepseek-chat",
                "host": "api.deepseek.com",
                "kind": "private",
                "tin": 80,
                "tout": 0,
                "latency": 300,
                "status": 502,
                "fallback": False,
                "ip": "203.0.113.10",
            },
            {
                "model": "deepseek-chat",
                "host": "api.deepseek.com",
                "kind": "private",
                "tin": 60,
                "tout": 150,
                "latency": 540,
                "status": 200,
                "fallback": True,
                "ip": "203.0.113.11",
            },
            {
                "model": "gpt-4o-mini",
                "host": "api.openai.com",
                "kind": "public",
                "tin": 42,
                "tout": 118,
                "latency": 610,
                "status": 200,
                "fallback": False,
                "ip": "203.0.113.11",
            },
            {
                "model": "moonshot-v1-8k",
                "host": "api.moonshot.cn",
                "kind": "private",
                "tin": 33,
                "tout": 0,
                "latency": 210,
                "status": 429,
                "fallback": False,
                "ip": "203.0.113.12",
            },
            {
                "model": "gpt-4o",
                "host": "api.openai.com",
                "kind": "public",
                "tin": 210,
                "tout": 640,
                "latency": 1330,
                "status": 200,
                "fallback": False,
                "ip": "203.0.113.12",
            },
        ]
        for i, row in enumerate(samples):
            session.add(
                AuditLog(
                    user_id=newuser.id if i % 2 == 0 else admin.id,
                    key_id=public_id if row["kind"] == "public" else private_id,
                    key_type=row["kind"],
                    model=row["model"],
                    base_url_host=row["host"],
                    tokens_in=row["tin"],
                    tokens_out=row["tout"],
                    latency_ms=row["latency"],
                    status=row["status"],
                    fallback_to_public=row["fallback"],
                    client_ip=row["ip"],
                )
            )
        await session.commit()

        # --- 加密会话与消息（经服务写入，确保密文与盲索引一致）---
        cache = ConversationKeyCache()
        service = ConversationService(session, key_manager, cache, search_enabled=True)
        conversations = [
            (
                "宋词里的科学意象",
                [
                    ("user", "梦溪，宋词里有哪些被今人忽略的科学意象？"),
                    (
                        "assistant",
                        "沈括在《梦溪笔谈》中已注意到「虹」的成因，苏轼亦写「不知天上宫阙」。"
                        "宋人观物入微：辛弃疾的「明月别枝惊鹊」暗含物候，"
                        "李清照的「风住尘香花已尽」记录物候与花期的关系。",
                    ),
                    ("user", "那「物候」和现代气象学怎么对应？"),
                    (
                        "assistant",
                        "物候是生物随季节变化的周期性现象，与现代积温、日照时长的记录一脉相承。"
                        "把诗词中的物候线索与现代气象数据对照，可以复原古代气候的冷暖波动。",
                    ),
                ],
            ),
            (
                "FastAPI 流式响应设计",
                [
                    ("user", "用 FastAPI 实现 SSE 流式输出，要注意哪些点？"),
                    (
                        "assistant",
                        "要点有四：其一，返回 StreamingResponse 并设置 text/event-stream；"
                        "其二，按「event: / data:」成对写出并空行分隔；"
                        "其三，禁用中间层缓冲（X-Accel-Buffering: no）；"
                        "其四，用生成器边算边发，并对异常降级为 error 事件。",
                    ),
                    ("user", "客户端断开会怎样？"),
                    (
                        "assistant",
                        "Starlette 会在断连时取消任务，生成器抛出的 CancelledError 应让它自然传播，"
                        "同时在 finally 中释放上游连接，避免连接池泄漏。",
                    ),
                ],
            ),
            (
                "周末杭州两日游",
                [
                    ("user", "帮我排一个不赶路的杭州两日行程。"),
                    (
                        "assistant",
                        "第一天从北山街散步到曲院风荷，午后在孤山看西泠印社，傍晚沿湖至断桥。"
                        "第二天去龙井村喝茶，再走九溪十八涧，避开正午的人流。",
                    ),
                ],
            ),
        ]
        for title, rows in conversations:
            conversation = Conversation(
                id=uuid.uuid4(), user_id=newuser.id, title=title, encrypted=True
            )
            await service.conversation_repo.add(conversation)
            await session.commit()
            for role, content in rows:
                await service.append_message(newuser, conversation, role, content)

    await database.dispose()


# --------------------------------------------------------------------------- #
# 应用装配与静态前端
# --------------------------------------------------------------------------- #


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    if not index.exists():
        return

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:  # noqa: ANN202
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)


def build_settings(args: argparse.Namespace) -> Settings:
    db_path = Path(args.db).resolve()
    data_dir = Path(args.data_dir).resolve()
    return Settings(
        environment="development",
        kek_profile="B",
        master_key_b64=demo_master_key(),
        database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        data_dir=data_dir,
        auto_create_tables=True,
        encrypted_search=True,
        session_secret="screenshots-demo-secret",
        builtin_plugins_dir=str(BUILTIN_PLUGINS_DIR),
        fallback_to_public=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="文档截图专用后端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--db", default=str(BACKEND_DIR / "_shots.db"))
    parser.add_argument("--data-dir", default=str(BACKEND_DIR / "_shotsdata"))
    parser.add_argument("--dist", default=str(DEFAULT_DIST), help="前端构建产物目录")
    parser.add_argument("--reset", action="store_true", help="重置数据库与密钥材料后重新播种")
    args = parser.parse_args()

    if args.reset:
        db_path = Path(args.db)
        if db_path.exists():
            db_path.unlink()
        data_dir = Path(args.data_dir)
        if data_dir.exists():
            import shutil

            shutil.rmtree(data_dir, ignore_errors=True)

    settings = build_settings(args)
    asyncio.run(_seed(settings))

    # 用确定性假上游替换真实客户端（ChatService 在实例化时读取该模块全局）
    chat_module.UpstreamClient = DemoUpstream  # type: ignore[assignment]

    from fakeredis.aioredis import FakeRedis

    store = RedisStore("redis://screenshots", client=FakeRedis(decode_responses=True))
    app = create_app(settings, redis_store=store)
    _mount_frontend(app, Path(args.dist).resolve())

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
