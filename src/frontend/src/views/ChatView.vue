<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError, api, streamChat } from '../api/client'
import type { Conversation, Message, SearchHit } from '../api/types'

const conversations = ref<Conversation[]>([])
const current = ref<Conversation | null>(null)
const messages = ref<Message[]>([])
const models = ref<string[]>([])
const model = ref('gpt-4o')
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

onMounted(async () => {
  await loadConversations()
  try {
    models.value = await api.models()
    if (models.value.length) model.value = models.value[0]
  } catch {
    /* 尚无密钥时忽略 */
  }
})
</script>

<template>
  <div class="chat">
    <aside class="convs">
      <button class="btn primary new-btn" @click="newConversation">＋ 新会话</button>

      <input
        v-model="query"
        class="search"
        placeholder="搜索会话/消息（Enter）"
        @keyup.enter="runSearch"
        @input="!query && clearSearch()"
      />

      <div v-if="hits.length" class="list results">
        <div v-for="(hit, i) in hits" :key="i" class="conv result" @click="openHit(hit)">
          <span class="title">{{ hit.snippet || hit.title }}</span>
        </div>
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
          @click="openConversation(conversation)"
        >
          <span class="title">{{ conversation.title }}</span>
          <span v-if="conversation.encrypted" title="已加密存储">🔒</span>
          <span v-if="conversation.archived" class="tag off">归档</span>
          <button class="act" title="重命名" @click.stop="renameConversation(conversation)">✎</button>
          <button
            class="act"
            :title="conversation.archived ? '取消归档' : '归档'"
            @click.stop="toggleArchive(conversation)"
          >
            {{ conversation.archived ? '↩' : '📦' }}
          </button>
          <button class="act" title="删除" @click.stop="removeConversation(conversation)">✕</button>
        </div>
      </div>
    </aside>

    <section class="main">
      <header class="topbar">
        <select v-model="model" class="model">
          <option v-if="!models.length" :value="model">{{ model }}</option>
          <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
        </select>
        <span class="tag">{{ current?.encrypted ? '已加密存储 🔒' : '未加密' }}</span>
      </header>

      <div class="scroll">
        <div v-for="(message, index) in messages" :key="index" class="msg" :class="message.role">
          <div class="avatar">{{ message.role === 'user' ? '我' : '溪' }}</div>
          <div class="bubble">{{ message.content || (streaming ? '…' : '') }}</div>
        </div>
        <p v-if="error" class="notice">{{ error }}</p>
      </div>

      <footer class="composer">
        <textarea
          v-model="input"
          rows="2"
          placeholder="向梦溪提问……（Enter 发送，Shift+Enter 换行）"
          @keydown.enter.exact.prevent="send"
        />
        <button class="btn primary" :disabled="streaming" @click="send">
          {{ streaming ? '生成中…' : '发送 ⏎' }}
        </button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  height: 100vh;
}
.convs {
  width: 240px;
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
  gap: 4px;
  padding: 8px 8px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
}
.conv:hover {
  background: var(--paper);
}
.conv.active {
  background: var(--bubble-user);
  color: var(--xi-dark);
  font-weight: 600;
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
.conv:hover .act {
  opacity: 1;
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
.msg.ai .avatar {
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
.msg.ai .bubble {
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
</style>
