# 梦溪畅谈 — CI/CD 与持续交付指南

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v1.0 |
| 日期 | 2026-10-06 |
| 相关文档 | [部署与运维手册](deployment-guide.md)、[CHANGELOG](../CHANGELOG.md) |

本指南说明自动化交付链路：**变更日志（git-cliff）→ 镜像构建与推送（GHCR）→ 镜像签名（cosign）→ 目标服务器部署（SSH）**，并给出 ArgoCD（GitOps）示例。

---

## 1. 总览

```
git tag v1.0.0 ──▶ release.yml
                    ├─ 测试门禁（ruff + pytest）
                    ├─ 构建并推送镜像到 GHCR（semver + latest）
                    ├─ cosign 无密钥签名
                    └─ git-cliff 生成 Release Notes → GitHub Release

Actions ▸ Deploy (CD) ──SSH──▶ 目标服务器：compose pull/up（GHCR 镜像）
                              或 ArgoCD 监听 Git 仓库自动同步
```

| 工作流 | 触发 | 作用 |
| --- | --- | --- |
| `ci.yml` | push / PR / 每日 | 质量与安全门禁（含 E2E、Trivy、SBOM） |
| `codeql.yml` | push / PR / 每周 | 代码安全分析 |
| `release.yml` | tag `v*.*.*` | 测试 → 镜像推送 GHCR → 签名 → Release |
| `deploy.yml` | 手动 | 通过 SSH 在服务器拉取新镜像并重启 |

---

## 2. 变更日志（git-cliff）

- 配置：`cliff.toml`（按 Conventional Commits 分组：新增/修复/文档/CI…）
- 发布时自动生成 Release Notes；本地生成：

```bash
docker run --rm -v "$PWD:/app" -w /app orhunp/git-cliff:latest --output CHANGELOG.md
```

- 提交规范：`feat(scope): …`、`fix: …`、`ci: …` 等，避免非规范消息（会被过滤）。

---

## 3. 镜像与签名（GHCR + cosign）

发布产物（每次 tag）：

```
ghcr.io/<owner>/mengxi-llm-chat-backend:<version>   # 及 latest、major.minor
ghcr.io/<owner>/mengxi-llm-chat-frontend:<version>
```

镜像以 **keyless（OIDC）** 方式签名，验证方式：

```bash
cosign verify ghcr.io/<owner>/mengxi-llm-chat-backend:v1.0.0 \
  --certificate-identity-regexp "https://github.com/<owner>/mengxi-llm-chat/.github/workflows/release.yml@refs/tags/.*" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

> `<owner>` 为小写（GHCR 要求）。示例：`marchbeta2087`。

---

## 4. 服务器部署（SSH CD）

### 4.1 一次性准备（目标服务器）

部署目录（如 `/opt/mengxi`）需包含：

```
/opt/mengxi/
├─ docker-compose.ghcr.yml     # 从仓库复制
├─ .env                        # 主密钥/会话密钥等（见 backend/.env.example）
└─ data/                       # keys/ 与 plugins/（务必备份）
```

### 4.2 GitHub 配置

- **Secrets**：`DEPLOY_HOST`、`DEPLOY_USER`、`DEPLOY_SSH_KEY`、`DEPLOY_PATH`（可选 `DEPLOY_PORT`）
- **Environment**：`production`（建议开启 Required reviewers 做人工审批）

### 4.3 触发

Actions ▸ **Deploy (CD)** ▸ Run workflow ▸ 选择环境与镜像 tag（如 `v1.0.0`）。工作流会：

1. 在 runner 上把 tag **解析为不可变 digest**；
2. SSH 到服务器，以 digest 固定方式拉取并启动：
   `docker compose -f docker-compose.ghcr.yml -f docker-compose.digest.yml up -d`；
3. 轮询 `http://127.0.0.1:8080/healthz`（最多 40 次 × 3s）；
4. **成功**则记录当前版本到 `.mengxi-deploy.env`；**失败**则自动回滚到上一个已记录版本并以非零退出。

### 4.4 回滚

- 自动：健康检查失败即回滚（§4.3）；
- 手动：重新触发并选择上一个 tag（或直接用 digest）。
- 若迁移不可逆，需先恢复数据库备份（见部署手册 §6）。

---

## 5. ArgoCD（GitOps）示例

以 Git 仓库作为期望状态来源，ArgoCD 监听并同步：

1. 将 `docker-compose.ghcr.yml` 转写为 Kubernetes 清单——仓库已提供
   [`deploy/k8s`](../deploy/k8s/README.md)（Kustomize base + production overlay）；
2. 把镜像 tag 参数化（用 Kustomize `images:` 或 Helm values）；
3. 新建 ArgoCD Application：

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: mengxi
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/<owner>/mengxi-llm-chat.git
    targetRevision: main
    path: deploy/k8s/overlays/production
  destination:
    server: https://kubernetes.default.svc
    namespace: mengxi
  syncPolicy:
    automated: { prune: true, selfHeal: true }
```

4. 发布新版本时，由 CI 更新清单中的镜像 tag（提交回仓库），ArgoCD 自动同步并滚动更新。

> 注意：主密钥（档 B）需以 Secret 注入；档 A 需在 Pod 启动后解锁（每个副本都要解锁，不推荐多副本）；跨副本请使用**档 B**（同一 `MENGXI_MASTER_KEY_B64` 注入所有副本）。档 C（KMS）为路线图，v1.0 未实现。详见设计说明书 §3.3、部署手册 §11。
>
> Secret 管理推荐 **Sealed Secrets**（密文可入 Git）或 **External Secrets**；
> 仓库提供生成脚本 `deploy/k8s/seal-secret.sh` 与示例模板，详见
> [`deploy/k8s/README.md`](../deploy/k8s/README.md)。

---

## 6. 安全要点

- 发布与部署使用 **OIDC 临时凭据**（GHCR 登录 + cosign 签名），不长期保存密钥；
- 部署用 SSH 私钥仅存于 GitHub Secrets，服务器账号按最小权限；
- `production` environment 建议开启人工审批；
- 所有镜像优先按 **digest** 部署（`@sha256:…`）以防 tag 漂移；
- 部署前务必确认 `data/keys` 与主密钥/恢复码可恢复（见部署手册 §6.1）。
