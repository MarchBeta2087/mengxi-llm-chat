"""插件路由：用户端启停 + 管理端安装/配置/调用（见设计说明书 §9.4）。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_plugin_sandbox,
    get_session,
    get_settings_dep,
    require_admin,
)
from app.core.config import Settings
from app.infra.sandbox import PluginSandbox
from app.models.user import User
from app.repositories import PluginRepository
from app.schemas.plugins import (
    BuiltinInstall,
    GroupPluginSet,
    PluginInstall,
    PluginInvoke,
    PluginToggle,
    PluginUpdate,
)
from app.services.plugins import PluginService

router = APIRouter(prefix="/api/plugins", tags=["plugins"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


def _ok(data, message: str = "ok") -> dict:
    return {"code": 0, "data": data, "message": message}


def _admin_read(plugin) -> dict:  # noqa: ANN001
    return {
        "id": str(plugin.id),
        "name": plugin.name,
        "version": plugin.version,
        "description": plugin.description,
        "type": plugin.type,
        "default_state": plugin.default_state,
        "status": plugin.status,
        "permissions": list(plugin.permissions_json or []),
        "runtime": dict(plugin.runtime_json or {}),
    }


# --- 用户端 ---
@router.get("")
async def list_my_plugins(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    sandbox: PluginSandbox = Depends(get_plugin_sandbox),
) -> dict:
    service = PluginService(session, settings, sandbox)
    resolved = await service.resolve_for_user(user)
    data = [service.to_read(item).model_dump(mode="json") for item in resolved]
    return _ok(data)


@router.post("/{plugin_id}/toggle")
async def toggle_plugin(
    plugin_id: uuid.UUID,
    body: PluginToggle,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    sandbox: PluginSandbox = Depends(get_plugin_sandbox),
) -> dict:
    service = PluginService(session, settings, sandbox)
    await service.toggle(user, plugin_id, body.enabled)
    resolved = await service.resolve_for_user(user)
    data = [service.to_read(item).model_dump(mode="json") for item in resolved]
    return _ok(data)


# --- 管理端：插件 ---
@admin_router.get("/plugins")
async def admin_list_plugins(
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    plugins = await PluginRepository(session).list()
    return _ok([_admin_read(plugin) for plugin in plugins])


@admin_router.get("/plugins/available")
async def admin_available_plugins(
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    sandbox: PluginSandbox = Depends(get_plugin_sandbox),
) -> dict:
    """内置插件市场：列出可安装的内置插件清单。"""
    return _ok(PluginService(session, settings, sandbox).list_builtin())


@admin_router.post("/plugins/install-builtin", status_code=201)
async def admin_install_builtin(
    body: BuiltinInstall,
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    sandbox: PluginSandbox = Depends(get_plugin_sandbox),
) -> dict:
    plugin = await PluginService(session, settings, sandbox).install_builtin(body.name)
    return _ok(_admin_read(plugin))


@admin_router.post("/plugins", status_code=201)
async def install_plugin(
    body: PluginInstall,
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    sandbox: PluginSandbox = Depends(get_plugin_sandbox),
) -> dict:
    plugin = await PluginService(session, settings, sandbox).install(body)
    return _ok(_admin_read(plugin))


@admin_router.patch("/plugins/{plugin_id}")
async def update_plugin(
    plugin_id: uuid.UUID,
    body: PluginUpdate,
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    sandbox: PluginSandbox = Depends(get_plugin_sandbox),
) -> dict:
    service = PluginService(session, settings, sandbox)
    plugin = await service.get(plugin_id)
    if body.type is not None:
        plugin.type = body.type
    if body.default_state is not None:
        plugin.default_state = body.default_state
    if body.status is not None:
        plugin.status = body.status
    await session.commit()
    return _ok(_admin_read(plugin))


@admin_router.post("/plugins/{plugin_id}/invoke")
async def invoke_plugin(
    plugin_id: uuid.UUID,
    body: PluginInvoke,
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    sandbox: PluginSandbox = Depends(get_plugin_sandbox),
) -> dict:
    service = PluginService(session, settings, sandbox)
    plugin = await service.get(plugin_id)
    result = await service.invoke(plugin, input=body.input, config=body.config)
    return _ok({"output": result.output, "logs": result.logs})


# --- 管理端：用户组插件配置 ---
@admin_router.get("/groups/{group_id}/plugins")
async def group_plugins(
    group_id: uuid.UUID,
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    sandbox: PluginSandbox = Depends(get_plugin_sandbox),
) -> dict:
    return _ok(await PluginService(session, settings, sandbox).group_config(group_id))


@admin_router.put("/groups/{group_id}/plugins/{plugin_id}")
async def set_group_plugin(
    group_id: uuid.UUID,
    plugin_id: uuid.UUID,
    body: GroupPluginSet,
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    sandbox: PluginSandbox = Depends(get_plugin_sandbox),
) -> dict:
    service = PluginService(session, settings, sandbox)
    await service.set_group_state(group_id, plugin_id, body.state)
    return _ok(await service.group_config(group_id))


@admin_router.delete("/groups/{group_id}/plugins/{plugin_id}")
async def clear_group_plugin(
    group_id: uuid.UUID,
    plugin_id: uuid.UUID,
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    sandbox: PluginSandbox = Depends(get_plugin_sandbox),
) -> dict:
    service = PluginService(session, settings, sandbox)
    await service.clear_group_state(group_id, plugin_id)
    return _ok(await service.group_config(group_id))
