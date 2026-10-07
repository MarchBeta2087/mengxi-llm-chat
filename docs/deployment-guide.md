# 梦溪畅谈 — 部署与运维手册

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v1.0 |
| 日期 | 2026-10-06 |
| 适用版本 | M1–M5 |
| 相关文档 | 《设计说明书》§10/§13、《使用自有密钥本地测试指南》、《插件系统说明书》 |

本手册面向**部署者与运维人员**，覆盖：Docker Compose 一键部署、生产 TLS、配置项、数据备份与恢复、升级、故障排查与安全加固。

---

## 1. 部署形态

```
浏览器 ──HTTPS──▶ TLS 反代（可选）──▶ web(Nginx+SPA) ──/api──▶ app(FastAPI)
                                                                  ├─▶ PostgreSQL
                                                                  ├─▶ Redis
                                                                  ├─▶ 插件沙箱子进程
                                                                  └─▶ 上游 LLM（经 SSRF 校验）
```

| 服务 | 镜像/构建 | 说明 |
| --- | --- | --- |
| `web` | `src/frontend`（Node 构建 → Nginx） | 托管 SPA，并把 `/api` 反代到 `app`（SSE 关闭缓冲） |
| `app` | `src/backend` | FastAPI + Uvicorn，加解密/调度/限流/插件 |
| `migrate` | 同 `app` | 一次性执行 `alembic upgrade head` |
| `postgres` | `postgres:17-alpine` | 业务库（密文）与审计 |
| `redis` | `redis:8-alpine` | 限流/配额/熔断/缓存 |

第一版推荐单机 Compose；多实例扩展见 §11。

---

## 2. 前置条件

- Docker 24+ 与 Docker Compose v2
- 2 vCPU / 4 GB 内存起（4C8G 更佳）
- （生产）域名与 TLS 证书

---

## 3. 快速开始（Docker Compose）

### 3.1 准备环境变量

```bash
cd src/backend
cp .env.example .env
# 生成档 B 主密钥（32 字节 base64）：
python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

把输出填入 `src/backend/.env` 的 `MENGXI_MASTER_KEY_B64=`，并设置强随机的
`MENGXI_SESSION_SECRET`（务必修改默认值）。主密钥档位选择：

| 档 | 变量 | 适用 |
| --- | --- | --- |
| A | `MENGXI_KEK_PROFILE=A` | 最高安全：口令派生，重启需解锁；提供恢复码 |
| B | `MENGXI_KEK_PROFILE=B` + `MENGXI_MASTER_KEY_B64=…` | 轻量部署：接受"读到密钥文件即可解密" |
| C | `MENGXI_KEK_PROFILE=C` + KMS 配置 | 生产/多实例（M5 后接入） |

### 3.2 启动

```bash
cd src/deploy
docker compose up -d --build
docker compose ps
```

访问 `http://<主机>:8080`，注册第一个账号。

### 3.3 管理员与恢复码

1. 注册账号后，将其角色提升为管理员（首次可用数据库一次性操作）：
   ```bash
   docker compose exec postgres psql -U mengxi -d mengxi \
     -c "UPDATE users SET role='admin' WHERE username='<你的用户名>';"
   ```
2. 档 A：初始化主密钥并**立即抄录恢复码**（仅展示一次）：
   ```bash
   curl -X POST http://<主机>:8080/api/admin/kek/initialize \
     -H 'Content-Type: application/json' -d '{"passphrase":"<强口令>"}'
   ```
3. 档 B：启动即已解锁，恢复码可通过
   `POST /api/admin/recovery-codes/regenerate` 生成并抄录。

### 3.4 安装内置插件（可选）

```bash
cd src/backend
python scripts/install_builtin_plugins.py --base http://<主机>:8080 \
  --username <admin> --password <password>
```

---

## 4. 生产部署（TLS）

推荐在 `web` 之前再放一层 TLS 终止（云 LB / Caddy / Traefik / Nginx）。
仓库提供 `src/deploy/nginx.conf` 作为 Nginx 示例（终止 TLS 并转发到 `web`）。

要点：

- **SSE 必须关闭缓冲**：`proxy_buffering off;`，并放大 `proxy_read_timeout`;
- 传递真实 IP：`X-Forwarded-For`，且只信任受控代理链（影响 IP 级限流）；
- `web` 已处理 SPA 路由回退与 `/api` 反代，外层只需整体转发。

---

## 5. 配置项（环境变量）

前缀统一 `MENGXI_`（见 `src/backend/.env.example`）：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `MENGXI_ENVIRONMENT` | development | `production` 时会话 Cookie 强制 Secure |
| `MENGXI_DATA_DIR` | ./data | 数据目录（含 `keys/` 与 `plugins/`） |
| `MENGXI_KEK_PROFILE` | A | 主密钥档位 A/B/C |
| `MENGXI_MASTER_KEY_B64` | — | 档 B 主密钥 |
| `MENGXI_DATABASE_URL` | postgresql+asyncpg://… | 数据库 |
| `MENGXI_REDIS_URL` | redis://localhost:6379/0 | Redis |
| `MENGXI_SESSION_SECRET` | dev-insecure… | **生产必改**，会话签名 |
| `MENGXI_FALLBACK_TO_PUBLIC` | true | 私有 Key 失败回退公有 |
| `MENGXI_USER_RATE_LIMITS` | 空 | 用户级兜底限流（JSON） |
| `MENGXI_IP_RATE_LIMITS` | 空 | IP 级兜底限流（JSON） |
| `MENGXI_DOMAIN_WHITELIST` | 空 | SSRF 域名白名单 |
| `MENGXI_ENCRYPTED_SEARCH` | false | 加密会话盲索引全文检索 |
| `MENGXI_AUDIT_RETENTION_DAYS` | 90 | 审计保留天数 |
| `MENGXI_RECOVERY_CODE_COUNT` | 8 | 恢复码数量 |

---

## 6. 数据、备份与恢复

### 6.1 必须备份的三样

| 对象 | 位置 | 丢失后果 |
| --- | --- | --- |
| PostgreSQL 数据 | 卷 `pgdata` | 用户、密文、审计丢失 |
| DEK 密文文件 | `deploy/data/keys/dek.key.enc` | 无法解密 API Key |
| 主密钥/口令 + 恢复码 | 档 B 的 `.env`；档 A 的口令与恢复码 | **丢失则所有密文永久不可恢复** |

> 备份策略：数据库定期 `pg_dump`；`data/keys` 与恢复码**离线、异地**保存。

### 6.2 数据库备份 / 恢复

```bash
# 备份
docker compose exec -T postgres pg_dump -U mengxi mengxi > backup-$(date +%F).sql

# 恢复（先停 app/web 写入）
docker compose stop app web
docker compose exec -T postgres psql -U mengxi -d mengxi < backup-2026-10-06.sql
docker compose start app web
```

### 6.3 整机迁移

1. 复制数据库备份 + `deploy/data/` 目录；
2. 在新机写入相同的 `MENGXI_MASTER_KEY_B64`（档 B）或准备口令/恢复码（档 A）；
3. `docker compose up -d --build`（`migrate` 会自动升级表结构）。

---

## 7. 升级

```bash
git pull
cd src/deploy
docker compose build
docker compose up -d          # migrate 服务先执行 alembic upgrade head
```

- 迁移由 `migrate` 服务在 `app` 之前完成（`service_completed_successfully`）；
- 出问题可回滚镜像，但**数据库迁移不自动回滚**，务必先备份；
- 主密钥轮换：见《设计说明书》§3.6（新写新代、旧读旧代、后台迁移）。

### 7.1 数据库大版本升级（PostgreSQL 15 → 17）

PostgreSQL 主版本间**数据目录不兼容**，直接更换镜像会启动失败。必须采用导出/导入：

```bash
# 1) 旧版本下导出
docker compose exec -T postgres pg_dump -U mengxi mengxi > backup.sql
# 2) 停止并移除旧数据卷（卷名通常为 <compose 项目名>_pgdata）
docker compose down
docker volume rm mengxi_pgdata
# 3) 确认 compose 中 postgres 镜像已更新（本例为 postgres:17-alpine）
# 4) 启动新数据库并导入
docker compose up -d postgres
docker compose exec -T postgres psql -U mengxi -d mengxi < backup.sql
docker compose up -d
```

> 全新部署无需此步骤。Redis 7 → 8 通常可直接替换镜像（持久化格式向后兼容）。

---

## 8. 日常运维

| 操作 | 命令/接口 |
| --- | --- |
| 健康检查 | `GET /healthz`（`web` 已透传） |
| 查看日志 | `docker compose logs -f app` |
| 审计查询 | `GET /api/admin/audit`（可按 user/key/status/fallback/时间过滤） |
| 主密钥状态 | `GET /api/admin/kek` |
| 解锁（档 A） | `POST /api/admin/kek/unlock {"passphrase":"…"}` |
| 锁定（档 A） | `POST /api/admin/kek/lock` |
| 重生成恢复码 | `POST /api/admin/recovery-codes/regenerate`（旧码全部失效） |
| 用量/配额 | 管理后台（用户/用户组）或 `/api/admin/users` |

**运维红线**：任何日志、截图、工单中都不得出现明文 Key、主口令或恢复码原值；排障需要时只引用脱敏形式。

---

## 9. 安全加固清单

- [ ] `MENGXI_SESSION_SECRET` 已改为强随机值
- [ ] `MENGXI_ENVIRONMENT=production`（Cookie Secure）
- [ ] 主密钥与恢复码离线备份，且**不在**数据库/镜像/日志中
- [ ] 数据库口令改为强口令（`POSTGRES_PASSWORD`）
- [ ] 仅暴露 `web`（及外层 TLS），`app/postgres/redis` 不对外
- [ ] 反代只信任受控代理链（防伪造 `X-Forwarded-For` 绕过 IP 限流）
- [ ] 定时数据库备份并**演练恢复**
- [ ] 依赖与镜像定期更新（CI 已含 lint/测试/镜像构建）

---

## 10. 故障排查

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| 启动报 `ciphertext authentication failed` | 主密钥与既有 `data/keys` 不匹配 | 恢复正确主密钥，或清空数据目录（会丢密文） |
| 归档/聊天返回 `50301 主密钥未解锁` | 档 A 重启后未解锁 | `POST /api/admin/kek/unlock` |
| 登录后立即失效 | `MENGXI_SESSION_SECRET` 变更或未设置 | 固定该值并重启 |
| 限流失效/整体放行 | Redis 不可用（降级放行） | 检查 `redis` 服务 |
| SSE 聊天无输出或卡顿 | 反代缓冲未关闭 | 设 `proxy_buffering off` |
| 创建 Key 报 `400/40010` | base_url 不可解析或命中私网 | 属 SSRF 预期防护 |
| 首次启动无表 | `migrate` 未成功 | 查看 `docker compose logs migrate` |

---

## 11. 多实例与水平扩展

- **状态外置**：限流/配额/熔断已在 Redis；会话目前为签名 Cookie（无状态），可直接多副本；
- **主密钥**：多实例需统一 KEK，建议档 C（KMS）或档 B + 相同密钥；
- **DEK 缓存**：多实例各自缓存 DEK_conv，轮换时需同时失效（演进方向：Redis 广播失效）；
- **插件沙箱**：可拆分为独立服务/容器以强化隔离；
- **数据库**：使用托管 PostgreSQL 或主从；
- 加解密为 AES-NI 轻量操作，不构成扩展瓶颈。

---

（完）
