<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError, api } from '../../api/client'
import type { AdminPlugin, BuiltinPlugin, GroupPluginEntry } from '../../api/types'

const plugins = ref<AdminPlugin[]>([])
const builtin = ref<BuiltinPlugin[]>([])
const expanded = ref('')
const groups = ref<{ id: string; name: string }[]>([])
const error = ref('')
const info = ref('')

const manifestText = ref(
  JSON.stringify(
    {
      name: 'my-plugin',
      version: '1.0.0',
      description: '示例插件',
      type: 'optional',
      entry: 'main.py',
      permissions: [],
      default_state: 'disabled',
      runtime: { timeout_ms: 5000, memory_mb: 64, cpu_seconds: 2 },
    },
    null,
    2,
  ),
)
const codeText = ref(
  [
    'import json',
    'import sys',
    '',
    'request = json.loads(sys.stdin.readline())',
    'text = str((request.get("input") or {}).get("text", ""))',
    'sys.stdout.write(json.dumps({"type": "result", "output": text}) + "\\n")',
    'sys.stdout.flush()',
  ].join('\n'),
)

const selectedGroup = ref('')
const groupPlugins = ref<GroupPluginEntry[]>([])

async function load() {
  plugins.value = await api.adminListPlugins()
  groups.value = (await api.adminGroups()) as unknown as { id: string; name: string }[]
  builtin.value = await api.adminBuiltinPlugins()
}

async function installBuiltin(name: string) {
  error.value = ''
  info.value = ''
  try {
    await api.adminInstallBuiltin(name)
    info.value = `已安装内置插件 ${name}`
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  }
}

async function install() {
  error.value = ''
  info.value = ''
  try {
    const manifest = JSON.parse(manifestText.value)
    await api.adminInstallPlugin(manifest, codeText.value)
    info.value = `已安装插件 ${manifest.name}`
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  }
}

async function patch(plugin: AdminPlugin, field: string, value: string) {
  error.value = ''
  try {
    await api.adminUpdatePlugin(plugin.id, { [field]: value })
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  }
}

async function invoke(plugin: AdminPlugin) {
  error.value = ''
  const raw = prompt('输入插件入参 JSON，例如 {"text":"hi"}', '{"text":"hi"}')
  if (raw === null) return
  try {
    const input = raw.trim() ? JSON.parse(raw) : {}
    const result = await api.adminInvokePlugin(plugin.id, input)
    info.value = `[${plugin.name}] 输出：${result.output}`
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  }
}

async function loadGroupPlugins() {
  groupPlugins.value = selectedGroup.value ? await api.adminGroupPlugins(selectedGroup.value) : []
}

async function setGroupState(pluginId: string, value: string) {
  if (!selectedGroup.value) return
  error.value = ''
  try {
    if (value === '') {
      groupPlugins.value = await api.adminClearGroupPlugin(selectedGroup.value, pluginId)
    } else {
      groupPlugins.value = await api.adminSetGroupPlugin(
        selectedGroup.value,
        pluginId,
        value as 'enabled' | 'disabled',
      )
    }
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  }
}

onMounted(load)
</script>

<template>
  <div>
    <p v-if="error" class="notice">{{ error }}</p>
    <p v-if="info" class="notice ok">{{ info }}</p>

    <div class="card">
      <h3>已安装插件</h3>
      <table>
        <thead>
          <tr>
            <th>名称</th>
            <th>版本</th>
            <th>类型</th>
            <th>默认状态</th>
            <th>启用</th>
            <th>权限</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="plugin in plugins" :key="plugin.id">
            <td>{{ plugin.name }}</td>
            <td>{{ plugin.version }}</td>
            <td>
              <select :value="plugin.type" @change="patch(plugin, 'type', ($event.target as HTMLSelectElement).value)">
                <option value="global">全局</option>
                <option value="optional">可选</option>
              </select>
            </td>
            <td>
              <select
                :value="plugin.default_state"
                @change="patch(plugin, 'default_state', ($event.target as HTMLSelectElement).value)"
              >
                <option value="enabled">启用</option>
                <option value="disabled">禁用</option>
              </select>
            </td>
            <td>
              <select
                :value="plugin.status"
                @change="patch(plugin, 'status', ($event.target as HTMLSelectElement).value)"
              >
                <option value="active">启用</option>
                <option value="disabled">停用</option>
              </select>
            </td>
            <td class="perm">{{ plugin.permissions.join(', ') || '无' }}</td>
            <td><button class="btn small" @click="invoke(plugin)">试运行</button></td>
          </tr>
          <tr v-if="!plugins.length">
            <td colspan="7" class="empty">暂无插件</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h3>👥 用户组插件策略</h3>
      <div class="row">
        <select v-model="selectedGroup" @change="loadGroupPlugins">
          <option value="">选择用户组…</option>
          <option v-for="group in groups" :key="group.id" :value="group.id">{{ group.name }}</option>
        </select>
      </div>
      <table v-if="selectedGroup">
        <thead>
          <tr>
            <th>插件</th>
            <th>类型</th>
            <th>组内状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in groupPlugins" :key="entry.plugin_id">
            <td>{{ entry.name }}</td>
            <td>{{ entry.type === 'global' ? '全局' : '可选' }}</td>
            <td>
              <select
                :value="entry.state ?? ''"
                @change="setGroupState(entry.plugin_id, ($event.target as HTMLSelectElement).value)"
              >
                <option value="">未设置</option>
                <option value="enabled">启用</option>
                <option value="disabled">禁用</option>
              </select>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="selectedGroup && !groupPlugins.length" class="empty">该组暂无插件配置项</p>
    </div>

    <div class="card">
      <h3>🛒 内置插件市场</h3>
      <table v-if="builtin.length">
        <thead>
          <tr>
            <th>名称</th>
            <th>版本</th>
            <th>类型</th>
            <th>说明</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="item in builtin" :key="item.name">
            <tr>
              <td>{{ item.name }}</td>
              <td>{{ item.version }}</td>
              <td>{{ item.type === 'global' ? '全局' : '可选' }}</td>
              <td class="desc">{{ item.description }}</td>
              <td>
                <button
                  class="btn small"
                  @click="expanded = expanded === item.name ? '' : item.name"
                >
                  详情
                </button>
                <button class="btn small primary" @click="installBuiltin(item.name)">安装</button>
              </td>
            </tr>
            <tr v-if="expanded === item.name">
              <td colspan="5">
                <pre>{{ JSON.stringify(item, null, 2) }}</pre>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <p v-else class="empty">未配置内置插件目录（MENGXI_BUILTIN_PLUGINS_DIR）</p>
    </div>

    <div class="card">
      <h3>＋ 安装插件</h3>
      <div class="cols">
        <label class="field">
          Manifest（JSON）
          <textarea v-model="manifestText" rows="12" spellcheck="false"></textarea>
        </label>
        <label class="field">
          入口代码（main.py）
          <textarea v-model="codeText" rows="12" spellcheck="false"></textarea>
        </label>
      </div>
      <button class="btn primary" @click="install">安装 / 更新</button>
    </div>
  </div>
</template>

<style scoped>
h3 {
  font-size: 15px;
  color: var(--xi-dark);
  margin-bottom: 12px;
}
.card {
  margin-bottom: 18px;
}
.row {
  margin-bottom: 12px;
}
select {
  padding: 4px 6px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--paper);
}
.perm {
  font-size: 12px;
  color: var(--muted);
}
.cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}
textarea {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
  color: var(--ink);
  resize: vertical;
}
.empty {
  text-align: center;
  color: var(--muted);
  padding: 16px;
}
.desc {
  font-size: 12px;
  color: var(--muted);
}
pre {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px;
  overflow-x: auto;
}
.notice.ok {
  background: #e6f0e6;
  border-color: #b7d7b7;
  color: #2f6b2f;
}
</style>
