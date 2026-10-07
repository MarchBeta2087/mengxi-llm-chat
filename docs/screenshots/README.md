# 界面截图

本目录的 PNG 由脚本自动生成，请勿手工替换：

```bash
cd src/frontend
pnpm exec playwright install chromium   # 仅首次，或设置 PW_CHANNEL=chrome|msedge 复用系统浏览器
pnpm screenshots                        # 构建 + 启动演示后端 + 截图
```

- 生成脚本：`src/frontend/scripts/screenshots.mjs`（Playwright）
- 演示后端：`src/backend/scripts/shots_backend.py`
  （SQLite `_shots.db` + fakeredis + 确定性假上游，不影响生产代码）
- 演示账号：`newuser` / `admin`，口令均为 `12345678`，**仅用于本地截图**
- 产物：`NN-*.png`（2× 设备像素比，PNG）

> 脚本会自动清理旧的 `*.png`；使用 `--keep` 可保留，`--skip-build` 可复用已有 `dist/`。
> 截图运行产生的 `_shots.db` 与 `_shotsdata/` 已在 `.gitignore` 中忽略。

## 截图清单

| 文件 | 页面 |
| --- | --- |
| `01-login.png` | 登录 / 注册页 |
| `02-chat.png` | 聊天主界面（已加密会话与历史消息） |
| `03-model-modal.png` | 模型选择弹窗（脱敏 Key、模型、用量） |
| `04-chat-reply.png` | 流式回复完成 |
| `05-keys.png` | 我的 Key（私有 Key 管理） |
| `06-plugins.png` | 插件（全局 / 可选、生效来源） |
| `07-settings.png` | 设置（账户、外观、用量与审计） |
| `08-about.png` | 关于（版本、许可证声明、第三方组件） |
| `09-chat-dark.png` | 深色模式聊天 |
| `10-admin-users.png` | 管理后台 · 用户与配额 |
| `11-admin-keys.png` | 管理后台 · 公有 Key |
| `12-admin-plugins.png` | 管理后台 · 已安装插件与内置市场 |
| `13-admin-audit.png` | 管理后台 · 审计检索与 CSV 导出 |
| `14-admin-groups.png` | 管理后台 · 用户组 |

## 在文档中引用

```markdown
![聊天](../docs/screenshots/02-chat.png)
```
