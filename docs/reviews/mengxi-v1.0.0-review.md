# 梦溪畅谈 v1.0.0 — 代码审查与后续处理清单

| 项目 | 内容 |
| --- | --- |
| 审查对象 | mengxi-llm-chat v1.0.0（首个正式版本，M1–M5） |
| 审查日期 | 2026-10-07 |
| 审查范围 | 仓库快照（后端源码、迁移、测试、部署、文档）+ 架构图 |
| 总体结论 | 工程质量扎实，里程碑全部落地；发现 **2 个应热修的安全项**，建议尽快发布 v1.0.1 |

---

## 1. 总体评价（摘要）

- 五个里程碑全部落地，与《需求分析 v2.0》《设计说明书》逐条对应；
- 后端 23 个测试文件、Playwright E2E + 自动截图、Alembic 迁移、fakeredis 测试基建；
- GHCR 发布签名、K8s + Sealed Secrets、git-cliff 自动 CHANGELOG 齐全；
- 架构分层干净：Web 应用 → API 编排 → 运行时集成（沙箱/上游）→ 持久化 → 安全策略；插件沙箱无 DEK / 数据库访问权这条红线已守住；
- 文档套件完整：设计说明书、部署手册、用户手册、插件开发指南、测试指南。

---

## 2. 问题清单（按优先级）

### P0-1 主密钥端点未鉴权 🔴 安全，建议热修

| 项 | 内容 |
| --- | --- |
| 位置 | `src/backend/app/api/admin.py` — `/api/admin/kek/initialize`、`/api/admin/kek/unlock`、`/api/admin/kek/lock` |
| 现象 | 三个端点**未挂 `Depends(require_admin)`**；同文件的恢复码端点（`/recovery-codes/*`）均有鉴权，唯独主密钥端点没有 |
| 影响 | ① 任何能访问服务的人可调用 `POST /api/admin/kek/lock` 锁死主密钥 → 全站密文业务不可用（拒绝服务）；② `unlock` 暴露给未认证方，扩大口令爆破面 |
| 修法 | 为三个端点添加 `_: object = Depends(require_admin)`；注意**锁定状态下的自锁死问题**——建议保留一个"管理员已登录即可解锁"的路径，不要把解锁端点做成"KEK 锁定时拒绝一切管理操作"（当前会话鉴权不依赖 KEK，管理员登录不受锁影响，直接加鉴权即可） |
| 验证 | 未登录调用三个端点应返回 401；普通用户调用应返回 403；管理员调用正常 |

### P0-2 口令错误锁定阈值声明了但未生效 🔴 安全，建议热修

| 项 | 内容 |
| --- | --- |
| 位置 | `Settings.kek_lock_threshold` / `Settings.kek_lock_seconds`（`app/core/config.py`）、`.env.example`；消费端缺失——`LocalKekProvider.unlock()` 未做任何失败计数 |
| 现象 | 配置项存在且写进了文档（"连续错 5 次锁 15 分钟"），但代码中无任何地方读取这两个值 |
| 影响 | 档 A 主口令可被无限次离线/在线爆破；需求文档 §12.8 的验收标准（"连续错误口令触发锁定"）无法达成 |
| 修法 | 在 `unlock` 流程（或 `KekProvider.unlock` 包装层）加入基于 Redis 的失败计数：键 `lock:kek:{ip}`（或 `lock:kek:{user_id}`），达到阈值后拒绝并返回剩余锁定时长；计数在成功解锁时清零。可在 `app/api/admin.py` 的 unlock 端点内实现，避免改动 provider 抽象 |
| 验证 | 连续 N 次错误口令后第 N+1 次应返回 429/403 并提示锁定；锁定期间即使口令正确也拒绝；成功后计数清零 |

### P1-3 档 C（KMS）仍为占位 🟡 文档口径需对齐

| 项 | 内容 |
| --- | --- |
| 位置 | `app/core/crypto/kek.py` — `KmsKekProvider.initialize/unlock` 均 `raise NotImplementedError` |
| 现象 | 设计说明书将档 C 列入 M5；CHANGELOG 写"M1–M5 全部落地"，二者口径不一致 |
| 影响 | 低（单实例自部署档 A/B 够用）；但多实例部署者按文档选择档 C 会直接踩到 NotImplementedError |
| 修法 | 二选一：① 实现档 C（AWS KMS / Vault，参照 `KekProvider` 协议，env.py 的 `build_kek_provider` 已留好分支）；② 短期内在《设计说明书》§3.3 与 CHANGELOG 中把档 C 标注为"路线图（未实现）" |
| 验证 | 若实现：档 C 配置下启动、加解密、轮换全链路测试 |

### P1-4 匿名访问开关是死配置 🟡 文档口径需对齐

| 项 | 内容 |
| --- | --- |
| 位置 | `Settings.allow_anonymous`（`config.py`）、`.env.example`；聊天路由统一走 `get_current_user` |
| 现象 | 配置项存在，但匿名使用公有 Key 的代码路径未实现 |
| 影响 | 低（默认 `false`）；但部署者置 `true` 后会发现"什么也没发生" |
| 修法 | 二选一：① 实现匿名路径（会话级身份 + IP 限流 + 可选验证码，需求 §3 权限矩阵已定义）；② 从配置、`.env.example`、部署手册 §5 中移除该开关，待实现时再加 |
| 验证 | 若实现：开启后未登录可聊天，关闭后 401 |

### P2-5 `GET /api/keys` 的 pool 参数对非管理员行为意外 🟢 小修正

| 项 | 内容 |
| --- | --- |
| 位置 | `app/api/keys.py` — `list_keys` |
| 现象 | 非管理员带 `pool=public` 请求时静默回退为返回其私有 Key（落到最后的 `return` 分支），既不报错也不返回公有池 |
| 修法 | 非管理员显式请求 `pool=public` 时返回 403 或空列表 + 说明；建议：`if not user.is_admin and pool == "public": raise Forbidden(...)` |
| 验证 | 普通用户 `pool=public` → 403；`pool=private` 或不带 → 正常 |

### P2-6 `messages.blind_index` 疑似遗留字段 🟢 清理

| 项 | 内容 |
| --- | --- |
| 位置 | `models/conversation.py`（`blind_index` 列）、迁移 `0003_conversations.py`；实际指纹均写入 `message_keywords` 表 |
| 现象 | 双份存储，且 `blind_index` 似乎从未被写入（`append_message` 只写 `keyword_repo`） |
| 修法 | 后续迁移中删除该列；注意设计说明书 §10.1 表格同步更新 |
| 验证 | 迁移后全文搜索仍正常，表结构无该列 |

### P2-7 中英文标识不一致 🟢 文档统一

| 项 | 内容 |
| --- | --- |
| 位置 | 仓库名 / 包名 / GHCR 镜像为 `mengxi-llm-chat`；早期《需求分析 v2.0》《可行性分析》写作 `mengxi-llm-talk` |
| 修法 | 统一为 `mengxi-llm-chat`，修订两份历史文档的抬头与正文（属文档勘误，不改代码） |

---

## 3. 需求验收标准对照（需求文档 §12）

| # | 验收标准 | 现状 | 对应测试 |
| --- | --- | --- | --- |
| 1 | 库内无明文 Key / 消息 | ✅ 信封加密 + AAD + Base64 密文 | `test_crypto.py` |
| 2 | 管理员无法取私有 Key / 他人对话明文 | ✅ 仓储层 owner 强制 + 无明文接口 | `test_keys_api.py` / `test_conversation_api.py` |
| 3 | 内网目标 100% 拦截（含重定向） | ✅ 五重校验（协议/解析/固定 IP/对端/逐跳） | `test_ssrf.py` |
| 4 | 六维限流独立 + 日配额跨 Key 汇总 | ✅ Lua 原子计数 + 用户/组两级配额 | `test_ratelimit.py` / `test_three_tier.py` |
| 5 | 回退：成功 + `fallback_to_public=1` + 前端弹窗 | ✅ meta 事件携带 fallback，前端提示 | `test_chat_api.py` |
| 6 | 全局插件无禁用入口 + 优先级链 | ✅ `resolve_state` 四级优先级 | `test_plugin_domain.py` / `test_plugins_api.py` |
| 7 | 沙箱越权 / 超时 / 超内存均拦截 | ✅ 子进程 + rlimit + 权限裁决 | `test_plugin_domain.py` |
| 8 | 档 A 解锁 / 恢复码重置并全量轮换 / **口令锁定** | ⚠️ 前两项 ✅（`test_recovery.py`）；**口令锁定缺实现（见 P0-2）** | 需补 `test_kek_lockout.py` |
| 9 | 加密搜索命中且盲索引不可还原 | ✅ HMAC 指纹 + 2-gram | `test_blind_index.py` |

结论：9 条中 8 条已达成，第 8 条部分达成（缺口令锁定）。

---

## 4. 建议的处理顺序

### v1.0.1（热修，预计 1~2 天）

1. P0-1：kek 端点补鉴权（+ 回归测试：未登录 401 / 非管理员 403）；
2. P0-2：口令错误锁定生效（+ 新增 `test_kek_lockout.py`）；
3. 顺带可做：P2-5（keys pool 参数行为）。

### v1.0.2 或文档修订（口径对齐，预计 1 天）

4. P1-3：档 C 标注"路线图"或实现；
5. P1-4：匿名开关标注"未实现"或移除；
6. P2-6 / P2-7：遗留列清理与文档统一。

### 1.1 路线图（后续版本）

- WASM 沙箱（更高隔离度）；
- E2EE 敏感会话模式（设计 §4.8.3）；
- 审计自动归档至对象存储；
- 档 C（KMS）正式接入（若 v1.0.2 选择仅标注）。

---

## 5. 附：P0-1 / P0-2 修复要点提示

**P0-1（鉴权）**——`admin.py` 中三个端点签名改为：

```python
@router.post("/kek/unlock")
async def kek_unlock(
    body: PassphraseRequest,
    request: Request,
    _: object = Depends(require_admin),   # 新增
) -> dict:
    ...
```

**P0-2（锁定）**——unlock 端点内前置检查（示意）：

```python
lock_key = f"lock:kek:{request.client.host if request.client else 'unknown'}"
failures = await redis_store.get_int(lock_key)
if failures >= settings.kek_lock_threshold:
    raise Forbidden(f"尝试次数过多，请 {settings.kek_lock_seconds // 60} 分钟后再试")
try:
    await provider.unlock(body.passphrase)
except WrongPassphrase:
    await redis_store.incr(lock_key, ttl=settings.kek_lock_seconds)
    raise
await redis_store.delete(lock_key)
```

> 注意：锁定计数应同时支持按账号与按 IP 两个维度（防分布式爆破时 IP 轮换）；解锁成功后必须清零计数。

---

（完）
