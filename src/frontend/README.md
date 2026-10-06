# 梦溪畅谈前端（Vue 3 + Vite）

单页应用，界面以 `prototype/prototype-*.html` 为基线，对应设计说明书 §11。
覆盖页面：聊天、我的 Key、插件、设置、管理后台。

## 技术栈

- Vue 3 + TypeScript + Vite
- Pinia（状态）、Vue Router（路由 + 鉴权守卫）
- 纯 CSS 设计令牌（`src/styles/tokens.css`），支持主题色 / 深色模式 / 侧边栏宽度 / 字号

## 目录结构

```
src/
├─ api/            # client.ts（REST + SSE）、types.ts
├─ stores/         # auth.ts、theme.ts（持久化到 localStorage）
├─ router.ts       # 路由与登录/管理员守卫
├─ components/     # AppLayout.vue、ThemePanel.vue
├─ views/          # LoginView / ChatView / KeysView / PluginsView / SettingsView / AdminView
└─ styles/tokens.css
```

## 开发

```bash
cd src/frontend
pnpm install
pnpm dev          # http://127.0.0.1:5173，/api 已代理到 127.0.0.1:8000
```

先启动后端（见 `docs/key-testing-guide.md`）。

## 构建

```bash
pnpm build        # 产物在 dist/
pnpm preview      # 本地预览
pnpm typecheck    # vue-tsc 类型检查（可选）
```

生产部署：将 `dist/` 交由 Nginx/静态服务托管，并把 `/api` 反向代理到后端
（参考 `src/deploy/nginx.conf`，注意 SSE 需关闭缓冲）。

## 与后端的契约

- 所有接口返回 `{ code, data, message }`；前端 `src/api/client.ts` 统一解包 `data`，错误抛 `ApiError`。
- 聊天 `/api/chat/completions` 为 SSE：事件 `meta` / `delta` / `usage` / `done` / `error`。
- 会话消息由服务端透明加解密；列表页不展示明文 Key（仅 `sk-...xxxx`）。
- 全局插件在界面上无禁用入口；可选插件显示生效来源（全局/用户组/个人/默认）。

## 备注

- 依赖安装：`pnpm-workspace.yaml` 中已允许 `esbuild`/`vue-demi` 构建脚本并关闭严格依赖构建检查。
- Naive UI 作为后续可选增强（当前用轻量 CSS 令牌实现主题定制，视觉与原型一致）。
