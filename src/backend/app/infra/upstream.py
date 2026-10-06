"""上游 LLM 流式客户端：SSE 解析 + SSRF 安全连接（见设计说明书 §7.1）。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.core.errors import UpstreamError
from app.core.ssrf import SafeHttpClient, SsrfPolicy


@dataclass
class UpstreamChunk:
    text: str | None = None
    usage: dict | None = None
    raw: dict | None = None


def parse_sse_data(line: str) -> dict | None:
    """解析单行 SSE 的 data 字段；注释行、非 data 行、[DONE] 返回 None。"""
    stripped = line.strip()
    if not stripped or stripped.startswith(":") or not stripped.startswith("data:"):
        return None
    payload = stripped[len("data:") :].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def chunk_from_openai(data: dict) -> UpstreamChunk:
    """OpenAI 兼容响应块 → 统一 UpstreamChunk。"""
    choices = data.get("choices") or []
    text: str | None = None
    if choices and isinstance(choices[0], dict):
        delta = choices[0].get("delta") or {}
        content = delta.get("content")
        if isinstance(content, str):
            text = content
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
    return UpstreamChunk(text=text, usage=usage, raw=data)


class UpstreamClient:
    def __init__(self, policy: SsrfPolicy, *, timeout: float = 120.0) -> None:
        self.policy = policy
        self.timeout = timeout

    async def stream_chat(
        self, *, base_url: str, api_key: str, payload: dict
    ) -> AsyncIterator[UpstreamChunk]:
        url = base_url.rstrip("/") + "/chat/completions"
        async with SafeHttpClient(self.policy, timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "text/event-stream",
                },
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise UpstreamError(
                        f"上游返回 {response.status_code}",
                        status=response.status_code,
                        body=body[:500].decode(errors="replace"),
                    )
                async for line in response.aiter_lines():
                    data = parse_sse_data(line)
                    if data is None:
                        continue
                    yield chunk_from_openai(data)
