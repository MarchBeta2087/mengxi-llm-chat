# 无障碍声明（Accessibility）

梦溪畅谈（mengxi-llm-chat）致力于让尽可能多的用户——无论是否使用辅助技术——都能顺畅地
登录、聊天、管理密钥与外观设置。本页说明我们遵循的标准、当前实现程度、已知限制，以及
**如何反馈无障碍问题**。

---

## 1. 目标标准

项目以 [**WCAG 2.1 Level AA**](https://www.w3.org/TR/WCAG21/) 为设计与验收目标，并参考
[WAI-ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/)。核心原则：

| 原则 | 我们的做法 |
| --- | --- |
| 可感知（Perceivable） | 语义化结构、表单标签、表格标题、非文本内容有替代文本；色彩不单独承载信息 |
| 可操作（Operable） | 全键盘可达、可见焦点、可缩放、尊重「减少动态效果」 |
| 可理解（Understandable） | 语言声明 `zh-CN`、状态用文字/图标双通道、错误就近提示并朗读 |
| 健壮（Robust） | 使用原生 HTML 元素优先，ARIA 仅作补充，兼容主流浏览器与读屏器 |

## 2. 符合性状态

> **当前状态：部分符合（Partially Conformant）** —— 应用已内置一组无障碍基础能力，
> 但尚未经过完整的第三方 / 自动化审计，仍存在第 4 节的已知限制。

本项目为**可自部署**应用，最终呈现还取决于部署方的主题、字号与浏览器环境。我们按版本逐步
收敛差距，欢迎通过第 5 节渠道反馈。

## 3. 已实现的无障碍特性

### 结构与导航

- 采用语义化地标：`<nav aria-label="主导航">`、`<main>`、`<aside aria-label>`；
- 页面提供 **「跳到主内容」跳转链接**，键盘用户可一键绕过侧边导航；
- 文档语言声明为 `zh-CN`；
- 装饰性 emoji 使用 `aria-hidden="true"`，不干扰读屏器朗读。

### 键盘与焦点

- 全部交互控件可聚焦、可激活；会话列表项、模型选项卡均为真实 `<button>`；
- 全局 `:focus-visible` 焦点环（仅键盘导航时出现，不干扰鼠标用户）；
- 模型选择弹窗具备 `role="dialog"` / `aria-modal="true"`，打开时自动聚焦，**Escape 关闭**并
  将焦点归还触发按钮；
- 悬停才显示的行内操作（重命名 / 归档 / 删除）在 `:focus-within` 时同样显示，键鼠一致。

### 屏幕阅读器

- 图标按钮均带 `aria-label`（如「删除会话 xxx」），不依赖 `title`；
- 开关使用 `role="switch"` + `aria-checked`；主题色/模型等选择使用 `aria-pressed`；
- 错误与提示使用 `role="alert"` / `role="status"`，动态更新会被朗读；
- 数据表格使用 `<caption>`（视觉隐藏）与 `scope="col"` 表头。

### 视觉与个性化

- 深浅色模式、主题色、字号、侧边栏宽度均可调；
- `@media (prefers-reduced-motion: reduce)` 下禁用过渡/动画；
- 布局在 **200% 缩放**下仍可用（不依赖固定像素视口）。

## 4. 已知限制

- **尚无完整审计**：未执行 axe-core 等自动化扫描，也未进行外部无障碍评估；
- **模态焦点管理为基线实现**：提供初始聚焦与 Esc 关闭，但未实现严格的焦点陷阱（Tab 循环）；
- **流式回复的朗读**：对话区使用 `aria-live="polite"`，长回复可能持续朗读，读屏器体验仍可优化；
- **复杂表格**：管理后台宽表在窄屏需横向滚动，暂未提供响应式卡片降级；
- **高对比度模式**：尚未针对 Windows 高对比度（forced-colors）做专项验证；
- **CI 未接入无障碍门禁**：目前靠人工走查，计划纳入自动化检查（见路线图）。

## 5. 反馈无障碍问题

若你遇到障碍，欢迎告诉我们：

- 提交 **无障碍 Issue**（[`.github/ISSUE_TEMPLATE/accessibility_report.yml`](.github/ISSUE_TEMPLATE/accessibility_report.yml)）——
  请描述**页面 / 操作 / 期望 / 实际**，并尽量附上：
  - 浏览器与版本、操作系统；
  - 使用的辅助技术（如 NVDA、VoiceOver、键盘导航、屏幕放大）；
  - 截图或复现步骤。
- 若涉及安全影响，请改用 [安全政策](SECURITY.md) 的私密渠道。

我们会评估并按优先级修复。

## 6. 面向贡献者的无障碍清单

提交界面变更前，请对照以下要点（与 [贡献指南](CONTRIBUTING.md) 配套）：

- [ ] 优先使用**原生语义元素**，交互元素用 `<button>` / `<a>` 而非 `<div @click>`；
- [ ] 每个表单控件都有**关联标签**（`<label>` 或 `aria-label`），而非仅靠 `placeholder`；
- [ ] 图标按钮提供 `aria-label`，装饰图形 `aria-hidden="true"`；
- [ ] 支持**纯键盘**完成操作，并检查焦点顺序与可见焦点；
- [ ] 动态状态（错误、加载、结果）使用 `role="alert"` / `aria-live` / `aria-busy`；
- [ ] 颜色对比度满足 **AA（正文 ≥ 4.5:1，大字 ≥ 3:1）**，不单独用颜色传达信息；
- [ ] 尊重 `prefers-reduced-motion`，并保证 **200% 缩放**下不丢内容；
- [ ] 为无障碍行为补充/更新测试；界面变更附截图。

## 7. 参考

- [WCAG 2.1](https://www.w3.org/TR/WCAG21/)
- [WAI-ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/)
- [MDN · Accessibility](https://developer.mozilla.org/zh-CN/docs/Web/Accessibility)
- [安全政策](SECURITY.md) · [贡献指南](CONTRIBUTING.md) · [行为准则](CODE_OF_CONDUCT.md)
