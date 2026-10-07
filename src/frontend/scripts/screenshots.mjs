#!/usr/bin/env node
/**
 * 自动化界面截图（Playwright）。
 *
 * 一条命令完成：构建前端 → 启动「截图后端」（SQLite + 内存 Redis + 假上游）
 * → 用 newuser / admin 两个演示账号走查各页面 → 输出 PNG 到 docs/screenshots/。
 *
 * 用法：
 *   pnpm screenshots              # 构建 + 截图
 *   pnpm screenshots --skip-build # 复用已有 dist/
 *   SHOTS_PORT=8801 pnpm screenshots
 *
 * 前置：已安装 Playwright 浏览器（`pnpm exec playwright install chromium`），
 * 或设置 PW_CHANNEL=chrome|msedge 复用系统浏览器。
 */

import { spawn, spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, readdirSync, rmSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import process from 'node:process'
import { chromium } from '@playwright/test'

const __dirname = dirname(fileURLToPath(import.meta.url))
const FRONTEND_DIR = resolve(__dirname, '..')
const REPO_ROOT = resolve(FRONTEND_DIR, '..', '..')
const BACKEND_SCRIPT = resolve(REPO_ROOT, 'src', 'backend', 'scripts', 'shots_backend.py')
const DIST_DIR = resolve(FRONTEND_DIR, 'dist')
const OUT_DIR = resolve(REPO_ROOT, 'docs', 'screenshots')

const PORT = Number(process.env.SHOTS_PORT ?? 8800)
const BASE_URL = `http://127.0.0.1:${PORT}`
const CHANNEL = process.env.PW_CHANNEL // chrome | msedge | undefined
const VIEWPORT = { width: 1440, height: 900 }
const TALL_VIEWPORT = { width: 1440, height: 1200 }

const USER = { username: 'newuser', password: '12345678' }
const ADMIN = { username: 'admin', password: '12345678' }

const args = new Set(process.argv.slice(2))
const SKIP_BUILD = args.has('--skip-build')
const KEEP_OLD = args.has('--keep')

const isWindows = process.platform === 'win32'

function log(message) {
  process.stdout.write(`\u001b[36m[screenshots]\u001b[0m ${message}\n`)
}

function findPython() {
  const candidates = [
    process.env.PYTHON,
    resolve(REPO_ROOT, '.venv', isWindows ? 'Scripts/python.exe' : 'bin/python'),
    resolve(REPO_ROOT, 'src', 'backend', '.venv', isWindows ? 'Scripts/python.exe' : 'bin/python'),
  ].filter(Boolean)
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate
  }
  return isWindows ? 'python' : 'python3'
}

function runSync(command, commandArgs, cwd) {
  const result = spawnSync(command, commandArgs, {
    cwd,
    stdio: 'inherit',
    shell: isWindows,
  })
  if (result.status !== 0) {
    throw new Error(`命令失败：${command} ${commandArgs.join(' ')}`)
  }
}

function buildFrontend() {
  if (SKIP_BUILD && existsSync(resolve(DIST_DIR, 'index.html'))) {
    log('跳过构建（--skip-build），复用现有 dist/')
    return
  }
  log('构建前端（pnpm build）…')
  runSync('pnpm', ['build'], FRONTEND_DIR)
}

async function waitForHealth(timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${BASE_URL}/healthz`)
      if (res.ok) return
    } catch {
      /* 尚未启动 */
    }
    await new Promise((r) => setTimeout(r, 400))
  }
  throw new Error(`截图后端在 ${timeoutMs / 1000}s 内未就绪（${BASE_URL}/healthz）`)
}

function startBackend(python) {
  log(`启动截图后端：${python} ${BACKEND_SCRIPT} --port ${PORT}`)
  const child = spawn(
    python,
    [BACKEND_SCRIPT, '--reset', '--port', String(PORT), '--dist', DIST_DIR],
    { cwd: REPO_ROOT, stdio: ['ignore', 'pipe', 'pipe'] },
  )
  child.stdout.on('data', (chunk) => process.stdout.write(`  backend | ${chunk}`))
  child.stderr.on('data', (chunk) => process.stderr.write(`  backend | ${chunk}`))
  child.on('exit', (code) => {
    if (code && code !== 0 && !child.killed) {
      process.stderr.write(`\u001b[31m[screenshots]\u001b[0m 截图后端退出，代码 ${code}\n`)
    }
  })
  return child
}

async function login(page, { username, password }) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' })
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码').fill(password)
  await page.getByRole('button', { name: '登录' }).last().click()
  await page.getByRole('button', { name: /退出登录/ }).waitFor({ timeout: 15_000 })
}

async function logout(page) {
  await page.getByRole('button', { name: /退出登录/ }).click()
  await page.getByLabel('用户名').waitFor({ timeout: 15_000 })
}

async function shot(page, name, { viewport = VIEWPORT, fullPage = false } = {}) {
  await page.setViewportSize(viewport)
  const path = resolve(OUT_DIR, name)
  await page.screenshot({ path, fullPage })
  log(`已保存 ${name}`)
}

async function goto(page, path) {
  await page.goto(`${BASE_URL}${path}`, { waitUntil: 'networkidle' })
}

async function main() {
  mkdirSync(OUT_DIR, { recursive: true })
  if (!KEEP_OLD) {
    // 仅清理本脚本产出的 PNG，保留目录内其它资源
    for (const name of readdirSync(OUT_DIR)) {
      if (name.endsWith('.png')) rmSync(resolve(OUT_DIR, name), { force: true })
    }
  }

  buildFrontend()

  const python = findPython()
  const backend = startBackend(python)
  let browser

  try {
    await waitForHealth()
    browser = await chromium.launch(CHANNEL ? { channel: CHANNEL } : { channel: 'chromium' })
    const context = await browser.newContext({
      viewport: VIEWPORT,
      deviceScaleFactor: 2,
      locale: 'zh-CN',
    })
    const page = await context.newPage()

    // --- 登录页 ---
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: '梦溪畅谈' }).waitFor()
    await shot(page, '01-login.png')

    // --- 普通用户：聊天 / 模型选择 / 流式回复 ---
    await login(page, USER)
    await goto(page, '/')
    await page.getByText('宋词里的科学意象').click()
    await page.getByText('沈括在《梦溪笔谈》').waitFor({ timeout: 15_000 })
    await shot(page, '02-chat.png')

    await page.getByRole('button', { name: /🧠/ }).click()
    await page.getByRole('heading', { name: '选择模型' }).waitFor()
    await shot(page, '03-model-modal.png')
    await page.locator('.modal-head button').click()

    await page.getByPlaceholder(/向梦溪提问/).fill('用一句话介绍梦溪畅谈。')
    await page.getByRole('button', { name: /发送/ }).click()
    await page.getByText('这是一个用于文档截图的演示回复').waitFor({ timeout: 20_000 })
    await page.getByRole('button', { name: /发送/ }).waitFor({ timeout: 20_000 })
    await shot(page, '04-chat-reply.png')

    // --- 我的 Key ---
    await goto(page, '/keys')
    await page.getByRole('heading', { name: '我的 Key' }).waitFor()
    await page.getByText('我的 DeepSeek').first().waitFor({ timeout: 15_000 })
    await shot(page, '05-keys.png', { viewport: TALL_VIEWPORT })

    // --- 插件 ---
    await goto(page, '/plugins')
    await page.getByRole('heading', { name: '插件', exact: true }).waitFor()
    await page.getByText('回显输入文本').first().waitFor({ timeout: 15_000 })
    await shot(page, '06-plugins.png', { viewport: TALL_VIEWPORT })

    // --- 设置 ---
    await goto(page, '/settings')
    await page.getByRole('heading', { name: '设置' }).waitFor()
    await shot(page, '07-settings.png', { viewport: TALL_VIEWPORT })

    // --- 关于（含许可证声明）---
    await goto(page, '/about')
    await page.getByRole('heading', { name: '关于' }).waitFor()
    await page.getByText('BSD 3-Clause License').first().waitFor({ timeout: 15_000 })
    await shot(page, '08-about.png', { viewport: TALL_VIEWPORT })

    // --- 深色模式聊天 ---
    await page.evaluate(() => {
      const raw = localStorage.getItem('mengxi.theme')
      const theme = raw ? JSON.parse(raw) : {}
      localStorage.setItem('mengxi.theme', JSON.stringify({ ...theme, mode: 'dark' }))
    })
    await goto(page, '/')
    await page.getByText('宋词里的科学意象').click()
    await page.getByText('沈括在《梦溪笔谈》').waitFor({ timeout: 15_000 })
    await shot(page, '09-chat-dark.png')
    await page.evaluate(() => {
      const raw = localStorage.getItem('mengxi.theme')
      const theme = raw ? JSON.parse(raw) : {}
      localStorage.setItem('mengxi.theme', JSON.stringify({ ...theme, mode: 'light' }))
    })

    // --- 管理员：用户 / 公有 Key / 插件 / 审计 / 用户组 ---
    await logout(page)
    await login(page, ADMIN)
    await goto(page, '/admin')
    await page.getByRole('heading', { name: '管理后台' }).waitFor()
    await page.getByText('newuser').first().waitFor({ timeout: 15_000 })
    await shot(page, '10-admin-users.png', { viewport: TALL_VIEWPORT })

    await page.getByRole('button', { name: '公有 Key' }).click()
    await page.getByText('官方主通道').first().waitFor({ timeout: 15_000 })
    await shot(page, '11-admin-keys.png', { viewport: TALL_VIEWPORT })

    await page.getByRole('button', { name: '插件' }).click()
    await page.getByRole('heading', { name: '已安装插件' }).waitFor({ timeout: 15_000 })
    await shot(page, '12-admin-plugins.png', { viewport: TALL_VIEWPORT })

    await page.getByRole('button', { name: '审计' }).click()
    await page.getByRole('cell', { name: 'gpt-4o', exact: true }).first().waitFor({ timeout: 15_000 })
    await shot(page, '13-admin-audit.png', { viewport: TALL_VIEWPORT })

    await page.getByRole('button', { name: '用户组' }).click()
    await page.getByText('研发组').first().waitFor({ timeout: 15_000 })
    await shot(page, '14-admin-groups.png', { viewport: TALL_VIEWPORT })

    await context.close()
    log(`全部完成，输出目录：${OUT_DIR}`)
  } finally {
    if (browser) await browser.close()
    backend.kill()
  }
}

main().catch((error) => {
  process.stderr.write(`\u001b[31m[screenshots] 失败：${error?.stack ?? error}\u001b[0m\n`)
  process.exitCode = 1
})
