# 内置插件目录

本目录用于存放官方内置 / 管理员上传的插件包，容器中以**只读**方式挂载给插件沙箱（见设计说明书 §6）。

规划中的内置插件：

| 插件 | 类型 | 权限声明 | 说明 |
| --- | --- | --- | --- |
| `web-search` | optional | `http:outbound:search.*` | 联网搜索，结果以不可信内容注入 |
| `code-runner` | optional | `subprocess`, 只读文件系统, 无网络 | 隔离子进程运行 Python 片段 |
| `doc-parse` | optional | `fs:read:uploads` | 解析 PDF / DOCX 附件 |

> M3 里程碑实现插件系统与沙箱宿主，此处先占位。

每个插件包结构：

```
<plugin-name>/
├─ manifest.json      # 见设计说明书 §6.1
└─ main.py            # 入口，stdin/stdout JSON 行协议
```
