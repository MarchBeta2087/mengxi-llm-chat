# Kubernetes 部署清单（Kustomize）

以 Kustomize 管理的 K8s 清单，配合 GitOps（ArgoCD/Flux）实现声明式交付。

```
deploy/k8s/
├─ base/                      # 通用基线（namespace/config/secret/postgres/redis/app/web/migrate/ingress）
└─ overlays/
   └─ production/kustomization.yaml   # 镜像 tag、副本数等环境差异
```

## 渲染与校验

```bash
kustomize build deploy/k8s/overlays/production
# 或
kubectl kustomize deploy/k8s/overlays/production
```

## 部署

```bash
# 1) 先创建 Secret（勿提交真实值）：建议 Sealed Secrets / External Secrets
kubectl -n mengxi create secret generic mengxi-secrets \
  --from-literal=MENGXI_SESSION_SECRET="$(openssl rand -base64 48)" \
  --from-literal=MENGXI_MASTER_KEY_B64="<32B base64>" \
  --from-literal=POSTGRES_PASSWORD="<强口令>"

# 2) 应用清单
kubectl apply -k deploy/k8s/overlays/production

# 3) 查看迁移 Job（应用启动前完成表结构升级）
kubectl -n mengxi logs job/mengxi-migrate
```

- 更新版本：修改 overlay 的 `images.newTag`（或改用 `newName` + `digest`）后 `kubectl apply -k`。
- 档 A（口令派生）需在启动后调用 `POST /api/admin/kek/unlock` 解锁（**每个副本都要解锁，不推荐多副本**）；跨副本请使用**档 B**（本清单默认 `MENGXI_KEK_PROFILE=B`，同一 `MENGXI_MASTER_KEY_B64` 经 Secret 注入所有副本）。档 C（KMS）为路线图，v1.0 未实现。
- `data` 为 RWO PVC，多副本 `app` 需 ReadWriteMany 或改用对象存储；单副本最简。
- SSE 需 Ingress 关闭缓冲（已在 `ingress.yaml` 注解）。

## Secret 管理

`secret.yaml` 仅为占位示例，**切勿提交真实值**。生产建议二选一：

### 方案 A：Sealed Secrets（推荐）

密文与集群控制器密钥绑定，可安全提交到 Git（契合 GitOps）：

```bash
# 安装控制器（一次）
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/latest/download/controller.yaml

# 生成 SealedSecret（脚本：deploy/k8s/seal-secret.sh）
NAMESPACE=mengxi \
MENGXI_SESSION_SECRET="$(openssl rand -base64 48)" \
MENGXI_MASTER_KEY_B64="<32B base64>" \
POSTGRES_PASSWORD="<强口令>" \
bash deploy/k8s/seal-secret.sh

# 应用（生成 kubectl 可解密的 Secret）
kubectl apply -f deploy/k8s/overlays/production/sealed-secret.yaml
```

参考模板：`deploy/k8s/overlays/production/sealed-secret.example.yaml`。

### 方案 B：External Secrets

从云密钥服务（Vault / AWS Secrets Manager / GCP/Azure）同步为 K8s Secret：

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata: { name: mengxi-secrets, namespace: mengxi }
spec:
  refreshInterval: 1h
  secretStoreRef: { name: vault-backend, kind: ClusterSecretStore }
  target: { name: mengxi-secrets }
  data:
    - { secretKey: MENGXI_SESSION_SECRET, remoteRef: { key: mengxi, property: session_secret } }
    - { secretKey: MENGXI_MASTER_KEY_B64, remoteRef: { key: mengxi, property: master_key } }
    - { secretKey: POSTGRES_PASSWORD, remoteRef: { key: mengxi, property: postgres_password } }
```

> 无论哪种方案，主密钥与恢复码务必**离线备份**；丢失则所有密文不可恢复。

## GitOps

ArgoCD Application 示例见 [`docs/cd-guide.md`](../../docs/cd-guide.md) §5，`path` 指向
`deploy/k8s/overlays/production`。
