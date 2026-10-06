# 梦溪畅谈 — 使用自有密钥本地测试指南

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v1.0 |
| 日期 | 2026-10-06 |
| 适用代码 | M1（密钥/调度/聊天）+ M2（限流/熔断/审计） |
| 相关文档 | 《设计说明书》§4.1/§4.2/§4.5、《需求分析文档》§12 |

本指南说明如何用**你自己的密钥**在本地验证梦溪畅谈的三条关键路径：

1. **真钥** → 正常流式对话；
2. **有效 base_url + 假钥** → 上游鉴权失败 → 熔断 → 回退公有真钥；
3. **无效 base_url + 假钥** → 创建密钥阶段即被 SSRF 防护拒绝。

> 本指南**不包含任何真实密钥**。文中 `sk-xxxxxxxx…xxxx` 均为占位符。

---

## 1. 安全须知（务必先读）

- **绝不提交真实密钥**。仓库已通过 `.gitignore` 忽略 `apikeys/` 目录与 `*.db`，请把密钥文件只放在该目录内。
- 文档、终端记录、截图、Issue 中一律脱敏，保留前 3~4 位与后 4 位，中段用 `x` 屏蔽：
  ```
  sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxabcd
  ```
- 密钥在本应用数据库中为 **AES-256-GCM 密文**，但仍建议：
  - 使用**专用/可吊销**的测试密钥，不要用生产主钥；
  - 测试结束后到上游服务商**吊销或轮换**该密钥；
  - 本地 `dev.db`（含密文）与 `devdata/`（含 DEK 密文）不要外发。
- 主密钥（`MENGXI_MASTER_KEY_B64`）与 DEK 文件互相绑定：**更换主密钥后必须清空数据目录**，否则会报 `ciphertext authentication failed`（见 §10）。

---

## 2. 密钥分类与用途

| 类型 | base_url | 密钥内容 | 预期结果 |
| --- | --- | --- | --- |
| 真钥 | 上游真实地址，如 `https://api.deepseek.com` | 有效密钥 | 200 流式输出 |
| 有效 base_url 假钥 | 上游真实地址 | 伪造/错误密钥 | 上游 401/403 → 记录 502 审计 → 熔断 → 回退公有真钥 |
| 无效 base_url 假钥 | 无法解析的域名，如 `https://api.example-invalid.test` | 任意 | 创建密钥时被拒：`400 / 40010` |

支持任意 OpenAI 兼容上游（OpenAI、DeepSeek、Ollama 等）。模型名需与所选上游匹配，例如 DeepSeek 用 `deepseek-chat`。

---

## 3. 目录与 CSV 格式

建议的本地目录结构（`apikeys/` 已被 gitignore）：

```
apikeys/
├─ real-keys/
│  └─ real.csv                    # 真钥
└─ fake-keys/
   ├─ valid-baseurl.csv           # 假钥 + 有效 base_url
   └─ invalid-baseurl.csv         # 假钥 + 无效 base_url
```

CSV 为两列：`baseurl,apikey`（首行为表头）。**模板（占位，请勿把真钥提交进仓库）：**

```csv
baseurl,apikey
https://api.deepseek.com,sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

```csv
baseurl,apikey
https://api.deepseek.com,sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
https://api.deepseek.com,xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

```csv
baseurl,apikey
https://api.example-invalid.test,sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
https://api.another-invalid.test,xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 4. 启动本地实例

准备（首次）：

```bash
python -m venv .venv
# Windows Git Bash:
source .venv/Scripts/activate
pip install -r src/backend/requirements.txt
```

启动（本地实测推荐 SQLite + 无 Redis 降级模式）：

```bash
cd src/backend

export MENGXI_KEK_PROFILE=B
export MENGXI_MASTER_KEY_B64="$(python -c 'import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
export MENGXI_DATABASE_URL="sqlite+aiosqlite:///./dev.db"
export MENGXI_AUTO_CREATE_TABLES=true
export MENGXI_SESSION_SECRET="dev-secret-change-me"
export MENGXI_DATA_DIR=./devdata
# 无 Redis 时可指向任意端口：限流会“降级放行”（见 §9）
export MENGXI_REDIS_URL="redis://127.0.0.1:6399/0"

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

> `MENGXI_MASTER_KEY_B64` 是随机主密钥：**每次重启都变**。若要保留已播种的密钥，重启时必须沿用同一个值（或改用档 A 口令派生），否则密钥密文无法解开。

生产/完整模式请改用 PostgreSQL + Redis，并参考《设计说明书》§13。

---

## 5. 播种密钥

使用仓库内脚本 `scripts/seed_keys.py`（不包含任何密钥，仅读取你指定的 CSV）：

```bash
python scripts/seed_keys.py \
  --base http://127.0.0.1:8000 \
  --username alice --password password123 \
  --csv ../../apikeys/real-keys/real.csv \
  --model deepseek-chat
```

参数说明：

| 参数 | 说明 |
| --- | --- |
| `--base` | 本地实例地址 |
| `--username/--password` | 首次自动注册，已存在则登录 |
| `--csv` | 密钥 CSV 路径（相对当前目录） |
| `--model` | 绑定到该密钥的模型名（如 `deepseek-chat`） |
| `--public` | 播种为公有 Key（需管理员账号） |
| `--weight` | 调度权重（默认 1） |

---

## 6. 场景 A — 真钥：正常流式对话

```bash
# 播种真钥（私有）
python scripts/seed_keys.py --base http://127.0.0.1:8000 \
  --username alice --password password123 \
  --csv ../../apikeys/real-keys/real.csv --model deepseek-chat

# 登录并对话
curl -s -c /tmp/alice.txt -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"password123"}' >/dev/null

curl -s -N -b /tmp/alice.txt -X POST http://127.0.0.1:8000/api/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"用一句话介绍你自己"}]}'
```

**预期**（节选）：

```
event: meta
data: {"model": "deepseek-chat", "pool": "private", "fallback": false, "key_id": "…"}

event: delta
data: {"text": "你好"}

event: delta
data: {"text": "！"}

event: usage
data: {"tokens_in": 7, "tokens_out": 20}

event: done
data: {"finish_reason": "stop"}
```

---

## 7. 场景 B — 有效 base_url 假钥：熔断 + 回退公有真钥

需要一个**公有真钥**作为回退目标，由管理员账号播种：

```bash
# 1) 注册管理员并提升（本地库直接改角色）
curl -s -X POST http://127.0.0.1:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"password123"}' >/dev/null
python -c "import sqlite3;c=sqlite3.connect('dev.db');c.execute(\"UPDATE users SET role='admin' WHERE username='admin'\");c.commit();c.close()"

# 2) 公有真钥
python scripts/seed_keys.py --base http://127.0.0.1:8000 \
  --username admin --password password123 \
  --csv ../../apikeys/real-keys/real.csv --model deepseek-chat --public

# 3) 普通用户播种“有效 base_url 的假钥”
python scripts/seed_keys.py --base http://127.0.0.1:8000 \
  --username bob --password password123 \
  --csv ../../apikeys/fake-keys/valid-baseurl.csv --model deepseek-chat

# 4) bob 对话
curl -s -c /tmp/bob.txt -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"bob","password":"password123"}' >/dev/null

curl -s -N -b /tmp/bob.txt -X POST http://127.0.0.1:8000/api/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"用两个字回答"}]}'
```

**预期**：私有假钥鉴权失败（内部记为 502 并触发熔断），随后回退到公有真钥：

```
event: meta
data: {"model": "deepseek-chat", "pool": "public", "fallback": true, "key_id": "…"}

event: delta
event: usage
event: done
```

查看审计可见失败与回退记录：

```bash
curl -s -b /tmp/bob.txt "http://127.0.0.1:8000/api/audit?limit=10"
```

预期节选：

| status | fallback_to_public | 说明 |
| --- | --- | --- |
| 200 | true | 回退到公有真钥的成功请求 |
| 502 | false | 假钥鉴权/调用失败（逐个尝试） |

---

## 8. 场景 C — 无效 base_url 假钥：SSRF 拦截

```bash
python scripts/seed_keys.py --base http://127.0.0.1:8000 \
  --username bob --password password123 \
  --csv ../../apikeys/fake-keys/invalid-baseurl.csv --model deepseek-chat
```

**预期**：创建阶段即被拒绝，返回 `400`，错误码 `40010`：

```
[400] invalid-baseurl-1 (https://api.example-invalid.test)
{"code":40010,"message":"无法解析主机: api.example-invalid.test","data":null}
```

SSRF 防护还会拒绝内网/回环/链路本地（含云元数据 `169.254.169.254`）与非 https 目标，详见《设计说明书》§4.4。

---

## 9. 限流与配额（可选）

三层兜底限流默认关闭，可通过环境变量启用：

```bash
export MENGXI_USER_RATE_LIMITS='{"rpm": 2, "rpd": 1000}'
export MENGXI_IP_RATE_LIMITS='{"rpm": 30}'
```

Keys 级限流在创建密钥时按条配置（`rate_limits` 字段，六维 RPM/RPH/RPD/TPM/TPH/TPD，0=不限）。

- **有 Redis**：限流精确生效，超限返回 SSE `event: error` 且 `code: 42900` / `42901`（配额）。
- **无 Redis**：系统**降级放行**已登录用户（不因限流设施故障拒绝服务），此时上述限制不生效。要实测限流，请启动 Redis 并把 `MENGXI_REDIS_URL` 指向它。

并发精度参考：200 并发请求、`rpm=10` 时恰好放行 10 个（原子 Lua 脚本，误差 0%）。

---

## 10. 清理与常见问题

清理：

```bash
rm -f dev.db
rm -rf devdata
# 测试完成后，请到上游服务商吊销 / 轮换测试密钥
```

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `ciphertext authentication failed` | 主密钥变了但沿用了旧 `devdata/` | 清空 `devdata`，或沿用同一 `MENGXI_MASTER_KEY_B64` |
| 创建密钥报 `400/40010 无法解析主机` | base_url 域名不可解析 | 检查域名；这是 SSRF 防护的预期行为 |
| 聊天返回 `event: error code 503 密钥池耗尽` | 没有可用 Key 或模型不匹配 | 确认已播种密钥且 `models` 含所用模型 |
| 聊天返回 `event: error 上游调用失败` | 上游不可达或密钥无效 | 检查网络与密钥；观察是否发生回退 |
| 重启后密钥全部无法使用 | 主密钥每次随机 | 固定 `MENGXI_MASTER_KEY_B64` 或使用档 A 口令 |

---

## 11. 附：密钥生命周期速览

```
创建（校验 SSRF）→ AES-256-GCM 加密落库（KEK 包裹 DEK，DEK 加密数据）
  → 调度（私有优先 → 回退公有）
  → 转发（连接时再次校验对端 IP）
  → 结算（限流/配额/审计，写 fallback_to_public）
  → 删除（仅 owner / 管理员）
```

参见《设计说明书》§3（加密）、§4.1（密钥管理）、§4.2（调度）、§5（限流配额）。
