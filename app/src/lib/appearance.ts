import { convertFileSrc } from "@tauri-apps/api/core";
import type { Config } from "./config";

/**
 * 外观：配色 + 背景图 + 磨砂 + 不透明度。
 *
 * 全都是往 `<html>` 上写几个 CSS 变量，真正画图的是 index.css 里的
 * `body::before`。所以「生效」这件事本身是零成本的 —— 一次 style 写入，
 * 下一帧就变了。
 *
 * 之所以单独抽出来：这段以前长在 App.tsx 的一个 `useEffect` 里，依赖数组写的是
 * `[page]`。于是它只在**换页**的时候才重新读一次配置 —— 用户在设置页选了背景
 * 图、拖了磨砂和不透明度，界面一动不动，非得切到别的页再切回来才看得见。
 * 三个开关一个都不「实时」，看着就像整块功能是坏的。
 *
 * 现在写配置的地方（useConfig）和启动的地方（App）都调这一个函数，
 * 传的是当时最新的整份配置。
 */
export const APPEARANCE_KEYS = [
  "theme_mode",
  "wallpaper_path",
  "wallpaper_blur",
  "wallpaper_opacity",
  "home_banner_opacity",
] as const;

/** 磨砂滑杆是 0–100，换算成实际的高斯半径。24px 上限是试出来的：
 *  再糊下去就只剩一团颜色，看不出用的是哪张图了。 */
const MAX_BLUR_PX = 24;

export function applyAppearance(cfg: Config): void {
  const el = document.documentElement;

  const mode = String(cfg.theme_mode ?? "system");
  if (mode === "system") el.removeAttribute("data-theme");
  else el.setAttribute("data-theme", mode);

  el.style.setProperty(
    "--wp-blur",
    `${(Number(cfg.wallpaper_blur ?? 40) / 100) * MAX_BLUR_PX}px`,
  );
  el.style.setProperty(
    "--wp-opacity",
    String(Number(cfg.wallpaper_opacity ?? 70) / 100),
  );
  // 首页横幅背景的不透明度。只影响那一格底色（HomePage 里用 color-mix 消费），
  // 文字与 LOGO 不跟着变淡。
  el.style.setProperty(
    "--banner-opacity",
    String(Math.min(100, Math.max(20, Number(cfg.home_banner_opacity ?? 100))) / 100),
  );

  const path = String(cfg.wallpaper_path ?? "");
  if (path) {
    // convertFileSrc 在浏览器预览里没有 Tauri 环境会抛，背景图这一项本来
    // 就只有装好的软件里有意义，抛了就当没设。
    try {
      el.style.setProperty("--wp-image", `url("${convertFileSrc(path)}")`);
    } catch {
      el.style.removeProperty("--wp-image");
    }
  } else {
    el.style.removeProperty("--wp-image");
  }
}
