"""从 CSV（baseurl,apikey 两列）向本地实例播种 API Key。

本地实测辅助脚本，本身不含任何密钥；密钥来自命令行指定的 CSV 文件。
用法::

    python scripts/seed_keys.py --username alice --password password123 \
        --csv ../apikeys/real-keys/real.csv --model deepseek-chat
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import httpx


def _authenticate(client: httpx.Client, username: str, password: str) -> None:
    resp = client.post("/api/auth/register", json={"username": username, "password": password})
    if resp.status_code != 200:
        resp = client.post("/api/auth/login", json={"username": username, "password": password})
    resp.raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser(description="从 CSV 播种 API Key")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--public", action="store_true")
    parser.add_argument("--weight", type=int, default=1)
    args = parser.parse_args()

    with httpx.Client(base_url=args.base, timeout=30) as client:
        _authenticate(client, args.username, args.password)
        with args.csv.open(newline="", encoding="utf-8") as handle:
            for index, row in enumerate(csv.DictReader(handle), start=1):
                payload = {
                    "provider_name": f"{args.csv.stem}-{index}",
                    "api_key": row["apikey"],
                    "base_url": row["baseurl"],
                    "models": [args.model],
                    "is_public": args.public,
                    "weight": args.weight,
                }
                resp = client.post("/api/keys", json=payload)
                print(
                    f"[{resp.status_code}] {payload['provider_name']} "
                    f"({row['baseurl']}) {resp.text[:160]}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
