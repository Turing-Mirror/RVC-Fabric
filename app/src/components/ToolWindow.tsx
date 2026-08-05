import type { ReactNode } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { invoke } from "@tauri-apps/api/core";
import { SeparatePanel } from "./SeparatePanel";
import { TrainPanel } from "./TrainPanel";
import { TtsPanel } from "./TtsPanel";
import { t } from "../i18n/t";

/** 地址里带的 `#/tool/<kind>` —— 主窗口和工具窗口用的是同一份前端。 */
export type ToolKind = "separate" | "train" | "tts";

const TITLES: Record<ToolKind, string> = {
  separate: t("s.8fd038283b"),
  train: t("s.ba65bd5595"),
  tts: t("s.6f311c47fe"),
};

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
  return k && k in TITLES ? (k as ToolKind) : null;
}

/** 从主窗口把某个工具窗口开起来（已经开着就拉到前面）。 */
export function openTool(kind: ToolKind): void {
  void (async () => {
    try {
      const { ensureEngineCoreOrPrompt } = await import("../lib/downloadModels");
      const ok = await ensureEngineCoreOrPrompt(
        `使用「${TITLES[kind]}」需要引擎资源（hubert / rmvpe / ffmpeg，约 720 MB）。与训练底模无关，下完后即可打开工具。`,
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
 * 工具窗口的外壳：一条自绘标题栏 + 一块能滚的内容区。
 *
 * 标题栏是自己画的，因为窗口建的时候 `decorations(false)` —— 主窗口也是无边框
 * 自绘的，这里要是用系统标题栏，同一个软件里会同时出现两种窗口长相。
 */
export function ToolWindow({ kind }: { kind: ToolKind }) {
  return (
    <div className="h-full flex flex-col text-[var(--ink)] overflow-hidden">
      <ToolTitleBar title={TITLES[kind]} />
      <div className="flex-1 overflow-y-auto">
        {kind === "separate" ? <SeparatePanel /> : null}
        {kind === "train" ? <TrainPanel /> : null}
        {kind === "tts" ? <TtsPanel /> : null}
      </div>
    </div>
  );
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
