"""插件领域规则（纯逻辑，见设计说明书 §6）。

- 生效状态优先级：全局 > 用户组 > 个人 > 默认
- 权限声明解析与校验
- 不可信输出边界包装（防提示词注入）
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatchcase
from urllib.parse import urlsplit

UNTRUSTED_OPEN = '<<<UNTRUSTED_PLUGIN_OUTPUT name="{name}">>>'
UNTRUSTED_CLOSE = "<<<END_UNTRUSTED_PLUGIN_OUTPUT>>>"


class PluginType(StrEnum):
    GLOBAL = "global"
    OPTIONAL = "optional"


class PluginState(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class PluginStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class StateSource(StrEnum):
    GLOBAL = "global"
    GROUP = "group"
    USER = "user"
    DEFAULT = "default"


def resolve_state(
    *,
    plugin_type: str,
    default_state: str,
    group_state: str | None = None,
    user_state: str | None = None,
) -> tuple[bool, StateSource]:
    """解析单个用户对某插件的最终生效状态。"""
    if plugin_type == PluginType.GLOBAL.value:
        return True, StateSource.GLOBAL
    if group_state is not None:
        return group_state == PluginState.ENABLED.value, StateSource.GROUP
    if user_state is not None:
        return user_state == PluginState.ENABLED.value, StateSource.USER
    return default_state == PluginState.ENABLED.value, StateSource.DEFAULT


def wrap_untrusted(name: str, content: str, *, max_chars: int = 20_000) -> str:
    """将插件返回值标记为不可信内容，供安全注入对话。"""
    trimmed = content if len(content) <= max_chars else content[:max_chars] + "\n…[内容已截断]"
    header = UNTRUSTED_OPEN.format(name=name)
    return f"{header}\n{trimmed}\n{UNTRUSTED_CLOSE}"


@dataclass(frozen=True)
class Permission:
    """形如 ``资源:动作[:约束]``，例如 ``http:outbound:search.*``。"""

    resource: str
    action: str
    scope: str | None = None

    @property
    def raw(self) -> str:
        return f"{self.resource}:{self.action}" + (f":{self.scope}" if self.scope else "")


def parse_permission(text: str) -> Permission:
    parts = text.split(":", 2)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(f"非法权限声明: {text!r}")
    scope = parts[2] if len(parts) == 3 and parts[2] else None
    return Permission(parts[0].strip(), parts[1].strip(), scope)


def parse_permissions(items: list[str]) -> list[Permission]:
    return [parse_permission(item) for item in items]


def _host_of(url: str) -> str | None:
    host = urlsplit(url).hostname
    return host.lower() if host else None


def allows_http(permissions: list[Permission], url: str, *, method: str = "GET") -> bool:
    """判断权限集合是否允许对目标 URL 发起出站请求。"""
    host = _host_of(url)
    if host is None:
        return False
    for permission in permissions:
        if permission.resource != "http" or permission.action != "outbound":
            continue
        if permission.scope is None or fnmatchcase(host, permission.scope):
            return True
    return False


def has_permission(permissions: list[Permission], resource: str, action: str) -> bool:
    return any(p.resource == resource and p.action == action for p in permissions)
