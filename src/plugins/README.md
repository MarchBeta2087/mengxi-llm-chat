# 内置插件

本目录存放官方内置 / 管理员导入的插件包。运行时由 `PluginSandbox` 以独立子进程加载，
容器部署时建议以**只读**方式挂载（见《插件系统说明书》§14）。

安装到本地实例：

```bash
cd src/backend
python scripts/install_builtin_plugins.py --base http://127.0.0.1:8000 \
  --username admin --password password123
```

## 现有插件

| 插件 | 类型 | 权限声明 | 说明 |
| --- | --- | --- | --- |
| `echo` | optional | 无 | 回显输入，验证沙箱与 JSON Lines 协议 |
| `http-fetch` | optional | `http:outbound:*` | 经宿主代理取 URL，演示出站权限与 SSRF 拦截 |

## 插件包结构

```
<plugin-name>/
├─ manifest.json      # 见《插件系统说明书》§4
└─ main.py            # 入口，stdin/stdout JSON Lines 协议（§6.1）
```

更完整的开发指南（权限模型、沙箱协议、生效优先级、API、安全）见
[`docs/plugin-system-guide.md`](../../docs/plugin-system-guide.md)。
