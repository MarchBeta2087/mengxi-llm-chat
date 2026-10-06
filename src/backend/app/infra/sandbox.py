"""插件沙箱宿主（见设计说明书 §6.3）。

隔离手段：
- 每次调用 fork 独立子进程，stdin/stdout 走 JSON Lines 协议，无共享内存；
- 超时强制 kill（跨平台）；
- POSIX 下用 ``resource.setrlimit`` 限制 CPU 与内存（Windows 无此机制，退化为仅超时）；
- 环境变量白名单，剔除任何 ``MENGXI_*`` 与疑似密钥；
- 出站网络由宿主代理（插件发送 ``http`` 请求，宿主按声明的权限与 SSRF 规则代发），
  插件自身不应直接访问网络；OS 级网络隔离由部署层负责。

协议（均为单行 JSON）::

  宿主 → 插件: {"type":"run","input":{...},"config":{...}}
  插件 → 宿主: {"type":"log","message":"..."}
             {"type":"http","id":1,"method":"GET","url":"...","headers":{},"body":null}
  宿主 → 插件: {"type":"http_result","id":1,"status":200,"body":"..."}
  插件 → 宿主: {"type":"result","output":"..."}  或  {"type":"error","message":"..."}
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.core.errors import PluginExecutionError, PluginPermissionDenied, PluginTimeout
from app.core.ssrf import SafeHttpClient, SsrfPolicy
from app.domain.plugins import Permission, allows_http

_ENV_ALLOWLIST = {
    "PATH",
    "PYTHONPATH",
    "PYTHONIOENCODING",
    "LANG",
    "LC_ALL",
    # Windows 运行 Python 所需
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "PATHEXT",
    "COMSPEC",
    "TEMP",
    "TMP",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
}
_SAFE_METHODS = {"GET", "POST", "HEAD"}
_MAX_HTTP_BODY = 10_000
_MAX_LINE = 256 * 1024


@dataclass
class PluginResult:
    output: str
    logs: list[str] = field(default_factory=list)


def _safe_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in _ENV_ALLOWLIST}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _make_preexec(memory_mb: int, cpu_seconds: int):  # noqa: ANN202 - 平台相关
    try:
        import resource  # type: ignore[import-not-found]
    except ImportError:  # Windows 无 resource
        return None

    def _apply() -> None:
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
            if hasattr(resource, "RLIMIT_AS"):
                limit = memory_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        except (ValueError, OSError):
            pass

    return _apply


class PluginSandbox:
    def __init__(
        self,
        policy: SsrfPolicy,
        *,
        max_timeout_ms: int = 60_000,
        max_memory_mb: int = 1024,
    ) -> None:
        self.policy = policy
        self.max_timeout_ms = max_timeout_ms
        self.max_memory_mb = max_memory_mb

    async def run(
        self,
        *,
        name: str,
        entry_path: Path,
        permissions: list[Permission],
        timeout_ms: int,
        memory_mb: int,
        cpu_seconds: int,
        input: dict,
        config: dict,
    ) -> PluginResult:
        timeout = min(timeout_ms, self.max_timeout_ms) / 1000
        memory = min(memory_mb, self.max_memory_mb)
        try:
            return await asyncio.wait_for(
                self._run(
                    name=name,
                    entry_path=entry_path,
                    permissions=permissions,
                    memory_mb=memory,
                    cpu_seconds=cpu_seconds,
                    input=input,
                    config=config,
                ),
                timeout,
            )
        except TimeoutError as exc:
            raise PluginTimeout(f"插件 {name} 执行超时（>{timeout:.0f}s）") from exc

    async def _run(
        self,
        *,
        name: str,
        entry_path: Path,
        permissions: list[Permission],
        memory_mb: int,
        cpu_seconds: int,
        input: dict,
        config: dict,
    ) -> PluginResult:
        workdir = Path(tempfile.mkdtemp(prefix="mengxi-plugin-"))
        kwargs: dict = {}
        preexec = _make_preexec(memory_mb, cpu_seconds)
        if preexec is not None:
            kwargs["preexec_fn"] = preexec

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(entry_path),
            cwd=str(workdir),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_safe_env(),
            **kwargs,
        )
        try:
            assert process.stdin is not None
            request = json.dumps({"type": "run", "input": input, "config": config})
            process.stdin.write((request + "\n").encode("utf-8"))
            await process.stdin.drain()
            return await self._pump(process, permissions=permissions, name=name)
        finally:
            await self._terminate(process)
            shutil.rmtree(workdir, ignore_errors=True)

    async def _pump(
        self, process: asyncio.subprocess.Process, *, permissions: list[Permission], name: str
    ) -> PluginResult:
        assert process.stdout is not None
        logs: list[str] = []
        while True:
            raw = await process.stdout.readline()
            if not raw:
                break
            if len(raw) > _MAX_LINE:
                raise PluginExecutionError(f"插件 {name} 输出行过长")
            try:
                message = json.loads(raw.decode("utf-8", "replace"))
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue

            kind = message.get("type")
            if kind == "log":
                logs.append(str(message.get("message", ""))[:500])
            elif kind == "http":
                result = await self._proxy_http(permissions, message, plugin=name)
                assert process.stdin is not None
                process.stdin.write((json.dumps(result) + "\n").encode("utf-8"))
                await process.stdin.drain()
            elif kind == "result":
                return PluginResult(output=str(message.get("output", "")), logs=logs)
            elif kind == "error":
                raise PluginExecutionError(str(message.get("message", "插件执行失败"))[:500])

        stderr = b""
        if process.stderr is not None:
            stderr = await process.stderr.read()
        raise PluginExecutionError(
            f"插件 {name} 未返回结果: {stderr.decode('utf-8', 'replace')[:300]}"
        )

    async def _proxy_http(
        self, permissions: list[Permission], message: dict, *, plugin: str
    ) -> dict:
        url = str(message.get("url", ""))
        method = str(message.get("method", "GET")).upper()
        if method not in _SAFE_METHODS:
            raise PluginPermissionDenied(f"插件 {plugin} 使用了不允许的方法 {method}")
        if not allows_http(permissions, url, method=method):
            raise PluginPermissionDenied(f"插件 {plugin} 无权访问该地址")

        headers = message.get("headers") if isinstance(message.get("headers"), dict) else None
        body = message.get("body")
        content = body.encode("utf-8") if isinstance(body, str) else None

        async with SafeHttpClient(self.policy, timeout=10.0) as client:
            response = await client.request(method, url, headers=headers, content=content)
        return {
            "type": "http_result",
            "id": message.get("id"),
            "status": response.status_code,
            "body": response.text[:_MAX_HTTP_BODY],
        }

    @staticmethod
    async def _terminate(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except TimeoutError:
            process.kill()
            await process.wait()
