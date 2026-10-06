"""插件服务：安装、生效状态解析、启停、用户组配置与沙箱调用（见设计说明书 §6）。"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import BadRequest, Forbidden, NotFound, PluginExecutionError
from app.domain.plugins import (
    PluginState,
    PluginStatus,
    StateSource,
    parse_permissions,
    resolve_state,
    wrap_untrusted,
)
from app.infra.sandbox import PluginResult, PluginSandbox
from app.models.plugin import Plugin
from app.models.user import User
from app.repositories import (
    GroupPluginRepository,
    GroupRepository,
    PluginRepository,
    UserPluginRepository,
)
from app.schemas.plugins import PluginInstall, PluginManifest, PluginRead


@dataclass
class ResolvedPlugin:
    plugin: Plugin
    enabled: bool
    source: StateSource


class PluginService:
    def __init__(self, session: AsyncSession, settings: Settings, sandbox: PluginSandbox) -> None:
        self.session = session
        self.settings = settings
        self.sandbox = sandbox
        self.plugins = PluginRepository(session)
        self.user_plugins = UserPluginRepository(session)
        self.group_plugins = GroupPluginRepository(session)
        self.groups = GroupRepository(session)

    # --- 安装 ---
    def _package_dir(self, name: str) -> Path:
        return (self.settings.plugins_path / name).resolve()

    async def install(self, payload: PluginInstall) -> Plugin:
        manifest: PluginManifest = payload.manifest
        package_dir = self._package_dir(manifest.name)
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "manifest.json").write_text(
            json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (package_dir / manifest.entry).write_text(payload.code, encoding="utf-8")

        plugin = await self.plugins.get_by_name(manifest.name)
        fields = {
            "version": manifest.version,
            "description": manifest.description,
            "type": manifest.type,
            "default_state": manifest.default_state,
            "status": PluginStatus.ACTIVE.value,
            "manifest_json": manifest.model_dump(),
            "permissions_json": list(manifest.permissions),
            "runtime_json": manifest.runtime.model_dump(),
            "package_dir": str(package_dir),
        }
        if plugin is None:
            plugin = Plugin(name=manifest.name, **fields)
            await self.plugins.add(plugin)
        else:
            for key, value in fields.items():
                setattr(plugin, key, value)
        await self.session.commit()
        return plugin

    async def install_from_directory(self, source_dir: Path) -> Plugin:
        manifest_path = source_dir / "manifest.json"
        if not manifest_path.exists():
            raise BadRequest(f"缺少 manifest.json: {source_dir}")
        manifest = PluginManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        entry = source_dir / manifest.entry
        if not entry.exists():
            raise BadRequest(f"缺少入口文件: {entry}")
        return await self.install(
            PluginInstall(manifest=manifest, code=entry.read_text(encoding="utf-8"))
        )

    # --- 内置插件市场 ---
    def list_builtin(self) -> list[dict]:
        base = self.settings.builtin_plugins_path
        if base is None or not base.exists():
            return []
        items: list[dict] = []
        for manifest_path in sorted(base.glob("*/manifest.json")):
            try:
                manifest = PluginManifest.model_validate_json(
                    manifest_path.read_text(encoding="utf-8")
                )
            except Exception:  # noqa: BLE001 - 跳过非法清单
                continue
            items.append(manifest.model_dump())
        return items

    async def install_builtin(self, name: str) -> Plugin:
        base = self.settings.builtin_plugins_path
        if base is None:
            raise BadRequest("未配置内置插件目录")
        source = base / name
        if not source.is_dir():
            raise NotFound(f"内置插件不存在: {name}")
        return await self.install_from_directory(source)

    # --- 查询与解析 ---
    async def get(self, plugin_id: uuid.UUID) -> Plugin:
        plugin = await self.plugins.get(plugin_id)
        if plugin is None:
            raise NotFound("插件不存在")
        return plugin

    async def resolve_for_user(self, user: User) -> list[ResolvedPlugin]:
        plugins = await self.plugins.list(status=PluginStatus.ACTIVE.value)
        user_map = await self.user_plugins.map_for_user(user.id)
        group_map = (
            await self.group_plugins.map_for_group(user.group_id)
            if user.group_id is not None
            else {}
        )
        resolved: list[ResolvedPlugin] = []
        for plugin in plugins:
            group_state = group_map.get(plugin.id)
            user_state: str | None = None
            if plugin.id in user_map:
                user_state = (
                    PluginState.ENABLED.value if user_map[plugin.id] else PluginState.DISABLED.value
                )
            enabled, source = resolve_state(
                plugin_type=plugin.type,
                default_state=plugin.default_state,
                group_state=group_state,
                user_state=user_state,
            )
            resolved.append(ResolvedPlugin(plugin=plugin, enabled=enabled, source=source))
        return resolved

    @staticmethod
    def to_read(resolved: ResolvedPlugin) -> PluginRead:
        plugin = resolved.plugin
        return PluginRead(
            id=plugin.id,
            name=plugin.name,
            version=plugin.version,
            description=plugin.description,
            type=plugin.type,
            default_state=plugin.default_state,
            status=plugin.status,
            permissions=list(plugin.permissions_json or []),
            runtime=dict(plugin.runtime_json or {}),
            enabled=resolved.enabled,
            state_source=resolved.source.value,
        )

    # --- 用户启停 ---
    async def toggle(self, user: User, plugin_id: uuid.UUID, enabled: bool) -> None:
        plugin = await self.get(plugin_id)
        if plugin.is_global:
            raise Forbidden("全局插件强制生效，不可禁用")
        await self.user_plugins.set(user.id, plugin_id, enabled)
        await self.session.commit()

    # --- 用户组配置 ---
    async def set_group_state(self, group_id: uuid.UUID, plugin_id: uuid.UUID, state: str) -> None:
        if await self.groups.get(group_id) is None:
            raise NotFound("用户组不存在")
        await self.get(plugin_id)
        await self.group_plugins.set(group_id, plugin_id, state)
        await self.session.commit()

    async def clear_group_state(self, group_id: uuid.UUID, plugin_id: uuid.UUID) -> None:
        await self.group_plugins.delete(group_id, plugin_id)
        await self.session.commit()

    async def group_config(self, group_id: uuid.UUID) -> list[dict]:
        if await self.groups.get(group_id) is None:
            raise NotFound("用户组不存在")
        mapping = await self.group_plugins.map_for_group(group_id)
        plugins = await self.plugins.list()
        return [
            {
                "plugin_id": str(plugin.id),
                "name": plugin.name,
                "type": plugin.type,
                "state": mapping.get(plugin.id),
            }
            for plugin in plugins
        ]

    # --- 调用沙箱 ---
    async def invoke(
        self, plugin: Plugin, *, input: dict, config: dict | None = None
    ) -> PluginResult:
        manifest = PluginManifest.model_validate(plugin.manifest_json)
        entry_path = (Path(plugin.package_dir) / manifest.entry).resolve()
        if not entry_path.exists():
            raise PluginExecutionError(f"插件入口不存在: {entry_path}")
        permissions = parse_permissions(list(plugin.permissions_json or []))
        runtime = manifest.runtime
        return await self.sandbox.run(
            name=plugin.name,
            entry_path=entry_path,
            permissions=permissions,
            timeout_ms=runtime.timeout_ms,
            memory_mb=runtime.memory_mb,
            cpu_seconds=runtime.cpu_seconds,
            input=input,
            config=config or {},
        )

    async def invoke_wrapped(
        self, plugin: Plugin, *, input: dict, config: dict | None = None
    ) -> tuple[str, PluginResult]:
        """调用并返回「不可信边界包装后」的输出，供安全注入对话。"""
        result = await self.invoke(plugin, input=input, config=config)
        return wrap_untrusted(plugin.name, result.output), result
