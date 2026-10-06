<script setup lang="ts">
import { ref } from 'vue'
import AdminAudit from '../components/admin/AdminAudit.vue'
import AdminGroups from '../components/admin/AdminGroups.vue'
import AdminPlugins from '../components/admin/AdminPlugins.vue'
import AdminPublicKeys from '../components/admin/AdminPublicKeys.vue'
import AdminUsers from '../components/admin/AdminUsers.vue'

type TabKey = 'users' | 'groups' | 'keys' | 'plugins' | 'audit'

const tabs: { key: TabKey; label: string }[] = [
  { key: 'users', label: '用户' },
  { key: 'groups', label: '用户组' },
  { key: 'keys', label: '公有 Key' },
  { key: 'plugins', label: '插件' },
  { key: 'audit', label: '审计' },
]
const tab = ref<TabKey>('users')
</script>

<template>
  <div class="page">
    <h2>管理后台</h2>
    <div class="tabs">
      <button
        v-for="item in tabs"
        :key="item.key"
        :class="{ on: tab === item.key }"
        @click="tab = item.key"
      >
        {{ item.label }}
      </button>
    </div>

    <AdminUsers v-if="tab === 'users'" />
    <AdminGroups v-else-if="tab === 'groups'" />
    <AdminPublicKeys v-else-if="tab === 'keys'" />
    <AdminPlugins v-else-if="tab === 'plugins'" />
    <AdminAudit v-else-if="tab === 'audit'" />
  </div>
</template>

<style scoped>
.page {
  padding: 24px 5vw;
  height: 100vh;
  overflow-y: auto;
}
h2 {
  font-family: 'Songti SC', serif;
  color: var(--xi-dark);
}
.tabs {
  display: flex;
  gap: 6px;
  margin: 14px 0;
}
.tabs button {
  padding: 7px 18px;
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: 8px;
}
.tabs button.on {
  background: var(--xi);
  color: #fff;
  border-color: var(--xi);
}
</style>
