import { createContext, useContext, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { invoke } from "@tauri-apps/api/core";
import { SeparatePanel } from "./SeparatePanel";
import { TrainPanel } from "./TrainPanel";
import { TtsPanel } from "./TtsPanel";
import { t } from "../i18n/t";
import { useI18n } from "../i18n";
import { WebDialogHost } from "./WebDialog";
import { NativeDialogHint } from "./NativeDialogHint";

/** 地址里带的 `#/tool/<kind>` —— 主窗口和工具窗口用的是同一份前端。 */
export type ToolKind = "separate" | "train" | "tts";

function toolTitle(kind: ToolKind): string {
  if (kind === "separate") return t("s.8fd038283b");
  if (kind === "train") return t("s.ba65bd5595");
  return t("s.6f311c47fe");
}

const TOOL_KINDS = new Set<string>(["separate", "train", "tts"]);

/**
 * 这个 webview 是不是一扇工具窗口，是的话是哪一个。
 *
 * 白名单匹配，不是把 fragment 直接当组件名用：地址栏在 webview 里虽然改不了，
 * 但「从 URL 里取一个字符串再拿去查表」和「取一个字符串再拿去当代码路径」是
 * 两种安全性完全不同的写法，前者永远只会落到这三个值之一。
 */
export function toolFromHash(hash: string): ToolKind | null {
  const m = /^#\/tool\/([a-z]+)$/.exec(hash);
  const k = m?.[1];
  return k && TOOL_KINDS.has(k) ? (k as ToolKind) : null;
}

/** 从主窗口把某个工具窗口开起来（已经开着就拉到前面）。 */
export function openTool(kind: ToolKind): void {
  void (async () => {
    try {
      // 音频工具需要引擎资源（hubert/rmvpe/ffmpeg）。缺了就打开「下载模型」
      // 弹窗：先下基础依赖，再下分离/训练附加包。底栏「开启变声」不走这里。
      const { ensureEngineCoreOrPrompt } = await import("../lib/downloadModels");
      const ok = await ensureEngineCoreOrPrompt(
        t("s.toolNeedEngine", { name: toolTitle(kind) }),
      );
      if (!ok) return;
    } catch {
      /* 浏览器预览或 assets_status 失败：仍尝试打开，由工具内再拦 */
    }
    void invoke("tools_open", { kind }).catch(() => {
      /* 浏览器预览里没有 shell */
    });
  })();
}

/**
 * 开出悬浮状态窗（已经开着就拉到前面）。
 *
 * 不走 `openTool`：那条路会先确认 engine-core 在不在（分离/训练/语音转换都要
 * hubert 和 rmvpe）。悬浮窗只读状态文件，一个模型都不加载，让它去等一次下载
 * 提示纯属添堵。
 */
export function openOverlay(): void {
  void invoke("tools_open", { kind: "overlay" }).catch(() => {
    /* 浏览器预览里没有 shell */
  });
}

/**
 * 工具窗口的外壳：一条自绘标题栏 + 一块能滚的内容区。
 *
 * 标题栏是自己画的，因为窗口建的时候 `decorations(false)` —— 主窗口也是无边框
 * 自绘的，这里要是用系统标题栏，同一个软件里会同时出现两种窗口长相。
 */
export function ToolWindow({ kind }: { kind: ToolKind }) {
  // 订阅语言。I18nProvider 刻意不用 key={locale} 重挂子树（那会把引擎状态一起
  // 拆掉），代价是每个根组件必须自己订阅才会在语言就绪后重渲染 —— provider 的
  // 注释里写着这一条。ToolWindow 就是这样一个根，而它一直没订阅：标题栏没有任何
  // state，于是永远停在 DEFAULT_LOCALE。面板里的文字因为自己有 state 会跟着刷新，
  // 结果同一扇窗上半截中文、下半截日文。
  useI18n();
  // 常驻操作栏挂载的那个格子。用 state 而不是 ref：ref 变了不会触发重渲染，
  // 面板第一次渲染时拿到的会永远是 null，按钮就再也进不了这条栏。
  const [footer, setFooter] = useState<HTMLElement | null>(null);
  return (
    // 无边框窗口 + shadow(false)，浅色桌面上整扇窗和背景糊在一起，看不出边界
    // 在哪 —— 用户报的就是这个。补一条 1px 外框；用 --line 不用 --hairline，
    // 后者是 0.1 透明度的界面内分隔线，当窗口边界几乎看不见。
    <div className="h-full flex flex-col text-[var(--ink)] overflow-hidden border border-[var(--line)]">
      <ToolTitleBar title={toolTitle(kind)} />
      <ToolFooterSlot.Provider value={footer}>
        <div className="flex-1 overflow-y-auto">
          {kind === "separate" ? <SeparatePanel /> : null}
          {kind === "train" ? <TrainPanel /> : null}
          {kind === "tts" ? <TtsPanel /> : null}
        </div>
      </ToolFooterSlot.Provider>
      <div ref={setFooter} className="flex-none" />
      <WebDialogHost />
      <NativeDialogHint />
    </div>
  );
}

/** 操作栏要挂到哪个 DOM 结点上。`null` = 还没挂好，先就地渲染。 */
const ToolFooterSlot = createContext<HTMLElement | null>(null);

/**
 * 工具窗口底部那条常驻操作栏 —— 和主窗口底栏同一个位置、同一条发丝线。
 *
 * 用 portal 传送到滚动区**外面**，而不是在滚动区里面写 `sticky bottom-0`：
 * sticky 只在元素本来会被挤出可视区时才生效，窗口拉高、内容又短的时候，那条
 * 栏会停在内容正下方的半空中，而不是贴着窗口底边。主按钮的位置不能取决于表单
 * 有多长。
 *
 * 传送目标还没准备好时就地渲染 —— 首帧 ref 回调还没跑完，这一帧退回原来的
 * 位置，比闪一下空白强。
 */
export function ToolActions({ children }: { children: ReactNode }) {
  const slot = useContext(ToolFooterSlot);
  const bar = (
    <div className="relative px-6 py-3.5 flex items-center gap-2.5">
      {/* 和主窗口底栏一样：两端内缩的发丝线，不是整条 border-top。 */}
      <div
        aria-hidden
        className="absolute top-0 left-6 right-6 h-px bg-[var(--hairline)]"
      />
      {children}
    </div>
  );
  return slot ? createPortal(bar, slot) : bar;
}

function ToolTitleBar({ title }: { title: string }) {
  const win = () => {
    try {
      return getCurrentWindow();
    } catch {
      return null;
    }
  };
  return (
    <header
      className="flex-none h-[42px] flex items-center pl-[18px] pr-1.5 border-b border-[var(--hairline)]"
      data-tauri-drag-region
    >
      <span
        className="text-[13px] font-semibold select-none"
        data-tauri-drag-region
      >
        {title}
      </span>
      <div
        className="ml-auto flex text-[var(--meta)]"
        onPointerDown={(e) => e.stopPropagation()}
      >
        <ToolWinBtn label={t("s.ca8223c5fc")} onClick={() => void win()?.minimize()}>
          —
        </ToolWinBtn>
        <ToolWinBtn label={t("s.da2d806e5f")} onClick={() => void win()?.toggleMaximize()}>
          □
        </ToolWinBtn>
        <ToolWinBtn label={t("s.6c14bd7f6f")} danger onClick={() => void win()?.close()}>
          ✕
        </ToolWinBtn>
      </div>
    </header>
  );
}

function ToolWinBtn({
  children,
  label,
  onClick,
  danger = false,
}: {
  children: ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={[
        "w-9 h-[30px] grid place-items-center text-xs rounded-md border-0 bg-transparent cursor-pointer",
        "text-[var(--meta)] transition-[background,color] duration-150 ease-[var(--ease)]",
        danger
          ? "hover:bg-[#e81123] hover:text-white"
          : "hover:bg-[color-mix(in_srgb,var(--ink)_6%,transparent)] hover:text-[var(--ink)]",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

/**
 * 工具正文的留白。
 *
 * 以前这三块是主窗口上的模态卡片，自己带 `max-w` 和圆角阴影 —— 那是「浮在
 * 页面上的一张纸」该有的样子。现在它们就是整扇窗口的内容，再套一层卡片等于
 * 窗口里画了个窗口，所以只留内边距和一个读起来舒服的最大宽度。
 */
export function ToolBody({ children }: { children: ReactNode }) {
  return <div className="px-6 py-5 max-w-[720px]">{children}</div>;
}
