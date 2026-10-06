<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError, api, streamChat } from '../api/client'
import type { Conversation, Message } from '../api/types'

const conversations = ref<Conversation[]>([])
const current = ref<Conversation | null>(null)
const messages = ref<Message[]>([])
const models = ref<string[]>([])
const model = ref('gpt-4o')
const input = ref('')
const streaming = ref(false)
const error = ref('')

async function loadConversations() {
  conversations.value = await api.listConversations()
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

async function removeConversation(conversation: Conversation) {
  if (!confirm(`删除会话「${conversation.title}」？`)) return
  await api.deleteConversation(conversation.id)
  if (current.value?.id === conversation.id) {
    current.value = null
    messages.value = []
  }
  await loadConversations()
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
          <button class="del" title="删除" @click.stop="removeConversation(conversation)">✕</button>
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
.list {
  overflow-y: auto;
}
.conv {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 10px;
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
.title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.del {
  border: none;
  background: none;
  color: var(--muted);
  opacity: 0;
}
.conv:hover .del {
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
