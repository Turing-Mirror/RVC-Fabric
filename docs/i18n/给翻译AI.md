# 给翻译 AI 的工作说明

> **你只负责把中文产品文案译成目标语言。**  
> 不改代码、不改 key、不合并进仓库结构、不碰 `app/src` / Rust / 脚本。  
> 工程接入（换语言开关、新语言注册、修 bug）由开发 AI / 维护者负责。

---

## 1. 你只需要读这些

| 优先级 | 文件 | 做什么 |
|:---:|---|---|
| **必读** | [`app/i18n/locales/zh-CN.json`](../../app/i18n/locales/zh-CN.json) | **唯一翻译源**。整文件结构 + 每个 value 的中文 |
| **建议** | 本文档 | 规则与交付格式 |
| 可选 | 同目录已有 [`en-US.json`](../../app/i18n/locales/en-US.json) | 已有英文可作风格参考；`s` 区可能仍空 |

**不要读、不要改：**

- `app/src/**`、`app/src-tauri/**`、Python 引擎  
- `docs/i18n/01-*.md` / `04-unique-index.md`（给开发对账用，不是翻译入口）  
- `docs/i18n/keys-draft.*`（未接入代码的草案，翻译主路径不依赖它）  
- 上游 Gradio 的 `i18n/locale/*.json`（另一套产品，无关）

---

## 2. 你要生成什么

### 主交付（必须）

**一份与 `zh-CN.json` 结构完全一致的目标语言 JSON 文件。**

| 目标语言 | 输出文件名 | 说明 |
|---|---|---|
| 英语 | `en-US.json` | 覆盖/补全 `app/i18n/locales/en-US.json` |
| 日语 | `ja-JP.json` | 新建，结构同 zh-CN |
| 其他 | `<BCP-47>.json` | 如 `zh-TW.json`、`ko-KR.json` |

路径约定（交给开发时写明）：

```
app/i18n/locales/<locale>.json
```

### 可选交付

- 简短 `NOTES.md`：专有名词译法表、无法确定的句子列表（key + 原因）  
- **不要**提交 diff 到 `.ts` / `.rs` / 脚本

---

## 3. 翻译规则（硬性）

1. **只改 value，不改 key**  
   - `"nav.home"` 的 key 路径必须与中文包一致  
   - `glossary.terms[].id` **禁止翻译、禁止改动**（如 `"runtime"`、`"hubert"`）  
   - `s` 下的 hash（如 `"a1b2c3d4e5"`）是 key，**不要翻译 hash**

2. **占位符原样保留**  
   - `{name}` `{delay}` `{infer}` `{author}` `{v0}` `{v1}` …  
   - 不要改成 `{名字}` 或删掉  
   - 语序可按目标语言调整，但花括号名必须一致  

3. **不要翻译这些**  
   - 品牌：`RVC Fabric`、`Turing Mirror` / 图灵镜（首次可加注，不替换品牌拉丁名）  
   - 技术固定名：`CUDA`、`DirectML`、`VB-Cable`、`CABLE Input/Output`、`RMVPE`、`WASAPI`、`MME`、`ASIO`、`HuBERT`、`RVC`  
   - 路径/文件名：`Runtime`、`tools/realtime_worker.py`、`.pth`、`.index`  
   - 已是英文的句子可保持或轻度润色，勿乱译成错误术语  

4. **语气**  
   - 面向普通 Windows 用户（开黑 / 连麦 / 直播），短句、可操作  
   - 设置问号、错误提示：说清楚「是什么 + 怎么办」  
   - 不要营销腔、不要 emoji（产品界面不用）  

5. **`s` 区**  
   - `zh-CN.json` 里 `"s": { "<hash>": "中文…" }` 必须**逐条**译出  
   - 英语包若 `s` 为空，翻译 AI 应**补全全部 hash 条目**，不要只译 nav/dock  

6. **编码**  
   - UTF-8，JSON 合法（可用 `json.load` 校验）  
   - 不要 BOM  

---

## 4. 结构速览（zh-CN 有什么）

```
meta          语言名称
nav           导航：首页/广场/…
window        最小化/关闭
dock          底栏：变声/音高/启停/引擎状态
settings      设置页标签、语言、外观选项
locale        语言显示名
tray          托盘菜单
engine        引擎相关提示
home          首页工具入口等
glossary      专有名词（term / brief / detail；保留 id）
msg           引擎 message_code 对应句（嵌套 engine/runtime/vc）
s             批量自动 key（hash → 中文），条数最多，必须全译
```

---

## 5. 交给翻译 AI 的提示词模板（可直接复制）

```
你是产品文案译者，只做翻译，不改工程代码。

必读：
1. docs/i18n/给翻译AI.md（规则）
2. app/i18n/locales/zh-CN.json（唯一中文源）

任务：
- 目标语言：English (en-US)   ← 可改成 ja-JP 等
- 输出完整文件：与 zh-CN.json 相同 JSON 结构
- 只翻译 value；key、glossary.terms[].id、s 的 hash 键名一律不动
- 保留所有 {placeholder} 名
- 技术专名见给翻译AI.md 第 3 节

交付：
- 完整 JSON 正文（可直接存为 app/i18n/locales/en-US.json）
- 如有不确定条目，另附列表：key路径 + 中文原文 + 疑问

校验：输出必须是合法 JSON。
```

---

## 6. 开发侧会做什么（你不用做）

翻译 AI 交付 JSON 后，由开发负责：

1. 把文件放进 `app/i18n/locales/`  
2. 新语言时改 `app/src/i18n/types.ts`、`i18n::supported`、设置页语言列表  
3. 跑编译 / 实机切语言检查  
4. 有漏 key 或缺占位符时修包，不回头改源码逻辑  

---

## 7. 质量自检清单（翻译 AI 交卷前）

- [ ] 与 zh-CN **键结构一致**（可用脚本 diff keys）  
- [ ] 所有 `s.*` hash 都有非空译文  
- [ ] 全文无残留未译的整句中文（专名/品牌除外）  
- [ ] 每个原文里的 `{xxx}` 在译文中仍出现且同名  
- [ ] `glossary.terms[].id` 与中文包完全相同  
- [ ] `json` 可解析  

---

## 8. 一句话

**读 `zh-CN.json`，按本文规则生成同结构的 `en-US.json`（或其它 locale），只动译文。**
