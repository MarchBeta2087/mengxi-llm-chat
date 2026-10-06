export interface User {
  id: string
  username: string
  role: 'user' | 'admin'
  status: 'active' | 'banned'
}

export interface ApiKey {
  id: string
  provider_name: string
  base_url: string
  models: string[]
  masked_key: string
  rate_limits: Record<string, number>
  weight: number
  status: string
  pool: 'public' | 'private'
  created_at: string
}

export interface Conversation {
  id: string
  title: string
  model: string | null
  encrypted: boolean
  archived: boolean
  created_at: string
}

export interface Message {
  id?: string
  role: 'system' | 'user' | 'assistant'
  content: string
  tokens_in?: number
  tokens_out?: number
  created_at?: string
}

export interface Plugin {
  id: string
  name: string
  version: string
  description: string
  type: 'global' | 'optional'
  default_state: 'enabled' | 'disabled'
  status: string
  permissions: string[]
  runtime: Record<string, number>
  enabled: boolean
  state_source: 'global' | 'group' | 'user' | 'default'
}

export interface SearchHit {
  conversation_id: string
  title: string
  kind: 'title' | 'message'
  message_id: string | null
  snippet: string | null
}

export interface SseEvent {
  event: string
  data: Record<string, unknown>
}

export interface AdminPlugin {
  id: string
  name: string
  version: string
  description: string
  type: 'global' | 'optional'
  default_state: 'enabled' | 'disabled'
  status: string
  permissions: string[]
  runtime: Record<string, number>
}

export interface GroupPluginEntry {
  plugin_id: string
  name: string
  type: string
  state: 'enabled' | 'disabled' | null
}

export interface KekStatus {
  profile: string
  state: string
  unlocked?: boolean
  recovery_codes?: string[]
}
