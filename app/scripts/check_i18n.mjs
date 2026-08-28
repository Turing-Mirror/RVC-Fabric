// i18n 语言包硬校验：结构与占位符必须八语言一致。
//
// 起因是 26.8 的一次线上事故：14 条新文案只写了 zh-CN 就发布，八语言里
// 其余七份直接显示字面 `{v0}` 大括号。这类问题肉眼看 diff 永看不全 ——
// 一条文案八份语言，漏改任何一份都是运行时才炸。所以这里用程序当关隘：
//
//   1. 结构：八个语言包的 key 树必须完全一致（glossary 按 term id 对齐、
//      extras.items 按 item id 对齐，缺一个词条就报）。
//   2. 占位符：每条字符串里 `{...}` 记号（`{v0}`、`{}`、`{:.1}` 都算）的
//      集合必须与 zh-CN 完全一致 —— 多一个少一个都是运行时的字面大括号
//      或者吞参数。
//
// 接在 `npm run build` 里，任何一条不过就构建失败，不给它上线的机会。

import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const LOCALES_DIR = join(HERE, "..", "i18n", "locales");
const BASE = "zh-CN";
const OTHERS = [
  "zh-TW",
  "en-US",
  "ja-JP",
  "ko-KR",
  "es-ES",
  "fr-FR",
  "ru-RU",
];

const TOKEN = /\{[^{}]*\}/g;

/** 把语言包压平成 dotted-key -> string。dict 往下走；「按 id 对齐」的数组
 * （glossary.terms）单独处理成 id -> 字段 map，缺哪个 id 一目了然。 */
function flatten(value, prefix, out) {
  if (typeof value !== "object" || value === null) {
    out[prefix] = String(value);
    return;
  }
  if (Array.isArray(value)) {
    // glossary.terms：唯一「有意义的数组」。逐条拍平成 terms.<id>.<field>。
    value.forEach((entry) => {
      if (entry && typeof entry === "object" && "id" in entry) {
        for (const [k, v] of Object.entries(entry)) {
          if (k === "id") continue;
          flatten(v, `${prefix}.${entry.id}.${k}`, out);
        }
      } else {
        flatten(value.indexOf(entry), `${prefix}.${value.indexOf(entry)}`, out);
      }
    });
    return;
  }
  for (const [k, v] of Object.entries(value)) flatten(v, `${prefix}${prefix ? "." : ""}${k}`, out);
}

function tokens(s) {
  return (s.match(TOKEN) || []).sort().join("|");
}

const packs = {};
for (const loc of [BASE, ...OTHERS]) {
  const raw = readFileSync(join(LOCALES_DIR, `${loc}.json`), "utf-8");
  packs[loc] = {};
  flatten(JSON.parse(raw), "", packs[loc]);
}

const problems = [];
const base = packs[BASE];

for (const loc of OTHERS) {
  const pack = packs[loc];
  const baseKeys = new Set(Object.keys(base));
  const packKeys = new Set(Object.keys(pack));

  for (const k of baseKeys) {
    if (!packKeys.has(k)) {
      problems.push(`${loc}: 缺 key「${k}」`);
      continue;
    }
    const a = tokens(base[k]);
    const b = tokens(pack[k]);
    if (a !== b) {
      problems.push(
        `${loc}: 「${k}」占位符不一致\n    zh-CN: ${a || "（无）"}\n    ${loc}:   ${b || "（无）"}`,
      );
    }
  }
  for (const k of packKeys) {
    if (!baseKeys.has(k)) problems.push(`${loc}: 多出 zh-CN 没有的 key「${k}」`);
  }
}

// —— 第三道：代码引用的 key，语言包里必须真的有 ——
//
// 前面两道只让八个语言包互相对齐，对不上「代码引用了一个谁都没有的 key」
// 这种情况：八个包一致地缺同一条，校验照样通过，而界面上那一格会原样印出
// `fps.settings.general` 这样的字符串。设置页整页的标签就是这么静默坏掉的
// （fps.settings.* 十三条从来没进过语言包，八种语言下都在显示 key 本身）。
//
// 扫描范围不止前端：Rust 侧的 `t("…")` / `t2("…")` 和 known_issues.json
// 这类数据文件同样按 key 取文案。只扫 app/src 曾漏掉过 ASIO 崩溃那两条，
// 那次是靠 Rust 的单测才拦下来的。
const SCAN_DIRS = [
  join(HERE, "..", "src"),
  join(HERE, "..", "src-tauri", "src"),
];

// src-tauri 根目录下的随附数据表（known_issues.json 之类）也按 key 取文案，
// 但不能整个目录走 —— 那下面还有 target/ 和 gen/。只收顶层的 json。
const DATA_FILES = [];
try {
  for (const name of readdirSync(join(HERE, "..", "src-tauri"))) {
    if (name.endsWith(".json")) DATA_FILES.push(join(HERE, "..", "src-tauri", name));
  }
} catch {
  /* 没有 src-tauri（纯前端仓）就算了 */
}

const CODE_EXT = /\.(tsx?|rs)$/;
const DATA_EXT = /\.json$/;

function walk(dir, out) {
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const name of entries) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (CODE_EXT.test(name) || DATA_EXT.test(name)) out.push(p);
  }
  return out;
}

/** 去掉注释再找 t(…)：注释里成段引用过 `t("s.xxx")` 当例子，那些不是引用。 */
function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

// 取文案的写法一共这几个：前端 t / tStatic，Rust 还有 te / tn / t2 / t_vars
// 这些「带参数」的变体。少认一个变体，就等于给那一批 key 开了后门 ——
// s.350261fb86（下载进度条那句）就是走 tn 才躲过第一版校验的。
const REF = /\b(?:t|tStatic|te|tn|t2|t_vars)\(\s*["'`]([\w.\-]+)["'`]/g;
// 数据文件里的 key 是普通字符串值，只认我们自己的命名空间。
const DATA_REF = /"((?:s|msg|home|dock|settings|engine|train|models|tray|nav|plaza|extras|glossary|locale|meta|crop|overlay|onboarding|social|window|store|dialog)\.[\w.\-]+)"/g;

const files = [...DATA_FILES];
for (const dir of SCAN_DIRS) walk(dir, files);

const refs = new Map();
for (const file of files) {
  const raw = readFileSync(file, "utf-8");
  const pat = DATA_EXT.test(file) ? DATA_REF : REF;
  const src = DATA_EXT.test(file) ? raw : stripComments(raw);
  for (const m of src.matchAll(pat)) {
    if (!refs.has(m[1])) refs.set(m[1], file);
  }
}
for (const [key, file] of refs) {
  if (!(key in base)) {
    problems.push(
      `zh-CN: 代码引用了不存在的 key「${key}」（${file.replace(HERE + "/../", "")}）`,
    );
  }
}

// —— 第四道：语言包里没人引用的 key，不许留着 ——
//
// 死文案不是无害的：它们是上一代产品的语域（「变声」「监听设备」「虚拟声卡」），
// 混在包里既误导翻译，也让「这条还在用吗」永远要人肉判断。八个语言包各留一份，
// 一条死文案就是八条。
//
// 少数 key 是运行时拼出来的，literal 永远不会出现在代码里 —— 白名单在此，
// 加前缀之前先确认它真的有 `${...}` 拼接的取用点。
const DYNAMIC_PREFIXES = [
  "meta.",
  "locale.",
  "msg.",
  "glossary.",
  "extras.items.",
  "settings.tabs.",
  "s.annot.issue.",
];

// 「引用」在这一道里放得比第三道宽：`labelKey: "nav.home"` 这类把 key 存进
// 表里、稍后再交给 t() 的写法同样算数，所以只要 key 的字面量在源码里出现过
// 就放行。宁可漏判一条死文案，也不能误杀一条活的。
const literals = files.map((f) => readFileSync(f, "utf-8")).join("\n");

for (const key of Object.keys(base)) {
  if (DYNAMIC_PREFIXES.some((p) => key.startsWith(p))) continue;
  if (literals.includes(`"${key}"`) || literals.includes(`'${key}'`) || literals.includes(`\`${key}\``)) {
    continue;
  }
  problems.push(`zh-CN: 没有任何地方引用 key「${key}」（删掉，或把它接回界面）`);
}

if (problems.length) {
  console.error(`i18n 校验失败，共 ${problems.length} 处：\n`);
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}

const nKeys = Object.keys(base).length;
console.log(
  `i18n 校验通过：${OTHERS.length + 1} 个语言包 × ${nKeys} 条，结构与占位符一致；` +
    `引用的 ${refs.size} 个 key 全部有着落，包里也没有无人引用的死文案`,
);
