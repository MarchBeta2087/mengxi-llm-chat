<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ApiError, api, streamChat } from '../api/client'
import type { AvailableKey, Conversation, Message, SearchHit } from '../api/types'

const conversations = ref<Conversation[]>([])
const current = ref<Conversation | null>(null)
const messages = ref<Message[]>([])
const available = ref<AvailableKey[]>([])
const showModels = ref(false)
const model = ref('gpt-4o')

const models = computed(() => {
  const list: string[] = []
  for (const key of available.value) {
    for (const item of key.models) {
      if (!list.includes(item)) list.push(item)
    }
  }
  return list
})
const input = ref('')
const streaming = ref(false)
const error = ref('')

const query = ref('')
const hits = ref<SearchHit[]>([])
const showArchived = ref(false)

async function loadConversations() {
  conversations.value = await api.listConversations(showArchived.value)
}

async function openConversation(conversation: Conversation) {
  current.value = conversation
  model.value = conversation.model || model.value
  messages.value = await api.messages(conversation.id)
}

async function newConversation() {
  const conversation = await api.createConversation('新会话', model.value)
  conversations.value = [conversation, ...conversations.value]
  current.value = conversation
  messages.value = []
}

async function renameConversation(conversation: Conversation) {
  const title = prompt('重命名会话', conversation.title)
  if (!title || title === conversation.title) return
  await api.updateConversation(conversation.id, { title })
  await loadConversations()
  if (current.value?.id === conversation.id) current.value.title = title
}

async function toggleArchive(conversation: Conversation) {
  const archived = !conversation.archived
  await api.updateConversation(conversation.id, { archived })
  if (current.value?.id === conversation.id && archived) {
    current.value = null
    messages.value = []
  }
  await loadConversations()
}

async function removeConversation(conversation: Conversation) {
  if (!confirm(`删除会话「${conversation.title}」？`)) return
  await api.deleteConversation(conversation.id)
  if (current.value?.id === conversation.id) {
    current.value = null
    messages.value = []
  }
  await loadConversations()
}

async function runSearch() {
  const q = query.value.trim()
  if (!q) {
    hits.value = []
    return
  }
  hits.value = await api.searchConversations(q)
}

function clearSearch() {
  query.value = ''
  hits.value = []
}

async function openHit(hit: SearchHit) {
  const list = await api.listConversations(true)
  const conversation = list.find((item) => item.id === hit.conversation_id)
  if (conversation) {
    await openConversation(conversation)
    clearSearch()
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || streaming.value) return
  if (!current.value) await newConversation()
  error.value = ''
  messages.value.push({ role: 'user', content: text })
  input.value = ''

  const assistant: Message = { role: 'assistant', content: '' }
  messages.value.push(assistant)
  streaming.value = true
  try {
    await streamChat(
      {
        model: model.value,
        messages: [{ role: 'user', content: text }],
        conversation_id: current.value?.id,
      },
      (event, data) => {
        if (event === 'delta') assistant.content += String(data.text ?? '')
        if (event === 'error') {
          assistant.content += `\n[错误 ${data.code}] ${data.message}`
        }
      },
    )
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  } finally {
    streaming.value = false
    await loadConversations()
  }
}

async function loadAvailable() {
  try {
    const data = await api.availableKeys()
    available.value = Array.isArray(data) ? data : []
    if (models.value.length && !models.value.includes(model.value)) {
      model.value = models.value[0]
    }
  } catch {
    /* 尚无密钥时忽略 */
  }
}

const modalRef = ref<HTMLElement | null>(null)
const modelButtonRef = ref<HTMLButtonElement | null>(null)

async function openModels() {
  showModels.value = true
  void loadAvailable()
  await nextTick()
  modalRef.value?.focus()
}

function closeModels() {
  showModels.value = false
  modelButtonRef.value?.focus()
}

function pickModel(value: string) {
  model.value = value
  closeModels()
}

onMounted(async () => {
  await loadConversations()
  await loadAvailable()
})
</script>

<template>
  <div class="chat">
    <aside class="convs" aria-label="会话列表">
      <button class="btn primary new-btn" type="button" @click="newConversation">＋ 新会话</button>

      <label class="visually-hidden" for="conv-search">搜索会话或消息</label>
      <input
        id="conv-search"
        v-model="query"
        class="search"
        type="search"
        placeholder="搜索会话/消息（Enter）"
        @keyup.enter="runSearch"
        @input="!query && clearSearch()"
      />

      <div v-if="hits.length" class="list results">
        <button
          v-for="(hit, i) in hits"
          :key="i"
          type="button"
          class="conv result"
          @click="openHit(hit)"
        >
          <span class="title">{{ hit.snippet || hit.title }}</span>
        </button>
      </div>

      <label class="arch">
        <input v-model="showArchived" type="checkbox" @change="loadConversations" /> 显示归档
      </label>

      <div class="list">
        <div
          v-for="conversation in conversations"
          :key="conversation.id"
          class="conv"
          :class="{ active: current?.id === conversation.id }"
        >
          <button
            type="button"
            class="conv-open"
            :aria-current="current?.id === conversation.id ? 'true' : undefined"
            @click="openConversation(conversation)"
          >
            <span class="title">{{ conversation.title }}</span>
            <span v-if="conversation.encrypted" title="已加密存储" aria-label="已加密存储">🔒</span>
            <span v-if="conversation.archived" class="tag off">归档</span>
          </button>
          <button
            class="act"
            type="button"
            :aria-label="`重命名会话 ${conversation.title}`"
            title="重命名"
            @click.stop="renameConversation(conversation)"
          >
            ✎
          </button>
          <button
            class="act"
            type="button"
            :aria-label="
              conversation.archived ? `取消归档 ${conversation.title}` : `归档 ${conversation.title}`
            "
            :title="conversation.archived ? '取消归档' : '归档'"
            @click.stop="toggleArchive(conversation)"
          >
            {{ conversation.archived ? '↩' : '📦' }}
          </button>
          <button
            class="act"
            type="button"
            :aria-label="`删除会话 ${conversation.title}`"
            title="删除"
            @click.stop="removeConversation(conversation)"
          >
            ✕
          </button>
        </div>
      </div>
    </aside>

    <section class="main">
      <header class="topbar">
        <button
          ref="modelButtonRef"
          class="model-btn"
          type="button"
          aria-haspopup="dialog"
          :aria-expanded="showModels"
          @click="openModels"
        >
          🧠 {{ model }} ▾
        </button>
        <span class="tag">{{ current?.encrypted ? '已加密存储 🔒' : '未加密' }}</span>
      </header>

      <div class="scroll" role="log" aria-label="对话消息" aria-live="polite">
        <div v-for="(message, index) in messages" :key="index" class="msg" :class="message.role">
          <div class="avatar" aria-hidden="true">{{ message.role === 'user' ? '我' : '溪' }}</div>
          <div class="bubble">{{ message.content || (streaming ? '…' : '') }}</div>
        </div>
        <p v-if="error" class="notice" role="alert">{{ error }}</p>
      </div>

      <footer class="composer">
        <textarea
          v-model="input"
          rows="2"
          aria-label="消息输入"
          placeholder="向梦溪提问……（Enter 发送，Shift+Enter 换行）"
          @keydown.enter.exact.prevent="send"
        />
        <button
          class="btn primary"
          type="button"
          :disabled="streaming"
          :aria-busy="streaming"
          @click="send"
        >
          {{ streaming ? '生成中…' : '发送 ⏎' }}
        </button>
      </footer>
    </section>

    <div v-if="showModels" class="modal-mask" @click.self="closeModels" @keydown.esc="closeModels">
      <div
        ref="modalRef"
        class="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="model-modal-title"
        tabindex="-1"
      >
        <header class="modal-head">
          <h3 id="model-modal-title">选择模型</h3>
          <button class="btn small" type="button" aria-label="关闭模型选择" @click="closeModels">
            ✕
          </button>
        </header>
        <p class="hint">展示名 · 脱敏 Key · 模型 · 用量（全局/个人）</p>
        <p v-if="!available.length" class="empty">
          暂无可用的 Key，请先在「我的 Key」添加，或联系管理员配置公有池。
        </p>
        <div v-for="key in available" :key="key.id" class="key-row">
          <div class="key-head">
            <strong>{{ key.provider_name }}</strong>
            <span class="tag" :class="{ priv: key.pool === 'private' }">
              {{ key.pool === 'public' ? '全局' : '个人' }}
            </span>
            <code>{{ key.masked_key }}</code>
            <span class="usage">
              {{ key.usage_scope === 'global' ? '全局用量' : '个人用量' }}：
              {{ key.usage.calls }} 次 · {{ key.usage.tokens_in + key.usage.tokens_out }} tokens
            </span>
          </div>
          <div class="chips">
            <button
              v-for="item in key.models"
              :key="item"
              class="chip"
              type="button"
              :class="{ on: item === model }"
              :aria-pressed="item === model"
              @click="pickModel(item)"
            >
              {{ item }}
            </button>
            <span v-if="!key.models.length" class="muted">（未声明模型）</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  height: 100vh;
}
.convs {
  width: var(--sidebar-width);
  flex-shrink: 0;
  border-right: 1px solid var(--line);
  background: var(--surface);
  display: flex;
  flex-direction: column;
  padding: 12px 8px;
}
.new-btn {
  margin-bottom: 10px;
}
.search {
  padding: 7px 9px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
  margin-bottom: 8px;
}
.arch {
  font-size: 11px;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 4px 6px;
}
.list {
  overflow-y: auto;
}
.results {
  border-bottom: 1px dashed var(--line);
  margin-bottom: 6px;
  padding-bottom: 6px;
}
.conv {
  display: flex;
  align-items: center;
  gap: 2px;
  border-radius: 8px;
  font-size: 13px;
}
.conv-open {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  min-width: 0;
  padding: 8px;
  border: none;
  border-radius: 8px;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.conv-open:hover {
  background: var(--paper);
}
.conv.active .conv-open {
  background: var(--bubble-user);
  color: var(--xi-dark);
  font-weight: 600;
}
.conv.result {
  width: 100%;
  padding: 8px;
  border: none;
  border-radius: 8px;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.conv.result:hover {
  background: var(--paper);
}
.conv.result .title {
  color: var(--muted);
  font-size: 12px;
}
.title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.act {
  border: none;
  background: none;
  color: var(--muted);
  opacity: 0;
  padding: 0 2px;
}
.conv:hover .act,
.conv:focus-within .act {
  opacity: 1;
}
@media (hover: none) {
  .act {
    opacity: 1;
  }
}
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.topbar {
  height: 52px;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 18px;
}
.model {
  padding: 6px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
}
.scroll {
  flex: 1;
  overflow-y: auto;
  padding: 22px 6vw;
}
.msg {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}
.msg.user {
  flex-direction: row-reverse;
}
.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bubble-user);
}
.msg.assistant .avatar {
  background: var(--xi);
  color: #fff;
  font-family: serif;
}
.bubble {
  max-width: 72%;
  padding: 11px 15px;
  border-radius: var(--radius);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg.assistant .bubble {
  background: var(--bubble-ai);
  border: 1px solid var(--line);
}
.msg.user .bubble {
  background: var(--bubble-user);
}
.composer {
  border-top: 1px solid var(--line);
  padding: 14px 6vw;
  display: flex;
  gap: 12px;
  align-items: flex-end;
}
.composer textarea {
  flex: 1;
  resize: none;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 10px 12px;
  background: var(--surface);
}
.model-btn {
  padding: 6px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  color: var(--ink);
  font-size: 13px;
}
.model-btn:hover {
  border-color: var(--xi);
  color: var(--xi);
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 30;
}
.modal {
  width: min(640px, 92vw);
  max-height: 80vh;
  overflow-y: auto;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 18px;
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.modal-head h3 {
  font-size: 15px;
  color: var(--xi-dark);
}
.hint {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 12px;
}
.key-row {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 10px;
}
.key-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 8px;
}
.key-head code {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  color: var(--muted);
}
.usage {
  margin-left: auto;
  font-size: 11px;
  color: var(--muted);
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.chip {
  font-size: 12px;
  color: var(--muted);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 4px 12px;
  background: var(--surface);
}
.chip:hover {
  border-color: var(--xi);
  color: var(--xi);
}
.chip.on {
  color: #fff;
  background: var(--xi);
  border-color: var(--xi);
}
.muted,
.empty {
  font-size: 12px;
  color: var(--muted);
}
.empty {
  text-align: center;
  padding: 16px;
}
</style>
