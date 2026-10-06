# 多阶段构建：Node 构建静态资源 → Nginx 托管并反代 /api
FROM node:24-alpine AS build
WORKDIR /app
RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
RUN pnpm build

FROM nginx:stable-alpine
# 基础镜像 Alpine 的系统包可能存在已知漏洞（openssl/libpng/libexpat 等），
# 构建时升级到当前分支的已修复版本（Trivy 会据此清零）
RUN apk upgrade --no-cache && rm -rf /var/cache/apk/*

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
