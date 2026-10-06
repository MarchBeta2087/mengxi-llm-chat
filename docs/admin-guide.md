# 梦溪畅谈 — 管理员手册

| 项目 | 内容 |
| --- | --- |
| 适用对象 | 管理员（`role=admin`） |
| 文档版本 | v1.0 |
| 相关文档 | [用户手册](user-guide.md)、[部署与运维手册](deployment-guide.md)、[插件系统说明书](plugin-system-guide.md)、[CI/CD 指南](cd-guide.md) |

本手册面向管理员，覆盖：初始设置、公有 Key、用户与用户组、配额、插件、审计、主密钥与恢复码，以及接口速查。

---

## 1. 权限概览

| 能力 | 说明 |
| --- | --- |
| 公有 Key 管理 | 配置全员可用的上游 Key（脱敏展示） |
| 用户与用户组 | 封禁、设置日配额、分组 |
| 插件管理 | 上传、设类型（全局/可选）、默认状态、按用户组配置 |
| 审计 | 检索全部调用记录（含回退标记） |
| 主密钥 | 查看状态、解锁/锁定、初始化、恢复码管理 |
| 系统策略 | 匿名访问、回退开关、域名白名单等（环境变量） |

> **隐私红线**：管理员**无法**查看任何用户的私有 Key 明文或对话明文。

---

## 2. 初始设置

### 2.1 将账号设为管理员

首个管理员需在数据库中提升（无内置引导）：

```bash
docker compose exec postgres psql -U mengxi -d mengxi \
  -c "UPDATE users SET role='admin' WHERE username='<你的用户名>';"
```

重新登录后即可看到 **🛡 管理后台**。

### 2.2 初始化主密钥（档 A）

档 A（口令派生）首次启动后需初始化，并**立即抄录恢复码（仅展示一次）**：

```bash
curl -s -X POST http://<站点>/api/admin/kek/initialize \
  -H 'Content-Type: application/json' \
  -d '{"passphrase":"<强口令>"}'
# 响应 data.recovery_codes 为 8 个恢复码，务必离线保存
```

档 B（环境变量主密钥）启动即已解锁，无需此步。

---

## 3. 公有 Key 管理

公有 Key 由管理员维护、全员可用、调度优先级低于用户私有 Key。

- **界面**：管理后台 → **公有 Key** 标签页（新增/测试/启停/删除，含六维限流字段）；
- **接口**：使用与用户相同的 `/api/keys`，以管理员身份创建时置 `is_public: true`。

```bash
curl -s -b admin-cookies.txt -X POST http://<站点>/api/keys \
  -H 'Content-Type: application/json' \
  -d '{
    "provider_name": "官方主通道",
    "api_key": "sk-xxxxxxxx",
    "base_url": "https://api.openai.com/v1",
    "models": ["gpt-4o", "gpt-4o-mini"],
    "rate_limits": {"rpm": 60, "rpd": 10000, "tpm": 150000, "tpd": 10000000},
    "is_public": true
  }'

# 查看公有池
curl -s -b admin-cookies.txt "http://<站点>/api/keys?pool=public"
```

要点：
- 新增即经 **SSRF 校验**（拒绝内网/回环/链路本地）；
- 设 `rate_limits` 六维上限，避免公有池被刷穿；
- 可用 `PATCH /api/keys/{id}` 启停或调参。

---

## 4. 用户与用户组

### 4.1 管理后台界面

**管理后台 → 用户**：

- 查看用户名/角色/状态/日配额/所属用户组；
- **改配额**：设置该用户每日 Token 上限（0 = 不限）；
- **封禁/解封**：封禁后无法登录；
- **用户组**：下拉选择将用户加入某组（可清空）。

**管理后台 → 用户组**：创建、**改名**、**设置组配额**；组内插件策略见「插件」标签页。

### 4.2 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/admin/users` | 用户列表 |
| PATCH | `/api/admin/users/{id}` | `daily_quota_tokens` / `status` / `role` / `group_id` |
| GET | `/api/admin/groups` | 用户组列表 |
| POST | `/api/admin/groups` | 创建：`{"name":"研发组","daily_quota_tokens":1000000}` |
| PATCH | `/api/admin/groups/{id}` | 改名 / 改组配额 |

示例：设置用户配额

```bash
curl -s -b admin-cookies.txt -X PATCH http://<站点>/api/admin/users/<uid> \
  -H 'Content-Type: application/json' -d '{"daily_quota_tokens": 2000000}'
```

---

## 5. 配额与限流策略

三层兜底限流（**环境变量配置**，见 §9）：

```
Key 级六维  →  用户级  →  IP 级
```

- **Key 级**：每条 Key 的 `rate_limits`（RPM/RPH/RPD/TPM/TPH/TPD）；
- **用户级/ IP 级**：`MENGXI_USER_RATE_LIMITS` / `MENGXI_IP_RATE_LIMITS`（JSON）；
- **日配额**：用户或用户组的每日 Token 上限（跨该用户所有 Key 汇总）；
- Redis 不可用时**降级放行**已登录用户（不因限流设施故障拒绝服务）。
- 超限返回 `429`（`42900` 限流 / `42901` 配额），SSE 场景以 `event: error` 下发。

建议：公有池务必设置 Key 级与用户级双重上限；匿名访问开启时叠加 IP 级限制。

---

## 6. 插件管理

### 6.1 概念

| 类型 | 生效范围 | 用户能否禁用 |
| --- | --- | --- |
| 全局插件 | 所有用户强制生效 | ❌ |
| 可选插件 | 按需 | ✅（并可被用户组策略覆盖） |

优先级：**全局 > 用户组 > 个人 > 默认状态**（详见[插件系统说明书](plugin-system-guide.md)）。

### 6.2 安装与配置

**界面**：管理后台 → **插件** 标签页：顶部为 **内置插件市场**（列出可安装的内置插件，支持查看详情与一键安装）；下方可安装自定义插件（Manifest JSON + 入口代码）、调整类型/默认状态/启停、**试运行**、以及 **用户组插件策略**。

**接口**：

```bash
# 安装：manifest + 入口代码
curl -s -b admin-cookies.txt -X POST http://<站点>/api/admin/plugins \
  -H 'Content-Type: application/json' \
  -d '{"manifest":{"name":"web-search","version":"1.0.0","type":"optional",
        "entry":"main.py","permissions":["http:outbound:search.*"],
        "default_state":"disabled","runtime":{"timeout_ms":10000,"memory_mb":128,"cpu_seconds":5}},
       "code":"<main.py 源码>"}'

# 调整类型/默认状态/启用状态
curl -s -b admin-cookies.txt -X PATCH http://<站点>/api/admin/plugins/<pid> \
  -H 'Content-Type: application/json' -d '{"type":"global"}'

# 试运行（沙箱）
curl -s -b admin-cookies.txt -X POST http://<站点>/api/admin/plugins/<pid>/invoke \
  -H 'Content-Type: application/json' -d '{"input":{"text":"hi"}}'
```

内置插件可一键安装：`python scripts/install_builtin_plugins.py --base <站点> --username admin --password <pwd>`。

### 6.3 用户组批量配置

```bash
curl -s -b admin-cookies.txt -X PUT \
  http://<站点>/api/admin/groups/<gid>/plugins/<pid> \
  -H 'Content-Type: application/json' -d '{"state":"enabled"}'
```

安全：插件运行于子进程沙箱，出站经宿主代理并受 SSRF 限制；返回值标记为不可信内容。

---

## 7. 审计日志

**管理后台 → 审计**：可按「仅看回退记录」与状态过滤，并**导出 CSV**；表格含时间、用户、Key 类型、模型、状态、tokens、是否回退。

接口：`GET /api/admin/audit`，支持过滤：

| 参数 | 说明 |
| --- | --- |
| `user_id` / `key_id` | 指定用户 / Key |
| `status` | HTTP 状态（如 200 / 502） |
| `fallback_only` | 仅回退记录 |
| `start` / `end` | 时间范围（ISO8601） |
| `limit` / `offset` | 分页 |

示例：查最近的回退记录

```bash
curl -s -b admin-cookies.txt "http://<站点>/api/admin/audit?fallback_only=true&limit=50"
```

审计默认保留 90 天（`MENGXI_AUDIT_RETENTION_DAYS`），**不含对话内容**，Key 字段脱敏。

---

## 8. 主密钥与恢复码

### 8.1 状态与解锁（档 A）

**界面**：设置 → **主密钥与恢复码**（初始化/解锁/锁定、恢复码剩余、重新生成、使用恢复码重置）。

**接口**：

```bash
curl -s -b admin-cookies.txt http://<站点>/api/admin/kek            # 状态/档位
curl -s -b admin-cookies.txt -X POST http://<站点>/api/admin/kek/unlock \
  -H 'Content-Type: application/json' -d '{"passphrase":"<口令>"}'
curl -s -b admin-cookies.txt -X POST http://<站点>/api/admin/kek/lock  # 手动锁定
```

设置页也会显示主密钥状态（档位、是否解锁）。未解锁时，创建 Key/聊天等会返回 `50301`。

### 8.2 恢复码

可在设置页的「主密钥与恢复码」面板中重新生成或使用恢复码重置；对应接口如下（恢复码仅展示一次）：

```bash
# 剩余数量
curl -s -b admin-cookies.txt http://<站点>/api/admin/recovery-codes

# 重新生成（旧码全部失效）
curl -s -b admin-cookies.txt -X POST http://<站点>/api/admin/recovery-codes/regenerate

# 使用恢复码重置主口令（档 A；用后旧码全部作废并生成新一批）
curl -s -b admin-cookies.txt -X POST http://<站点>/api/admin/recovery-codes/use \
  -H 'Content-Type: application/json' \
  -d '{"code":"XXXX-XXXX-XXXX","new_passphrase":"<新口令>"}'
```

> ⚠️ 恢复码与主口令均无法找回；全部失效则所有密文**永久不可恢复**。请离线备份。

---

## 9. 环境变量与系统设置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `MENGXI_ALLOW_ANONYMOUS` | false | 匿名访问开关（开启建议叠加 IP 限流） |
| `MENGXI_FALLBACK_TO_PUBLIC` | true | 私有 Key 失败是否回退公有 |
| `MENGXI_USER_RATE_LIMITS` | 空 | 用户级兜底限流（JSON，如 `{"rpm":60,"rpd":5000}`） |
| `MENGXI_IP_RATE_LIMITS` | 空 | IP 级兜底限流（JSON） |
| `MENGXI_DOMAIN_WHITELIST` | 空 | SSRF 可选白名单 |
| `MENGXI_ENCRYPTED_SEARCH` | false | 加密会话盲索引全文检索 |
| `MENGXI_AUDIT_RETENTION_DAYS` | 90 | 审计保留天数 |
| `MENGXI_RECOVERY_CODE_COUNT` | 8 | 恢复码数量 |

详见 [部署与运维手册](deployment-guide.md) §5。

---

## 10. 部署、升级与备份

- **部署 / TLS / 备份 / 升级 / 多实例**：见[部署与运维手册](deployment-guide.md)；
- **发布与 CD**：见 [CI/CD 指南](cd-guide.md)（GHCR 镜像、cosign 签名、SSH 部署、自动回滚）；
- **数据库大版本升级**：部署手册 §7.1（务必先备份）。

---

## 11. 故障排查

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| 创建 Key 返回 `50301` | 档 A 未解锁 | `POST /api/admin/kek/unlock` |
| 聊天 `503 密钥池耗尽` | 公有池为空或模型不匹配 | 配置公有 Key / 校正模型 |
| 大面积 `429` | 兜底限流过严 / Redis 异常 | 检查 `MENGXI_*_RATE_LIMITS` 与 Redis |
| 回退记录激增 | 私有 Key 普遍失效 | 审计排查，通知用户更新 Key |
| 镜像/端口异常 | 见部署手册 §10 | — |

---

## 12. 附录：管理员接口速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST/PATCH | `/api/admin/plugins` | 插件列表 / 安装 / 调整 |
| POST | `/api/admin/plugins/{id}/invoke` | 沙箱试运行 |
| GET/PUT/DELETE | `/api/admin/groups/{gid}/plugins[/{pid}]` | 用户组插件策略 |
| GET/PATCH | `/api/admin/users[/{id}]` | 用户列表 / 配额·封禁·分组 |
| GET/POST/PATCH | `/api/admin/groups[/{id}]` | 用户组管理 |
| GET | `/api/admin/audit` | 审计检索 |
| GET/POST | `/api/admin/kek[/initialize|unlock|lock]` | 主密钥状态与操作 |
| GET/POST | `/api/admin/recovery-codes[/regenerate|use]` | 恢复码管理 |
