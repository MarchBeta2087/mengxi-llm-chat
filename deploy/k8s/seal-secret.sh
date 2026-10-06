#!/usr/bin/env bash
# 由明文值生成 SealedSecret（密文与集群密钥绑定，可安全提交到仓库）。
#
# 前置：安装 kubeseal 并配置好 kubectl 上下文（能访问目标集群）。
# 用法：
#   NAMESPACE=mengxi \
#   MENGXI_SESSION_SECRET="$(openssl rand -base64 48)" \
#   MENGXI_MASTER_KEY_B64="<32B base64>" \
#   POSTGRES_PASSWORD="<强口令>" \
#   bash deploy/k8s/seal-secret.sh
#
# 产物默认写入 deploy/k8s/overlays/production/sealed-secret.yaml

set -euo pipefail

namespace="${NAMESPACE:-mengxi}"
secret_name="${SECRET_NAME:-mengxi-secrets}"
out="${SEALED_OUT:-deploy/k8s/overlays/production/sealed-secret.yaml}"

if ! command -v kubeseal >/dev/null 2>&1; then
  echo "错误：未找到 kubeseal（https://github.com/bitnami-labs/sealed-secrets）" >&2
  exit 1
fi

: "${MENGXI_SESSION_SECRET:?请设置 MENGXI_SESSION_SECRET}"
: "${MENGXI_MASTER_KEY_B64:?请设置 MENGXI_MASTER_KEY_B64}"
: "${POSTGRES_PASSWORD:?请设置 POSTGRES_PASSWORD}"

kubectl -n "$namespace" create secret generic "$secret_name" \
  --dry-run=client -o yaml \
  --from-literal=MENGXI_SESSION_SECRET="$MENGXI_SESSION_SECRET" \
  --from-literal=MENGXI_MASTER_KEY_B64="$MENGXI_MASTER_KEY_B64" \
  --from-literal=POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  | kubeseal --format yaml > "$out"

echo "✅ 已生成 $out（可安全提交；请离线备份主密钥与恢复码）"
