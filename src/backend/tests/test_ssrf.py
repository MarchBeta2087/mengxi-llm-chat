"""SSRF 防护测试（对应验收标准 §12.3）。"""

from __future__ import annotations

import pytest

from app.core.errors import SsrfRejected
from app.core.ssrf import (
    SsrfPolicy,
    ValidatedTarget,
    domain_allowed,
    host_header,
    is_forbidden_ip,
    pinned_url,
    validate_url,
)

FORBIDDEN = [
    "127.0.0.1",
    "10.0.0.1",
    "172.16.5.5",
    "192.168.1.1",
    "169.254.169.254",  # 云元数据
    "0.0.0.0",
    "224.0.0.1",
    "100.64.0.1",  # CGNAT
    "::1",
    "fe80::1",
    "fc00::1",
    "::ffff:10.0.0.1",  # IPv4-mapped
]

ALLOWED = ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111"]


@pytest.mark.parametrize("ip", FORBIDDEN)
def test_forbidden_ips(ip: str) -> None:
    assert is_forbidden_ip(ip) is True


@pytest.mark.parametrize("ip", ALLOWED)
def test_allowed_ips(ip: str) -> None:
    assert is_forbidden_ip(ip) is False


def test_domain_allowed_matches_subdomains() -> None:
    whitelist = ("example.com",)
    assert domain_allowed("example.com", whitelist)
    assert domain_allowed("a.b.example.com", whitelist)
    assert not domain_allowed("notexample.com", whitelist)
    assert not domain_allowed("example.com.evil.net", whitelist)


async def test_http_rejected_by_default() -> None:
    with pytest.raises(SsrfRejected):
        await validate_url("http://example.com/v1", SsrfPolicy())


async def test_http_allowed_when_enabled() -> None:
    async def resolver(host: str) -> list[str]:
        return ["93.184.216.34"]

    target = await validate_url(
        "http://example.com/v1", SsrfPolicy(allow_http=True), resolver=resolver
    )
    assert target.ip == "93.184.216.34"
    assert target.port == 80


async def test_metadata_ip_literal_rejected() -> None:
    with pytest.raises(SsrfRejected):
        await validate_url("https://169.254.169.254/latest/meta-data", SsrfPolicy())


async def test_dns_resolving_to_private_rejected() -> None:
    async def resolver(host: str) -> list[str]:
        return ["93.184.216.34", "10.0.0.5"]

    with pytest.raises(SsrfRejected):
        await validate_url("https://evil.example.com", SsrfPolicy(), resolver=resolver)


async def test_dns_rebinding_single_private_rejected() -> None:
    async def resolver(host: str) -> list[str]:
        return ["10.0.0.5"]

    with pytest.raises(SsrfRejected):
        await validate_url("https://rebind.example.com", SsrfPolicy(), resolver=resolver)


async def test_public_target_accepted() -> None:
    async def resolver(host: str) -> list[str]:
        return ["93.184.216.34"]

    target = await validate_url("https://api.example.com/v1/chat", SsrfPolicy(), resolver=resolver)
    assert target.host == "api.example.com"
    assert target.port == 443
    assert target.ip == "93.184.216.34"


async def test_whitelist_does_not_exempt_private() -> None:
    async def resolver(host: str) -> list[str]:
        return ["10.1.2.3"]

    policy = SsrfPolicy(domain_whitelist=("example.com",))
    with pytest.raises(SsrfRejected):
        await validate_url("https://internal.example.com", policy, resolver=resolver)


async def test_missing_host_rejected() -> None:
    with pytest.raises(SsrfRejected):
        await validate_url("https:///nohost", SsrfPolicy())


def test_pinned_url_and_host_header() -> None:
    target = ValidatedTarget(
        url="https://api.example.com:8443/v1/x?q=1",
        scheme="https",
        host="api.example.com",
        port=8443,
        ip="93.184.216.34",
    )
    assert pinned_url(target) == "https://93.184.216.34:8443/v1/x?q=1"
    assert host_header(target) == "api.example.com:8443"

    default_port = ValidatedTarget(
        url="https://api.example.com/v1",
        scheme="https",
        host="api.example.com",
        port=443,
        ip="93.184.216.34",
    )
    assert pinned_url(default_port) == "https://93.184.216.34/v1"
    assert host_header(default_port) == "api.example.com"
