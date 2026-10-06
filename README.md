# 梦溪畅谈（mengxi-llm-chat）

[![CI](https://github.com/MarchBeta2087/mengxi-llm-chat/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/MarchBeta2087/mengxi-llm-chat/actions/workflows/ci.yml)
[![CodeQL](https://github.com/MarchBeta2087/mengxi-llm-chat/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/MarchBeta2087/mengxi-llm-chat/actions/workflows/codeql.yml)
[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776ab.svg)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/vue-3-42b883.svg)](https://vuejs.org/)
[![Node](https://img.shields.io/badge/node-22-339933.svg)](https://nodejs.org/)

> 一个可自部署的 LLM 聊天 Web 应用：多模型、多 API Key 公私双轨管理与调度、六维限流、
> 插件系统、对话加密与盲索引搜索、审计日志、可定制界面。
>
> 名称取自沈括《梦溪笔谈》——"笔谈"之记录与"畅谈"之对谈双关，恰合"加密聊天记录 + AI 对谈"。

---

## 核心特性

| 能力 | 说明 |
| --- | --- |
| 🔐 密钥安全 | API Key 以 AES-256-GCM 加密存储；KEK（主密钥）与数据库分离；三档主密钥（口令派生 / 环境变量 / KMS） |
| 💬 对话隐私 | 消息正文按用户 DEK 加密落库，每消息独立 IV；数据库泄露不泄露聊天内容 |
| 🗝 恢复码 | 档 A 口令遗忘时用一次性恢复码重置口令并全量轮换 |
| 🔎 盲索引搜索 | 加密会话基于 HMAC 指纹的可搜索映射，指纹表不可还原明文 |
| 🔀 公私双轨调度 | 公有 Key 全员可用、私有 Key 仅本人；私有优先，失败可回退公有；配额感知加权轮询 + 熔断 |
| 🚦 三层限流 | Key 级六维（RPM/RPH/RPD/TPM/TPH/TPD）→ 用户级 → IP 级；用户/用户组日配额 |
| 🧩 插件系统 | 全局/可选插件 + 用户组策略；子进程沙箱、权限声明制、不可信输出边界包装 |
| 🛡 SSRF 防护 | 协议/IP/对端/重定向多重校验，拒绝内网与云元数据地址 |
| 🎨 可定制界面 | 主题色、深浅模式、侧边栏宽度、字号；多套预设 |
| 📊 审计日志 | 每次上游调用记录用量/延迟/回退/客户端 IP；分角色可查 |

## 架构

```
浏览器 ──HTTPS──▶ web(Nginx + Vue SPA) ──/api──▶ app(FastAPI)
                                                    ├─▶ PostgreSQL（密文业务库 + 审计）
                                                    ├─▶ Redis（限流 / 配额 / 熔断）
                                                    ├─▶ 插件沙箱子进程（隔离）
                                                    └─▶ 上游 LLM（经 SSRF 校验）
```

- **前端**：Vue 3 + TypeScript + Vite + Pinia + Vue Router
- **后端**：FastAPI + SQLAlchemy 2.0(async) + httpx + pydantic v2
- **加密**：cryptography（AES-256-GCM、HKDF）+ argon2-cffi
- **存储**：PostgreSQL 18（唯一官方支持）+ Redis 8
- **部署**：Docker Compose

## 快速开始

### 方式一：Docker Compose（推荐）

```bash
# 1) 准备后端环境变量
cd src/backend
cp .env.example .env
python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"  # 填入 MENGXI_MASTER_KEY_B64
# 同时务必修改 MENGXI_SESSION_SECRET

# 2) 启动全栈
cd ../deploy
docker compose up -d --build
```

访问 `http://<主机>:8080`。详见 **[部署与运维手册](docs/deployment-guide.md)**。

### 方式二：本地开发

```bash
# 后端（Python 3.11+）
cd src/backend
python -m venv .venv && source .venv/Scripts/activate     # Windows Git Bash
pip install -r requirements-dev.txt
cp .env.example .env        # 档 B：设置 MENGXI_MASTER_KEY_B64
uvicorn app.main:app --reload --port 8000

# 前端（Node 24 + pnpm）
cd ../frontend
pnpm install
pnpm dev                    # http://127.0.0.1:5173（/api 代理到 8000）
```

想用自己的真/假密钥跑通"成功 / 熔断回退 / SSRF 拦截"三条路径，见
**[使用自有密钥本地测试指南](docs/key-testing-guide.md)**。

## 目录结构

```
.
├─ docs/                     # 文档（见下方索引）
├─ deploy/k8s/               # Kubernetes（Kustomize）清单
├─ prototype/                # 界面原型（HTML）
├─ usecase/                  # PlantUML 用例图
├─ .github/workflows/        # CI（ci.yml）与安全分析（codeql.yml）
└─ src/
   ├─ backend/               # FastAPI 服务、迁移、测试、脚本
   ├─ frontend/              # Vue 3 SPA
   ├─ deploy/                # docker-compose.yml、nginx.conf
   └─ plugins/               # 内置插件（echo、http-fetch）
```

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [需求分析 v2.0](docs/llm-chat-app-requirements-v2.md) | 功能/非功能需求、权限矩阵、威胁模型 |
| [可行性分析](docs/llm-chat-app-feasibility.md) | 技术/经济/法律/进度可行性 |
| [设计说明书](docs/llm-chat-app-design.md) | 架构、模块、数据模型、接口、安全、测试 |
| [部署与运维手册](docs/deployment-guide.md) | Compose 部署、TLS、备份恢复、升级、排障 |
| [CI/CD 与持续交付指南](docs/cd-guide.md) | 变更日志(git-cliff)、镜像签名(cosign)、SSH CD、ArgoCD |
| [使用自有密钥测试指南](docs/key-testing-guide.md) | 真钥 / 有效假钥 / 无效 base_url 三条路径 |
| [插件系统说明书](docs/plugin-system-guide.md) | Manifest、权限、沙箱协议、优先级、开发指南 |

## 安全要点

- 数据库内**不含任何明文** API Key 与消息内容（密文 + 脱敏）；
- 管理员**无法**通过任何接口读取他人私有 Key 或对话明文；
- 主密钥不落数据库；恢复码一次性使用、用后全量轮换；
- 请勿提交真实密钥：仓库已忽略 `apikeys/` 与 `*.db`；排障信息一律脱敏。

## 开发

```bash
# 后端：lint + 测试
cd src/backend
ruff check . && ruff format --check .
pytest

# 前端：单测 + 覆盖率门禁 + 构建
cd src/frontend
pnpm test:coverage
pnpm build

# 前端 E2E（需先 pnpm exec playwright install chromium）
pnpm exec playwright install chromium
pnpm e2e

# 全栈冒烟（Docker Compose 构建并健康检查，完成后自动清理）
bash src/deploy/smoke.sh
```

CI 在 push / PR 时自动执行（`.github/workflows/ci.yml`）：

| Job | 内容 |
| --- | --- |
| Backend | `ruff check` / `ruff format` / `pytest` / 许可证扫描（`pip-licenses`，阻止 GPL/AGPL）/ 漏洞审计（`pip-audit`） |
| Frontend | `pnpm audit`（high+）/ `vitest` 单测 + **覆盖率门禁** / `pnpm build` |
| Frontend E2E | Playwright（登录 + 流式聊天，API mock；初期非阻断） |
| Compose smoke | 全栈构建 + `/healthz` 健康检查 |
| K8s | `kustomize build deploy/k8s/overlays/production` 渲染校验 |
| Trivy | 后端/前端镜像 CVE 扫描（CRITICAL/HIGH） |
| SBOM | 生成 CycloneDX（后端 `cyclonedx-py`、前端 Syft）并上传产物 |

CI 同时支持**每日定时全量运行**（`schedule`）与手动触发；安全分析由 **CodeQL** 工作流负责
（`.github/workflows/codeql.yml`）；依赖更新由 **Dependabot** 负责
（`.github/dependabot.yml`：pip / npm / actions / docker，每周）。

## 发布

打 tag 即触发发布流水线（`.github/workflows/release.yml`）：

```bash
# 打版本 tag 并推送，即自动测试 → 构建镜像 → 推送 GHCR → 创建 Release
git tag v1.0.0 && git push origin v1.0.0
```

- 测试门禁：`ruff check` + `pytest`；
- 镜像推送到 GHCR（自动小写化）并用 **cosign 无密钥签名**：
  - `ghcr.io/<owner>/mengxi-llm-chat-backend:<version>`（含 `latest`）
  - `ghcr.io/<owner>/mengxi-llm-chat-frontend:<version>`（含 `latest`）
- 由 **git-cliff** 依据提交生成变更日志与 Release Notes（`cliff.toml`），并自动创建 GitHub Release。
- 交付到服务器：Actions ▸ **Deploy (CD)**（SSH 拉取 GHCR 镜像并重启），详见 [CI/CD 指南](docs/cd-guide.md)。

镜像验签：

```bash
cosign verify ghcr.io/<owner>/mengxi-llm-chat-backend:v1.0.0 \
  --certificate-identity-regexp "https://github.com/<owner>/mengxi-llm-chat/.github/workflows/release.yml@refs/tags/.*" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

## 许可证

[BSD 3-Clause](LICENSE)
