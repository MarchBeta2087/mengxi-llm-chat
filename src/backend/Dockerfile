# 梦溪畅谈（mengxi-llm-chat）后端镜像
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 系统依赖：argon2/cryptography 使用 manylinux wheel，通常无需编译工具
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# 安装依赖：
# - 先升级构建工具链（修复 setuptools 等已知漏洞）
# - 强制传递依赖的已修复版本（urllib3 / msgpack）
# - 运行时不需 pip/setuptools/wheel，移除之（缩小攻击面与镜像体积）
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir --upgrade "urllib3>=2.8.0" "msgpack>=1.2.1" \
    && (python -m pip uninstall -y pip setuptools wheel || true) \
    && rm -rf /root/.cache /tmp/*

COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

# 非 root 运行
RUN useradd --create-home --uid 10001 mengxi \
    && mkdir -p /data/keys /data/plugins \
    && chown -R mengxi:mengxi /app /data
USER mengxi

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
