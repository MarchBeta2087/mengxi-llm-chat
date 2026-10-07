# 更新日志

本项目的变更记录。每次打 tag 发布时，由
[git-cliff](https://git-cliff.org/) 依据 [Conventional Commits](https://www.conventionalcommits.org/)
自动生成（配置见 [`cliff.toml`](./cliff.toml)）；完整历史见
[GitHub Releases](https://github.com/MarchBeta2087/mengxi-llm-chat/releases)。

## 本地生成

```bash
# 生成完整 CHANGELOG.md
docker run --rm -v "$PWD:/app" -w /app orhunp/git-cliff:latest --output CHANGELOG.md

# 仅预览最新未发布变更
docker run --rm -v "$PWD:/app" -w /app orhunp/git-cliff:latest --unreleased --strip header
```

## [1.0.0] - 2026-10-07

首个正式版本：M1–M5 里程碑全部落地，并补齐发布所需的社区与文档材料。

### 新增

- **关于页**：版本号、BSD-3-Clause 完整许可证声明、第三方组件许可与贡献入口。
- **社区健康文件**：行为准则、贡献指南、Bug / 功能建议 Issue 模板与 PR 模板。
- **自动化截图**：`pnpm screenshots` 一键生成 `docs/screenshots/`
  （Playwright + 演示账号 `newuser` / `admin`，无需真实 LLM）。

### 变更

- 版本号统一升级到 `1.0.0`（后端 `__version__` / `pyproject.toml`、前端 `package.json`）。
- 侧边栏新增「关于」入口；`docs/screenshots/README.md` 记录截图清单与再生成方式。

### 修复

- 关于页 `package.json` 相对导入路径错误导致 `pnpm typecheck` 失败。
- 聊天界面助手气泡样式选择器（`.msg.ai` → `.msg.assistant`）与消息角色不匹配。

## 里程碑概览

| 里程碑 | 内容 |
| --- | --- |
| M1 | 加密子系统、SSRF 防护、密钥存储与调度、SSE 基础聊天 |
| M2 | 六维限流、三层兜底、熔断、审计、用户/组配额 |
| M3 | 插件系统（Manifest + 子进程沙箱 + 全局/可选 + 用户组） |
| M4 | 对话加密、盲索引搜索、恢复码 |
| M5 | 管理后台、前端 SPA、发布打磨 |
| CI/CD | 质量门禁、安全扫描、SBOM、E2E、GHCR 发布与签名、CD |

> 说明：主密钥档 C（KMS，`KmsKekProvider`）与匿名访问开关均为路线图能力，v1.0.0 尚未实现（设计说明书 §3.3 / §13.2 已标注）。
