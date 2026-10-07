"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

import app.models  # noqa: F401  导入以注册 ORM 元数据
from app import __version__
from app.api import (
    admin_router,
    audit_router,
    auth_router,
    chat_router,
    conversations_router,
    keys_router,
    plugins_admin_router,
    plugins_router,
)
from app.core.config import Settings, get_settings
from app.core.crypto.kek import KekProvider, build_kek_provider
from app.core.errors import MengxiError
from app.core.logging import setup_logging
from app.core.ssrf import SsrfPolicy
from app.db.session import Database
from app.domain.ratelimit import RateLimitSpec
from app.infra.redis_store import RedisStore
from app.infra.sandbox import PluginSandbox
from app.services.conversation import ConversationKeyCache
from app.services.key_manager import KeyManager
from app.services.ratelimit import CircuitBreaker, RateLimiter
from app.services.scheduler import SchedulerService

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None, *, redis_store: RedisStore | None = None
) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings)

    try:
        kek_provider: KekProvider | None = build_kek_provider(settings)
    except ValueError as exc:
        # 例如档 B 未配置主密钥：允许启动以暴露明确的错误状态，而非直接崩溃
        logger.error("主密钥提供者初始化失败: %s", exc)
        kek_provider = None

    key_manager = KeyManager(kek_provider, settings.keys_dir) if kek_provider else None
    ssrf_policy = SsrfPolicy(
        allow_http=settings.allow_http_upstream,
        domain_whitelist=settings.domain_whitelist_set,
        max_redirects=settings.max_redirects,
    )
    database = Database(settings.database_url, echo=settings.debug)
    redis_store = redis_store or RedisStore(settings.redis_url)
    user_rate_spec = RateLimitSpec.from_json(settings.user_rate_limits)
    ip_rate_spec = RateLimitSpec.from_json(settings.ip_rate_limits)
    plugin_sandbox = PluginSandbox(ssrf_policy)
    conversation_cache = ConversationKeyCache()
    rate_limiter = RateLimiter(redis_store)
    circuit_breaker = CircuitBreaker(redis_store)
    scheduler = SchedulerService(rate_limiter, circuit_breaker)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.auto_create_tables:
            await database.create_all()

        app.state.settings = settings
        app.state.kek_provider = kek_provider
        app.state.key_manager = key_manager
        app.state.ssrf_policy = ssrf_policy
        app.state.db = database
        app.state.redis_store = redis_store
        app.state.rate_limiter = rate_limiter
        app.state.circuit_breaker = circuit_breaker
        app.state.scheduler = scheduler
        app.state.user_rate_spec = user_rate_spec
        app.state.ip_rate_spec = ip_rate_spec
        app.state.plugin_sandbox = plugin_sandbox
        app.state.conversation_cache = conversation_cache

        logger.info(
            "%s 启动 (env=%s, kek_profile=%s)",
            settings.app_name,
            settings.environment,
            settings.kek_profile,
        )
        yield
        await redis_store.close()
        await database.dispose()
        logger.info("%s 关闭", settings.app_name)

    app = FastAPI(
        title="梦溪畅谈 API",
        version=__version__,
        description="可自部署的 LLM 聊天服务",
        lifespan=lifespan,
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie=settings.session_cookie,
        max_age=settings.session_max_age,
        same_site="lax",
        https_only=settings.environment == "production",
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        """为所有响应补齐安全响应头（API 层纵深防御，SPA 静态资源由 Nginx 统一设置）。

        使用 setdefault，避免覆盖反向代理已注入的同名头。API 仅返回 JSON，
        因此对其施加最严格的 CSP；/docs 等开发页面不受影响。
        """
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if request.url.path.startswith("/api"):
            response.headers.setdefault(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
            )
        return response

    @app.exception_handler(MengxiError)
    async def _handle_mengxi_error(_request, exc: MengxiError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_payload())

    app.include_router(auth_router)
    app.include_router(keys_router)
    app.include_router(chat_router)
    app.include_router(conversations_router)
    app.include_router(audit_router)
    app.include_router(plugins_router)
    app.include_router(plugins_admin_router)
    app.include_router(admin_router)

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
