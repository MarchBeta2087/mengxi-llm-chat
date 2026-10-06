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
- 档 A（口令派生）需在启动后调用 `POST /api/admin/kek/unlock` 解锁；跨副本请使用档 C（KMS）。
- `data` 为 RWO PVC，多副本 `app` 需 ReadWriteMany 或改用对象存储；单副本最简。
- SSE 需 Ingress 关闭缓冲（已在 `ingress.yaml` 注解）。

## GitOps

ArgoCD Application 示例见 [`docs/cd-guide.md`](../../docs/cd-guide.md) §5，`path` 指向
`deploy/k8s/overlays/production`。
