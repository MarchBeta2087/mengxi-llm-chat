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
      // 覆盖率门禁仅针对已有单测的核心模块（视图/组件暂不计入门禁）
      include: ['src/api/client.ts', 'src/stores/theme.ts'],
      thresholds: {
        lines: 85,
        functions: 90,
        statements: 85,
        branches: 70,
      },
    },
  },
})
