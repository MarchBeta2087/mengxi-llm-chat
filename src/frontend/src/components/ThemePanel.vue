<script setup lang="ts">
import { useThemeStore } from '../stores/theme'

const theme = useThemeStore()
const colors = ['#2e6e63', '#3a5f8a', '#8a5a3a', '#6a4a8a']
</script>

<template>
  <aside v-if="theme.panelOpen" class="panel">
    <header>
      <h3>外观定制</h3>
      <button class="btn small" @click="theme.panelOpen = false">✕</button>
    </header>
    <label class="row">
      侧边栏宽度 {{ theme.settings.sidebarWidth }}px
      <input
        type="range"
        min="200"
        max="340"
        :value="theme.settings.sidebarWidth"
        @input="theme.update({ sidebarWidth: Number(($event.target as HTMLInputElement).value) })"
      />
    </label>
    <label class="row">
      界面密度
      <input
        type="range"
        min="1"
        max="3"
        :value="theme.settings.density"
        @input="theme.update({ density: Number(($event.target as HTMLInputElement).value) })"
      />
    </label>
    <div class="row">
      主题色
      <span class="swatches">
        <button
          v-for="c in colors"
          :key="c"
          class="sw"
          :class="{ sel: theme.settings.color === c }"
          :style="{ background: c }"
          @click="theme.update({ color: c })"
        />
      </span>
    </div>
    <div class="row">
      模式
      <select
        :value="theme.settings.mode"
        @change="theme.update({ mode: ($event.target as HTMLSelectElement).value as never })"
      >
        <option value="light">浅色</option>
        <option value="dark">深色</option>
        <option value="system">跟随系统</option>
      </select>
    </div>
    <label class="row">
      字号 {{ theme.settings.fontSize }}px
      <input
        type="range"
        min="12"
        max="18"
        :value="theme.settings.fontSize"
        @input="theme.update({ fontSize: Number(($event.target as HTMLInputElement).value) })"
      />
    </label>
  </aside>
</template>

<style scoped>
.panel {
  position: fixed;
  right: 0;
  top: 0;
  width: 250px;
  height: 100vh;
  background: var(--surface);
  border-left: 1px solid var(--line);
  padding: 18px;
  box-shadow: -4px 0 16px rgba(0, 0, 0, 0.08);
  z-index: 20;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
h3 {
  font-size: 14px;
  color: var(--xi-dark);
}
.row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 14px;
}
.swatches {
  display: flex;
  gap: 8px;
}
.sw {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid transparent;
}
.sw.sel {
  border-color: var(--ink);
}
</style>
