# 贡献指南（Contributing）

感谢参与 **梦溪畅谈（mengxi-llm-chat）**！本指南说明开发环境、分支模型、提交规范与 PR 流程。

参与前请阅读并遵守 [行为准则](CODE_OF_CONDUCT.md)。

---

## 1. 开发环境

### 后端（Python 3.11+，本项目 CI 使用 3.14）

```bash
cd src/backend
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements-dev.txt
cp .env.example .env        # 档 B：填入 MENGXI_MASTER_KEY_B64 与 MENGXI_SESSION_SECRET
uvicorn app.main:app --reload --port 8000
```

### 前端（Node 22+，CI 使用 24 + pnpm 11）

```bash
cd src/frontend
pnpm install
pnpm dev                    # http://127.0.0.1:5173（/api 代理到 8000）
```

---

## 2. 分支模型

| 分支 | 用途 |
| --- | --- |
| `main` | 稳定分支；仅通过 PR 合入，且 **CI 必须全绿**；每次发布在此打 tag |
| `dev` | 集成分支；日常特性先并入 dev，验证后再批量合入 main |
| `feature/*` | 新功能 |
| `fix/*` | 缺陷修复 |
| `docs/*` | 文档 |
| `chore/*` | 构建/依赖/杂项 |

日常开发以 `dev` 为基线，发布时由维护者将 `dev`（或经评审的 `feature/*`）合入 `main` 并打 tag：

```bash
git checkout dev && git pull
git checkout -b feature/your-feature
# ... 开发与自测 ...
git push -u origin feature/your-feature
# 在 GitHub 上向 dev 发起 PR
```

紧急热修复可直接基于 `main` 开 `fix/*`，修复合入 `main` 后同步回 `dev`。

---

## 3. 提交规范

采用 [Conventional Commits](https://www.conventionalcommits.org/)（`CHANGELOG` 由 git-cliff 依据提交生成）：

```
feat(scope): 新功能
fix: 修复
docs: 文档
test: 测试
ci: 流水线
chore: 杂项
refactor/perf: 重构/性能
```

- 说明写清楚「为什么」，而非只写「做了什么」；
- 一个提交聚焦一件事。

---

## 4. 本地检查（提交前务必执行）

```bash
# 后端
cd src/backend
ruff check . && ruff format --check .
pytest

# 前端
cd src/frontend
pnpm typecheck
pnpm test:coverage       # 含覆盖率门禁
pnpm e2e                 # 需先 pnpm exec playwright install chromium（或 PW_CHANNEL=chrome 用系统浏览器）
pnpm build
```

CI 还会执行：依赖许可证扫描（无 GPL/AGPL）、`pip-audit`/`pnpm audit`、镜像 Trivy 扫描、SBOM、CodeQL、K8s 清单渲染、Docker Compose 冒烟。

### 无障碍（Accessibility）

界面改动以 [WCAG 2.1 AA](https://www.w3.org/TR/WCAG21/) 为目标，请对照[无障碍声明的贡献者清单](ACCESSIBILITY.md#6-面向贡献者的无障碍清单)：
优先使用原生语义元素、为表单控件关联标签、图标按钮补 `aria-label`、支持纯键盘操作与可见焦点、
动态状态使用 `role="alert"`/`aria-live`，并满足 AA 对比度与 `prefers-reduced-motion`。

---

## 5. 安全红线

- **绝不提交真实密钥**：仓库已忽略 `apikeys/` 与 `*.db`；测试请使用假密钥或环境变量；
- 不在 Issue/PR/日志/截图中粘贴 API Key、主口令或恢复码（一律脱敏为 `sk-xxxx…xxxx`）；
- 涉及安全问题的改动请在描述中说明威胁与缓解；
- 发现安全漏洞请按 [安全政策](SECURITY.md) 的**私密渠道**报告，勿公开提交。

---

## 6. 提交 PR

1. 推送到你的分支并创建 PR（日常目标 `dev`，发布/热修复目标 `main`），按 [PR 模板](.github/PULL_REQUEST_TEMPLATE.md) 填写；
2. 确保 CI 全绿；如涉及界面变更，附**截图**（可用 `pnpm screenshots` 生成）；
3. 保持 PR 聚焦、可评审；必要时补充测试与文档；
4. 评审通过后由维护者合并（默认 Squash）。

---

## 7. 相关文档

- [设计说明书](docs/llm-chat-app-design.md)
- [插件系统说明书](docs/plugin-system-guide.md)（开发插件）
- [部署与运维手册](docs/deployment-guide.md)
- [CI/CD 与持续交付指南](docs/cd-guide.md)
- [安全政策](SECURITY.md)（漏洞报告）
- [无障碍声明](ACCESSIBILITY.md)

感谢你的贡献！
