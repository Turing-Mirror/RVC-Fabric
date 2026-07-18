# Turing Mirror — UI / 美学设计手册

> **读者说明：** 本文档自包含。不熟悉本仓库、不打开源码或其它 docs 的协作者（含其他项目中的 AI 对话）只读本文件，即可继承同一套视觉语言。实现时请把下列令牌、组件范式与「禁止项」当作硬约束，而不是灵感参考。

---

## 1. 产品语境（为何长成这样）

Turing Mirror 是**邀请制**的 AI 提示词与技巧内容站，覆盖生图、聊天、角色扮演、视频、编程、音乐、办公等领域。界面目标是：

- 像**精品目录 / 纸本刊头**，而不是 AI SaaS 落地页；
- 安静、可读、克制，突出内容与 demo，而不是品牌色块；
- 中文优先的用户文案与信息架构。

---

## 2. 设计语言名称与哲学

### 2.1 名称

**「白无垢」** — 取自 Magia 设计语言，适配内容展示站。

### 2.2 核心哲学（必须背下来）

> **背景即画布。层级靠字号对比 + 留白 + 极淡分组面，不靠线和框去切。**

| 原则 | 含义 |
|------|------|
| 画布优先 | 整页暖白/暗墨底色是主舞台，内容「长在纸上」，不是塞进灰壳卡片墙 |
| 无硬切分 | 少用实线粗边框；用极低透明度的 surface / inset / hairline 暗示分组 |
| 纯墨强调 | 主按钮、active 指示、强调色 = 墨色本身，**零独立品牌色** |
| 反 AI 味 | 禁止蓝紫渐变、发光、霓虹、彩虹科技感 |
| 精品感 | 衬线标题 + 无衬线正文 + 克制弹簧动效 |

### 2.3 一句话气质

**纸本精品目录 × 现代系统 UI** — 安静、克制、可读。

---

## 3. 色彩系统

命名约定：语义令牌统一前缀 `--tm-`（Turing Mirror）。

### 3.1 主题模式

- **已实现：** 暖白（light）+ 暗墨（dark）
- **文档曾规划、未作第三主题要求：** 冷银（可忽略）
- **切换：** `html[data-theme="light"|"dark"]`；无手动选择时跟随 `prefers-color-scheme`；用户选择可持久化（如 `localStorage` 键 `tm-theme`）
- 暗色不是冷灰 OLED 黑，而是**暗墨纸**（底 `#1c1b18`，字偏暖米 `#ece3d0`）

### 3.2 核心语义色（照抄）

| Token | Light | Dark | 用途 |
|-------|-------|------|------|
| `--tm-bg` | `#f4f1ea` | `#1c1b18` | 页面画布 |
| `--tm-surface` | `rgba(255, 255, 255, 0.48)` | `rgba(236, 227, 208, 0.04)` | 卡片 / 分组面 |
| `--tm-surface-hover` | `rgba(255, 255, 255, 0.7)` | `rgba(236, 227, 208, 0.08)` | hover 面 |
| `--tm-ink` | `#1c1a17` | `#ece3d0` | 正文 / 强调字 |
| `--tm-ink-muted` | `#9a948a` | `#9c948a` | 弱化文案 |
| `--tm-meta` | `#b0a99d` | `#7c756a` | 元信息（模型名、难度等） |
| `--tm-inset` | `rgba(28, 26, 23, 0.06)` | `rgba(236, 227, 208, 0.07)` | 组内细分隔线 |
| `--tm-hairline` | `rgba(28, 26, 23, 0.08)` | `rgba(236, 227, 208, 0.1)` | 极淡分割 |
| `--tm-accent` | `#1c1a17`（= ink） | `#ece3d0`（= ink） | **素墨强调**（主按钮底等） |
| `--tm-accent-ink` | `#ffffff` | `#1c1b18` | accent 上的文字 |

要点：

- **Accent 不是彩色**，就是当前主题的墨色。
- Surface 是半透明叠在画布上的「淡面」，不是实心白卡片。

### 3.3 内容类型语义色（仅文字，不加框）

用于「生图 / 聊天 / …」等类型标签的**文字颜色 only**。不要做成彩色 chip、badge 或底框。

| 类型（示例 key） | Light | Dark | 气质 |
|------------------|-------|------|------|
| Image / 生图 | `#5c7a6b` | `#7c9a8b` | 灰绿 |
| Chat / 聊天 | `#a8894e` | `#c0a468` | 琥珀 |
| Roleplay / 角色扮演 | `#8b5a6b` | `#ab7a8b` | 玫瑰褐 |
| Video / 视频 | `#5a7a8b` | `#7a9aab` | 灰蓝 |
| Coding / 编程 | `#7a6b5a` | `#9a8b7a` | 暖褐 |
| Music / 音乐 | `#6b5a8b` | `#8b7aab` | 灰紫 |
| Office / 办公 | `#5a6b7a` | `#7a8b9a` | 蓝灰 |

实现侧 token 示例：`--tm-c-image`、`--tm-c-chat`、…  
若分类可配置，颜色可来自数据；**表现形态仍必须是纯文字色**。

### 3.4 禁止的色彩用法

- 蓝紫 / 彩虹渐变背景或按钮  
- Glow、外发光、霓虹描边  
- 高饱和「AI 产品」主色（紫、电蓝、品红）作为品牌色  
- 类型色当大面积填充或实心标签底  

---

## 4. 字体与字阶

### 4.1 字体栈

| 角色 | 栈 | 用途 |
|------|-----|------|
| 衬线标题 | `'Songti SC', 'Noto Serif SC', Georgia, serif` | Logo、页面/卡片/详情标题、小节标题 |
| 无衬线正文 | `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif` | 正文、导航、按钮、元信息 |
| 等宽 | `'SF Mono', ui-monospace, 'Cascadia Code', Menlo, monospace` | 提示词、代码块、参数 |

### 4.2 推荐字阶

| 元素 | 规格 |
|------|------|
| Logo | 衬线 16px / font-weight 600 |
| 页面英雄标题 | 衬线 22px / 600 |
| 详情主标题 h1 | 衬线 24px / 600，line-height ~1.35 |
| 卡片标题 | 衬线 15px / 600，line-height ~1.4 |
| 小节标题 | 衬线 16px / 600 |
| 状态块标题 | 衬线 18px / 600 |
| 正文 | 13–14px / 400，line-height 1.5–1.7 |
| 导航链接 | 13px |
| 摘要 / 副文 | 12–14px，`ink-muted` |
| 类型标签文字 | 12px / 500，语义色 |
| 元信息 | 11–12px，`meta` |
| 代码 | 12–13px mono，line-height ~1.6–1.7 |
| 按钮主文案 | 12–13px / 500 |
| 复制按钮等微控件 | 11px / 500 |

策略：**大标题用衬线做「刊头」**；其余偏小、偏克制，靠字号与灰度分层，而不是粗色块。

### 4.3 文案语气

- **中文优先**（`lang="zh-CN"` 级体验）  
- 短、冷静、工具向：浏览、登录、复制、已复制、收藏、菜单  
- 避免营销口号堆砌、emoji 装饰 UI、夸张 CTA  

---

## 5. 形、间距、圆角

### 5.1 圆角令牌

| Token | 值 | 用途 |
|-------|-----|------|
| `--tm-r-sm` | `8px` | 代码块、demo 图、较小 inset 块 |
| `--tm-r` | `14px` | 默认卡片、参数组、状态块 |
| `--tm-pill` | `999px` | 主按钮、搜索框、分段控件、主题切换、小圆钮 |

### 5.2 间距与布局密度

- **页面左右 gutter：** 流体，约 `clamp(12px, 3vw, 28px)`，并尊重 `safe-area-inset`；超窄屏（≤360px）可收到约 10px  
- **网格间距：** 卡片网格约 `12px`  
- **卡片内边距：** 约 `14px 16px`（极窄可 `12px`）  
- **英雄区：** 上 padding 约 `28–40px`，下收紧  
- **整体密度：** 偏疏、安静 — 不是后台表格高密度  

### 5.3 触控与窄屏

- 最小触控目标：`44px`（粗指针设备上的按钮/关键操作）  
- 卡片最小宽度约 `280–320px`（极窄 `240–260px`），网格用 `auto-fit` / `minmax` 自适应  
- 详情桌面：主栏 + 约 `260px` 侧栏；平板/手机单列，侧栏下移  
- 导航中小屏折行 + 菜单展开；分段控件小屏横向滚动，不压缩文字  
- 全局防横向撑破：`overflow-x: clip`、容器 `min-width: 0`、表单可收缩  

---

## 6. 动效

### 6.1 时长与曲线

| Token | 值 | 用途 |
|-------|-----|------|
| `--tm-fast` | `140ms` | hover 色/背景 |
| `--tm-normal` | `240ms` | 卡片上浮、分段切换 |
| `--tm-slow` | `420ms` | 图片微缩放 |
| `--tm-spring` | `cubic-bezier(0.34, 1.4, 0.5, 1)` | 弹簧回弹 |
| `--tm-ease` | `cubic-bezier(0.2, 0, 0, 1)` | 标准缓出 |

### 6.2 规则

- **只动画 `transform` 与 `opacity`**（GPU 友好），避免大面积 layout 动画  
- `prefers-reduced-motion: reduce` 时：`--tm-fast/normal/slow` 全部 **0ms**；滚动渐隐可直接最终态  

### 6.3 标准交互手感

| 元素 | Hover | Active |
|------|-------|--------|
| 内容卡 | `translateY(-3px)` + surface-hover + 轻阴影 `0 8px 30px rgba(0,0,0,0.07)`，spring | `translateY(-1px) scale(0.99)`，约 80ms |
| 主按钮 / 登录 | `opacity: 0.85` | `scale(0.97)` |
| Demo 图 | `scale(1.04)` 或约 `1.02`，slow + ease | — |
| 链接 / 弱按钮 | muted → ink | — |
| 分段 active 项 | surface-hover + 轻外阴影 + 可选 inset 0.5px 描边，spring | — |

---

## 7. 组件与页面范式

以下是「长什么样」的可复用配方。类名可用 `tm-*` 前缀，也可在新项目映射为同语义 token。

### 7.1 全局基线

- 页面背景 / body：`--tm-bg`  
- 默认字色：`--tm-ink`，字体 sans，line-height ~1.5  
- 链接默认 `color: inherit`，无下划线（交互态再强调）  
- 按钮默认去系统边框，继承字体  
- `:focus-visible`：约 2px `accent` 半透明 outline，offset 2px  
- 抗锯齿、`text-rendering: optimizeLegibility`、稳定滚动条槽、动态视口高度（`100dvh` 等）  

### 7.2 导航栏

- Sticky，`background: var(--tm-bg)`（不是重毛玻璃框）  
- **不要**用硬底部分割线  
- 滚动响应：`scrollY` 0→100px 映射 header 底部伪元素 opacity 0→1；伪元素为约 16px 高、自上而下的 **ink 5% → 透明** 渐隐遮罩  
- Logo：衬线 16/600  
- 导航链接：13px，`ink-muted`，hover → `ink`；active：`font-weight: 500` + 底部 **1.5px** accent 细线（`border-radius: 1px`）  
- 搜索：药丸，`surface` 底，hover/focus → `surface-hover`，约 12px 字，左侧小搜索图标  
- 主题切换：小圆形/药丸 surface 按钮  
- 登录：药丸 **accent 实心** + `accent-ink` 字  
- 已登录：用户名 13/500；退出/后台为 muted 文字链  

### 7.3 首页英雄区

- 衬线大标题 + 一行 `ink-muted` 副文  
- 不铺大 hero 图、不铺渐变横幅  

### 7.4 分段控件（筛选芯片轨）

- 外轨：`padding: 3px`，背景 `color-mix(in srgb, var(--tm-ink) 5%, transparent)`，`border-radius: pill`，`width: fit-content`  
- 项：`padding: 6px 16px`，12px/500，默认 muted  
- Active：`surface-hover` 底 + ink 字 + 轻阴影  
- 小屏：横向滚动，隐藏滚动条亦可  

### 7.5 内容卡片

- **无 border**；`background: surface`；`border-radius: 14px`；`overflow: hidden`  
- 封面区：`aspect-ratio 16/10`（窄屏可 4/3）；无图时用极淡斜线占位（opacity 很低）  
- 标题衬线 15/600；摘要 12px muted，**两行 clamp**  
- 类型：12/500 **语义色纯文字**；模型名 meta  
- 底栏：`border-top: 1px solid inset`；左难度/收藏 meta 11px；右可放锁图标（暗示会员）  
- Hover：上浮 3px + 阴影（见 §6.3）  

### 7.6 内容网格

- `display: grid`  
- `grid-template-columns: repeat(auto-fit, minmax(min(100%, 280–320px), 1fr))`  
- `gap: 12px`；左右跟 page gutter  

### 7.7 面包屑

- 12px，`meta` 色  
- 分隔符 `/` 用 `hairline` 色  
- 类型名可用语义色 + weight 500  
- 链接 hover → ink  

### 7.8 详情页

- 桌面：`grid-template-columns: 1fr 260px`，gap 约 28px  
- 类型标签：12/500 语义色，无框  
- 标题衬线 24/600；副标题 14 muted  
- Demo：2×2 方形网格，圆角 8px，hover 微放大；可点开灯箱  
- 代码块：背景 `ink 4%` 混合，圆角 8px，mono 13px，`pre-wrap`；右上角药丸「复制」按钮（surface → surface-hover）  
- 反向提示词等次级块：可略更淡（ink 3%），小写 uppercase label + mono 正文  
- 标签：无底无框，**点状虚线下划线**（`text-decoration: underline dotted`，颜色 hairline；hover 加深），暗示可点进标签页  
- 使用说明：13px muted，line-height 1.7  
- 侧栏主按钮：全宽倾向的 pill accent；次按钮 soft 圆（surface）  
- 参数组：surface + 14px 圆角；行间 `inset` 分割；label muted，value weight 500；类型值可用语义色  

### 7.9 分页

- 居中，12px muted  
- 页码/上一页下一页：药丸 surface，hover surface-hover  

### 7.10 空态 / 状态提示

- 可用很淡的 `hairline` 边 + surface 底（比内容卡略「框」一点，仍保持低对比）  
- 可选 kicker：11px、大写、letter-spacing 约 0.16em、meta 色  
- 标题衬线；说明 muted  
- 动作按钮仍用 ink 药丸 accent  
- 错误态仅轻微偏红 border mix，**不要**大红块警报风格  

### 7.11 主按钮 vs 软按钮

```
主按钮 (primary):
  padding: 10px 20px (登录可 7px 18px)
  border-radius: pill
  background: accent
  color: accent-ink
  font: 12–13px / 500
  hover: opacity 0.85
  active: scale(0.97)

软按钮 (soft):
  background: surface
  color: ink-muted
  hover: surface-hover + ink
  圆形图标钮约 32–38px 或 44px 触控
```

---

## 8. 可复制的 CSS 令牌起点

将下列片段作为新项目的设计 token 基线（可按需改前缀，**数值勿随意改**）：

```css
:root {
  --tm-bg: #f4f1ea;
  --tm-surface: rgba(255, 255, 255, 0.48);
  --tm-surface-hover: rgba(255, 255, 255, 0.7);
  --tm-ink: #1c1a17;
  --tm-ink-muted: #9a948a;
  --tm-meta: #b0a99d;
  --tm-inset: rgba(28, 26, 23, 0.06);
  --tm-hairline: rgba(28, 26, 23, 0.08);
  --tm-accent: #1c1a17;
  --tm-accent-ink: #ffffff;

  --tm-c-image: #5c7a6b;
  --tm-c-chat: #a8894e;
  --tm-c-roleplay: #8b5a6b;
  --tm-c-video: #5a7a8b;
  --tm-c-coding: #7a6b5a;
  --tm-c-music: #6b5a8b;
  --tm-c-office: #5a6b7a;

  --tm-r-sm: 8px;
  --tm-r: 14px;
  --tm-pill: 999px;
  --tm-page-gutter: max(clamp(12px, 3vw, 28px), env(safe-area-inset-left, 0px), env(safe-area-inset-right, 0px));
  --tm-card-min: min(100%, 280px);
  --tm-card-wide-min: min(100%, 320px);
  --tm-touch-target: 44px;

  --tm-serif: 'Songti SC', 'Noto Serif SC', Georgia, serif;
  --tm-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --tm-mono: 'SF Mono', ui-monospace, 'Cascadia Code', Menlo, monospace;

  --tm-fast: 140ms;
  --tm-normal: 240ms;
  --tm-slow: 420ms;
  --tm-spring: cubic-bezier(0.34, 1.4, 0.5, 1);
  --tm-ease: cubic-bezier(0.2, 0, 0, 1);
  color-scheme: light;
}

:root[data-theme='dark'] {
  --tm-bg: #1c1b18;
  --tm-surface: rgba(236, 227, 208, 0.04);
  --tm-surface-hover: rgba(236, 227, 208, 0.08);
  --tm-ink: #ece3d0;
  --tm-ink-muted: #9c948a;
  --tm-meta: #7c756a;
  --tm-inset: rgba(236, 227, 208, 0.07);
  --tm-hairline: rgba(236, 227, 208, 0.1);
  --tm-accent: #ece3d0;
  --tm-accent-ink: #1c1b18;

  --tm-c-image: #7c9a8b;
  --tm-c-chat: #c0a468;
  --tm-c-roleplay: #ab7a8b;
  --tm-c-video: #7a9aab;
  --tm-c-coding: #9a8b7a;
  --tm-c-music: #8b7aab;
  --tm-c-office: #7a8b9a;
  color-scheme: dark;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme='light']) {
    /* 与 data-theme='dark' 相同的一套覆盖 */
  }
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --tm-fast: 0ms;
    --tm-normal: 0ms;
    --tm-slow: 0ms;
  }
}
```

Body 最小基线：

```css
html, body {
  background: var(--tm-bg);
  color: var(--tm-ink);
  font-family: var(--tm-sans);
  line-height: 1.5;
}
```

---

## 9. 给实现者的检查清单

做任何新界面前自问：

1. 背景是否仍是**画布色**，而不是另一套灰底？  
2. 层级是否主要靠**字号 / 灰度 / 留白 / 淡 surface**，而不是粗线框？  
3. 主强调是否仍是**素墨 accent**，没有引入新品牌色？  
4. 标题是否**衬线**，正文是否 **sans**？  
5. 类型信息是否**只有文字色**、没有彩色底？  
6. 按钮/搜索/分段是否倾向 **pill**，卡片是否 **14px 圆角无边框**？  
7. 动效是否只有 transform/opacity，且尊重 **reduced-motion**？  
8. 窄屏是否有 **gutter / 触控 44px / 不横向撑破**？  
9. 用户可见文案是否**中文优先**、语气克制？  
10. 是否出现了蓝紫渐变、glow、霓虹？若有 → **删掉**。  

---

## 10. 明确禁止 / 继承红线

1. **禁止**蓝紫/彩虹渐变、glow、霓虹、重度玻璃拟态堆叠。  
2. **禁止**新增品牌主色；强调继续用墨色 `--tm-accent`。  
3. **禁止**类型标签彩色底框；语义色 text-only。  
4. **禁止**用硬分割线作为主要层级手段。  
5. **禁止**拆掉「衬线标题 + 无衬线正文」结构。  
6. **禁止**忽略 reduced-motion、触控目标、安全区与流体 gutter。  
7. **禁止**为了「更 AI」而把 UI 做成发光科技风。  
8. 默认 **严格继承「白无垢」**；任何风格突破必须有产品/设计明文许可。  

---

## 11. 反面教材（看到就改）

| 错误 | 正确 |
|------|------|
| 紫色渐变 CTA | 墨色实心 pill 按钮 |
| 彩色圆角类型 badge | 12px 语义色纯文字 |
| 卡片 1px 实线 + 重阴影默认态 | 无 border 的淡 surface，阴影仅 hover |
| 全站 Inter + 无衬线大标题墙 | 标题 Songti/Noto Serif |
| Header 固定灰底 + 1px 底边 | 画布同色 + 滚动渐隐遮罩 |
| 高饱和错误大红条 | 淡 surface + 轻微 border mix |
| 标签实心灰 chip | 点状虚线下划线文字链 |

---

## 12. 跨项目使用方式（给其他 Grok / 协作者）

1. 把本文件整份提供给对话或仓库（无需附带源码）。  
2. 指令示例：  
   > 严格按 `UI-AESTHETIC-DESIGN.md` 的「白无垢」语言实现 UI：使用文中 token 数值，衬线标题，无边框淡面卡片，素墨 accent，禁止蓝紫渐变与类型色底框。  
3. 实现后用 **§9 检查清单** 与 **§10 红线** 做 diff 审查。  
4. 若需视觉对照：原项目中有可交互 HTML 稿（首页/详情 mockup），但**无 mockup 时仅凭本文即可开工**。  

---

## 13. 摘要（30 秒版）

Turing Mirror 使用 Magia 衍生的 **「白无垢」** 设计：暖纸/暗墨画布、**纯墨强调**、**衬线刊头 + 系统无衬线正文**、卡片是**半透明淡面而非描边盒**、类型用**低饱和语义色文字**、控件多为 **pill**、动效为 **短时 spring/ease 的位移与透明度**。整体像安静的纸本精品目录，**明确拒绝**常见 AI 产品的蓝紫渐变与发光外观。后续一切 UI 默认继承本文，不得自行换肤。
