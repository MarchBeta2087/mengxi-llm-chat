"""FastAPI 应用入口（M1 骨架）。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.core.config import Settings, get_settings
from app.core.crypto.kek import KekProvider, build_kek_provider
from app.core.errors import MengxiError

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    from app.core.logging import setup_logging

    setup_logging(settings)

    try:
        kek_provider: KekProvider | None = build_kek_provider(settings)
    except ValueError as exc:
        # 例如档 B 未配置主密钥：允许应用启动以暴露明确错误，而非崩溃
        logger.error("主密钥提供者初始化失败: %s", exc)
        kek_provider = None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.kek_provider = kek_provider
        logger.info(
            "%s 启动 (env=%s, kek_profile=%s)",
            settings.app_name,
            settings.environment,
            settings.kek_profile,
        )
        yield
        logger.info("%s 关闭", settings.app_name)

    app = FastAPI(
        title="梦溪畅谈 API",
        version=__version__,
        description="可自部署的 LLM 聊天服务",
        lifespan=lifespan,
    )

    @app.exception_handler(MengxiError)
    async def _handle_mengxi_error(_request: Request, exc: MengxiError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_payload())

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/admin/kek", tags=["admin"])
    async def kek_status(request: Request) -> dict[str, object]:
        provider: KekProvider | None = request.app.state.kek_provider
        if provider is None:
            return {
                "code": 50001,
                "data": {
                    "profile": request.app.state.settings.kek_profile,
                    "state": "unconfigured",
                },
                "message": "主密钥提供者未就绪",
            }
        return {"code": 0, "data": provider.status(), "message": "ok"}

    return app


app = create_app()
