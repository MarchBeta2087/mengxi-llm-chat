"""http-fetch：请求 input.url，经宿主代理发起出站请求。

出站必须声明权限 ``http:outbound:<hostpattern>``，且由宿主按 SSRF 规则代为发起，
插件自身不持有网络能力（OS 级隔离由部署层负责）。
"""

from __future__ import annotations

import json
import sys


def main() -> None:
    line = sys.stdin.readline()
    if not line:
        return
    request = json.loads(line)
    url = str((request.get("input") or {}).get("url", ""))

    sys.stdout.write(json.dumps({"type": "http", "id": 1, "method": "GET", "url": url}) + "\n")
    sys.stdout.flush()

    response = json.loads(sys.stdin.readline())
    status = response.get("status")
    body = str(response.get("body", ""))
    output = f"HTTP {status}\n{body[:2000]}"
    sys.stdout.write(json.dumps({"type": "result", "output": output}) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
