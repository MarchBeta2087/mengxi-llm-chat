#!/usr/bin/env bash
# 本地全栈冒烟：构建并启动 docker compose，等待 web 健康检查通过后清理。
#
# 用法：bash src/deploy/smoke.sh
# 依赖：Docker + Compose v2，python3（用于生成临时主密钥）
# 说明：若 src/backend/.env 不存在，脚本会基于 .env.example 生成一份临时配置
#       （档 B，随机主密钥/会话密钥），并追加到该文件（已被 .gitignore 忽略）。

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
backend="$here/../backend"
env_file="$backend/.env"
base_url="${MENGXI_SMOKE_URL:-http://127.0.0.1:8080}"
wait_seconds="${MENGXI_SMOKE_WAIT:-120}"

if ! command -v docker >/dev/null 2>&1; then
  echo "错误：未找到 docker" >&2
  exit 1
fi

if [ ! -f "$env_file" ]; then
  echo "未发现 $env_file，基于 .env.example 生成临时配置"
  cp "$backend/.env.example" "$env_file"
  master_key="$(python3 -c 'import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
  session_secret="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
  {
    echo ""
    echo "# --- smoke.sh 自动追加（本地冒烟，勿用于生产）---"
    echo "MENGXI_KEK_PROFILE=B"
    echo "MENGXI_MASTER_KEY_B64=$master_key"
    echo "MENGXI_SESSION_SECRET=$session_secret"
  } >> "$env_file"
fi

cleanup() {
  echo "清理 compose ..."
  (cd "$here" && docker compose down -v --remove-orphans) >/dev/null 2>&1 || true
}
trap cleanup EXIT

cd "$here"
echo "构建并启动全栈 ..."
docker compose up -d --build

echo "等待 $base_url/healthz（最多 ${wait_seconds}s）..."
deadline=$(( $(date +%s) + wait_seconds ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if curl -fsS "$base_url/healthz" >/dev/null 2>&1; then
    echo "✅ 冒烟通过"
    curl -s "$base_url/healthz"; echo
    exit 0
  fi
  sleep 2
done

echo "❌ 冒烟失败：健康检查超时" >&2
docker compose ps || true
docker compose logs --tail=100 || true
exit 1
