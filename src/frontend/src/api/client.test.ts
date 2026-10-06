// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest'
import { parseSseBlock, streamChat } from './client'

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

describe('streamChat', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

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
    await streamChat({ model: 'gpt-4o', messages: [{ role: 'user', content: 'hi' }] }, (event, data) => {
      events.push(event)
      if (event === 'delta') reply += String(data.text ?? '')
    })

    expect(events).toEqual(['meta', 'delta', 'delta', 'done'])
    expect(reply).toBe('你好')
  })
})
