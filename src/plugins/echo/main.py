"""echo：回显 input.text，演示 JSON Lines 协议（无任何权限）。"""

from __future__ import annotations

import json
import sys


def main() -> None:
    line = sys.stdin.readline()
    if not line:
        return
    request = json.loads(line)
    text = str((request.get("input") or {}).get("text", ""))
    sys.stdout.write(json.dumps({"type": "result", "output": text}) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
