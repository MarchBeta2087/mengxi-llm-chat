import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      // 覆盖率范围：核心 TS 模块 + 组件（视图视图暂不计入门禁）
      include: ['src/api/client.ts', 'src/stores/theme.ts', 'src/components/**/*.vue'],
      thresholds: {
        'src/api/client.ts': { lines: 85, functions: 90, statements: 85, branches: 70 },
        'src/stores/theme.ts': { lines: 85, functions: 90, statements: 85, branches: 70 },
        'src/components/**': { lines: 70, functions: 70, statements: 70, branches: 55 },
      },
    },
  },
})
