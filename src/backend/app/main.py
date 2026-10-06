"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

import app.models  # noqa: F401  导入以注册 ORM 元数据
from app import __version__
from app.api import admin_router, auth_router, keys_router
from app.core.config import Settings, get_settings
from app.core.crypto.kek import KekProvider, build_kek_provider
from app.core.errors import MengxiError
from app.core.logging import setup_logging
from app.core.ssrf import SsrfPolicy
from app.db.session import Database
from app.services.key_manager import KeyManager

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
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

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.auto_create_tables:
            await database.create_all()

        app.state.settings = settings
        app.state.kek_provider = kek_provider
        app.state.key_manager = key_manager
        app.state.ssrf_policy = ssrf_policy
        app.state.db = database

        logger.info(
            "%s 启动 (env=%s, kek_profile=%s)",
            settings.app_name,
            settings.environment,
            settings.kek_profile,
        )
        yield
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

    @app.exception_handler(MengxiError)
    async def _handle_mengxi_error(_request, exc: MengxiError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_payload())

    app.include_router(auth_router)
    app.include_router(keys_router)
    app.include_router(admin_router)

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
