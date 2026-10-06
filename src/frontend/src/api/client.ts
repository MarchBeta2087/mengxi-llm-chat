import type { ApiKey, Conversation, Message, Plugin, SearchHit, User } from './types'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

export class ApiError extends Error {
  status: number
  code: number
  extra: Record<string, unknown>

  constructor(message: string, status: number, code: number, extra: Record<string, unknown> = {}) {
    super(message)
    this.status = status
    this.code = code
    this.extra = extra
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    ...init,
  })
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new ApiError(
      (body as { message?: string }).message ?? res.statusText,
      res.status,
      (body as { code?: number }).code ?? res.status,
      body as Record<string, unknown>,
    )
  }
  return (body as { data: T }).data
}

export const api = {
  // 认证
  register: (username: string, password: string) =>
    request<User>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  login: (username: string, password: string) =>
    request<User>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<null>('/api/auth/logout', { method: 'POST' }),
  me: () => request<User>('/api/auth/me'),

  // 密钥
  listKeys: (pool?: 'public' | 'private') =>
    request<ApiKey[]>(`/api/keys${pool ? `?pool=${pool}` : ''}`),
  createKey: (payload: Record<string, unknown>) =>
    request<ApiKey>('/api/keys', { method: 'POST', body: JSON.stringify(payload) }),
  updateKey: (id: string, payload: Record<string, unknown>) =>
    request<ApiKey>(`/api/keys/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteKey: (id: string) => request<null>(`/api/keys/${id}`, { method: 'DELETE' }),
  testKey: (id: string) =>
    request<{ ok: boolean; status_code: number; latency_ms: number; error: string | null }>(
      `/api/keys/${id}/test`,
      { method: 'POST' },
    ),
  models: () => request<string[]>('/api/keys/models'),

  // 会话
  listConversations: (includeArchived = false) =>
    request<Conversation[]>(`/api/conversations?include_archived=${includeArchived}`),
  createConversation: (title = '新会话', model: string | null = null) =>
    request<Conversation>('/api/conversations', {
      method: 'POST',
      body: JSON.stringify({ title, model }),
    }),
  updateConversation: (id: string, payload: Record<string, unknown>) =>
    request<Conversation>(`/api/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteConversation: (id: string) =>
    request<null>(`/api/conversations/${id}`, { method: 'DELETE' }),
  messages: (id: string) => request<Message[]>(`/api/conversations/${id}/messages`),
  searchConversations: (q: string) =>
    request<SearchHit[]>(`/api/conversations/search?q=${encodeURIComponent(q)}`),

  // 插件
  listPlugins: () => request<Plugin[]>('/api/plugins'),
  togglePlugin: (id: string, enabled: boolean) =>
    request<Plugin[]>(`/api/plugins/${id}/toggle`, {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    }),

  // 审计
  myAudit: (limit = 100) => request<Record<string, unknown>[]>(`/api/audit?limit=${limit}`),

  // 管理端
  adminUsers: () => request<Record<string, unknown>[]>('/api/admin/users'),
  adminUpdateUser: (id: string, payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/admin/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  adminGroups: () => request<Record<string, unknown>[]>('/api/admin/groups'),
  adminCreateGroup: (name: string, dailyQuota = 0) =>
    request<Record<string, unknown>>('/api/admin/groups', {
      method: 'POST',
      body: JSON.stringify({ name, daily_quota_tokens: dailyQuota }),
    }),
  adminAudit: (params = '') => request<Record<string, unknown>[]>(`/api/admin/audit${params}`),
  adminKek: () => request<Record<string, unknown>>('/api/admin/kek'),
  adminRecoveryStatus: () =>
    request<{ remaining: number }>('/api/admin/recovery-codes'),
}

/** 解析单个 SSE 块（event + data），失败返回 null。 */
export function parseSseBlock(
  block: string,
): { event: string; data: Record<string, unknown> } | null {
  const eventMatch = /^event:\s*(.*)$/m.exec(block)
  const dataMatch = /^data:\s*(.*)$/m.exec(block)
  if (!eventMatch || !dataMatch) return null
  try {
    return { event: eventMatch[1].trim(), data: JSON.parse(dataMatch[1]) }
  } catch {
    return null
  }
}

/** 聊天：SSE 流式（fetch + ReadableStream）。 */
export async function streamChat(
  payload: { model: string; messages: Message[]; conversation_id?: string | null },
  onEvent: (event: string, data: Record<string, unknown>) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(BASE + '/api/chat/completions', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(
      (body as { message?: string }).message ?? res.statusText,
      res.status,
      (body as { code?: number }).code ?? res.status,
    )
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const parsed = parseSseBlock(block)
      if (parsed) onEvent(parsed.event, parsed.data)
    }
  }
}
