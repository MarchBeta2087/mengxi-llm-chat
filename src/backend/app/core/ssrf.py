"""SSRF 防护（见设计说明书 §4.4）。

防护要点：
1. 协议白名单（默认仅 https，http 需管理员显式开启）；
2. 解析目标全部 A/AAAA 记录，任一命中禁止网段即拒绝（防 DNS 轮询/重绑定）；
3. IP 字面量直接判定；
4. 连接时固定到已校验 IP（``SafeHttpClient`` 手工处理重定向，逐跳复检）；
5. 可选域名白名单（不作为私网豁免）。
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from app.core.errors import SsrfRejected

_DEFAULT_PORTS = {"https": 443, "http": 80}

Resolver = Callable[[str], Awaitable[list[str]]]


@dataclass(frozen=True)
class SsrfPolicy:
    allow_http: bool = False
    domain_whitelist: tuple[str, ...] = ()
    max_redirects: int = 5


@dataclass(frozen=True)
class ValidatedTarget:
    url: str
    scheme: str
    host: str
    port: int
    ip: str


def is_forbidden_ip(value: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """禁止回环 / 私网 / 链路本地（含 169.254.169.254）/ 保留 / 组播等地址。"""
    ip = ipaddress.ip_address(value) if isinstance(value, str) else value

    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return is_forbidden_ip(ip.ipv4_mapped)
        if ip.sixtofour is not None:
            return is_forbidden_ip(ip.sixtofour)
        if ip.teredo is not None:
            return True

    # is_global 对公网单播返回 True；组播/保留等需显式判定（标准库 is_global 覆盖不全）
    return bool(
        not ip.is_global
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_private
    )


def domain_allowed(host: str, whitelist: tuple[str, ...]) -> bool:
    """白名单支持精确匹配与子域匹配（``example.com`` 匹配 ``a.example.com``）。"""
    h = host.rstrip(".").lower()
    for entry in whitelist:
        e = entry.rstrip(".").lower()
        if e and (h == e or h.endswith("." + e)):
            return True
    return False


async def resolve_host(host: str) -> list[str]:
    """解析主机名为去重后的 IP 列表（A + AAAA）。"""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    result: list[str] = []
    for family, _type, _proto, _canon, sockaddr in infos:
        if family in (socket.AF_INET, socket.AF_INET6):
            addr = sockaddr[0]
            if addr not in result:
                result.append(addr)
    return result


async def validate_url(
    url: str,
    policy: SsrfPolicy,
    *,
    resolver: Resolver = resolve_host,
) -> ValidatedTarget:
    """校验 URL 安全性并返回已固定的目标。"""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()

    if scheme not in ("https", "http"):
        raise SsrfRejected(f"不支持的协议: {scheme!r}")
    if scheme == "http" and not policy.allow_http:
        raise SsrfRejected("默认仅允许 https；http 需管理员显式开启")

    if not parts.hostname:
        raise SsrfRejected("URL 缺少主机名")

    host = parts.hostname
    try:
        port = parts.port or _DEFAULT_PORTS[scheme]
    except ValueError as exc:
        raise SsrfRejected("端口不合法") from exc

    # http 需命中白名单（管理员显式开启后仍要求白名单）
    if (
        scheme == "http"
        and policy.domain_whitelist
        and not domain_allowed(host, policy.domain_whitelist)
    ):
        raise SsrfRejected("http 目标不在域名白名单内")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        candidates = [str(literal)]
    else:
        try:
            candidates = await resolver(host)
        except OSError as exc:
            raise SsrfRejected(f"无法解析主机: {host}") from exc
        if not candidates:
            raise SsrfRejected(f"无法解析主机: {host}")

    forbidden = [c for c in candidates if is_forbidden_ip(c)]
    if forbidden:
        raise SsrfRejected(f"目标解析到禁止地址: {', '.join(forbidden)}")

    return ValidatedTarget(url=url, scheme=scheme, host=host, port=port, ip=candidates[0])


def pinned_url(target: ValidatedTarget) -> str:
    """把 URL 主机替换为已校验 IP，保留 path/query（配合 Host 头与 SNI）。"""
    parts = urlsplit(target.url)
    host = f"[{target.ip}]" if ":" in target.ip else target.ip
    default = _DEFAULT_PORTS[target.scheme]
    netloc = host if target.port == default else f"{host}:{target.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def host_header(target: ValidatedTarget) -> str:
    default = _DEFAULT_PORTS[target.scheme]
    return target.host if target.port == default else f"{target.host}:{target.port}"


class SafeHttpClient:
    """SSRF 安全的 HTTP 客户端：逐跳校验 + 固定 IP 连接。

    需要 ``httpx``。用法::

        async with SafeHttpClient(policy) as client:
            resp = await client.request("GET", url)
    """

    def __init__(
        self,
        policy: SsrfPolicy,
        *,
        timeout: float = 10.0,
        verify: bool = True,
        resolver: Resolver = resolve_host,
    ) -> None:
        self.policy = policy
        self.timeout = timeout
        self.verify = verify
        self.resolver = resolver
        self._client = None  # 延迟创建，避免无 httpx 环境下导入即失败

    async def __aenter__(self) -> SafeHttpClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_client(self):
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(
                follow_redirects=False,
                timeout=self.timeout,
                verify=self.verify,
                trust_env=False,  # 忽略环境代理，防止绕过校验
            )
        return self._client

    async def request(self, method: str, url: str, **kwargs) -> object:
        current_url = url
        current_method = method
        content = kwargs.pop("content", None)

        for hop in range(self.policy.max_redirects + 1):
            target = await validate_url(current_url, self.policy, resolver=self.resolver)
            headers = dict(kwargs.pop("headers", {}) or {})
            headers.setdefault("Host", host_header(target))
            extensions = dict(kwargs.pop("extensions", {}) or {})
            if target.scheme == "https":
                extensions.setdefault("sni_hostname", target.host)

            resp = await self._get_client().request(
                current_method,
                pinned_url(target),
                headers=headers,
                content=content,
                extensions=extensions,
                **kwargs,
            )

            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                if not location:
                    return resp
                if hop >= self.policy.max_redirects:
                    raise SsrfRejected("重定向次数超限")
                current_url = str(resp.request.url.join(location))
                if resp.status_code == 303 or (
                    resp.status_code in (301, 302) and current_method not in ("GET", "HEAD")
                ):
                    current_method = "GET"
                    content = None
                continue

            return resp

        raise SsrfRejected("重定向次数超限")

    @asynccontextmanager
    async def stream(self, method: str, url: str, **kwargs) -> AsyncIterator[object]:
        """流式请求（不跟随重定向，适合 SSE）；进入上下文前已完成 SSRF 校验。"""
        target = await validate_url(url, self.policy, resolver=self.resolver)
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Host", host_header(target))
        extensions = dict(kwargs.pop("extensions", {}) or {})
        if target.scheme == "https":
            extensions.setdefault("sni_hostname", target.host)

        async with self._get_client().stream(
            method,
            pinned_url(target),
            headers=headers,
            extensions=extensions,
            **kwargs,
        ) as response:
            yield response
