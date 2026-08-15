import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";

type HelpOpener = (section: string) => void;

let helpOpener: HelpOpener | null = null;

export function registerHelpOpener(fn: HelpOpener | null): void {
  helpOpener = fn;
}

/** 打开说明页某一段。工具窗没有说明页，一律把主窗口叫过去。 */
export function openHelpSection(section: string): void {
  let isMain = false;
  try {
    isMain = getCurrentWindow().label === "main";
  } catch {
    isMain = !/^#\/tool\//.test(window.location.hash || "");
  }
  if (isMain && helpOpener) {
    helpOpener(section);
    return;
  }
  void invoke("tools_open_help", { section }).catch(() => {
    /* 浏览器预览里没有 shell */
  });
}
