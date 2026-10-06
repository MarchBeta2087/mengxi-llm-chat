import { expect, test, type Page } from '@playwright/test'

interface MockState {
  authed: boolean
}

const USER = { id: 'u1', username: 'alice', role: 'user', status: 'active' }

async function mockApi(page: Page, state: MockState): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const method = request.method()
    const ok = (data: unknown) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, data, message: 'ok' }),
      })

    if (path === '/api/auth/me') {
      if (state.authed) return ok(USER)
      return route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ code: 401, message: '未登录', data: null }),
      })
    }
    if (path === '/api/auth/login') {
      state.authed = true
      return ok(USER)
    }
    if (path === '/api/conversations' && method === 'GET') return ok([])
    if (path === '/api/conversations' && method === 'POST') {
      return ok({
        id: 'c1',
        title: '新会话',
        model: 'gpt-4o',
        encrypted: true,
        archived: false,
        created_at: new Date().toISOString(),
      })
    }
    if (path.endsWith('/messages')) return ok([])
    if (path === '/api/keys/models') return ok(['gpt-4o'])
    if (path === '/api/chat/completions') {
      const sse =
        'event: meta\ndata: {"conversation_id":"c1"}\n\n' +
        'event: delta\ndata: {"text":"你好"}\n\n' +
        'event: delta\ndata: {"text":"，世界"}\n\n' +
        'event: done\ndata: {"finish_reason":"stop"}\n\n'
      return route.fulfill({
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
        body: sse,
      })
    }
    return ok({})
  })
}

test('未登录时展示登录页', async ({ page }) => {
  await mockApi(page, { authed: false })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '梦溪畅谈' })).toBeVisible()
  await expect(page.getByLabel('用户名')).toBeVisible()
})

test('登录后可流式聊天', async ({ page }) => {
  const state: MockState = { authed: false }
  await mockApi(page, state)

  await page.goto('/')
  await page.getByLabel('用户名').fill('alice')
  await page.getByLabel('密码').fill('password123')
  await page.getByRole('button', { name: '登录' }).last().click()

  // 进入聊天界面
  await expect(page.getByRole('button', { name: /新会话/ })).toBeVisible()

  await page.getByPlaceholder(/向梦溪提问/).fill('你好')
  await page.getByRole('button', { name: /发送/ }).click()

  // 流式回复渲染
  await expect(page.getByText('你好，世界')).toBeVisible()
})

test('可退出登录', async ({ page }) => {
  const state: MockState = { authed: false }
  await mockApi(page, state)

  await page.goto('/')
  await page.getByLabel('用户名').fill('alice')
  await page.getByLabel('密码').fill('password123')
  await page.getByRole('button', { name: '登录' }).last().click()
  await expect(page.getByRole('button', { name: /新会话/ })).toBeVisible()

  state.authed = false
  await page.getByRole('button', { name: /退出登录/ }).click()

  await expect(page.getByRole('heading', { name: '梦溪畅谈' })).toBeVisible()
  await expect(page.getByLabel('用户名')).toBeVisible()
})
