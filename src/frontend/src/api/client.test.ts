// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, parseSseBlock, streamChat } from './client'

function stubJson(data: unknown, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(JSON.stringify({ code: status === 200 ? 0 : status, data, message: 'ok' }), {
          status,
          headers: { 'Content-Type': 'application/json' },
        }),
    ),
  )
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('parseSseBlock', () => {
  it('解析 event 与 data', () => {
    expect(parseSseBlock('event: delta\ndata: {"text":"你好"}')).toEqual({
      event: 'delta',
      data: { text: '你好' },
    })
  })

  it('忽略缺少字段或非法 JSON 的块', () => {
    expect(parseSseBlock('event: x')).toBeNull()
    expect(parseSseBlock('data: {')).toBeNull()
    expect(parseSseBlock('')).toBeNull()
  })
})

describe('request via api', () => {
  it('解包 { code, data, message }', async () => {
    stubJson({ id: 'u1', username: 'alice', role: 'user', status: 'active' })
    await expect(api.me()).resolves.toMatchObject({ username: 'alice' })
  })

  it('错误响应抛出 ApiError（带 code）', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ code: 401, message: '未登录' }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' },
          }),
      ),
    )
    await expect(api.me()).rejects.toBeInstanceOf(ApiError)
    await expect(api.me()).rejects.toMatchObject({ status: 401, code: 401, message: '未登录' })
  })

  it('204 无内容返回 undefined', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 204 })))
    await expect(api.logout()).resolves.toBeUndefined()
  })

  it('覆盖各业务端点的调用', async () => {
    stubJson({})
    await api.register('a', 'b')
    await api.login('a', 'b')
    await api.listKeys('public')
    await api.createKey({ provider_name: 'p' })
    await api.updateKey('k1', { weight: 2 })
    await api.deleteKey('k1')
    await api.testKey('k1')
    await api.models()
    await api.listConversations(true)
    await api.createConversation('t', 'gpt-4o')
    await api.updateConversation('c1', { title: 'x' })
    await api.deleteConversation('c1')
    await api.messages('c1')
    await api.searchConversations('量子')
    await api.listPlugins()
    await api.togglePlugin('p1', true)
    await api.myAudit(10)
    await api.adminUsers()
    await api.adminUpdateUser('u1', { status: 'banned' })
    await api.adminGroups()
    await api.adminCreateGroup('g', 100)
    await api.adminAudit('?fallback_only=true')
    await api.adminKek()
    await api.adminRecoveryStatus()
    expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(20)
  })
})

describe('streamChat', () => {
  it('按顺序回调 SSE 事件', async () => {
    const payload =
      'event: meta\ndata: {"conversation_id":"c1"}\n\n' +
      'event: delta\ndata: {"text":"你"}\n\n' +
      'event: delta\ndata: {"text":"好"}\n\n' +
      'event: done\ndata: {"finish_reason":"stop"}\n\n'
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(payload))
        controller.close()
      },
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(stream, { status: 200 })),
    )

    const events: string[] = []
    let reply = ''
    await streamChat(
      { model: 'gpt-4o', messages: [{ role: 'user', content: 'hi' }] },
      (event, data) => {
        events.push(event)
        if (event === 'delta') reply += String(data.text ?? '')
      },
    )

    expect(events).toEqual(['meta', 'delta', 'delta', 'done'])
    expect(reply).toBe('你好')
  })

  it('非 2xx 抛出 ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ code: 503, message: '密钥池耗尽' }), { status: 503 }),
      ),
    )
    await expect(
      streamChat({ model: 'gpt-4o', messages: [] }, () => {}),
    ).rejects.toBeInstanceOf(ApiError)
  })
})
