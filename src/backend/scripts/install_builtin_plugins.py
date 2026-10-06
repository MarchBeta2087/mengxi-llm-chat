"""把仓库内置插件（src/plugins/*）安装到运行实例。

需要管理员账号。用法::

    python scripts/install_builtin_plugins.py --base http://127.0.0.1:8000 \
        --username admin --password password123
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

BUILTIN_DIR = Path(__file__).resolve().parents[2] / "plugins"


def main() -> int:
    parser = argparse.ArgumentParser(description="安装内置插件")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--dir", type=Path, default=BUILTIN_DIR)
    args = parser.parse_args()

    with httpx.Client(base_url=args.base, timeout=60) as client:
        resp = client.post(
            "/api/auth/login", json={"username": args.username, "password": args.password}
        )
        resp.raise_for_status()

        for manifest_path in sorted(args.dir.glob("*/manifest.json")):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            entry = manifest_path.parent / manifest.get("entry", "main.py")
            payload = {
                "manifest": manifest,
                "code": entry.read_text(encoding="utf-8"),
            }
            result = client.post("/api/admin/plugins", json=payload)
            print(f"[{result.status_code}] {manifest['name']} {result.text[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
