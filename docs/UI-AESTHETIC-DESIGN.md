# Turing Mirror — UI / 美学设计手册

> **读者说明：** 本文档描述 **变声器产品壳**（`launcher/`）与内容站共用的设计原则。  
> **以代码为准：** 桌面壳色板与控件实现见 `launcher/theme.py`、`launcher/ui/`。  
> 历史名称「白无垢」仍可指气质（安静、反 AI 味）；**现行桌面色板已演化**，不再强制 accent = ink。

---

## 0. 变声器壳（现行 · 2026-07）

### 0.1 结构参考

| 来源 | 借鉴 |
|------|------|
| Schale-Library | **配色直接取用**（浅蓝库感）+ 库感顶栏、封面优先卡片、左描边分组卡、内容留白 |
| LyricsKara | 衬线刊头字阶、等宽 meta、焦点「舞台」层次 |

### 0.2 现行 light token（`launcher/theme.py` · 取自 Schale-Library globals.css）

> **配色定案（2026-07）：** 禁 AI 配色、禁青绿。桌面壳配色**直接抄 Schale-Library**
> 浅蓝库感（主色 = BA blue `#1289F0`）；**不用** Schale 青绿 accent `#2DF3E0`（无青绿），
> 蓝色一色承担主色 + live/active。下表值即 Schale token 1:1（个别文字色为可读性微调）。

| Token | 值 | Schale 来源 | 用途 |
|-------|-----|-------------|------|
| `TM_BG` | `#f7f9fb` | `--background` | 画布（浅蓝白） |
| `TM_SURFACE` | `#ffffff` | `--card` | 卡片 / 顶底栏 |
| `TM_SURFACE_HOVER` | `#f0f4f8` | `--muted` | hover |
| `TM_INK` | `#2b333e` | `--foreground` | 正文 |
| `TM_INK_MUTED` | `#46525f` | (比 muted-fg 深，为可读) | 表单项标签 / 次要正文 |
| `TM_HELP` | `#5a6a7a` | `--muted-foreground` | 设置说明小字 |
| `TM_META` | `#6e7d8c` | (比 help 浅) | 等宽 meta / 眉题 |
| `TM_INSET` | `#f0f4f8` | `--muted` | 封面占位 / 徽章底 |
| `TM_HAIRLINE` | `#d6e4f0` | `--border` | 分割 |
| `TM_STAGE` | `#e8f4fd` | `--secondary` | 首页舞台带（浅蓝 wash） |
| `TM_ACCENT` | `#1289f0` | `--primary`（BA blue） | CTA / active / 选中 |
| `TM_ACCENT_INK` | `#ffffff` | `--primary-foreground` | accent 上文字 |
| `TM_ACCENT_SOFT` | `#e8f4fd` | `--secondary` | active 导航浅底 |
| `TM_OK` | `#1178d6` | (深一档蓝) | live / 变声中（用蓝，非绿/青） |
| `TM_WARN` | `#b5791c` | (克制琥珀) | 连接中 / busy |
| `TM_ERROR` | `#e53e3e` | `--destructive` | 错误 |

禁止：RVCMAX 粉紫壳、蓝紫渐变/霓虹、**青绿/青色 accent（含 Schale `#2DF3E0`）**、
Schale BA 粉 `#F32D90`、LyricsKara 近黑 `#050508` 作主壳。（`theme.forbidden_chrome_hexes()`
有单测守护。）

### 0.3 组件与页面

| 模块 | 说明 |
|------|------|
| `launcher/ui/widgets.py` | SectionCard、Primary/GhostButton、NavItem、StatusBadge、ModelCoverCard、SoftActionCard、HoverTip、**SearchField**、**SegmentControl** |
| `launcher/ui/covers.py` | 音色 cover 缩略缓存 |
| 首页 | 舞台轮播 + 封面焦点卡 |
| 模型 | 封面网格 + **搜索(SearchField ⌕)/排序(SegmentControl 分段 pill)** + 检索库角标 |
| 设置 | SectionCard 分组（左 accent 条） |
| 启动器 | 同 token + SoftActionCard |

> **SearchField / SegmentControl 借鉴**：Schale 库感搜索框（扁平淡面 + ⌕，无发光）
> 与分段导航 pill（inactive 融入 rail、active 取 accent）；等宽 `SORT` 眉题延续
> LyricsKara mono meta。二者是通用件，避免把筛选逻辑写进 `main_app.py`。

### 0.4 MagiaDC 参考（UI/UX 目标形态，**排在性能等更重要任务之后再做**）

作者另一产品 MagiaDC（桌面伴侣）的界面语言，作为本壳后续 UX 打磨的目标：

| 区块 | MagiaDC 做法 | 对应我们 |
|------|-------------|----------|
| 左侧栏 | 图标+文字行，active = 浅底圆角 pill；顶部余额/状态；`全局设置` 固定底部带分隔 | 已有 NavItem；可加底部固定项 + 顶部状态块 |
| 顶部状态条 | 圆角 pill 卡：已授权 / 所有者 / 域名·id | 可用于「引擎/账户」状态行 |
| 设置分段 | 顶部 pill 分段 tab（常规/聊天·文件/…） | **已有 SegmentControl**，设置分级可直接用 |
| 内容卡 | 大圆角白卡 + 充裕留白 + 发丝边 + 轻投影；小节 = 小图标+标题+灰副标题 | SectionCard 增大圆角感 + 图标 |
| 列表行 | 圆角方图标 + 标题 + 灰副标题 + 右侧 `›` chevron（以太工作台/工坊列表） | 「其他」页/工坊可采用此行式 |
| KPI 磁贴 | 大数字 + 图标 + 标签 + 小副（运营总览网格） | 首页/状态可用 stat tile |
| 整体气质 | 极浅、通透、大圆角(~12–16px)、柔灰边、蓝色 active、磨砂玻璃(可选)、留白足 | 与现行 Schale 浅蓝 token 一致 |

> **落地顺序（用户明确）**：先完成更重要任务（性能正确性、真机验收、打包等），
> **UI/UX 再动**。本表仅为目标存档，非本轮施工项。Tk 大圆角需 PIL 贴图（参考
> SoftSlider 的 2× 超采样思路），列表行 chevron 用 `›` mono 字形即可。

---

## 1. 产品语境（为何长成这样）

Turing Mirror 内容站与本地变声器配套。壳层目标：

- 像**内容库 / 工具台**，不是 AI SaaS 霓虹落地页；
- 安静、可读；中文优先；
- 桌面 Tk 实现：结构清晰，**不把业务逻辑堆进样式文件**。

---

## 2. 设计语言名称与哲学

### 2.1 名称

**内容库壳 · 舞台焦点**（历史文档称「白无垢」；气质延续：克制、反 AI 味）。

### 2.2 核心哲学

> **背景即画布。层级靠字号对比 + 留白 + 淡面分组；主操作允许独立 accent，但不做霓虹。**

| 原则 | 含义 |
|------|------|
| 画布优先 | 浅色画布是主舞台 |
| 结构分组 | 顶栏 / 卡片 / 底栏分区清晰；设置用左描边 SectionCard |
| 独立 accent | 主 CTA / active 导航用 `TM_ACCENT`（非强制 = ink） |
| 反 AI 味 | 禁止蓝紫渐变、发光、霓虹 |
| 精品感 | 衬线标题 + 无衬线正文；meta 可用等宽 |

### 2.3 一句话气质

**现代内容库 × 安静工具台** — 可读、分区清楚、封面可辨。

---

## 3. 色彩系统

命名约定：语义令牌统一前缀 `tm-` / `TM_`（Turing Mirror）。

### 3.1 主题模式

- **桌面壳已实现：** light（上表）
- **暗色 token** 在 `theme.py` 仅预留，壳层默认浅色

### 3.2 核心语义色

**以 §0.2 / `launcher/theme.py` 为准。** 下方历史站用表仅作内容站参考，勿再当作变声器硬编码。

| Token | 历史站 Light（归档） | 用途备忘 |
|-------|----------------------|----------|
| `--tm-bg` | `#f4f1ea` | 旧暖纸画布 |
| `--tm-accent` | 曾 = ink | 旧「素墨」强调 |

要点：

- **Accent 可为安静有色**（现行青绿 `#3d5c55`），不是强制素墨。
- Surface 比画布略亮，用于卡片与 chrome。

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
