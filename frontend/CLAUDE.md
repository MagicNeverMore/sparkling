## UI Contract

Sparkling 是一个 local-first 的 AI 笔记工作台，用于快速记录碎片想法、自动整理内容、发现相关笔记，并通过图谱探索想法之间的关系。

UI 目标是：安静、专注、精确、高密度但不拥挤，适合长时间写作、回看和思考。不要做成通用 AI SaaS、营销 landing page 或低密度 dashboard。

## 产品工作流优先级

1. 快速记录一个想法，输入路径必须低摩擦。
2. 在 Inbox 中快速扫描、回看最近的 atoms。
3. 处理 AI suggested links：确认、忽略、进入详情判断上下文。
4. 通过 Search 做语义检索。
5. 通过 Graph 探索想法之间的关系。
6. 在 Settings 中配置 provider、模型、embedding 维度等；Settings 不做营销式 onboarding。

## 设计气质

参考产品只取其特征，不照搬视觉：

- Linear：布局纪律、信息密度、状态清晰。
- Obsidian：知识工作台感、长期写作感。
- Apple Notes：快速捕获和轻量编辑。
- Raycast：command palette 和快捷操作的克制感。
- Notion：仅参考基础文档编辑体验，不参考其视觉风格。

## Design Tokens

当前项目以 Tailwind 手写组件为主。除非明确需要，不新增 UI framework 或 icon library。

- 页面背景：`bg-slate-950`
- 主 surface：`bg-slate-900`
- 次级 surface / hover：`bg-slate-800`
- 边框：`border-slate-800`，hover 可用 `border-slate-700`
- 主文本：`text-slate-100`
- 次级文本：`text-slate-400`
- 弱文本：`text-slate-500`
- 主 accent：`violet-400`，只用于 active state、primary action、AI signal
- 成功 / confirmed：`emerald-400`
- 警告 / conflict：`amber-400`
- 错误 / destructive：`rose-400`
- 默认圆角：`rounded-md` / `rounded-lg`
- 主要卡片最大使用 `rounded-xl`，不要使用更大的圆角
- 避免大面积阴影；如需浮层阴影，使用克制的 `shadow-xl`

不要引入紫蓝渐变、glassmorphism、装饰 blobs、hero 大标题、嵌套 cards、低密度 widget、无意义动画。

## 布局规则

- Desktop 使用左侧导航 + 主内容区。
- Tablet 可使用窄侧栏。
- Mobile 使用顶部轻量 header + 底部 tab bar。
- 主内容必须避免横向滚动。
- Inbox 主列保持适合阅读的宽度，优先扫描效率。
- Atom detail 可使用主内容 + 右侧关联面板；移动端应自然堆叠。
- Graph 应尽量占满可用 viewport，不要包在装饰性 card 里。
- Settings 是配置表单，不要做成宣传页或向导页。

## 组件规则

优先复用和扩展现有组件，不要重复造视觉模式：

- `AppShell`：应用框架和响应式导航。
- `SideNav` / `BottomTabBar`：导航。
- `QuickInput`：快速记录入口。
- `AtomCard`：atom 列表项。
- `LinkSuggest`：AI 关联建议。
- `LinkBadge` / `SimilarityBar`：关联和相似度表达。
- `Toast` / `ConfirmDialog`：反馈和确认。
- `EmptyState`：空状态。

新增组件前先检查是否可以通过 props 或小范围重构复用已有组件。不要在每个页面重新写 card、button、dialog、empty state。

## 交互规则

- 快速记录优先：输入框自动聚焦、键盘提交、提交后回到输入状态。
- AI 建议必须清楚区分 suggested 和 confirmed。
- destructive action 必须有确认，且视觉上低噪声。
- loading、empty、error、offline/reconnecting 都要有明确状态。
- 动画只用于状态进入、建议出现、轻量 hover；不要做持续性装饰动画。
- 不提交 `console.log`、`debugger` 或临时调试 UI。

## 技术规则

- 使用已有组件和 Tailwind。
- 当前项目未正式接入 shadcn/ui 或 lucide icons；不要假设它们可用。
- 如确实需要新增依赖，先说明原因，并保持依赖面很小。
- 使用 `pnpm` 运行前端命令。
- UI 改动后运行 `pnpm lint` 和 `pnpm build`。
- 如果改动影响布局或交互，尽量用截图检查 desktop 和 mobile。
