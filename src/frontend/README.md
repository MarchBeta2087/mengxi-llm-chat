# 前端（Vue 3 + Vite + Naive UI）

> M5 里程碑实现。界面以 `prototype/prototype-*.html` 为基线，设计说明见 §11。

规划目录：

```
frontend/
├─ src/
│  ├─ views/        # chat / keys / plugins / settings / admin
│  ├─ stores/       # Pinia：auth / conversation / key / plugin / theme
│  ├─ components/   # 消息气泡、开关、沙箱权限卡、回退 toast
│  ├─ theme/        # 设计令牌与 Naive UI themeOverrides
│  └─ api/          # 由后端 OpenAPI 生成的客户端
└─ vite.config.ts
```

后端契约：启动后端后访问 `/docs` 或 `/openapi.json` 获取 OpenAPI，前端据此生成类型化客户端，支持前后端并行开发。
