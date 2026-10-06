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

## 里程碑概览

| 里程碑 | 内容 |
| --- | --- |
| M1 | 加密子系统、SSRF 防护、密钥存储与调度、SSE 基础聊天 |
| M2 | 六维限流、三层兜底、熔断、审计、用户/组配额 |
| M3 | 插件系统（Manifest + 子进程沙箱 + 全局/可选 + 用户组） |
| M4 | 对话加密、盲索引搜索、恢复码 |
| M5 | 管理后台、前端 SPA、发布打磨 |
| CI/CD | 质量门禁、安全扫描、SBOM、E2E、GHCR 发布与签名、CD |
